from flask import Blueprint, jsonify, render_template

from app.core.profile_service import get_profile_payload
from app.helpers.session import get_user_id_from_cookie


profile_bp = Blueprint('profile', __name__)


@profile_bp.route('/profile')
def profile_page():
    return render_template('profile.html')


@profile_bp.route('/api/profile')
def profile_data():
    user_id = get_user_id_from_cookie()
    response_body, status_code = get_profile_payload(user_id)
    response = jsonify(response_body)
    response.status_code = status_code
    return response