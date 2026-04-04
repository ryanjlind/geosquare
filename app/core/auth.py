import os
from datetime import datetime, timezone

from authlib.integrations.flask_client import OAuth
from flask import current_app, session

from app.core.db import get_conn


LASTLOGIN_PROVIDER = 'lastlogin'

_oauth = OAuth()
_lastlogin_client = None


def _utcnow():
    return datetime.now(timezone.utc)


def is_local_auth_bypass_enabled() -> bool:
    return os.getenv('LOCAL_AUTH_BYPASS', '').lower() in ('1', 'true', 'yes')


def get_lastlogin_client():
    global _lastlogin_client

    if _lastlogin_client is not None:
        return _lastlogin_client

    _oauth.init_app(current_app)

    _lastlogin_client = _oauth.register(
        name='lastlogin',
        server_metadata_url='https://lastlogin.net/.well-known/openid-configuration',
        client_id=os.getenv('LASTLOGIN_CLIENT_ID'),
        client_secret='',
        client_kwargs={'scope': 'openid profile email'},
    )
    return _lastlogin_client


def _get_linked_user_id(cur, subject: str) -> int | None:
    cur.execute(
        """
        SELECT UserId
        FROM Users
        WHERE AuthProvider = ? AND AuthProviderSubject = ?
        """,
        (LASTLOGIN_PROVIDER, subject),
    )
    row = cur.fetchone()
    return int(row.UserId) if row else None


def _touch_lastlogin(cur, user_id: int) -> None:
    cur.execute(
        """
        UPDATE Users
        SET LastLoginAt = ?
        WHERE UserId = ?
        """,
        (_utcnow(), user_id),
    )


def _link_user_to_lastlogin(cur, user_id: int, subject: str) -> None:
    cur.execute(
        """
        UPDATE Users
        SET AuthProvider = ?, AuthProviderSubject = ?, LastLoginAt = ?
        WHERE UserId = ?
        """,
        (LASTLOGIN_PROVIDER, subject, _utcnow(), user_id),
    )


def _get_sessions_by_game(cur, user_id: int) -> dict[int, object]:
    cur.execute(
        """
        SELECT SessionId, GameId, CompletedAt
        FROM GameSessions
        WHERE UserId = ?
        """,
        (user_id,),
    )
    rows = cur.fetchall()
    return {int(row.GameId): row for row in rows}


def _build_merge_plan(source_user_id: int, target_user_id: int) -> dict:
    with get_conn() as conn:
        cur = conn.cursor()
        source_by_game = _get_sessions_by_game(cur, source_user_id)
        target_by_game = _get_sessions_by_game(cur, target_user_id)

    move_source_to_target: list[int] = []
    move_target_to_source: list[int] = []
    conflict_game_ids: list[int] = []

    all_game_ids = set(source_by_game.keys()) | set(target_by_game.keys())

    for game_id in all_game_ids:
        source_session = source_by_game.get(game_id)
        target_session = target_by_game.get(game_id)

        if source_session and not target_session:
            move_source_to_target.append(int(source_session.SessionId))
            continue

        if target_session and not source_session:
            continue

        source_completed = source_session.CompletedAt is not None
        target_completed = target_session.CompletedAt is not None

        if source_completed and target_completed:
            conflict_game_ids.append(int(game_id))
            continue

        if source_completed and not target_completed:
            move_source_to_target.append(int(source_session.SessionId))
            move_target_to_source.append(int(target_session.SessionId))
            continue

        if not source_completed and target_completed:
            continue

        move_source_to_target.append(int(source_session.SessionId))
        move_target_to_source.append(int(target_session.SessionId))

    return {
        'source_user_id': source_user_id,
        'target_user_id': target_user_id,
        'move_source_to_target': move_source_to_target,
        'move_target_to_source': move_target_to_source,
        'conflict_game_ids': conflict_game_ids,
    }


def _update_sessions_user_id(cur, session_ids: list[int], new_user_id: int) -> None:
    if not session_ids:
        return

    placeholders = ','.join('?' for _ in session_ids)
    cur.execute(
        f"""
        UPDATE GameSessions
        SET UserId = ?
        WHERE SessionId IN ({placeholders})
        """,
        (new_user_id, *session_ids),
    )


def _apply_merge_plan(
    source_user_id: int,
    target_user_id: int,
    move_source_to_target: list[int],
    move_target_to_source: list[int],
) -> None:
    with get_conn() as conn:
        cur = conn.cursor()
        _update_sessions_user_id(cur, move_source_to_target, target_user_id)
        _update_sessions_user_id(cur, move_target_to_source, source_user_id)
        conn.commit()


def begin_lastlogin_link(current_user_id: int, subject: str | None) -> dict:
    if not subject:
        return {'status': 'error', 'message': 'Missing LastLogin subject.'}

    with get_conn() as conn:
        cur = conn.cursor()

        linked_user_id = _get_linked_user_id(cur, subject)

        if linked_user_id is None:
            _link_user_to_lastlogin(cur, current_user_id, subject)
            conn.commit()
            return {
                'status': 'linked_current_user',
                'user_id': current_user_id,
            }

        if linked_user_id == current_user_id:
            _touch_lastlogin(cur, current_user_id)
            conn.commit()
            return {
                'status': 'already_linked',
                'user_id': current_user_id,
            }

    plan = _build_merge_plan(current_user_id, linked_user_id)

    if plan['conflict_game_ids']:
        session['pending_lastlogin_link'] = {
            'subject': subject,
            'source_user_id': current_user_id,
            'target_user_id': linked_user_id,
        }
        return {
            'status': 'conflict',
            'conflict_count': len(plan['conflict_game_ids']),
        }

    _apply_merge_plan(
        source_user_id=current_user_id,
        target_user_id=linked_user_id,
        move_source_to_target=plan['move_source_to_target'],
        move_target_to_source=plan['move_target_to_source'],
    )

    with get_conn() as conn:
        cur = conn.cursor()
        _touch_lastlogin(cur, linked_user_id)
        conn.commit()

    return {
        'status': 'switched_to_linked_user',
        'user_id': linked_user_id,
    }


def resolve_lastlogin_conflict(action: str | None) -> dict:
    pending = session.get('pending_lastlogin_link')
    if not pending:
        return {'status': 'error', 'message': 'No pending login conflict.'}

    source_user_id = int(pending['source_user_id'])
    target_user_id = int(pending['target_user_id'])

    if action == 'abort':
        session.pop('pending_lastlogin_link', None)
        return {
            'status': 'aborted',
            'user_id': source_user_id,
        }

    plan = _build_merge_plan(source_user_id, target_user_id)

    move_source_to_target = list(plan['move_source_to_target'])
    move_target_to_source = list(plan['move_target_to_source'])

    if action == 'overwrite_profile':
        with get_conn() as conn:
            cur = conn.cursor()
            source_by_game = _get_sessions_by_game(cur, source_user_id)
            target_by_game = _get_sessions_by_game(cur, target_user_id)

        for game_id in plan['conflict_game_ids']:
            move_source_to_target.append(int(source_by_game[game_id].SessionId))
            move_target_to_source.append(int(target_by_game[game_id].SessionId))

    elif action == 'discard_this_device_conflicts':
        pass

    else:
        return {'status': 'error', 'message': 'Invalid conflict action.'}

    _apply_merge_plan(
        source_user_id=source_user_id,
        target_user_id=target_user_id,
        move_source_to_target=move_source_to_target,
        move_target_to_source=move_target_to_source,
    )

    with get_conn() as conn:
        cur = conn.cursor()
        _touch_lastlogin(cur, target_user_id)
        conn.commit()

    session.pop('pending_lastlogin_link', None)

    return {
        'status': 'resolved',
        'user_id': target_user_id,
    }