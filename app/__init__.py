import logging
import os
from flask import Flask, Response, request
from app.routes.daily_dashboard import daily_dashboard_bp
from app.routes.main import main_bp
from app.routes.profile import profile_bp
from app.routes.weekly_e2e import weekly_e2e_bp


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder='templates',
        static_folder='static',
    )
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')

    logging.basicConfig(
        level=logging.INFO,
        format='[%(levelname)s] %(asctime)s %(name)s: %(message)s',
    )
    logging.getLogger('azure.core.pipeline.policies.http_logging_policy').setLevel(logging.WARNING)
    logging.getLogger('azure.monitor.opentelemetry.exporter.export._base').setLevel(logging.WARNING)
    logging.getLogger('geosquare').setLevel(logging.INFO)
    app.logger.setLevel(logging.INFO)

    @app.after_request
    def require_static_asset_revalidation(response: Response) -> Response:
        if request.path.startswith(f'{app.static_url_path}/'):
            response.headers['Cache-Control'] = 'no-cache, max-age=0, must-revalidate'
        return response

    app.register_blueprint(daily_dashboard_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(weekly_e2e_bp)

    if os.getenv('FLASK_ENV') == 'development':
        from app.admin.routes import admin_bp
        app.register_blueprint(admin_bp)

    return app