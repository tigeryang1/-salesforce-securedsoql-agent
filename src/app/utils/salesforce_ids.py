from __future__ import annotations

import re


SALESFORCE_ID_RE = re.compile(r"^[a-zA-Z0-9]{18}$")


def looks_like_salesforce_id(value: str | None) -> bool:
    if not value:
        return False
    return bool(SALESFORCE_ID_RE.fullmatch(value))
