"""Optional LLM assistance. OFF unless ENABLE_LLM_ASSIST=true.

Used for two things only:
  * classify(): Tier-1 fallback for reviews the local zero-shot model is unsure about
  * name_cluster(): turn a cluster's sample verbatims into a readable issue title

Only PII-redacted text is ever passed in. Calls are hard-capped by LLM_MAX_CALLS.
Providers: OpenAI (OPENAI_API_KEY) or Hugging Face Inference (HUGGINGFACE_HUB_TOKEN).
"""
from __future__ import annotations

import logging
import re
from typing import List, Optional, Sequence

from .config import Settings

log = logging.getLogger("feedback_analyzer")


class LLMAssist:
    def __init__(self, settings: Settings):
        self.s = settings
        self.enabled = False
        self.provider = "none"
        self.calls = 0
        self.notes: List[str] = []
        self._client = None
        if not settings.enable_llm_assist:
            return

        provider = settings.llm_provider
        if provider == "auto":
            provider = "openai" if settings.openai_api_key else ("huggingface" if settings.hf_token else "none")
        try:
            if provider == "openai":
                if not settings.openai_api_key:
                    raise ValueError("OPENAI_API_KEY is not set")
                from openai import OpenAI

                self._client = OpenAI(api_key=settings.openai_api_key)
            elif provider == "huggingface":
                if not settings.hf_token:
                    raise ValueError("HUGGINGFACE_HUB_TOKEN is not set")
                from huggingface_hub import InferenceClient

                self._client = InferenceClient(model=settings.hf_llm_model, token=settings.hf_token)
            else:
                raise ValueError("no API key found for LLM assist")
            self.provider = provider
            self.enabled = True
        except Exception as exc:
            self.notes.append(f"LLM assist requested but disabled: {exc}")
            log.warning(self.notes[-1])

    # ------------------------------------------------------------------ core
    def _chat(self, system: str, user: str, max_tokens: int = 40) -> Optional[str]:
        if not self.enabled or self.calls >= self.s.llm_max_calls:
            return None
        self.calls += 1
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        try:
            if self.provider == "openai":
                r = self._client.chat.completions.create(
                    model=self.s.openai_model, messages=messages, temperature=0, max_tokens=max_tokens
                )
            else:
                r = self._client.chat_completion(messages=messages, max_tokens=max_tokens, temperature=0.1)
            return (r.choices[0].message.content or "").strip()
        except Exception as exc:
            self.notes.append(f"LLM call failed ({type(exc).__name__}); continuing locally.")
            log.warning(self.notes[-1])
            return None

    # ------------------------------------------------------------------- API
    def classify(self, text: str, categories: Sequence[str]) -> Optional[str]:
        reply = self._chat(
            "You assign customer app reviews to exactly one category. Reply with the category name only, "
            "or 'Other' if none fits.",
            f"Categories: {' | '.join(categories)}\nReview: {text[:600]}",
            max_tokens=12,
        )
        if not reply:
            return None
        for cat in categories:
            if cat.lower() in reply.lower():
                return cat
        return None

    def name_cluster(self, general_class: str, samples: Sequence[str]) -> Optional[str]:
        bullets = "\n".join(f"- {s[:240]}" for s in samples[:5])
        reply = self._chat(
            "You write short issue titles for groups of similar customer reviews. Reply with a 3-7 word "
            "Title Case title only: no quotes, no trailing punctuation.",
            f"Category: {general_class}\nReviews:\n{bullets}",
            max_tokens=24,
        )
        if not reply:
            return None
        title = re.sub(r"[\"'`]|[.!]+$", "", reply.splitlines()[0]).strip()
        return title if 2 <= len(title.split()) <= 10 else None
