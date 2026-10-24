from pathlib import Path

from flask import Flask, jsonify, render_template, request
from pymongo import MongoClient

from app.config import Config
from app.extensions import close_mongo, get_database
from app.routes.api import api
from app.routes.web import web


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    if not app.config.get("SECRET_KEY"):
        raise RuntimeError("Set SECRET_KEY in the environment before starting HireHub.")

    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    if "MONGO_CLIENT" not in app.config:
        app.config["MONGO_CLIENT"] = MongoClient(
            app.config["MONGO_URI"], serverSelectionTimeoutMS=3000
        )
    app.teardown_appcontext(close_mongo)
    app.register_blueprint(web)
    app.register_blueprint(api, url_prefix="/api")

    @app.context_processor
    def inject_current_user():
        from flask import session
        from app.repositories.user_repository import UserRepository

        user_id = session.get("user_id")
        return {"current_user": UserRepository(get_database()).get_by_id(user_id) if user_id else None}

    @app.errorhandler(404)
    def not_found(error):
        if request.path.startswith("/api/"):
            return jsonify(success=False, message="Resource not found", error_code="NOT_FOUND"), 404
        return render_template("errors/404.html"), 404

    @app.errorhandler(413)
    def too_large(error):
        message = "Uploaded file is too large."
        if request.path.startswith("/api/"):
            return jsonify(success=False, message=message, error_code="FILE_TOO_LARGE"), 413
        return render_template("errors/error.html", message=message), 413

    return app
