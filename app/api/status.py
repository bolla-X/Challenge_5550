from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, jsonify, send_from_directory

status_bp = Blueprint("status", __name__)


@status_bp.get("/")
@status_bp.get("/dashboard")
@status_bp.get("/dashboard/")
def index():
    # Serves the React build's shell (frontend/vite.config.ts outputs here).
    # Approved migration step 10: this replaces the old render_template("index.html")
    # Jinja path — app/templates/index.html and app/static/app.js/styles.css
    # are no longer referenced by any route, but were left on disk (not
    # deleted) pending explicit confirmation per the migration plan.
    dist_dir = Path(current_app.static_folder) / "dist"
    return send_from_directory(dist_dir, "index.html")


@status_bp.get("/status")
def status():
    monitor = current_app.extensions["monitor_service"]
    return jsonify({"system": "VisionEPI", **monitor.status()})


@status_bp.get("/preflight")
def preflight():
    monitor = current_app.extensions["monitor_service"]
    return jsonify(monitor.preflight())
