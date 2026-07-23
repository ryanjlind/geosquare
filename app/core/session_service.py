# core/session_service.py

from app.core.game_queries import get_today_game, create_session
from app.core.user_queries import create_user, get_user_by_id
from app.helpers.session import get_session_id_from_cookie, get_user_id_from_cookie


def _require_today_game(cur):
    row = get_today_game(cur)
    if row is None:
        return None
    return int(row.GameId)


def get_current_session(cur, user_id: int, session_id: int | None):
    game_id = _require_today_game(cur)
    if game_id is None:
        return None

    if session_id is not None:
        cur.execute(
            """
            SELECT SessionId, GameId, UserId, CompletedAt, TotalScore
            FROM GameSessions
            WHERE SessionId = ?
            """,
            (session_id,),
        )
        row = cur.fetchone()
        if row and int(row.UserId) == user_id and int(row.GameId) == game_id:
            return row

    cur.execute(
        """
        SELECT SessionId, GameId, UserId, CompletedAt, TotalScore
        FROM GameSessions
        WHERE UserId = ? AND GameId = ?
        ORDER BY
            CASE WHEN CompletedAt IS NOT NULL THEN 0 ELSE 1 END,
            StartedAt DESC
        """,
        (user_id, game_id),
    )
    row = cur.fetchone()
    if row:
        return row

    return create_session(cur, user_id, game_id)


def resolve_request_identity(cur):
    cookie_user_id = get_user_id_from_cookie()
    cookie_session_id = get_session_id_from_cookie()

    if cookie_user_id is not None:
        user = get_user_by_id(cur, cookie_user_id)
    else:
        user = None

    if user is None:
        user = create_user(cur)

    user_id = int(user.UserId)
    session = get_current_session(cur, user_id, cookie_session_id)

    return {
        "user_id": user_id,
        "session_id": int(session.SessionId) if session else None,
    }