import os
import secrets
from hmac import compare_digest

from flask import current_app, jsonify, request
from itsdangerous import URLSafeSerializer

from app.constants import (
    COOKIE_MAX_AGE_SECONDS,
    CSRF_COOKIE_NAME,
    CSRF_SALT,
    DEVELOPMENT_ENVIRONMENT,
    PRODUCTION_ORIGIN,
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


def _expected_origin() -> str:
    if os.getenv('FLASK_ENV') == DEVELOPMENT_ENVIRONMENT:
        return request.host_url.rstrip('/')
    return PRODUCTION_ORIGIN


def enforce_csrf_protection():
    if request.method not in UNSAFE_METHODS or request.path in CSRF_EXEMPT_PATHS:
        return None

    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
    header_token = request.headers.get('X-CSRF-Token')
    origin = request.headers.get('Origin')

    if cookie_token is None or header_token is None:
        return jsonify({'ok': False, 'error': 'Request rejected.'}), 403

    if (
        origin != _expected_origin()
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

    is_development = os.getenv('FLASK_ENV') == DEVELOPMENT_ENVIRONMENT
    response.set_cookie(
        CSRF_COOKIE_NAME,
        _signer().dumps(secrets.token_urlsafe(32)),
        max_age=COOKIE_MAX_AGE_SECONDS,
        httponly=False,
        secure=not is_development,
        samesite='Strict',
    )
    return response