import os

from flask import Flask

from app.routes.main import main_bp


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder='templates',
        static_folder='static',
    )
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-change-me')
    app.register_blueprint(main_bp)
    return app
