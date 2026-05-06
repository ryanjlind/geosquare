import os
import smtplib
import json
import logging
import time

from flask import Blueprint, jsonify, render_template, request, current_app, url_for, redirect, make_response
from email.message import EmailMessage
from datetime import datetime, timezone

from app.core.auth import (
    begin_lastlogin_link,
    resolve_lastlogin_conflict,
    get_lastlogin_client,
    is_local_auth_bypass_enabled
)

from app.core.game_service import (
    get_daily_square_data,
    get_game_state_payload,
    get_player_stats_payload,
    submit_guess,
    submit_pass,
    get_all_daily_square_data,
    get_all_daily_square_data_preview,
    expand_square
)

from app.core.session_service import resolve_request_identity
from app.core.user import is_username_available, set_username
from app.helpers.session import attach_session_cookie, COOKIE_NAME, get_user_id_from_cookie, get_session_id_from_cookie
from app.core.db import get_conn

main_bp = Blueprint("main", __name__)

client_log_logger = logging.getLogger("geosquare.client")


def _identity():
    with get_conn() as conn:
        cur = conn.cursor()
        return resolve_request_identity(cur)


@main_bp.route("/")
def index():
    return render_template("index.html", cesium_ion_token=os.getenv("CESIUM_ION_TOKEN", ""))


@main_bp.route("/api/client-log", methods=["POST"])
def client_log():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "error": "Invalid JSON payload"}), 400

    log_record = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "ip": request.headers.get("X-Forwarded-For", request.remote_addr),
        "user_agent": request.headers.get("User-Agent"),
        "referer": request.headers.get("Referer"),
        "payload": payload,
    }

    current_app.logger.error(json.dumps(log_record, ensure_ascii=False))
    print("CLIENT_LOG_RECEIVED:", json.dumps(log_record, ensure_ascii=False))
    return jsonify({"ok": True})


@main_bp.route("/api/daily-square")
def daily_square():
    identity = _identity()
    round_number = int(request.args["round"])

    body = get_daily_square_data(
        identity["user_id"],
        identity["session_id"],
        round_number,
    )

    resp = jsonify(body)
    return attach_session_cookie(resp, identity["user_id"], identity["session_id"])


@main_bp.route("/api/all-daily-squares")
def all_daily_squares():
    identity = _identity()

    body, status = get_all_daily_square_data(
        identity["user_id"],
        identity["session_id"],
    )

    resp = jsonify(body)
    resp.status_code = status
    return attach_session_cookie(resp, identity["user_id"], identity["session_id"])


@main_bp.route("/api/game-state")
def game_state():
    print(f"{time.perf_counter():.9f} game_state: start", flush=True)

    identity = _identity()
    print(f"{time.perf_counter():.9f} game_state: identity={identity}", flush=True)

    try:
        print(f"{time.perf_counter():.9f} game_state: before get_game_state_payload call", flush=True)

        body, status = get_game_state_payload(
            identity["user_id"],
            identity["session_id"],
        )

        print(f"{time.perf_counter():.9f} game_state: after get_game_state_payload call", flush=True)
        print(f"{time.perf_counter():.9f} game_state: payload status={status}", flush=True)
    except Exception as e:
        print(f"{time.perf_counter():.9f} game_state: exception in get_game_state_payload: {e}", flush=True)
        raise

    resp = jsonify(body)
    resp.status_code = status
    print(f"{time.perf_counter():.9f} game_state: response built", flush=True)

    return attach_session_cookie(resp, identity["user_id"], identity["session_id"])

@main_bp.route("/api/guess", methods=["POST"])
def guess():
    identity = _identity()
    payload = request.get_json(silent=True) or {}

    body, status = submit_guess(payload, identity["user_id"], identity["session_id"])

    resp = jsonify(body)
    resp.status_code = status
    return attach_session_cookie(resp, identity["user_id"], identity["session_id"])


@main_bp.route("/api/pass", methods=["POST"])
def pass_round():
    identity = _identity()
    payload = request.get_json(silent=True) or {}

    body, status = submit_pass(payload, identity["user_id"], identity["session_id"])

    resp = jsonify(body)
    resp.status_code = status
    return attach_session_cookie(resp, identity["user_id"], identity["session_id"])


@main_bp.route("/api/player-stats")
def player_stats():
    identity = _identity()

    body, status = get_player_stats_payload(identity["user_id"])

    resp = jsonify(body)
    resp.status_code = status
    return attach_session_cookie(resp, identity["user_id"], identity["session_id"])


@main_bp.route("/api/expand", methods=["POST"])
def expand():
    identity = _identity()
    payload = request.get_json(silent=True) or {}

    body, status = expand_square(
        identity["user_id"],
        identity["session_id"],
        int(payload.get("round_number")),
    )

    resp = jsonify(body)
    resp.status_code = status
    return attach_session_cookie(resp, identity["user_id"], identity["session_id"])


@main_bp.route("/api/all-daily-squares/preview")
def all_daily_squares_preview():
    game_date = request.args.get("game_date")

    user_id = get_user_id_from_cookie()
    if user_id != 152:
        return jsonify({"error": "forbidden"}), 403

    body, status = get_all_daily_square_data_preview(game_date)

    resp = jsonify(body)
    resp.status_code = status
    return resp


@main_bp.route("/api/username-check")
def username_check():
    username = (request.args.get("username") or "").strip()
    return jsonify({"available": is_username_available(username)})


@main_bp.route("/api/set-username", methods=["POST"])
def set_username_route():
    identity = _identity()
    payload = request.get_json(silent=True) or {}

    ok, error = set_username(identity["user_id"], payload.get("username", ""))

    if not ok:
        return jsonify({"ok": False, "error": error}), 400

    return jsonify({"ok": True})


@main_bp.route("/preview")
def preview():
    return render_template("preview.html")