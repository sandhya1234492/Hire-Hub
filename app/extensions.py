from flask import current_app, g


def get_database():
    if "database" not in g:
        g.database = current_app.config["MONGO_CLIENT"][
            current_app.config["MONGO_DATABASE"]
        ]
    return g.database


def close_mongo(_error=None):
    g.pop("database", None)
