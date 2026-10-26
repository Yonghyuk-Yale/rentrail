"""The app's clock. In the demo, "now" is the user's time-machine date, everywhere on the server.

- today(user)      the simulated date (or the real date if the user never set one)
- stamp(user_id)   an ISO timestamp on the simulated date (time of day is real) for ledger rows,
                   uploads, settlements, posts ...
- visible(d, user) True if something dated `d` has already happened on the user's simulated date.
                   Lists only show records that exist "as of today", so moving the time machine
                   really changes what the user sees.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import db


def _parse(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def today(user: dict | None) -> date:
    return _parse((user or {}).get("demo_today")) or date.today()


def today_for(user_id: int | None) -> date:
    row = db.one("SELECT demo_today FROM users WHERE id = ?", (user_id,)) if user_id else None
    return today(row)


def stamp(user_id: int | None) -> str:
    d = today_for(user_id)
    t = datetime.now(timezone.utc).strftime("%H:%M:%S")
    return f"{d.isoformat()}T{t}+00:00"


def visible(when: str | None, user: dict) -> bool:
    d = _parse(when)
    return d is None or d <= today(user)
