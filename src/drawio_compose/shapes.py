from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

from .errors import DrawioComposeError
from .resources import SHAPE_INDEX


def _soundex(token: str) -> str:
    token = re.sub(r"[^a-z]", "", token.lower())
    if not token:
        return ""
    table = str.maketrans("bfpvcgjkqsxzdtlmnr", "111122222222334556")
    first = token[0].upper()
    digits: list[str] = []
    previous = ""
    for digit in token[1:].translate(table):
        if digit.isdigit() and digit != previous:
            digits.append(digit)
        previous = digit if digit.isdigit() else ""
    return (first + "".join(digits) + "000")[:4]


def _tokens(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", value.lower())


def _aws4_preference(style: str, terms: list[str]) -> int:
    """Prefer current AWS4 service icons without overriding poor text matches."""
    if "mxgraph.aws4." not in style:
        return 0

    bonus = 25
    term_set = set(terms)
    identifiers = re.findall(
        r"(?:resIcon|shape)=mxgraph\.aws4\.([a-zA-Z0-9_]+)",
        style,
    )
    for identifier in identifiers:
        identifier_tokens = [token for token in _tokens(identifier) if not token.isdigit()]
        if identifier_tokens and set(identifier_tokens).issubset(term_set):
            bonus += 25
            break
    return bonus


@lru_cache(maxsize=1)
def load_shape_index() -> list[dict[str, Any]]:
    try:
        payload = json.loads(SHAPE_INDEX.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DrawioComposeError(f"cannot load shape index: {exc}") from exc
    if not isinstance(payload, list):
        raise DrawioComposeError("shape index must contain a JSON array")
    return payload


def search_shapes(query: str, limit: int = 5) -> list[dict[str, Any]]:
    terms = _tokens(query)
    if not terms:
        return []
    scored: list[tuple[int, str, str, dict[str, Any]]] = []
    for item in load_shape_index():
        title = str(item.get("title", ""))
        tags = str(item.get("tags", ""))
        style = str(item.get("style", ""))
        haystack = " ".join((title, tags, style)).lower()
        words = _tokens(" ".join((title, tags)))
        word_tokens = set(words)
        word_soundex = {_soundex(word) for word in words if word}
        score = 0
        matched = True
        title_tokens = set(_tokens(title))
        for term in terms:
            if term in title_tokens:
                score += 100
            elif term in word_tokens:
                score += 80
            elif any(word.startswith(term) for word in words):
                score += 60
            elif term in haystack:
                score += 30
            elif _soundex(term) and _soundex(term) in word_soundex:
                score += 10
            else:
                matched = False
                break
        if matched:
            score += _aws4_preference(style, terms)
            scored.append((score, title.casefold(), style, item))
    scored.sort(key=lambda row: (-row[0], row[1], row[2]))
    return [
        {
            "title": item.get("title"),
            "style": item.get("style"),
            "w": item.get("w"),
            "h": item.get("h"),
            "tags": item.get("tags"),
            "type": item.get("type"),
        }
        for _score, _title, _style, item in scored[: max(0, min(limit, 50))]
    ]
