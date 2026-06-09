from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """
    Sync LLM interface. All implementations must use OpenAI function-calling
    so callers always get validated JSON back — never free text to parse.
    Returns {} on any error so callers fall back to deterministic results.
    """

    def complete_structured(
        self,
        prompt: str,
        tool_name: str,
        tool_schema: dict[str, Any],
    ) -> dict[str, Any]: ...

    def is_available(self) -> bool: ...


class FakeLLMProvider:
    """Deterministic stub for tests. Never calls external APIs."""

    def complete_structured(
        self,
        prompt: str,
        tool_name: str,
        tool_schema: dict[str, Any],
    ) -> dict[str, Any]:
        return {}

    def is_available(self) -> bool:
        return False


class OpenAILLMProvider:
    """
    Sync OpenAI provider using function-calling for guaranteed structured output.
    Falls back silently to {} on any API error so deterministic results are
    always returned to the caller.
    """

    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        import openai  # noqa: PLC0415
        self._client = openai.OpenAI(api_key=api_key)
        self._model = model

    def is_available(self) -> bool:
        return True

    def complete_structured(
        self,
        prompt: str,
        tool_name: str,
        tool_schema: dict[str, Any],
    ) -> dict[str, Any]:
        import json  # noqa: PLC0415

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                tools=[{
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "description": f"Return structured {tool_name} output.",
                        "parameters": tool_schema,
                    },
                }],
                tool_choice={"type": "function", "function": {"name": tool_name}},
                max_tokens=600,
                temperature=0.2,
            )
            args = response.choices[0].message.tool_calls[0].function.arguments
            return json.loads(args)
        except Exception:  # noqa: BLE001
            return {}
