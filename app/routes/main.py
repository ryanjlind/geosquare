from flask import Blueprint, jsonify, render_template, request, current_app
from email.message import EmailMessage
import os
import smtplib
import json
import logging
from datetime import datetime, timezone

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

client_log_logger = logging.getLogger('geosquare.client')

@main_bp.route('/')
def index():
    return render_template('index.html', cesium_ion_token=os.getenv('CESIUM_ION_TOKEN', ''))

@main_bp.route('/api/client-log', methods=['POST'])
def client_log():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({'ok': False, 'error': 'Invalid JSON payload'}), 400

    log_record = {
        'timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'ip': request.headers.get('X-Forwarded-For', request.remote_addr),
        'user_agent': request.headers.get('User-Agent'),
        'referer': request.headers.get('Referer'),
        'payload': payload,
    }

    current_app.logger.error(json.dumps(log_record, ensure_ascii=False))
    print('CLIENT_LOG_RECEIVED:', json.dumps(log_record, ensure_ascii=False))

    return jsonify({'ok': True})

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

@main_bp.route('/api/feedback', methods=['POST'])
def feedback():
    data = request.form

    msg = EmailMessage()
    msg['Subject'] = f"GeoSquare Feedback ({data.get('type')})"
    msg['From'] = os.environ['SMTP_FROM']
    msg['To'] = os.environ['FEEDBACK_EMAIL']

    diagnostics = data.get('diagnostics')

    body = f"""
        Type: {data.get('type')}
        Platform: {data.get('platform')}
        Include Diagnostics: {data.get('includeDiagnostics')}
        Allow Email: {data.get('allowEmail')}
        User Email: {data.get('email')}

        Description:
        {data.get('description')}
    """

    if data.get('includeDiagnostics') == 'true' and diagnostics:
        body += f"""

        Diagnostics:
        {diagnostics}
        """

    msg.set_content(body)

    for file in request.files.getlist('screenshots'):
        msg.add_attachment(file.read(), maintype='image', subtype='png', filename=file.filename)

    with smtplib.SMTP(os.environ['SMTP_HOST'], int(os.environ['SMTP_PORT'])) as s:
        s.starttls()
        s.login(os.environ['SMTP_USER'], os.environ['SMTP_PASS'])
        s.send_message(msg)

    return jsonify({'ok': True})