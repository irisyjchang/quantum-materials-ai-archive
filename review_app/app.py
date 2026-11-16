"""Local review app: startup, database access, and environment banner (Task 9).

Usage: python review_app/app.py --env test [--port 5000]

The environment comes from --env or $GROWTH_LOG_ENV. Test and Archive use
separate databases (test.sqlite and archive.sqlite). The server listens on
127.0.0.1 only, so it is reachable from this laptop alone.
"""

import argparse
import sqlite3
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flask import Flask, g, render_template  # noqa: E402

from common.config import ConfigError, load_config  # noqa: E402
from db import env as environments  # noqa: E402
from db.connect import connect  # noqa: E402
from review_app.reviewers import ReviewerError  # noqa: E402

REQUIRED_TABLES = {"source_pdfs", "draft_runs", "growth_runs", "run_revisions", "processing_status"}


class AppStartupError(RuntimeError):
    """The app cannot start; the message tells the operator what to fix."""


def check_database(environment):
    """Raise AppStartupError unless the environment's database exists and has the MVP schema."""
    database = environment.database_path
    setup = f"create it with: python db/init_db.py {database.name}"
    if not database.is_file():
        raise AppStartupError(f"{environment.label} database not found at {database}; {setup}")
    try:
        connection = connect(database, read_only=True)
        try:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
                )
            }
        finally:
            connection.close()
    except sqlite3.DatabaseError as error:
        raise AppStartupError(f"{database} is not a readable SQLite database: {error}") from None
    missing = REQUIRED_TABLES - tables
    if missing:
        raise AppStartupError(
            f"{database} is missing the MVP tables {', '.join(sorted(missing))}; {setup} in an empty location"
        )


def get_db():
    """One connection per request, opened through the shared helper and closed at teardown."""
    if "db" not in g:
        g.db = connect(g.environment.database_path)
    return g.db


def create_app(env_name=None, root=environments.PROJECT_ROOT, config_path=None):
    """Build the app for one environment. Raises AppStartupError or ValueError.

    ``config_path`` defaults to $GROWTH_LOG_CONFIG, then config.json. The
    reviewer names are read once here and never written.
    """
    environment = environments.resolve(env_name, root=root)
    check_database(environment)
    try:
        config = load_config(config_path)
    except ConfigError as error:
        raise AppStartupError(f"config problem: {error}") from None

    app = Flask("review_app", root_path=str(Path(__file__).resolve().parent))
    app.config["ENVIRONMENT"] = environment
    app.config["REVIEWERS"] = config.reviewers
    app.config["CHECKLIST_PATH"] = config.checklist_path

    from review_app.routes import approve, clearance, corrections, drafts, hold, pdf, revise, run_detail, search
    from review_app.routes import status as status_routes
    for module in (status_routes, clearance, drafts, pdf, corrections, hold, approve, run_detail, revise, search):
        app.register_blueprint(module.blueprint)

    @app.before_request
    def bind_environment():
        g.environment = environment

    @app.teardown_appcontext
    def close_db(_error):
        connection = g.pop("db", None)
        if connection is not None:
            connection.close()

    @app.context_processor
    def shared_template_values():
        return {"environment": environment, "reviewers": app.config["REVIEWERS"]}

    @app.errorhandler(ReviewerError)
    def reviewer_error(error):
        return render_template("reviewer_error.html", message=str(error)), 400

    @app.route("/")
    def index():
        pending = get_db().execute(
            "SELECT count(*) FROM draft_runs WHERE review_status = 'Pending review'"
        ).fetchone()[0]
        return render_template("index.html", pending=pending)

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("not_found.html"), 404

    return app


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the local review app.")
    parser.add_argument("--env", help="test or archive (default: $GROWTH_LOG_ENV)")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--root", default=str(environments.PROJECT_ROOT),
                        help="folder that holds test.sqlite and archive.sqlite (default: the repository)")
    args = parser.parse_args(argv)
    try:
        app = create_app(args.env, root=args.root)
    except (AppStartupError, ValueError) as error:
        print(f"review app: {error}", file=sys.stderr)
        return 1
    environment = app.config["ENVIRONMENT"]
    print(f"Review app ({environment.label}) using {environment.database_path}")
    if not app.config["REVIEWERS"]:
        print("No authorized reviewers in config.json; clearances, corrections, holds, and approvals "
              "will be refused until the lab adds names.")
    app.run(host="127.0.0.1", port=args.port, debug=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
