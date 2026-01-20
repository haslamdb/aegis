"""Dashboards routes for analytics and visualizations."""

from flask import Blueprint, render_template

dashboards_bp = Blueprint("dashboards", __name__, url_prefix="/dashboards")


@dashboards_bp.route("/")
def index():
    """Render the dashboards landing page."""
    return render_template("dashboards_index.html")
