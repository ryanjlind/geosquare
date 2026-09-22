# core/session_service.py

import os
from time import perf_counter

from flask import current_app, request
from itsdangerous import URLSafeSerializer

from app.constants import COOKIE_MAX_AGE_SECONDS, COOKIE_NAME
from app.core.db import get_conn
from app.core.game_queries import get_today_game, create_session
from app.core.user_queries import create_user, get_user_by_id


def _require_today_game(cur):
    row = get_today_game(cur)
    if row is None:
        return None
    return int(row.GameId)


def get_current_session(
    cur,
    user_id: int,
    session_id: int | None,
    *,
    timings_ms: dict[str, float] | None = None,
):
    today_game_started_at = perf_counter()
    game_id = _require_today_game(cur)
    if timings_ms is not None:
        timings_ms['today_game'] = (perf_counter() - today_game_started_at) * 1000.0
    if game_id is None:
        return None

    session_started_at = perf_counter()
    try:
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
    finally:
        if timings_ms is not None:
            timings_ms['session'] = (perf_counter() - session_started_at) * 1000.0


def resolve_request_identity():
    timings_ms = {}
    connection_started_at = perf_counter()
    with get_conn() as conn:
        timings_ms['connection'] = (perf_counter() - connection_started_at) * 1000.0
        cur = conn.cursor()

        cookie_started_at = perf_counter()
        cookie_identity = _get_identity_from_cookie()
        timings_ms['cookie'] = (perf_counter() - cookie_started_at) * 1000.0
        cookie_user_id = (
            cookie_identity.get('user_id')
            if cookie_identity is not None
            else None
        )
        cookie_session_id = (
            cookie_identity.get('session_id')
            if cookie_identity is not None
            else None
        )

        user_started_at = perf_counter()
        if cookie_user_id is not None:
            user = get_user_by_id(cur, cookie_user_id)
        else:
            user = None

        if user is None:
            user = create_user(cur)
        timings_ms['user'] = (perf_counter() - user_started_at) * 1000.0

        user_id = int(user.UserId)
        session = get_current_session(
            cur,
            user_id,
            cookie_session_id,
            timings_ms=timings_ms,
        )

        return {
            "user_id": user_id,
            "session_id": int(session.SessionId) if session else None,
            "timings_ms": timings_ms,
        }


def _get_identity_from_cookie() -> dict | None:
    raw = request.cookies.get(COOKIE_NAME)
    if raw is None:
        return None

    signer = URLSafeSerializer(current_app.config['SECRET_KEY'], salt='geosquare-session')
    is_valid, data = signer.loads_unsafe(raw)
    if not is_valid or not isinstance(data, dict):
        return None

    identity = {}
    if data.get('user_id') is not None:
        identity['user_id'] = int(data['user_id'])
    if data.get('session_id') is not None:
        identity['session_id'] = int(data['session_id'])
    return identity


def get_request_user_id():
    identity = _get_identity_from_cookie()
    if identity is None:
        return None
    return identity.get('user_id')


def attach_request_session_cookie(response, user_id: int, session_id: int | None):
    is_local = os.getenv('LOCAL_AUTH_BYPASS', '').lower() in ('1', 'true', 'yes')
    signer = URLSafeSerializer(current_app.config['SECRET_KEY'], salt='geosquare-session')
    response.set_cookie(
        COOKIE_NAME,
        signer.dumps({
            'user_id': int(user_id),
            'session_id': int(session_id) if session_id is not None else None,
        }),
        max_age=COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        secure=not is_local,
        samesite='Lax',
    )
    return response


def clear_request_session_cookie(response):
    response.delete_cookie(COOKIE_NAME)
    return response