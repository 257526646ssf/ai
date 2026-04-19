from typing import Any, Protocol


class LLMClient(Protocol):
    def generate_json(self, system_prompt: str, user_prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        ...
