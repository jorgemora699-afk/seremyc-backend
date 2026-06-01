from flask import Flask
from flask_cors import CORS
from flask_jwt_extended import JWTManager
import os
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

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
    
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=["200 per day", "50 per hour"]
    )


    return app