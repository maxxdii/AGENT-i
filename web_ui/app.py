import os
import threading
from flask import Flask

from .routes import bp


def create_app() -> Flask:
    app = Flask(__name__)
    app.register_blueprint(bp)
    return app


if __name__ == "__main__":
    app = create_app()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
