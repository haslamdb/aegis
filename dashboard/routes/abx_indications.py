"""Routes for Antibiotic Indications module.

This module provides ICD-10 based antibiotic appropriateness classification
following Chua et al. methodology with pediatric inpatient modifications.
"""

import logging
import sys
from pathlib import Path

from flask import Blueprint, render_template

logger = logging.getLogger(__name__)

# Lazy import to avoid src module conflicts
_indication_db_class = None


def _get_indication_db():
    """Get IndicationDatabase class with lazy import to avoid conflicts."""
    global _indication_db_class
    if _indication_db_class is None:
        # Add antimicrobial-usage-alerts to path
        _project_root = Path(__file__).parent.parent.parent
        _au_alerts_path = str(_project_root / "antimicrobial-usage-alerts")

        # Clear cached src modules to avoid conflicts
        modules_to_clear = [k for k in sys.modules if k.startswith('src.')]
        for mod in modules_to_clear:
            del sys.modules[mod]
        if 'src' in sys.modules:
            del sys.modules['src']

        # Add path and import
        if _au_alerts_path in sys.path:
            sys.path.remove(_au_alerts_path)
        sys.path.insert(0, _au_alerts_path)

        from src.indication_db import IndicationDatabase
        _indication_db_class = IndicationDatabase

    return _indication_db_class()

abx_indications_bp = Blueprint(
    "abx_indications", __name__, url_prefix="/abx-indications"
)


@abx_indications_bp.route("/")
def dashboard():
    """Render the Antibiotic Indications dashboard."""
    try:
        db = _get_indication_db()

        # Get counts by classification (last 7 days)
        counts = db.get_candidate_count_by_classification(days=7)

        # Get recent candidates for the table
        recent_candidates = db.list_candidates(limit=20)

        # Get override stats
        override_stats = db.get_override_stats(days=30)

    except Exception as e:
        logger.error(f"Error loading indication data: {e}")
        counts = {}
        recent_candidates = []
        override_stats = {}

    return render_template(
        "abx_indications_dashboard.html",
        counts=counts,
        recent_candidates=recent_candidates,
        override_stats=override_stats,
    )


@abx_indications_bp.route("/help")
def help_page():
    """Render the help page for Antibiotic Indications."""
    return render_template("abx_indications_help.html")
