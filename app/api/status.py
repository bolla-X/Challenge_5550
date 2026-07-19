from __future__ import annotations

from flask import Blueprint, current_app, jsonify, render_template

status_bp = Blueprint("status", __name__)


@status_bp.get("/")
@status_bp.get("/dashboard")
@status_bp.get("/dashboard/")
def index():
    return render_template("index.html")


@status_bp.get("/status")
def status():
    monitor = current_app.extensions["monitor_service"]
    return jsonify({"system": "VisionEPI", **monitor.status()})


@status_bp.get("/preflight")
def preflight():
    monitor = current_app.extensions["monitor_service"]
    return jsonify(monitor.preflight())
