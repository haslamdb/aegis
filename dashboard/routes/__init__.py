"""Dashboard routes."""

from .main import main_bp
from .views import asp_alerts_bp
from .api import api_bp
from .hai import hai_detection_bp
from .au_ar import nhsn_reporting_bp
from .dashboards import dashboards_bp
from .abx_indications import abx_indications_bp
from .guideline_adherence import guideline_adherence_bp
from .surgical_prophylaxis import surgical_prophylaxis_bp

__all__ = [
    "main_bp",
    "asp_alerts_bp",
    "api_bp",
    "hai_detection_bp",
    "nhsn_reporting_bp",
    "dashboards_bp",
    "abx_indications_bp",
    "guideline_adherence_bp",
    "surgical_prophylaxis_bp",
]
