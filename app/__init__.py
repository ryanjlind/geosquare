import logging
import os
from flask import Flask
from app.routes.main import main_bp
from app.routes.profile import profile_bp

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

    app.register_blueprint(main_bp)
    app.register_blueprint(profile_bp)

    if os.getenv('FLASK_ENV') == 'development':
        from app.routes.admin import admin_bp
        app.register_blueprint(admin_bp)

    return app