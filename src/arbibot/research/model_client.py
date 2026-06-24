from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel


@dataclass(frozen=True, slots=True)
class ModelClientConfig:
    base_url: str | None
    api_key: str | None
    model: str | None

    @classmethod
    def from_env(cls) -> ModelClientConfig:
        return cls(
            os.getenv("OPENAI_BASE_URL") or "https://bedrock-mantle.us-east-1.api.aws/v1",
            os.getenv("OPENAI_API_KEY"),
            os.getenv("ARBIBOT_RESEARCH_MODEL"),
        )

    def is_configured(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)

    def redacted(self) -> dict[str, str | bool | None]:
        return {
            "base_url": self.base_url,
            "model": self.model,
            "api_key_configured": bool(self.api_key),
        }


class ResearchCritiqueInput(BaseModel):
    hypothesis: dict[str, Any]
    feature_spec: dict[str, Any]
    edge_summary: str
    gate_failure_counts: dict[str, int]
    passing_rows: list[dict[str, Any]]
    failing_rows: list[dict[str, Any]]
    qa_report: dict[str, Any]


class ResearchCritiqueOutput(BaseModel):
    status: str
    text: str
    skipped_reason: str | None = None


class ResearchModelClient:
    def __init__(self, config: ModelClientConfig | None = None) -> None:
        self.config = config or ModelClientConfig.from_env()

    def generate_research_critique(self, input: ResearchCritiqueInput) -> ResearchCritiqueOutput:
        if not self.config.is_configured():
            return ResearchCritiqueOutput(
                status="skipped_missing_model_config",
                text="AI critique skipped: missing OPENAI_API_KEY or ARBIBOT_RESEARCH_MODEL.",
                skipped_reason="skipped_missing_model_config",
            )
        try:
            from openai import OpenAI  # type: ignore[import-not-found]
        except ImportError:
            return ResearchCritiqueOutput(
                status="skipped_missing_openai_sdk",
                text="AI critique skipped: openai package is not installed.",
                skipped_reason="skipped_missing_openai_sdk",
            )

        client = OpenAI(base_url=self.config.base_url, api_key=self.config.api_key)
        prompt = _load_prompt() + "\n\nINPUT:\n" + input.model_dump_json(indent=2)
        try:
            text = self._responses_create(client, prompt)
        except Exception:
            text = self._chat_completions_create(client, prompt)
        return ResearchCritiqueOutput(status="generated", text=text)

    def _responses_create(self, client: Any, prompt: str) -> str:
        if not hasattr(client, "responses"):
            raise AttributeError("Responses API is unavailable on installed OpenAI SDK")
        response = client.responses.create(model=self.config.model, input=prompt)
        text = getattr(response, "output_text", None)
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Responses API returned no output_text")
        return text

    def _chat_completions_create(self, client: Any, prompt: str) -> str:
        response = client.chat.completions.create(
            model=self.config.model,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.choices[0].message.content
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Chat Completions API returned no content")
        return text


def _load_prompt() -> str:
    prompt_path = Path(__file__).parent / "prompts" / "research_critique.md"
    return prompt_path.read_text(encoding="utf-8")
