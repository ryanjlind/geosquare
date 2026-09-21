import json
from datetime import datetime, timezone

from app.core.db import get_conn


def write_log_event(
    *,
    event_type: str,
    details: dict | None,
    ip_address: str | None,
    user_agent: str | None,
    referer: str | None,
) -> None:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO dbo.LogEvents (
                OccurredAtUtc,
                EventType,
                DetailsJson,
                IpAddress,
                UserAgent,
                Referer
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(timezone.utc),
                event_type,
                json.dumps(details, ensure_ascii=False),
                ip_address,
                user_agent,
                referer,
            ),
        )
        conn.commit()