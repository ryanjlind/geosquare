import os
import json
import logging
import time

from flask import Blueprint, jsonify, render_template, request, current_app, url_for, redirect, make_response
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
    set_round_difficulty,
    get_all_daily_square_data,
    get_all_daily_square_data_preview,
    expand_square
)
from app.core.infinity_service import (
    get_infinity_state,
    select_infinity_round,
    submit_infinity_guess,
)

from app.core.session_service import resolve_request_identity
from app.core.user import is_username_available, set_username
from app.helpers.session import attach_session_cookie, COOKIE_NAME, get_user_id_from_cookie, get_session_id_from_cookie
from app.core.db import get_conn
from app.core.feedback_service import send_feedback_email
from app.helpers.logging import debug as log_debug

main_bp = Blueprint("main", __name__)

client_log_logger = logging.getLogger("geosquare.client")


def _env_flag(name, default=False):
    raw = os.getenv(name)
    if raw is None:
        return default

    value = raw.strip().lower()
    return value in {"1", "true", "yes", "on"}


def _identity():
    with get_conn() as conn:
        cur = conn.cursor()
        return resolve_request_identity(cur)


@main_bp.route("/")
def index():
    return render_template(
        "index.html",
        cesium_ion_token=os.getenv("CESIUM_ION_TOKEN", ""),
        difficulty_slider_enabled=_env_flag("GEOSQUARE_ENABLE_DIFFICULTY_SLIDER", default=False),
    )


@main_bp.route("/api/client-log", methods=["POST"])
def client_log():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "error": "Invalid JSON payload"}), 400

    log_record = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "ip": request.headers.get("X-Forwarded-For") or request.remote_addr,
        "user_agent": request.headers.get("User-Agent"),
        "referer": request.headers.get("Referer"),
        "payload": payload,
    }

    current_app.logger.error(json.dumps(log_record, ensure_ascii=False))
    print(f"CLIENT_LOG_RECEIVED: {json.dumps(log_record, ensure_ascii=False)}", flush=True)
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
    print(f"{time.perf_counter():.9f} game_state: identity loaded", flush=True)

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
    print(f"guess payload: {payload}", flush=True)

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


@main_bp.route("/api/infinity-state")
def infinity_state():
    identity = _identity()
    infinity_pool_session_id = request.args.get('infinity_pool_session_id', type=int)
    body, status = get_infinity_state(
        identity["user_id"],
        identity["session_id"],
        infinity_pool_session_id,
    )
    resp = jsonify(body)
    resp.status_code = status
    return attach_session_cookie(resp, identity["user_id"], identity["session_id"])


@main_bp.route("/api/infinity-round", methods=["POST"])
def infinity_round():
    identity = _identity()
    payload = request.get_json()
    if not isinstance(payload, dict):
        return jsonify({"error": "Invalid or missing JSON body"}), 400
    if "round_number" not in payload:
        return jsonify({"error": "round_number is required."}), 400
    body, status = select_infinity_round(
        identity["user_id"],
        identity["session_id"],
        int(payload["round_number"]),
        int(payload["infinity_pool_session_id"])
        if payload.get("infinity_pool_session_id") is not None
        else None,
    )
    resp = jsonify(body)
    resp.status_code = status
    return attach_session_cookie(resp, identity["user_id"], identity["session_id"])


@main_bp.route("/api/infinity-guess", methods=["POST"])
def infinity_guess():
    identity = _identity()
    payload = request.get_json()
    if not isinstance(payload, dict):
        return jsonify({"error": "Invalid or missing JSON body"}), 400
    body, status = submit_infinity_guess(
        payload,
        identity["user_id"],
        identity["session_id"],
    )
    resp = jsonify(body)
    resp.status_code = status
    return attach_session_cookie(resp, identity["user_id"], identity["session_id"])


@main_bp.route("/api/difficulty", methods=["POST"])
def difficulty():
    identity = _identity()
    payload = request.get_json()
    if not isinstance(payload, dict):
        return jsonify({"error": "Invalid or missing JSON body"}), 400
    body, status = set_round_difficulty(payload, identity["user_id"], identity["session_id"])
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
    username = request.args.get("username")
    if not username:
        return jsonify({"available": False})
    return jsonify({"available": is_username_available(username.strip())})


@main_bp.route("/api/set-username", methods=["POST"])
def set_username_route():
    identity = _identity()
    payload = request.get_json()
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "error": "Invalid or missing JSON body"}), 400
    if "username" not in payload:
        return jsonify({"ok": False, "error": "username is required."}), 400
    ok, error = set_username(identity["user_id"], payload["username"])

    if not ok:
        return jsonify({"ok": False, "error": error}), 400

    return jsonify({"ok": True})

@main_bp.route("/api/feedback", methods=["POST"])
def feedback():
    send_feedback_email(
        request.form,
        request.files.getlist("screenshots"),
    )

    return jsonify({"ok": True})


@main_bp.route("/login")
def login():
    if is_local_auth_bypass_enabled():
        popup_url = url_for(
            "main.auth_callback",
            dev_sub="local-test-user",
        )
        return redirect(popup_url)

    client = get_lastlogin_client()
    redirect_uri = url_for("main.auth_callback", _external=True)

    return client.authorize_redirect(redirect_uri)


@main_bp.route("/auth/callback")
def auth_callback():
    if is_local_auth_bypass_enabled():
        user_info = {
            "sub": request.args.get("dev_sub") or "local-test-user",
        }
    else:
        client = get_lastlogin_client()
        token = client.authorize_access_token()
        user_info = token.get("userinfo")
        if not user_info:
            user_info = {}

    identity = _identity()

    result = begin_lastlogin_link(
        current_user_id=identity["user_id"],
        subject=user_info.get("sub"),
    )

    print(
        f"[AUTH] subject={user_info.get('sub')} "
        f"current_user_id={identity['user_id']} "
        f"result={result}",
        flush=True,
    )

    def build_popup_response(payload, user_id, session_id):
        message_json = json.dumps(payload)

        response = make_response(
            f"""
<!doctype html>
<html>
<body>
<script>
window.opener.postMessage({message_json}, window.location.origin);
window.close();
</script>
</body>
</html>
"""
        )

        return attach_session_cookie(
            response,
            user_id,
            session_id,
        )

    status = result["status"]

    if status in (
        "linked_current_user",
        "already_linked",
        "switched_to_linked_user",
    ):
        print(
            f"[AUTH] success -> user_id={result['user_id']} status={status}",
            flush=True,
        )

        return build_popup_response(
            {"type": "auth_success"},
            result["user_id"],
            None,
        )

    if status == "conflict":
        print(
            f"[AUTH] conflict -> current_user_id={identity['user_id']}",
            flush=True,
        )

        return build_popup_response(
            {
                "type": "auth_conflict",
                "message": "How should GeoSquare handle the conflict?",
            },
            identity["user_id"],
            identity["session_id"],
        )

    print(f"[AUTH] error -> result={result}", flush=True)

    return build_popup_response(
        {
            "type": "auth_error",
        "message": result["message"] if "message" in result else "Login failed.",
        },
        identity["user_id"],
        identity["session_id"],
    )


@main_bp.route("/auth/resolve", methods=["POST"])
def auth_resolve():
    payload = request.get_json()
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "error": "Invalid or missing JSON body"}), 400
    if "action" not in payload:
        return jsonify({"ok": False, "error": "action is required"}), 400

    result = resolve_lastlogin_conflict(payload["action"])

    if result["status"] == "resolved":
        response = jsonify({"ok": True})

        return attach_session_cookie(
            response,
            result["user_id"],
            None,
        )

    if result["status"] == "aborted":
        response = jsonify({
            "ok": True,
            "aborted": True,
        })

        return attach_session_cookie(
            response,
            result["user_id"],
            None,
        )

    return jsonify({
        "ok": False,
        "error": result["message"],
    }), 400


@main_bp.route("/logout", methods=["POST"])
def logout():
    response = jsonify({"ok": True})
    response.delete_cookie(COOKIE_NAME)
    return response

@main_bp.route("/preview")
def preview():
    return render_template("preview.html")