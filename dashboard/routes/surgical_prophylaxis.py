"""Routes for Surgical Prophylaxis module.

This module provides monitoring and validation of surgical antibiotic
prophylaxis following ASHP/IDSA/SHEA/SIS guidelines.
"""

from flask import Blueprint, render_template

surgical_prophylaxis_bp = Blueprint(
    "surgical_prophylaxis", __name__, url_prefix="/surgical-prophylaxis"
)


@surgical_prophylaxis_bp.route("/")
def dashboard():
    """Render the Surgical Prophylaxis dashboard."""
    return render_template("surgical_prophylaxis_dashboard.html")


@surgical_prophylaxis_bp.route("/help")
def help_page():
    """Render the help page for Surgical Prophylaxis."""
    return render_template("surgical_prophylaxis_help.html")
