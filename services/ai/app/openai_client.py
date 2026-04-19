import json
from typing import Any

from openai import OpenAI

from .llm_client import LLMClient


class OpenAIClient(LLMClient):
    def __init__(self, model: str = "gpt-5.4-mini") -> None:
        self.client = OpenAI()
        self.model = model

    def generate_json(self, system_prompt: str, user_prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        response = self.client.responses.create(
            model=self.model,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "test_case_output",
                    "schema": schema,
                    "strict": True,
                }
            },
        )

        output_text = response.output_text
        return json.loads(output_text)
