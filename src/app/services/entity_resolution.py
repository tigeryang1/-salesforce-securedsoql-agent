from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(slots=True)
class AccountCandidate:
    record: dict[str, str]
    score: int


def rank_account_matches(account_name: str, records: list[dict[str, str]]) -> list[dict[str, str]]:
    target = _normalize(account_name)
    ranked: list[AccountCandidate] = []
    for record in records:
        name = record.get("Name", "")
        normalized = _normalize(name)
        score = 0
        if normalized == target:
            score = 100
        elif normalized.startswith(target):
            score = 80
        elif target in normalized:
            score = 60
        elif any(part == target for part in normalized.split()):
            score = 40
        ranked.append(AccountCandidate(record=record, score=score))
    ranked.sort(key=lambda item: (-item.score, item.record.get("Name", "")))
    return [item.record for item in ranked]


def is_unambiguous_best_match(account_name: str, records: list[dict[str, str]]) -> bool:
    ranked = rank_account_matches(account_name, records)
    if not ranked:
        return False
    if len(ranked) == 1:
        return True
    top = _match_score(account_name, ranked[0])
    second = _match_score(account_name, ranked[1])
    return top >= 100 and second < 100


def _match_score(account_name: str, record: dict[str, str]) -> int:
    target = _normalize(account_name)
    normalized = _normalize(record.get("Name", ""))
    if normalized == target:
        return 100
    if normalized.startswith(target):
        return 80
    if target in normalized:
        return 60
    if any(part == target for part in normalized.split()):
        return 40
    return 0


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
