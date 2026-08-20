"""Runtime configuration. Environment only; no secrets in code."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv(override=True)


@dataclass(frozen=True)
class Settings:
    provider: str
    model: str
    max_tokens: int
    temperature: float

    @staticmethod
    def load() -> "Settings":
        return Settings(
            provider=os.getenv("TRIPWIRE_LLM_PROVIDER", "groq").strip().lower(),
            model=os.getenv("TRIPWIRE_LLM_MODEL", "openai/gpt-oss-20b").strip(),
            # gpt-oss models spend tokens on hidden reasoning before emitting
            # visible output, so a small budget yields empty responses.
            max_tokens=int(os.getenv("TRIPWIRE_MAX_TOKENS", "1024")),
            temperature=float(os.getenv("TRIPWIRE_TEMPERATURE", "0.0")),
        )


SETTINGS = Settings.load()
