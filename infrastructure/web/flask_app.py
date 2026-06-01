from flask import Flask
from flask_cors import CORS
from flask_jwt_extended import JWTManager
import os

from infrastructure.database.db import db, migrate
from config import Config


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    migrate.init_app(app, db)
    CORS(app)
    JWTManager(app)

    from infrastructure.web.routes import register_routes
    register_routes(app)

    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        from infrastructure.web.scheduler import init_scheduler
        init_scheduler(app)

    return app