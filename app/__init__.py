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

    app.register_blueprint(main_bp)
    app.register_blueprint(profile_bp)

    if os.getenv('FLASK_ENV') == 'development':
        from app.routes.admin import admin_bp
        app.register_blueprint(admin_bp)

    return app