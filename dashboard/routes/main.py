"""Main routes for AEGIS dashboard landing page."""

from flask import Blueprint, render_template

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def landing():
    """Render the main landing page with section cards."""
    return render_template("landing.html")
