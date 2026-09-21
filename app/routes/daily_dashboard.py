from flask import Blueprint, jsonify, request
from app.core.github_workflow_dispatch import dispatch_github_workflow


daily_dashboard_bp = Blueprint('daily_dashboard', __name__)

@daily_dashboard_bp.route('/api/internal/daily-dashboard', methods=['POST'])
def dispatch_daily_dashboard():
    if not dispatch_github_workflow(
        request.headers.get('Authorization'),
        'daily_dashboard.yml',
    ):
        return jsonify({'error': 'Unauthorized.'}), 401
    return jsonify({'ok': True, 'workflow': 'daily_dashboard.yml'}), 202