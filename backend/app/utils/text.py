"""Deterministic, testable text utilities: normalization, similarity, guards."""

from __future__ import annotations

import difflib
import re
import unicodedata
from typing import Iterable

from app.core.enums import PROHIBITED_TERMS

_WHITESPACE = re.compile(r"\s+")
_NON_ALNUM = re.compile(r"[^a-z0-9 ]+")
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    value = unicodedata.normalize("NFKD", str(value))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = _NON_ALNUM.sub(" ", value.lower())
    return _WHITESPACE.sub(" ", value).strip()


def normalize_for_match(value: str | None) -> str:
    """Aggressive normalization used for service-name matching."""
    return _PUNCT.sub(" ", normalize_text(value)).strip()


def tokenize(value: str | None) -> list[str]:
    normalized = normalize_for_match(value)
    return [t for t in normalized.split(" ") if t]


# Domain vocabulary that appears in many different ways on real bills.
_STOPWORDS: frozenset[str] = frozenset(
    {
        "a", "an", "and", "the", "of", "for", "to", "in", "on", "at", "by",
        "charge", "charges", "charges:", "service", "services", "amount",
        "total", "bill", "hospital", "pvt", "ltd", "private", "limited",
        "dr", "dr.", "mrs", "mr", "ms", "day", "days", "per", "rate",
        "department", "dept", "no", "nos", "unit", "units", "qty",
        "misc", "miscellaneous", "other", "others", "general", "wards",
    }
)

# Words that carry strong signal when matching a service description.
_SIGNAL_BOOSTS: frozenset[str] = frozenset(
    {
        "cabg", "bypass", "angioplasty", "stent", "cath", "catheter",
        "cabin", "arthroplasty", "knee", "hip", "hernia", "appendectomy",
        "cholecystectomy", "caesarean", "cesarean", "delivery", "lscs",
        "dialysis", "icu", "nicu", "ventilator", "mri", "ct", "xray",
        "x-ray", "ultrasound", "usg", "echo", "ecg", "ekg", "lab",
        "cbc", "cbcs", "cbcs", "tsh", "lft", "kft", "blood", "urine",
        "surgery", "operation", "procedure", "anaesthesia", "anesthesia",
        "oxygen", "ventilator", "monitor", "pharmacy", "medicine",
        "consumable", "consumables", "stethoscope", "syringe", "drip",
        "bed", "room", "nursing", "care", "charge", "consultation",
    }
)


def similarity(a: str | None, b: str | None) -> float:
    """0..1 token-aware similarity between two service names."""
    ta, tb = tokenize(a), tokenize(b)
    if not ta or not tb:
        return 0.0
    set_a, set_b = set(ta), set(tb)
    overlap = set_a & set_b
    union = set_a | set_b
    jaccard = len(overlap) / len(union) if union else 0.0
    sequence = difflib.SequenceMatcher(None, " ".join(ta), " ".join(tb)).ratio()
    return round(max(jaccard, sequence * 0.5 + jaccard * 0.5), 4)


def content_tokens(value: str | None) -> set[str]:
    return {t for t in tokenize(value) if t not in _STOPWORDS and len(t) > 1}


def keyword_score(description: str | None, service_name: str | None) -> float:
    """Signal-weighted overlap between a bill description and a benchmark name.

    A bill line says ``"ICU Charges"`` while the benchmark record is called
    ``"Intensive Care Unit ICU"``. Pure Jaccard scoring punishes that badly, so
    the score is asymmetric: how much of the *description* is explained by the
    record, and how much of the record is explained by the description.
    """
    desc_tokens = content_tokens(description)
    svc_tokens = content_tokens(service_name)
    if not desc_tokens or not svc_tokens:
        return 0.0
    shared = desc_tokens & svc_tokens
    if not shared:
        return 0.0
    coverage_desc = len(shared) / len(desc_tokens)
    coverage_svc = len(shared) / len(svc_tokens)
    base = 0.6 * coverage_desc + 0.4 * coverage_svc
    boosted = sum(1 for t in shared if t in _SIGNAL_BOOSTS) / len(shared)
    return round(min(1.0, base + 0.1 * boosted), 4)


def combined_match_score(description: str | None, service_name: str | None) -> float:
    """Blend of fuzzy string similarity and keyword overlap."""
    return round(max(similarity(description, service_name), keyword_score(description, service_name)), 4)


def contains_prohibited_language(text: str | None) -> list[str]:
    """Return prohibited accusation terms found in ``text``."""
    if not text:
        return []
    lowered = f" {normalize_text(text)} "
    return sorted(term for term in PROHIBITED_TERMS if f" {term} " in lowered)


def guard_language(text: str | None) -> tuple[str, list[str]]:
    """Neutralise accusation language before text reaches a user.

    MedBill Lens never asserts wrongdoing. This is a defence-in-depth safety
    net applied to *every* generated string, regardless of which provider
    produced it.
    """
    if not text:
        return "", []
    cleaned = text
    found: list[str] = []
    for term in sorted(PROHIBITED_TERMS, key=len, reverse=True):
        pattern = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
        if pattern.search(cleaned):
            found.append(term)
            cleaned = pattern.sub("questionable", cleaned)
    return cleaned.strip(), found


def truncate_words(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]).rstrip(",;:") + "…"


def dedupe_preserving_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = normalize_text(value)
        if key and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def humanize_key(key: str) -> str:
    return key.replace("_", " ").capitalize()
