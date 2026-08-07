import hmac
import os

import requests
from flask import Blueprint, jsonify, request


daily_dashboard_bp = Blueprint('daily_dashboard', __name__)

GITHUB_DISPATCH_URL = (
    'https://api.github.com/repos/ryanjlind/geosquare/actions/'
    'workflows/daily_dashboard.yml/dispatches'
)
GITHUB_API_VERSION = '2022-11-28'
GITHUB_WORKFLOW_REF = 'main'
REQUEST_TIMEOUT_SECONDS = 30


def _required_environment_value(name: str) -> str:
    value = os.environ[name].strip()
    if not value:
        raise RuntimeError(f'{name} must not be empty.')
    return value


@daily_dashboard_bp.route('/api/internal/daily-dashboard', methods=['POST'])
def dispatch_daily_dashboard():
    authorization = request.headers.get('Authorization')
    expected_authorization = (
        f"Bearer {_required_environment_value('DASHBOARD_TRIGGER_TOKEN')}"
    )
    if authorization is None or not hmac.compare_digest(
        authorization,
        expected_authorization,
    ):
        return jsonify({'error': 'Unauthorized.'}), 401

    github_token = _required_environment_value('GITHUB_WORKFLOW_TOKEN')
    response = requests.post(
        GITHUB_DISPATCH_URL,
        headers={
            'Accept': 'application/vnd.github+json',
            'Authorization': f'Bearer {github_token}',
            'X-GitHub-Api-Version': GITHUB_API_VERSION,
        },
        json={'ref': GITHUB_WORKFLOW_REF},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    return jsonify({'ok': True, 'workflow': 'daily_dashboard.yml'}), 202