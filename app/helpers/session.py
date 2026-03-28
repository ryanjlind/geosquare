from flask import current_app, request
from itsdangerous import URLSafeSerializer

COOKIE_NAME = 'geosquare_session'
COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 365 * 5


def get_session_signer():
    return URLSafeSerializer(current_app.config['SECRET_KEY'], salt='geosquare-session')


def get_identity_from_cookie() -> dict:
    raw = request.cookies.get(COOKIE_NAME)
    if raw is None:
        return {}

    is_valid, data = get_session_signer().loads_unsafe(raw)
    if not is_valid or not isinstance(data, dict):
        return {}

    identity = {}

    user_id = data.get('user_id')
    session_id = data.get('session_id')

    if user_id is not None:
        identity['user_id'] = int(user_id)

    if session_id is not None:
        identity['session_id'] = int(session_id)

    return identity


def get_user_id_from_cookie():
    return get_identity_from_cookie().get('user_id')


def get_session_id_from_cookie():
    return get_identity_from_cookie().get('session_id')


def attach_session_cookie(response, user_id: int, session_id: int):
    response.set_cookie(
        COOKIE_NAME,
        get_session_signer().dumps({
            'user_id': int(user_id),
            'session_id': int(session_id),
        }),
        max_age=COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        secure=True,
        samesite='Lax',
    )
    return response