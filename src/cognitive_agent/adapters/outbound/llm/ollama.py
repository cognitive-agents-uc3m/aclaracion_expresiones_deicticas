from __future__ import annotations

import logging
import threading
from .base import ChatResponse, LlmUnavailable

logger = logging.getLogger(__name__)

class OllamaChatModel:
    name = "ollama"

    def __init__(
        self,
        *,
        model_id: str = "qwen3:4b-instruct-2507-q4_K_M",
        base_url: str = "http://localhost:11434",
        num_gpu: int = 99,
        num_ctx: int = 8192,
        default_timeout: float = 90.0,
    ) -> None:
        self.model_id = model_id
        self._base_url = base_url
        self._num_gpu = num_gpu
        self._num_ctx = num_ctx
        self._default_timeout = default_timeout
        self._client = None
        self._lock = threading.Lock()
        self._unavailable_reason: str | None = None

    def _get_client(self, timeout_seconds: float | None = None):
        if self._client is not None:
            return self._client
        with self._lock:
            if self._client is not None:
                return self._client
            try:
                from langchain_ollama import ChatOllama
            except ImportError as exc:
                self._unavailable_reason = (
                    "Falta langchain-ollama. Instala el extra: "
                    "pip install 'cognitive-agent[ollama]'"
                )
                raise LlmUnavailable(self._unavailable_reason) from exc

            kwargs: dict = {
                "model": self.model_id,
                "temperature": 0.0,
                "base_url": self._base_url,
                "num_gpu": self._num_gpu,
                "num_ctx": self._num_ctx,
            }
            try:
                kwargs["client_kwargs"] = {
                    "timeout": timeout_seconds or self._default_timeout
                }
                self._client = ChatOllama(**kwargs)
            except TypeError:

                kwargs.pop("client_kwargs", None)
                self._client = ChatOllama(**kwargs)
            self._unavailable_reason = None
            return self._client

    def complete(
        self,
        *,
        system: str = "",
        user: str = "",
        temperature: float = 0.0,
        timeout_seconds: float | None = None,
    ) -> ChatResponse:
        client = self._get_client(timeout_seconds)
        messages: list[tuple[str, str]] = []
        if system:
            messages.append(("system", system))
        messages.append(("human", user))

        response = client.invoke(messages)
        content = getattr(response, "content", "") or ""
        if isinstance(content, list):
            content = " ".join(
                part.get("text", "") if isinstance(part, dict) else str(part) for part in content
            )
        usage = getattr(response, "usage_metadata", None) or {}
        return ChatResponse(
            text=str(content).strip(),
            model=self.model_id,
            input_tokens=usage.get("input_tokens") if isinstance(usage, dict) else None,
            output_tokens=usage.get("output_tokens") if isinstance(usage, dict) else None,
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
        import base64

        if pdf is not None and image is None:
            raise LlmUnavailable("El proveedor Ollama no admite PDF directamente; usa una imagen.")

        from langchain_core.messages import HumanMessage

        client = self._get_client(timeout_seconds)
        encoded = base64.b64encode(image or b"").decode("utf-8")
        message = HumanMessage(
            content=[
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": f"data:{mime_type};base64,{encoded}"},
            ]
        )
        response = client.invoke([message])
        return ChatResponse(text=(getattr(response, "content", "") or "").strip(), model=self.model_id)

    @property
    def is_available(self) -> bool:
        try:
            self._get_client()
        except Exception:
            return False
        return True

    @property
    def unavailable_reason(self) -> str | None:
        return self._unavailable_reason
