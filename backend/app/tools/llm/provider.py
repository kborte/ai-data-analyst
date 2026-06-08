from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """
    Abstraction over LLM backends. All LLM usage must go through this interface.
    Implementations must not mutate data, execute code, or perform destructive operations.
    """

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        """Return a completion for the given prompt."""
        ...

    async def complete_structured(self, prompt: str, schema: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        """Return a structured JSON-compatible completion validated against schema."""
        ...


class FakeLLMProvider:
    """Deterministic fake for testing. Never calls external APIs."""

    def __init__(self, fixed_response: str = "fake response") -> None:
        self._response = fixed_response

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        return self._response

    async def complete_structured(self, prompt: str, schema: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        return {}
