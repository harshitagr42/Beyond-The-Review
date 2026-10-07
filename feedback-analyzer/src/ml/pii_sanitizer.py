"""PII sanitizer / masker.

Regex detects emails, phone numbers, credit cards (Luhn-validated), SSNs and IP
addresses. Optional spaCy NER additionally redacts PERSON entities.

Tags:  [EMAIL_REDACTED]  [PHONE_REDACTED]  [PII_REDACTED] (cards, SSNs, IPs, names)

The running tally counts redacted *entities* (one per replaced span), per type,
since the last ``reset()``.
"""
from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Dict, Iterable, List, Optional

log = logging.getLogger("feedback_analyzer")

TAG_EMAIL = "[EMAIL_REDACTED]"
TAG_PHONE = "[PHONE_REDACTED]"
TAG_PII = "[PII_REDACTED]"

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}")
SSN_RE = re.compile(r"(?<![\d-])(?!000|666|9\d\d)\d{3}[- ]\d{2}[- ]\d{4}(?![\d-])")
CC_RE = re.compile(r"(?<![\d-])(?:\d[ -]?){12,18}\d(?![\d-])")
IPV4_RE = re.compile(
    r"(?<![\d.])(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}"
    r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(?!\.?\d)"
)
IPV6_RE = re.compile(r"(?<![\w:])(?:[A-Fa-f0-9]{1,4}:){7}[A-Fa-f0-9]{1,4}(?![\w:])")

# (pattern, min digits, max digits)
PHONE_PATTERNS = [
    # NANP / generic 10-digit, optional country code: +1 415-555-0132, (415) 555-0132, 4155550132
    (
        re.compile(
            r"(?<![\w.])(?:\+?\d{1,3}[\s.\-]?)?(?:\(\d{3}\)\s?|\d{3}[\s.\-]?)\d{3}[\s.\-]?\d{4}(?!\w)"
        ),
        10,
        13,
    ),
    # International with leading +: +91 98765 43210, +44 20 7946 0958
    (re.compile(r"(?<![\w.])\+\d{1,3}(?:[\s.\-]?\(?\d{1,5}\)?){2,5}(?!\w)"), 8, 15),
    # Indian mobile written as 5+5: 98765 43210
    (re.compile(r"(?<![\w.])[6-9]\d{4}[\s\-]?\d{5}(?!\w)"), 10, 10),
]


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s)


def luhn_ok(number: str) -> bool:
    digits = _digits(number)
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    parity = len(digits) % 2
    for i, ch in enumerate(digits):
        d = int(ch)
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


class PIISanitizer:
    def __init__(self, enable_ner: bool = False, spacy_model: str = "en_core_web_sm"):
        self.counts: Counter = Counter()
        self.notes: List[str] = []
        self._nlp = None
        if enable_ner:
            self._load_ner(spacy_model)

    # ------------------------------------------------------------------ tally
    @property
    def total_redacted(self) -> int:
        return int(sum(self.counts.values()))

    def reset(self) -> None:
        self.counts.clear()

    def report(self) -> Dict[str, int]:
        out = {k: int(v) for k, v in sorted(self.counts.items())}
        out["total"] = self.total_redacted
        return out

    # -------------------------------------------------------------------- NER
    def _load_ner(self, model: str) -> None:
        try:
            import spacy

            self._nlp = spacy.load(model, disable=["parser", "lemmatizer", "attribute_ruler"])
        except Exception as exc:
            self.notes.append(
                f"spaCy NER disabled ({type(exc).__name__}: {exc}). "
                f"Install with: python -m spacy download {model}"
            )
            log.warning(self.notes[-1])

    def _ner_pass(self, texts: List[str]) -> List[str]:
        out: List[str] = []
        for doc, original in zip(self._nlp.pipe(texts, batch_size=128), texts):
            pieces, last = [], 0
            for ent in doc.ents:
                if ent.label_ == "PERSON" and len(ent.text.strip()) > 1:
                    pieces.append(original[last : ent.start_char])
                    pieces.append(TAG_PII)
                    last = ent.end_char
                    self.counts["person"] += 1
            pieces.append(original[last:])
            out.append("".join(pieces))
        return out

    # ------------------------------------------------------------------ regex
    def _tag(self, kind: str, tag: str) -> str:
        self.counts[kind] += 1
        return tag

    def _cc_repl(self, m: "re.Match[str]") -> str:
        return self._tag("credit_card", TAG_PII) if luhn_ok(m.group()) else m.group()

    def _phone_repl(self, lo: int, hi: int):
        def repl(m: "re.Match[str]") -> str:
            n = len(_digits(m.group()))
            return self._tag("phone", TAG_PHONE) if lo <= n <= hi else m.group()

        return repl

    def _regex_pass(self, text: str) -> str:
        if not text:
            return text
        text = EMAIL_RE.sub(lambda m: self._tag("email", TAG_EMAIL), text)
        text = SSN_RE.sub(lambda m: self._tag("ssn", TAG_PII), text)
        text = CC_RE.sub(self._cc_repl, text)
        text = IPV4_RE.sub(lambda m: self._tag("ip_address", TAG_PII), text)
        text = IPV6_RE.sub(lambda m: self._tag("ip_address", TAG_PII), text)
        for pattern, lo, hi in PHONE_PATTERNS:
            text = pattern.sub(self._phone_repl(lo, hi), text)
        return text

    # -------------------------------------------------------------------- API
    def sanitize(self, text: Optional[str]) -> str:
        return self.sanitize_batch([text or ""])[0]

    def sanitize_batch(self, texts: Iterable[Optional[str]]) -> List[str]:
        cleaned = [self._regex_pass(t or "") for t in texts]
        if self._nlp is not None and cleaned:
            cleaned = self._ner_pass(cleaned)
        return cleaned
