"""Main routes for AEGIS dashboard landing page."""

from flask import Blueprint, render_template

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def landing():
    """Render the main landing page with section cards."""
    return render_template("landing.html")


@main_bp.route("/about")
def about():
    """Render the about page describing the system and modules."""
    return render_template("about.html")
