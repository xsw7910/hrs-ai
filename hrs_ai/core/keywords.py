"""Keyword extraction."""

from __future__ import annotations

import json
import re
from collections import Counter


STOP_WORDS = {
    "about",
    "after",
    "and",
    "are",
    "because",
    "before",
    "for",
    "from",
    "into",
    "not",
    "that",
    "the",
    "this",
    "until",
    "with",
}


def extract_keywords(text: str, max_keywords: int = 15) -> dict[str, object]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", text)
    counter = Counter(word.lower() for word in words if word.lower() not in STOP_WORDS)
    ranked = [{"keyword": word, "score": score} for word, score in counter.most_common(max_keywords)]
    high_value = [item["keyword"] for item in ranked[:5]]
    return {"high_value": high_value, "ranked": ranked}


def keywords_json(keywords: dict[str, object]) -> str:
    return json.dumps(keywords, indent=2, sort_keys=True) + "\n"
