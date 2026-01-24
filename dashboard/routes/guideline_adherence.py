"""Routes for Guideline Adherence module.

This module tracks adherence to evidence-based clinical guidelines/bundles
at the population level for quality improvement and JC reporting.
"""

from flask import Blueprint, render_template

guideline_adherence_bp = Blueprint(
    "guideline_adherence", __name__, url_prefix="/guideline-adherence"
)


@guideline_adherence_bp.route("/")
def dashboard():
    """Render the Guideline Adherence dashboard."""
    return render_template("guideline_adherence_dashboard.html")


@guideline_adherence_bp.route("/help")
def help_page():
    """Render the help page for Guideline Adherence."""
    return render_template("guideline_adherence_help.html")
