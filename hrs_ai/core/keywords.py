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
    ranked = [word for word, _score in counter.most_common()]
    return {
        "high_value_keywords": ranked[:5],
        "normal_keywords": ranked[5:max_keywords],
        "dropped_keywords": ranked[max_keywords:],
    }


def keywords_json(keywords: dict[str, object]) -> str:
    return json.dumps(keywords, indent=2, sort_keys=True) + "\n"
