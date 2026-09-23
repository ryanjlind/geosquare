import logging
import os
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from flask import Flask, Response, g, request
from werkzeug.exceptions import HTTPException, InternalServerError

from app.constants import STATIC_ASSET_HASH_LENGTH
from app.core.csrf import attach_csrf_cookie, enforce_csrf_protection
from app.core.logging import backend_exception
from app.routes.daily_dashboard import daily_dashboard_bp
from app.routes.main import main_bp
from app.routes.profile import profile_bp
from app.routes.weekly_e2e import weekly_e2e_bp


STATIC_JS_DIRECTORY = Path(__file__).parent / 'static' / 'js'


def _static_asset_hash(filename: str) -> str:
    asset_path = (Path(__file__).parent / 'static' / filename).resolve()
    asset_path.relative_to((Path(__file__).parent / 'static').resolve())
    return sha256(asset_path.read_bytes()).hexdigest()[:STATIC_ASSET_HASH_LENGTH]


def _static_asset_url(filename: str) -> str:
    return f'/static/{filename}?v={_static_asset_hash(filename)}'


def _static_js_import_map() -> dict[str, str]:
    return {
        f'@geosquare/{asset_path.name}': _static_asset_url(f'js/{asset_path.name}')
        for asset_path in STATIC_JS_DIRECTORY.glob('*.js')
    }


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder='templates',
        static_folder='static',
    )
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
    app.config['CSRF_ORIGIN'] = os.environ['CSRF_ORIGIN'].rstrip('/')

    logging.basicConfig(
        level=logging.INFO,
        format='[%(levelname)s] %(asctime)s %(name)s: %(message)s',
    )
    logging.getLogger('azure.core.pipeline.policies.http_logging_policy').setLevel(logging.WARNING)
    logging.getLogger('azure.monitor.opentelemetry.exporter.export._base').setLevel(logging.WARNING)
    logging.getLogger('geosquare').setLevel(logging.INFO)
    app.logger.setLevel(logging.INFO)

    @app.context_processor
    def inject_static_asset_helpers() -> dict:
        return {
            'asset_url': _static_asset_url,
            'js_import_map': _static_js_import_map,
        }

    @app.before_request
    def initialize_request_context() -> None:
        g.request_id = str(uuid4())
        g.user_id = None
        g.session_id = None

    app.before_request(enforce_csrf_protection)

    @app.after_request
    def require_static_asset_revalidation(response: Response) -> Response:
        if request.path.startswith(f'{app.static_url_path}/'):
            response.headers['Cache-Control'] = 'no-cache, max-age=0, must-revalidate'
        response.headers['X-Request-ID'] = g.request_id
        return attach_csrf_cookie(response)

    @app.errorhandler(Exception)
    def handle_unhandled_exception(exception_value: Exception):
        if isinstance(exception_value, HTTPException):
            return exception_value

        backend_exception(
            exception_value,
            request_method=request.method,
            request_path=request.path,
            endpoint=request.endpoint,
            user_id=g.user_id,
            session_id=g.session_id,
            request_id=g.request_id,
        )
        return InternalServerError()

    app.register_blueprint(daily_dashboard_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(weekly_e2e_bp)

    if os.getenv('FLASK_ENV') == 'development':
        from app.admin.routes import admin_bp
        app.register_blueprint(admin_bp)

    return app