import os
import json
from time import perf_counter

from flask import Blueprint, jsonify, render_template, request, current_app, url_for, redirect, make_response

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
from app.core.infinity_service import (
    get_infinity_state,
    select_infinity_round,
    submit_infinity_guess,
)

from app.core.session_service import (
    attach_request_session_cookie,
    clear_request_session_cookie,
    get_request_user_id,
    resolve_request_identity,
)
from app.core.side_missions.service import start_side_missions
from app.core.user import is_username_available, set_username
from app.core.feedback_service import send_feedback_email
from app.core.logging import client_event, exception as log_exception, timing

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    return render_template(
        "index.html",
        cesium_ion_token=os.getenv("CESIUM_ION_TOKEN", ""),
    )


@main_bp.route("/api/client-log", methods=["POST"])
def client_log():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "error": "Invalid JSON payload"}), 400

    event_type = payload.get("event_type")
    if not isinstance(event_type, str) or not event_type:
        return jsonify({"ok": False, "error": "event_type is required"}), 400

    details = payload.get("details")
    if details is not None and not isinstance(details, dict):
        return jsonify({"ok": False, "error": "details must be an object"}), 400

    ip_address = request.headers.get("X-Forwarded-For") or request.remote_addr
    user_agent = request.headers.get("User-Agent")
    referer = request.headers.get("Referer")

    client_event(
        payload=payload,
        event_type=event_type,
        details=details,
        ip_address=ip_address,
        user_agent=user_agent,
        referer=referer,
    )
    return jsonify({"ok": True})


@main_bp.route("/api/daily-square")
def daily_square():
    identity = resolve_request_identity()
    round_number = int(request.args["round"])

    body = get_daily_square_data(
        identity["user_id"],
        identity["session_id"],
        round_number,
    )

    resp = jsonify(body)
    return attach_request_session_cookie(resp, identity["user_id"], identity["session_id"])


@main_bp.route("/api/all-daily-squares")
def all_daily_squares():
    identity = resolve_request_identity()

    body, status = get_all_daily_square_data(
        identity["user_id"],
        identity["session_id"],
    )

    resp = jsonify(body)
    resp.status_code = status
    return attach_request_session_cookie(resp, identity["user_id"], identity["session_id"])


@main_bp.route("/api/game-state")
def game_state():
    started_at = perf_counter()
    timings_ms = {}

    identity_started_at = perf_counter()
    identity = resolve_request_identity()
    timings_ms['identity'] = (perf_counter() - identity_started_at) * 1000.0
    timing(
        'game_state.identity',
        timings_ms['identity'],
    )

    try:
        payload_started_at = perf_counter()
        body, status, payload_timings_ms = get_game_state_payload(
            identity["user_id"],
            identity["session_id"],
        )
        payload_elapsed_ms = (
            perf_counter() - payload_started_at
        ) * 1000.0
        timings_ms['get_game_state_payload'] = {
            'total': payload_elapsed_ms,
            **payload_timings_ms,
        }
        timing(
            'game_state.get_game_state_payload',
            payload_elapsed_ms,
            details={'status': status},
        )
    except Exception:
        log_exception('game_state: exception in get_game_state_payload')
        raise

    response_started_at = perf_counter()
    resp = jsonify(body)
    resp.status_code = status
    timings_ms['response'] = (perf_counter() - response_started_at) * 1000.0
    timing(
        'game_state.response',
        timings_ms['response'],
        details={'status': status},
    )
    timing(
        'game_state.total',
        (perf_counter() - started_at) * 1000.0,
        details={'status': status, 'timings_ms': timings_ms},
    )

    return attach_request_session_cookie(resp, identity["user_id"], identity["session_id"])

@main_bp.route("/api/guess", methods=["POST"])
def guess():
    identity = resolve_request_identity()
    payload = request.get_json(silent=True)
    print(f"guess payload: {payload}", flush=True)

    body, status = submit_guess(payload, identity["user_id"], identity["session_id"])

    resp = jsonify(body)
    resp.status_code = status
    return attach_request_session_cookie(resp, identity["user_id"], identity["session_id"])


@main_bp.route("/api/pass", methods=["POST"])
def pass_round():
    identity = resolve_request_identity()
    payload = request.get_json(silent=True)

    body, status = submit_pass(payload, identity["user_id"], identity["session_id"])

    resp = jsonify(body)
    resp.status_code = status
    return attach_request_session_cookie(resp, identity["user_id"], identity["session_id"])


@main_bp.route("/api/player-stats")
def player_stats():
    identity = resolve_request_identity()

    body, status = get_player_stats_payload(identity["user_id"])

    resp = jsonify(body)
    resp.status_code = status
    return attach_request_session_cookie(resp, identity["user_id"], identity["session_id"])


@main_bp.route("/api/infinity-state")
def infinity_state():
    identity = resolve_request_identity()
    infinity_pool_session_id = request.args.get('infinity_pool_session_id', type=int)
    body, status = get_infinity_state(
        identity["user_id"],
        identity["session_id"],
        infinity_pool_session_id,
    )
    resp = jsonify(body)
    resp.status_code = status
    return attach_request_session_cookie(resp, identity["user_id"], identity["session_id"])


@main_bp.route("/api/side-missions/start", methods=["POST"])
def side_missions_start():
    identity = resolve_request_identity()
    body, status = start_side_missions(
        identity["user_id"],
        identity["session_id"],
    )
    resp = jsonify(body)
    resp.status_code = status
    return attach_request_session_cookie(resp, identity["user_id"], identity["session_id"])


@main_bp.route("/api/infinity-round", methods=["POST"])
def infinity_round():
    identity = resolve_request_identity()
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
    return attach_request_session_cookie(resp, identity["user_id"], identity["session_id"])


@main_bp.route("/api/infinity-guess", methods=["POST"])
def infinity_guess():
    identity = resolve_request_identity()
    payload = request.get_json()
    if not isinstance(payload, dict):
        return jsonify({"error": "Invalid or missing JSON body"}), 400
    body, status = submit_infinity_guess(
        payload,
        identity["user_id"],
        identity["session_id"],
        'infinity',
    )
    resp = jsonify(body)
    resp.status_code = status
    return attach_request_session_cookie(resp, identity["user_id"], identity["session_id"])


@main_bp.route("/api/side-mission-guess", methods=["POST"])
def side_mission_guess():
    identity = resolve_request_identity()
    payload = request.get_json()
    if not isinstance(payload, dict):
        return jsonify({"error": "Invalid or missing JSON body"}), 400
    body, status = submit_infinity_guess(
        payload,
        identity["user_id"],
        identity["session_id"],
        'side_missions',
    )
    resp = jsonify(body)
    resp.status_code = status
    return attach_request_session_cookie(resp, identity["user_id"], identity["session_id"])


@main_bp.route("/api/expand", methods=["POST"])
def expand():
    identity = resolve_request_identity()
    payload = request.get_json(silent=True)

    body, status = expand_square(
        identity["user_id"],
        identity["session_id"],
        int(payload.get("round_number")),
    )

    resp = jsonify(body)
    resp.status_code = status
    return attach_request_session_cookie(resp, identity["user_id"], identity["session_id"])


@main_bp.route("/api/all-daily-squares/preview")
def all_daily_squares_preview():
    game_date = request.args.get("game_date")

    user_id = get_request_user_id()
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
    identity = resolve_request_identity()
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

    identity = resolve_request_identity()

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

        return attach_request_session_cookie(
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

        return attach_request_session_cookie(
            response,
            result["user_id"],
            None,
        )

    if result["status"] == "aborted":
        response = jsonify({
            "ok": True,
            "aborted": True,
        })

        return attach_request_session_cookie(
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
    return clear_request_session_cookie(response)

@main_bp.route("/preview")
def preview():
    return render_template("preview.html")