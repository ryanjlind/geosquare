from flask import Blueprint, jsonify, render_template, request
import os

from app.core.game_service import (
    get_daily_square_data,
    get_game_state_payload,
    get_player_stats_payload,
    resolve_request_identity,
    submit_guess,
    submit_pass,
)
from app.helpers.session import attach_session_cookie

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    return render_template('index.html', cesium_ion_token=os.getenv('CESIUM_ION_TOKEN', ''))


@main_bp.route('/api/daily-square')
def daily_square():
    round_number = int(request.args['round'])
    return jsonify(get_daily_square_data(round_number))


@main_bp.route('/api/game-state')
def game_state():
    identity = resolve_request_identity()
    response_body, status_code = get_game_state_payload(identity['user_id'], identity['session_id'])
    response = jsonify(response_body)
    response.status_code = status_code
    return attach_session_cookie(response, identity['user_id'], identity['session_id'])


@main_bp.route('/api/guess', methods=['POST'])
def guess():
    identity = resolve_request_identity()
    payload = request.get_json(silent=True) or {}
    response_body, status_code = submit_guess(payload, identity['user_id'], identity['session_id'])
    response = jsonify(response_body)
    response.status_code = status_code
    return attach_session_cookie(response, identity['user_id'], identity['session_id'])


@main_bp.route('/api/pass', methods=['POST'])
def pass_round():
    identity = resolve_request_identity()
    payload = request.get_json(silent=True) or {}
    response_body, status_code = submit_pass(payload, identity['user_id'], identity['session_id'])
    response = jsonify(response_body)
    response.status_code = status_code
    return attach_session_cookie(response, identity['user_id'], identity['session_id'])

@main_bp.route('/api/player-stats')
def player_stats():
    identity = resolve_request_identity()
    response_body, status_code = get_player_stats_payload(identity['user_id'])
    response = jsonify(response_body)
    response.status_code = status_code
    return attach_session_cookie(response, identity['user_id'], identity['session_id'])