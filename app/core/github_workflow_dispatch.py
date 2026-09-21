import hmac
import os

import requests

from app.constants import (
    GITHUB_API_VERSION,
    GITHUB_REQUEST_TIMEOUT_SECONDS,
    GITHUB_WORKFLOW_REF,
)


def _required_environment_value(name: str) -> str:
    value = os.environ[name].strip()
    if not value:
        raise RuntimeError(f'{name} must not be empty.')
    return value


def dispatch_github_workflow(
    authorization: str | None,
    workflow_filename: str,
) -> bool:
    expected_authorization = (
        f"Bearer {_required_environment_value('DASHBOARD_TRIGGER_TOKEN')}"
    )
    if authorization is None or not hmac.compare_digest(
        authorization,
        expected_authorization,
    ):
        return False

    github_token = _required_environment_value('GITHUB_WORKFLOW_TOKEN')
    response = requests.post(
        (
            'https://api.github.com/repos/ryanjlind/geosquare/actions/'
            f'workflows/{workflow_filename}/dispatches'
        ),
        headers={
            'Accept': 'application/vnd.github+json',
            'Authorization': f'Bearer {github_token}',
            'X-GitHub-Api-Version': GITHUB_API_VERSION,
        },
        json={'ref': GITHUB_WORKFLOW_REF},
        timeout=GITHUB_REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return True