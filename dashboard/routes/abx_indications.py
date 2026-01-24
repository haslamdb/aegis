"""Routes for Antibiotic Indications module.

This module provides ICD-10 based antibiotic appropriateness classification
following Chua et al. methodology with pediatric inpatient modifications.
"""

from flask import Blueprint, render_template

abx_indications_bp = Blueprint(
    "abx_indications", __name__, url_prefix="/abx-indications"
)


@abx_indications_bp.route("/")
def dashboard():
    """Render the Antibiotic Indications dashboard."""
    return render_template("abx_indications_dashboard.html")


@abx_indications_bp.route("/help")
def help_page():
    """Render the help page for Antibiotic Indications."""
    return render_template("abx_indications_help.html")
