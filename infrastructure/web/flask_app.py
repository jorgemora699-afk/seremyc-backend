from flask import Flask
from flask_cors import CORS
from flask_jwt_extended import JWTManager

from infrastructure.database.db import db, migrate
from config import Config


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Extensiones
    db.init_app(app)
    migrate.init_app(app, db)
    CORS(app)
    JWTManager(app)

    # Blueprints
    from infrastructure.web.routes import register_routes
    register_routes(app)


    return app