from time import perf_counter

from flask import Blueprint, jsonify, render_template, request

from app.core.profile_service import (
    get_infinity_pools_payload,
    get_profile_history_payload,
    get_profile_payload,
)
from app.helpers.logging import info as log_info
from app.helpers.session import get_user_id_from_cookie


profile_bp = Blueprint('profile', __name__)


@profile_bp.route('/profile')
def profile_page():
    return render_template('profile.html')


@profile_bp.route('/profile/infinity-pools')
def infinity_pools_page():
    return render_template('infinity_pools.html')


@profile_bp.route('/api/profile')
def profile_data():
    request_start = perf_counter()
    log_info('[profile] /api/profile started')
    user_id = get_user_id_from_cookie()
    payload_start = perf_counter()
    response_body, status_code = get_profile_payload(user_id)
    log_info(
        f'[profile] /api/profile payload completed in '
        f'{perf_counter() - payload_start:.3f}s status={status_code}'
    )
    serialization_start = perf_counter()
    response = jsonify(response_body)
    log_info(
        f'[profile] /api/profile jsonify completed in '
        f'{perf_counter() - serialization_start:.3f}s'
    )
    response.status_code = status_code
    log_info(
        f'[profile] /api/profile completed in '
        f'{perf_counter() - request_start:.3f}s status={status_code}'
    )
    return response


@profile_bp.route('/api/profile/history')
def profile_history():
    request_start = perf_counter()
    log_info('[profile] /api/profile/history started')
    if 'offset' not in request.args:
        return jsonify({'error': 'offset is required.'}), 400

    try:
        offset = int(request.args['offset'])
    except ValueError:
        return jsonify({'error': 'offset must be an integer.'}), 400

    user_id = get_user_id_from_cookie()
    response_body, status_code = get_profile_history_payload(user_id, offset)
    response = jsonify(response_body)
    response.status_code = status_code
    log_info(
        f'[profile] /api/profile/history completed in '
        f'{perf_counter() - request_start:.3f}s status={status_code}'
    )
    return response


@profile_bp.route('/api/profile/infinity-pools')
def infinity_pools_data():
    user_id = get_user_id_from_cookie()
    response_body, status_code = get_infinity_pools_payload(user_id)
    response = jsonify(response_body)
    response.status_code = status_code
    return response