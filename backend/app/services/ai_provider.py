import asyncio
import json
import logging
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Protocol

from app.core.config import get_settings

logger = logging.getLogger(__name__)

TIMEOUT_WARNING = "The reply provider timed out. Human review is required."
HTTP_WARNING = "The reply provider returned an error. Human review is required."
UNREACHABLE_WARNING = "The reply provider could not be reached. Human review is required."
UNREADABLE_WARNING = "The reply provider returned an unreadable draft. Human review is required."
UNCONFIGURED_WARNING = "The reply provider is not configured. Human review is required."

Transport = Callable[[str, dict, dict[str, str], float], dict]


class ProviderError(Exception):
    def __init__(self, warning: str) -> None:
        super().__init__(warning)
        self.warning = warning


class AIProvider(Protocol):
    async def generate_json(
        self,
        *,
        messages: list[dict[str, str]],
        json_schema: dict,
    ) -> dict:
        """Return one JSON object. Raise ProviderError on failure."""


def urllib_transport(
    url: str,
    payload: dict,
    headers: dict[str, str],
    timeout: float,
) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(1_000_000)
    except TimeoutError as error:
        raise ProviderError(TIMEOUT_WARNING) from error
    except urllib.error.HTTPError as error:
        logger.warning("Reply provider HTTP %s", error.code)
        raise ProviderError(HTTP_WARNING) from error
    except urllib.error.URLError as error:
        if "timed out" in str(error.reason).lower():
            raise ProviderError(TIMEOUT_WARNING) from error
        logger.warning("Reply provider unreachable (%s)", type(error.reason).__name__)
        raise ProviderError(UNREACHABLE_WARNING) from error
    try:
        body = json.loads(raw.decode())
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ProviderError(UNREADABLE_WARNING) from error
    if not isinstance(body, dict):
        raise ProviderError(UNREADABLE_WARNING)
    return body


def _token_count(usage: dict, *keys: str) -> int | None:
    for key in keys:
        value = usage.get(key)
        if isinstance(value, bool) or not isinstance(value, int | float):
            continue
        if value >= 0 and float(value).is_integer():
            return int(value)
    return None


class OpenRouterProvider:
    """Chat-completions client for OpenRouter.

    The API key is kept on this object and sent only as the Authorization
    header. It is not included in logs or in the returned draft.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        timeout_seconds: float,
        app_name: str,
        transport: Transport | None = None,
    ) -> None:
        self._api_key = api_key.strip()
        self._model = model.strip()
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds if timeout_seconds > 0 else 20.0
        self._app_name = app_name
        self._transport = transport or urllib_transport

    def __repr__(self) -> str:
        return f"OpenRouterProvider(model={self._model!r})"

    @property
    def model_name(self) -> str:
        return self._model

    async def generate_json(
        self,
        *,
        messages: list[dict[str, str]],
        json_schema: dict,
    ) -> dict:
        if not self._api_key or not self._model:
            raise ProviderError(UNCONFIGURED_WARNING)
        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 800,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "cx_suggested_reply",
                    "strict": True,
                    "schema": json_schema,
                },
            },
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Title": self._app_name,
        }
        try:
            body = await asyncio.to_thread(
                self._transport,
                f"{self._base_url}/chat/completions",
                payload,
                headers,
                self._timeout_seconds,
            )
        except ProviderError:
            raise
        except TimeoutError as error:
            raise ProviderError(TIMEOUT_WARNING) from error
        except urllib.error.HTTPError as error:
            logger.warning("Reply provider HTTP %s", error.code)
            raise ProviderError(HTTP_WARNING) from error
        except urllib.error.URLError as error:
            if "timed out" in str(error.reason).lower():
                raise ProviderError(TIMEOUT_WARNING) from error
            logger.warning("Reply provider unreachable (%s)", type(error.reason).__name__)
            raise ProviderError(UNREACHABLE_WARNING) from error
        parsed = _content_json(body)
        usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
        reported_model = body.get("model") if isinstance(body.get("model"), str) else self._model
        parsed["_audit"] = {
            "model": reported_model,
            "prompt_tokens": _token_count(usage, "prompt_tokens", "input_tokens"),
            "completion_tokens": _token_count(usage, "completion_tokens", "output_tokens"),
            "total_tokens": _token_count(usage, "total_tokens"),
        }
        return parsed


def get_ai_provider() -> OpenRouterProvider:
    settings = get_settings()
    return OpenRouterProvider(
        api_key=settings.openrouter_api_key,
        model=settings.openrouter_model,
        base_url=settings.openrouter_base_url,
        timeout_seconds=settings.openrouter_timeout_seconds,
        app_name=settings.app_name,
    )


def _content_json(body: dict) -> dict:
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise ProviderError(UNREADABLE_WARNING) from error
    if isinstance(content, dict):
        return content
    if not isinstance(content, str):
        raise ProviderError(UNREADABLE_WARNING)
    text = content.strip()
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as error:
        raise ProviderError(UNREADABLE_WARNING) from error
    if not isinstance(parsed, dict):
        raise ProviderError(UNREADABLE_WARNING)
    return parsed
