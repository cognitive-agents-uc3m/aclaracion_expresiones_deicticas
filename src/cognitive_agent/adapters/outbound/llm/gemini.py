from __future__ import annotations

import logging
import os
import threading
from .base import ChatResponse, LlmUnavailable

logger = logging.getLogger(__name__)

def resolve_gcp_project(configured: str = "") -> str | None:

    candidate = (
        (configured or "").strip()
        or os.getenv("COGNITIVE_AGENT__LLM__GCP_PROJECT", "").strip()
        or os.getenv("GCP_PROJECT_ID", "").strip()
        or os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
    )
    if candidate:
        return candidate
    try:
        import google.auth

        _credentials, project = google.auth.default()
        return project
    except Exception:
        return None

def resolve_gcp_location(configured: str = "") -> str:
    return (
        (configured or "").strip()
        or os.getenv("COGNITIVE_AGENT__LLM__GCP_LOCATION", "").strip()
        or os.getenv("GCP_LOCATION", "").strip()
        or "us-central1"
    )

class GeminiChatModel:
    name = "gemini"

    def __init__(
        self,
        *,
        model_id: str = "gemini-2.5-flash",
        project: str = "",
        location: str = "us-central1",
        default_timeout: float = 90.0,
        disable_thinking: bool = True,
    ) -> None:
        self.model_id = model_id
        self._project_setting = project
        self._location_setting = location
        self._default_timeout = default_timeout
        self._disable_thinking = disable_thinking
        self._client = None
        self._lock = threading.Lock()
        self._unavailable_reason: str | None = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        with self._lock:
            if self._client is not None:
                return self._client
            try:
                from google import genai
            except ImportError as exc:
                self._unavailable_reason = (
                    "Falta google-genai. Instala el extra: pip install 'cognitive-agent[gemini]'"
                )
                raise LlmUnavailable(self._unavailable_reason) from exc

            project = resolve_gcp_project(self._project_setting)
            if not project:
                self._unavailable_reason = (
                    "No hay proyecto de GCP. Configura llm.gcp_project o las credenciales ADC."
                )
                raise LlmUnavailable(self._unavailable_reason)

            location = resolve_gcp_location(self._location_setting)
            logger.info("Cliente Gemini (Vertex AI) proyecto=%s region=%s", project, location)
            self._client = genai.Client(vertexai=True, project=project, location=location)
            self._unavailable_reason = None
            return self._client

    def _config(self, temperature: float, system: str):
        from google.genai import types

        kwargs: dict = {"temperature": temperature}
        if system:
            kwargs["system_instruction"] = system

        if self._disable_thinking and "flash" in self.model_id.lower():
            kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
        return types.GenerateContentConfig(**kwargs)

    def complete(
        self,
        *,
        system: str = "",
        user: str = "",
        temperature: float = 0.0,
        timeout_seconds: float | None = None,
    ) -> ChatResponse:
        client = self._get_client()
        response = client.models.generate_content(
            model=self.model_id,
            contents=user,
            config=self._config(temperature, system),
        )
        return ChatResponse(
            text=(getattr(response, "text", "") or "").strip(),
            model=self.model_id,
            input_tokens=_usage(response, "prompt_token_count"),
            output_tokens=_usage(response, "candidates_token_count"),
        )

    def describe(
        self,
        *,
        prompt: str,
        image: bytes | None = None,
        pdf: bytes | None = None,
        mime_type: str = "image/png",
        timeout_seconds: float | None = None,
    ) -> ChatResponse:
        from google.genai import types

        client = self._get_client()
        parts: list = []
        if pdf:
            parts.append(types.Part.from_bytes(data=pdf, mime_type="application/pdf"))
        elif image:
            parts.append(types.Part.from_bytes(data=image, mime_type=mime_type))
        parts.append(prompt)

        response = client.models.generate_content(model=self.model_id, contents=parts)
        return ChatResponse(
            text=(getattr(response, "text", "") or "").strip(),
            model=self.model_id,
            input_tokens=_usage(response, "prompt_token_count"),
            output_tokens=_usage(response, "candidates_token_count"),
        )

    @property
    def is_available(self) -> bool:
        try:
            self._get_client()
        except LlmUnavailable:
            return False
        except Exception:
            return False
        return True

    @property
    def unavailable_reason(self) -> str | None:
        return self._unavailable_reason

def _usage(response: object, attribute: str) -> int | None:
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return None
    value = getattr(usage, attribute, None)
    return int(value) if isinstance(value, int) else None
