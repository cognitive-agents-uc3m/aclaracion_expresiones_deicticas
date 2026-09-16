from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from pathlib import Path
import yaml
from ...application.ports.outbound.prompts import PromptRepositoryPort
from ...domain.errors import PromptNotFound
from ...domain.value_objects.prompt import PromptRef, RenderedPrompt
from ...domain.value_objects.subject import Subject

_FRONT_MATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
_PLACEHOLDER = re.compile(r"\{([A-Z_][A-Z0-9_]*)\}")

@dataclass(frozen=True, slots=True)
class PromptFile:
    path: Path
    metadata: dict
    body: str

    @property
    def role(self) -> str:
        return str(self.metadata.get("role", "user"))

    @property
    def declared_placeholders(self) -> tuple[str, ...]:
        raw = self.metadata.get("placeholders") or []
        return tuple(str(p) for p in raw)

def parse_prompt_file(path: Path) -> PromptFile:
    text = path.read_text(encoding="utf-8")
    match = _FRONT_MATTER.match(text)
    if match is None:
        return PromptFile(path=path, metadata={}, body=text.strip("\n"))
    metadata = yaml.safe_load(match.group(1)) or {}
    if not isinstance(metadata, dict):
        metadata = {}
    return PromptFile(path=path, metadata=metadata, body=match.group(2).strip("\n"))

class FileSystemPromptRepository:
    def __init__(self, *, root: Path | str, registry_path: Path | str | None = None) -> None:
        self._root = Path(root)
        self._registry_path = Path(registry_path) if registry_path else self._root / "registry.yaml"
        self._lock = threading.RLock()
        self._cache: dict[Path, PromptFile] = {}
        self._registry: dict = {}
        self.reload()

    def reload(self) -> None:
        with self._lock:
            if not self._registry_path.is_file():
                raise PromptNotFound(f"No se encuentra el registro de prompts: {self._registry_path}")
            data = yaml.safe_load(self._registry_path.read_text(encoding="utf-8")) or {}
            self._registry = data.get("prompts") or {}
            self._cache.clear()

    def _load(self, relative: str) -> PromptFile:
        path = self._root / relative
        with self._lock:
            cached = self._cache.get(path)
            if cached is not None:
                return cached
            if not path.is_file():
                raise PromptNotFound(f"No se encuentra el prompt: {path}")
            parsed = parse_prompt_file(path)
            self._cache[path] = parsed
            return parsed

    def _entry(self, name: str) -> dict:
        entry = self._registry.get(name)
        if not entry:
            raise PromptNotFound(f"El registro no declara el prompt '{name}'.")
        return entry

    def _resolve(
        self, name: str, subject: Subject, version: str | None
    ) -> tuple[str, list[str], bool]:

        entry = self._entry(name)
        base = entry.get("base") or {}
        subjects = entry.get("subjects") or {}
        specific = subjects.get(subject.value) if subject is not Subject.GENERIC else None

        if specific:
            resolved_version = version or specific.get("active") or "v1"
            versions = specific.get("versions") or {}
            if resolved_version not in versions:
                raise PromptNotFound(
                    f"El prompt '{name}' no tiene la version {resolved_version} para "
                    f"la asignatura {subject.value}."
                )
            is_overlay = bool(specific.get("overlay", False))
            files = []
            if is_overlay:
                base_version = base.get("active") or "v1"
                base_versions = base.get("versions") or {}
                if base_version not in base_versions:
                    raise PromptNotFound(f"El prompt base '{name}' no tiene version {base_version}.")
                files.append(base_versions[base_version])
            files.append(versions[resolved_version])
            return resolved_version, files, is_overlay

        resolved_version = version or base.get("active") or "v1"
        versions = base.get("versions") or {}
        if resolved_version not in versions:
            raise PromptNotFound(f"El prompt '{name}' no tiene la version {resolved_version}.")
        return resolved_version, [versions[resolved_version]], False

    @staticmethod
    def _user_variant(relative: str) -> str:

        return re.sub(r"\.(v\d+)\.md$", r".user.\1.md", relative)

    def ref(
        self, name: str, *, subject: Subject = Subject.GENERIC, version: str | None = None
    ) -> PromptRef:
        resolved_version, _files, _overlay = self._resolve(name, subject, version)
        return PromptRef(name=name, version=resolved_version, subject=subject)

    def render(
        self,
        name: str,
        *,
        subject: Subject = Subject.GENERIC,
        variables: dict[str, str] | None = None,
        version: str | None = None,
    ) -> RenderedPrompt:
        resolved_version, files, _overlay = self._resolve(name, subject, version)
        values = {k: str(v) for k, v in (variables or {}).items()}

        system_parts: list[str] = []
        user_parts: list[str] = []

        for relative in files:
            prompt_file = self._load(relative)
            target = system_parts if prompt_file.role == "system" else user_parts
            target.append(self._substitute(prompt_file.body, values, prompt_file, name))

            user_relative = self._user_variant(relative)
            if user_relative != relative and (self._root / user_relative).is_file():
                user_file = self._load(user_relative)
                user_parts.append(self._substitute(user_file.body, values, user_file, name))

        return RenderedPrompt(
            ref=PromptRef(name=name, version=resolved_version, subject=subject),
            system="\n\n".join(p for p in system_parts if p).strip(),
            user="\n\n".join(p for p in user_parts if p).strip(),
            variables=tuple(sorted(values)),
        )

    def _substitute(
        self, body: str, values: dict[str, str], prompt_file: PromptFile, name: str
    ) -> str:
        missing: list[str] = []

        def replace(match: re.Match[str]) -> str:
            key = match.group(1)
            if key in values:
                return values[key]
            missing.append(key)
            return match.group(0)

        rendered = _PLACEHOLDER.sub(replace, body)
        if missing:
            declared = set(prompt_file.declared_placeholders)
            unexpected = [m for m in missing if m in declared]
            if unexpected:
                raise PromptNotFound(
                    f"Al prompt '{name}' ({prompt_file.path.name}) le faltan variables: "
                    f"{', '.join(sorted(set(unexpected)))}"
                )
        return rendered

    def available(self) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        for name, entry in self._registry.items():
            versions = set((entry.get("base") or {}).get("versions", {}))
            for subject_entry in (entry.get("subjects") or {}).values():
                versions.update((subject_entry or {}).get("versions", {}))
            result[name] = sorted(versions)
        return result

    def subjects_for(self, name: str) -> list[str]:
        entry = self._entry(name)
        return sorted((entry.get("subjects") or {}).keys())

    def raw_text(
        self, name: str, *, subject: Subject = Subject.GENERIC, version: str | None = None
    ) -> str:

        _version, files, _overlay = self._resolve(name, subject, version)
        parts = []
        for relative in files:
            parts.append(self._load(relative).body)
            user_relative = self._user_variant(relative)
            if user_relative != relative and (self._root / user_relative).is_file():
                parts.append(self._load(user_relative).body)
        return "\n\n".join(parts)

class StaticPromptRepository:

    def __init__(self, prompts: dict[str, str] | None = None, *, version: str = "test") -> None:
        self._prompts = prompts or {}
        self._version = version

    def render(
        self,
        name: str,
        *,
        subject: Subject = Subject.GENERIC,
        variables: dict[str, str] | None = None,
        version: str | None = None,
    ) -> RenderedPrompt:
        body = self._prompts.get(name, f"[prompt {name}]")
        for key, value in (variables or {}).items():
            body = body.replace(f"{{{key}}}", str(value))
        return RenderedPrompt(
            ref=PromptRef(name=name, version=version or self._version, subject=subject),
            system="",
            user=body,
        )

    def ref(
        self, name: str, *, subject: Subject = Subject.GENERIC, version: str | None = None
    ) -> PromptRef:
        return PromptRef(name=name, version=version or self._version, subject=subject)

    def available(self) -> dict[str, list[str]]:
        return {name: [self._version] for name in self._prompts}
