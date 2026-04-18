from __future__ import annotations

import re


SELECT_RE = re.compile(
    r"select\s+(?P<fields>.*?)\s+from\s+(?P<object>[A-Za-z0-9_]+)",
    re.IGNORECASE | re.DOTALL,
)
WHERE_RE = re.compile(r"\bwhere\b(?P<clause>.*?)(?:\border\s+by\b|\blimit\b|\boffset\b|$)", re.IGNORECASE | re.DOTALL)
ORDER_BY_RE = re.compile(r"\border\s+by\b(?P<clause>.*?)(?:\blimit\b|\boffset\b|$)", re.IGNORECASE | re.DOTALL)


def extract_selected_fields(soql_query: str) -> list[str]:
    match = SELECT_RE.search(soql_query.strip())
    if not match:
        return []
    fields = []
    for chunk in match.group("fields").split(","):
        field = chunk.strip()
        if not field:
            continue
        fields.append(field.split()[-1] if " " in field else field)
    return fields


def extract_from_object(soql_query: str) -> str | None:
    match = SELECT_RE.search(soql_query.strip())
    if not match:
        return None
    return match.group("object")


def extract_where_clause(soql_query: str) -> str | None:
    match = WHERE_RE.search(soql_query)
    if not match:
        return None
    clause = match.group("clause").strip()
    return clause or None


def extract_order_by_clause(soql_query: str) -> str | None:
    match = ORDER_BY_RE.search(soql_query)
    if not match:
        return None
    clause = match.group("clause").strip()
    return clause or None


def escape_soql_like(value: str) -> str:
    """Escape SOQL LIKE wildcards and single quotes in a user-provided value."""
    return value.replace("'", "''").replace("%", "\\%").replace("_", "\\_")


def escape_soql_string(value: str) -> str:
    """Escape single quotes for a SOQL string literal."""
    return value.replace("'", "''")


def remove_field_from_where_or_order_by(soql_query: str, field_name: str) -> str:
    updated = re.sub(
        rf"\b{re.escape(field_name)}\b\s*(=|!=|<|>|<=|>=|LIKE|IN)\s*('[^']*'|[A-Za-z0-9_().-]+)\s*(AND|OR)?",
        "",
        soql_query,
        flags=re.IGNORECASE,
    )
    updated = re.sub(
        rf"\border\s+by\s+{re.escape(field_name)}\b(?:\s+(ASC|DESC))?",
        "",
        updated,
        flags=re.IGNORECASE,
    )
    updated = re.sub(r"\bWHERE\s+(AND|OR)\b", "WHERE", updated, flags=re.IGNORECASE)
    updated = re.sub(r"\bWHERE\s*$", "", updated, flags=re.IGNORECASE)
    updated = re.sub(r"\s{2,}", " ", updated).strip()
    return updated
