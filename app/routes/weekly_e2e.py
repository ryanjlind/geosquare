from flask import Blueprint, jsonify, request
from app.core.github_workflow_dispatch import dispatch_github_workflow


weekly_e2e_bp = Blueprint('weekly_e2e', __name__)

@weekly_e2e_bp.route('/api/internal/weekly-random-e2e', methods=['POST'])
def dispatch_weekly_e2e():
    if not dispatch_github_workflow(
        request.headers.get('Authorization'),
        'weekly_random_e2e.yml',
    ):
        return jsonify({'error': 'Unauthorized.'}), 401
    return jsonify({'ok': True, 'workflow': 'weekly_random_e2e.yml'}), 202