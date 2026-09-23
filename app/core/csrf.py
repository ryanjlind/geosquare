import secrets
from hmac import compare_digest
from urllib.parse import urlsplit

from flask import current_app, jsonify, request
from itsdangerous import URLSafeSerializer

from app.constants import (
    COOKIE_MAX_AGE_SECONDS,
    CSRF_COOKIE_NAME,
    CSRF_SALT,
)


CSRF_EXEMPT_PATHS = {
    '/api/internal/daily-dashboard',
    '/api/internal/weekly-random-e2e',
}
UNSAFE_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}


def _signer() -> URLSafeSerializer:
    return URLSafeSerializer(current_app.config['SECRET_KEY'], salt=CSRF_SALT)


def _is_valid_signed_token(token: str) -> bool:
    is_valid, value = _signer().loads_unsafe(token)
    return is_valid and isinstance(value, str)


def enforce_csrf_protection():
    if request.method not in UNSAFE_METHODS or request.path in CSRF_EXEMPT_PATHS:
        return None

    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
    header_token = request.headers.get('X-CSRF-Token')
    origin = request.headers.get('Origin')

    if cookie_token is None or header_token is None:
        return jsonify({'ok': False, 'error': 'Request rejected.'}), 403

    if (
        origin != current_app.config['CSRF_ORIGIN']
        or not _is_valid_signed_token(cookie_token)
        or not compare_digest(cookie_token, header_token)
    ):
        return jsonify({'ok': False, 'error': 'Request rejected.'}), 403

    return None


def attach_csrf_cookie(response):
    if response.mimetype != 'text/html':
        return response

    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
    if cookie_token is not None and _is_valid_signed_token(cookie_token):
        return response

    is_secure_origin = urlsplit(current_app.config['CSRF_ORIGIN']).scheme == 'https'
    response.set_cookie(
        CSRF_COOKIE_NAME,
        _signer().dumps(secrets.token_urlsafe(32)),
        max_age=COOKIE_MAX_AGE_SECONDS,
        httponly=False,
        secure=is_secure_origin,
        samesite='Strict',
    )
    return response