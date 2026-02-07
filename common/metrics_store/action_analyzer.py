"""Query aggregation layer for ASP/IP Action Analytics.

Provides methods to query and aggregate data from existing tables
(provider_activity, provider_sessions, metrics_daily_snapshot) and
module-specific stores (AbxApprovalStore) for the Action Analytics dashboard.
"""

import json
import logging
import os
import sqlite3
from datetime import date, datetime, timedelta
from typing import Any

from .models import ActivityType, ModuleSource
from .store import MetricsStore

logger = logging.getLogger(__name__)

# Human-readable module names
MODULE_DISPLAY_NAMES = {
    "hai": "HAI Detection",
    "asp_alerts": "ASP Alerts",
    "guideline_adherence": "Guideline Adherence",
    "abx_indications": "Antibiotic Indications",
    "drug_bug": "Drug-Bug Mismatch",
    "surgical_prophylaxis": "Surgical Prophylaxis",
    "abx_approvals": "ABX Approvals",
    "mdro_surveillance": "MDRO Surveillance",
    "outbreak_detection": "Outbreak Detection",
    "nhsn_reporting": "NHSN Reporting",
}

# Human-readable activity type names
ACTIVITY_TYPE_DISPLAY = {
    "review": "Review",
    "acknowledgment": "Acknowledgment",
    "resolution": "Resolution",
    "intervention": "Intervention",
    "education": "Education",
    "override": "Override",
}


class ActionAnalyzer:
    """Query aggregation layer over existing MetricsStore data.

    All methods are read-only queries against existing tables.
    No new data collection or schema changes required.
    """

    def __init__(self, metrics_store: MetricsStore | None = None):
        self.store = metrics_store or MetricsStore()

    def _connect(self) -> sqlite3.Connection:
        """Get database connection."""
        conn = sqlite3.connect(self.store.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # =========================================================================
    # Phase 1: Core Dashboard
    # =========================================================================

    def get_action_summary(self, days: int = 30) -> dict[str, Any]:
        """Get high-level action summary for stat cards.

        Returns:
            Dict with total_actions, unique_reviewers, avg_per_day,
            total_time_minutes, total_interventions, total_reviews
        """
        cutoff = (date.today() - timedelta(days=days)).isoformat()

        with self._connect() as conn:
            # Total actions + unique providers
            row = conn.execute(
                """
                SELECT
                    COUNT(*) as total_actions,
                    COUNT(DISTINCT provider_id) as unique_reviewers,
                    COUNT(DISTINCT date(performed_at)) as active_days,
                    SUM(COALESCE(duration_minutes, 0)) as total_minutes,
                    SUM(CASE WHEN activity_type = 'intervention' THEN 1 ELSE 0 END) as total_interventions,
                    SUM(CASE WHEN activity_type IN ('review', 'acknowledgment', 'resolution') THEN 1 ELSE 0 END) as total_reviews
                FROM provider_activity
                WHERE date(performed_at) >= ?
                """,
                (cutoff,)
            ).fetchone()

            total = row["total_actions"] or 0
            active_days = row["active_days"] or 1

            return {
                "total_actions": total,
                "unique_reviewers": row["unique_reviewers"] or 0,
                "active_days": active_days,
                "avg_per_day": round(total / max(active_days, 1), 1),
                "total_time_minutes": row["total_minutes"] or 0,
                "total_time_hours": round((row["total_minutes"] or 0) / 60, 1),
                "total_interventions": row["total_interventions"] or 0,
                "total_reviews": row["total_reviews"] or 0,
                "period_days": days,
            }

    def get_module_breakdown(self, days: int = 30) -> list[dict]:
        """Get action counts per module with display names.

        Returns:
            List of dicts with module, display_name, count, percentage
        """
        cutoff = (date.today() - timedelta(days=days)).isoformat()

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT module, COUNT(*) as count
                FROM provider_activity
                WHERE date(performed_at) >= ?
                GROUP BY module
                ORDER BY count DESC
                """,
                (cutoff,)
            ).fetchall()

            total = sum(r["count"] for r in rows) or 1
            return [
                {
                    "module": r["module"],
                    "display_name": MODULE_DISPLAY_NAMES.get(r["module"], r["module"]),
                    "count": r["count"],
                    "percentage": round(r["count"] / total * 100, 1),
                }
                for r in rows
            ]

    def get_activity_type_breakdown(self, days: int = 30) -> list[dict]:
        """Get counts by activity type.

        Returns:
            List of dicts with activity_type, display_name, count, percentage
        """
        cutoff = (date.today() - timedelta(days=days)).isoformat()

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT activity_type, COUNT(*) as count
                FROM provider_activity
                WHERE date(performed_at) >= ?
                GROUP BY activity_type
                ORDER BY count DESC
                """,
                (cutoff,)
            ).fetchall()

            total = sum(r["count"] for r in rows) or 1
            return [
                {
                    "activity_type": r["activity_type"],
                    "display_name": ACTIVITY_TYPE_DISPLAY.get(r["activity_type"], r["activity_type"]),
                    "count": r["count"],
                    "percentage": round(r["count"] / total * 100, 1),
                }
                for r in rows
            ]

    def get_daily_action_trends(self, days: int = 30) -> list[dict]:
        """Get daily action counts from metrics_daily_snapshot and provider_activity.

        Returns:
            List of dicts with date, total_actions, reviews, interventions
        """
        cutoff = (date.today() - timedelta(days=days)).isoformat()

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    date(performed_at) as day,
                    COUNT(*) as total_actions,
                    SUM(CASE WHEN activity_type IN ('review', 'acknowledgment', 'resolution') THEN 1 ELSE 0 END) as reviews,
                    SUM(CASE WHEN activity_type = 'intervention' THEN 1 ELSE 0 END) as interventions
                FROM provider_activity
                WHERE date(performed_at) >= ?
                GROUP BY date(performed_at)
                ORDER BY day ASC
                """,
                (cutoff,)
            ).fetchall()

            return [
                {
                    "date": r["day"],
                    "total_actions": r["total_actions"],
                    "reviews": r["reviews"],
                    "interventions": r["interventions"],
                }
                for r in rows
            ]

    def get_recent_actions(self, limit: int = 25) -> list[dict]:
        """Get most recent provider_activity rows with module/type info.

        Returns:
            List of dicts with action details and drill-down info
        """
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    id, provider_id, provider_name, provider_role,
                    activity_type, module, entity_id, entity_type,
                    action_taken, outcome, patient_mrn, location_code,
                    service, duration_minutes, performed_at, details
                FROM provider_activity
                ORDER BY performed_at DESC
                LIMIT ?
                """,
                (limit,)
            ).fetchall()

            results = []
            for r in rows:
                details = {}
                if r["details"]:
                    try:
                        details = json.loads(r["details"])
                    except (json.JSONDecodeError, TypeError):
                        pass

                results.append({
                    "id": r["id"],
                    "provider_name": r["provider_name"] or r["provider_id"] or "Unknown",
                    "provider_role": r["provider_role"],
                    "activity_type": r["activity_type"],
                    "activity_display": ACTIVITY_TYPE_DISPLAY.get(r["activity_type"], r["activity_type"]),
                    "module": r["module"],
                    "module_display": MODULE_DISPLAY_NAMES.get(r["module"], r["module"]),
                    "entity_id": r["entity_id"],
                    "entity_type": r["entity_type"],
                    "action_taken": r["action_taken"],
                    "outcome": r["outcome"],
                    "patient_mrn": r["patient_mrn"],
                    "location_code": r["location_code"],
                    "service": r["service"],
                    "duration_minutes": r["duration_minutes"],
                    "performed_at": r["performed_at"],
                    "details": details,
                })
            return results

    # =========================================================================
    # Phase 2: Recommendations, Approvals, Therapy Changes
    # =========================================================================

    def get_recommendation_breakdown(self, days: int = 30) -> dict[str, Any]:
        """Parse action_taken + details from provider_activity for recommendation types.

        Identifies de-escalation, escalation, discontinuation, IV-to-PO,
        duration optimization recommendations.

        Returns:
            Dict with by_type list, total, acceptance_rate, trends
        """
        cutoff = (date.today() - timedelta(days=days)).isoformat()

        # Recommendation type keywords
        rec_patterns = {
            "de-escalation": ["de-escalat", "narrow", "step-down", "step down"],
            "escalation": ["escalat", "broaden", "upgrade"],
            "discontinuation": ["discontinu", "stop", "d/c"],
            "iv-to-po": ["iv to po", "iv-to-po", "iv to oral", "oral switch", "po conversion"],
            "duration": ["duration", "shorten", "extend duration", "day course"],
        }

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT action_taken, outcome, details, module
                FROM provider_activity
                WHERE date(performed_at) >= ?
                  AND action_taken IS NOT NULL
                """,
                (cutoff,)
            ).fetchall()

        by_type: dict[str, dict] = {}
        for key in rec_patterns:
            by_type[key] = {"count": 0, "accepted": 0, "display_name": key.replace("-", " ").title()}

        for r in rows:
            action = (r["action_taken"] or "").lower()
            outcome = (r["outcome"] or "").lower()
            details_str = r["details"] or ""

            # Try to parse details JSON for recommendation_type
            details = {}
            if details_str:
                try:
                    details = json.loads(details_str)
                except (json.JSONDecodeError, TypeError):
                    pass

            rec_type = details.get("recommendation_type", "").lower()
            combined = f"{action} {outcome} {rec_type} {details_str.lower()}"

            for key, patterns in rec_patterns.items():
                if any(p in combined for p in patterns):
                    by_type[key]["count"] += 1
                    if any(w in outcome for w in ("accepted", "changed", "implemented", "completed")):
                        by_type[key]["accepted"] += 1
                    break

        result_list = []
        total = 0
        total_accepted = 0
        for key, data in by_type.items():
            if data["count"] > 0:
                acceptance = round(data["accepted"] / data["count"] * 100, 1)
            else:
                acceptance = 0
            total += data["count"]
            total_accepted += data["accepted"]
            result_list.append({
                "type": key,
                "display_name": data["display_name"],
                "count": data["count"],
                "accepted": data["accepted"],
                "acceptance_rate": acceptance,
            })

        result_list.sort(key=lambda x: x["count"], reverse=True)

        return {
            "by_type": result_list,
            "total": total,
            "total_accepted": total_accepted,
            "overall_acceptance_rate": round(total_accepted / max(total, 1) * 100, 1),
        }

    def get_approval_metrics(self, days: int = 30) -> dict[str, Any]:
        """Query AbxApprovalStore for approval analytics.

        Returns:
            Dict with approval_rate, by_antibiotic, response_times,
            denial_reasons, decision_breakdown
        """
        try:
            from common.abx_approvals.store import AbxApprovalStore
            store = AbxApprovalStore()
            analytics = store.get_analytics(days=days)

            return {
                "total_requests": analytics.get("total_requests", 0),
                "approval_rate": analytics.get("approval_rate"),
                "decision_breakdown": analytics.get("decision_breakdown", []),
                "top_antibiotics": analytics.get("top_antibiotics", []),
                "response_times": analytics.get("response_times", {}),
                "avg_requests_per_day": analytics.get("avg_requests_per_day"),
                "reapproval_rate": analytics.get("reapproval_rate"),
                "total_reapprovals": analytics.get("total_reapprovals", 0),
                "avg_approval_duration_hours": analytics.get("avg_approval_duration_hours"),
                "compliance_rate": analytics.get("compliance_rate"),
                "by_day_of_week": analytics.get("by_day_of_week", []),
                "available": True,
            }
        except Exception as e:
            logger.warning(f"Could not load approval metrics: {e}")
            return {"available": False, "error": str(e)}

    def get_therapy_change_metrics(self, days: int = 30) -> dict[str, Any]:
        """Filter provider_activity for therapy change outcomes.

        Returns:
            Dict with total_suggestions, total_changes, change_rate,
            by_module, by_unit
        """
        cutoff = (date.today() - timedelta(days=days)).isoformat()

        change_keywords = [
            "therapy_changed", "therapy_stopped", "changed", "de-escalated",
            "escalated", "switched", "discontinued", "narrowed",
        ]

        suggestion_types = ["review", "acknowledgment", "resolution", "intervention"]

        with self._connect() as conn:
            # Total suggestion-type activities
            row = conn.execute(
                """
                SELECT COUNT(*) as total
                FROM provider_activity
                WHERE date(performed_at) >= ?
                  AND activity_type IN ('review', 'acknowledgment', 'resolution', 'intervention')
                """,
                (cutoff,)
            ).fetchone()
            total_suggestions = row["total"] or 0

            # Activities with therapy change outcomes
            rows = conn.execute(
                """
                SELECT module, location_code, outcome, action_taken
                FROM provider_activity
                WHERE date(performed_at) >= ?
                  AND activity_type IN ('review', 'acknowledgment', 'resolution', 'intervention')
                """,
                (cutoff,)
            ).fetchall()

        total_changes = 0
        by_module: dict[str, dict] = {}
        by_unit: dict[str, dict] = {}

        for r in rows:
            outcome = (r["outcome"] or "").lower()
            action = (r["action_taken"] or "").lower()
            combined = f"{outcome} {action}"
            is_change = any(kw in combined for kw in change_keywords)

            module = r["module"] or "unknown"
            unit = r["location_code"] or "Unknown"

            if module not in by_module:
                by_module[module] = {"suggestions": 0, "changes": 0}
            by_module[module]["suggestions"] += 1

            if unit not in by_unit:
                by_unit[unit] = {"suggestions": 0, "changes": 0}
            by_unit[unit]["suggestions"] += 1

            if is_change:
                total_changes += 1
                by_module[module]["changes"] += 1
                by_unit[unit]["changes"] += 1

        # Calculate rates
        by_module_list = []
        for mod, data in by_module.items():
            rate = round(data["changes"] / max(data["suggestions"], 1) * 100, 1)
            by_module_list.append({
                "module": mod,
                "display_name": MODULE_DISPLAY_NAMES.get(mod, mod),
                "suggestions": data["suggestions"],
                "changes": data["changes"],
                "change_rate": rate,
            })
        by_module_list.sort(key=lambda x: x["changes"], reverse=True)

        by_unit_list = []
        for unit, data in by_unit.items():
            rate = round(data["changes"] / max(data["suggestions"], 1) * 100, 1)
            by_unit_list.append({
                "unit": unit,
                "suggestions": data["suggestions"],
                "changes": data["changes"],
                "change_rate": rate,
            })
        by_unit_list.sort(key=lambda x: x["changes"], reverse=True)

        return {
            "total_suggestions": total_suggestions,
            "total_changes": total_changes,
            "overall_change_rate": round(total_changes / max(total_suggestions, 1) * 100, 1),
            "by_module": by_module_list,
            "by_unit": by_unit_list[:20],
        }

    # =========================================================================
    # Phase 3: Unit Analysis, Time Analysis
    # =========================================================================

    def get_unit_metrics(self, days: int = 30) -> list[dict]:
        """Aggregate provider_activity by location_code.

        Returns:
            List of dicts with unit, action_count, intervention_count,
            change_rate, unique_providers, avg_duration
        """
        cutoff = (date.today() - timedelta(days=days)).isoformat()

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    location_code,
                    COUNT(*) as action_count,
                    COUNT(DISTINCT provider_id) as unique_providers,
                    SUM(CASE WHEN activity_type = 'intervention' THEN 1 ELSE 0 END) as intervention_count,
                    SUM(CASE WHEN activity_type IN ('review', 'acknowledgment', 'resolution') THEN 1 ELSE 0 END) as review_count,
                    AVG(COALESCE(duration_minutes, 0)) as avg_duration
                FROM provider_activity
                WHERE date(performed_at) >= ?
                  AND location_code IS NOT NULL
                GROUP BY location_code
                ORDER BY action_count DESC
                """,
                (cutoff,)
            ).fetchall()

            return [
                {
                    "unit": r["location_code"],
                    "action_count": r["action_count"],
                    "unique_providers": r["unique_providers"],
                    "intervention_count": r["intervention_count"],
                    "review_count": r["review_count"],
                    "avg_duration": round(r["avg_duration"], 1) if r["avg_duration"] else 0,
                }
                for r in rows
            ]

    def get_service_metrics(self, days: int = 30) -> list[dict]:
        """Aggregate provider_activity by service field.

        Returns:
            List of dicts with service, action_count, unique_providers, etc.
        """
        cutoff = (date.today() - timedelta(days=days)).isoformat()

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    service,
                    COUNT(*) as action_count,
                    COUNT(DISTINCT provider_id) as unique_providers,
                    SUM(CASE WHEN activity_type = 'intervention' THEN 1 ELSE 0 END) as intervention_count,
                    SUM(CASE WHEN activity_type IN ('review', 'acknowledgment', 'resolution') THEN 1 ELSE 0 END) as review_count
                FROM provider_activity
                WHERE date(performed_at) >= ?
                  AND service IS NOT NULL
                GROUP BY service
                ORDER BY action_count DESC
                """,
                (cutoff,)
            ).fetchall()

            return [
                {
                    "service": r["service"],
                    "action_count": r["action_count"],
                    "unique_providers": r["unique_providers"],
                    "intervention_count": r["intervention_count"],
                    "review_count": r["review_count"],
                }
                for r in rows
            ]

    def get_time_analysis(self, days: int = 30) -> dict[str, Any]:
        """Duration aggregation from provider_activity + provider_sessions.

        Returns:
            Dict with by_module, by_activity_type, by_day, total_hours
        """
        cutoff = (date.today() - timedelta(days=days)).isoformat()

        with self._connect() as conn:
            # Time by module
            mod_rows = conn.execute(
                """
                SELECT module, SUM(COALESCE(duration_minutes, 0)) as total_minutes,
                       COUNT(*) as action_count
                FROM provider_activity
                WHERE date(performed_at) >= ? AND duration_minutes IS NOT NULL
                GROUP BY module
                ORDER BY total_minutes DESC
                """,
                (cutoff,)
            ).fetchall()

            by_module = [
                {
                    "module": r["module"],
                    "display_name": MODULE_DISPLAY_NAMES.get(r["module"], r["module"]),
                    "total_minutes": r["total_minutes"],
                    "total_hours": round(r["total_minutes"] / 60, 1),
                    "action_count": r["action_count"],
                    "avg_minutes": round(r["total_minutes"] / max(r["action_count"], 1), 1),
                }
                for r in mod_rows
            ]

            # Time by activity type
            type_rows = conn.execute(
                """
                SELECT activity_type, SUM(COALESCE(duration_minutes, 0)) as total_minutes,
                       COUNT(*) as action_count
                FROM provider_activity
                WHERE date(performed_at) >= ? AND duration_minutes IS NOT NULL
                GROUP BY activity_type
                ORDER BY total_minutes DESC
                """,
                (cutoff,)
            ).fetchall()

            by_activity_type = [
                {
                    "activity_type": r["activity_type"],
                    "display_name": ACTIVITY_TYPE_DISPLAY.get(r["activity_type"], r["activity_type"]),
                    "total_minutes": r["total_minutes"],
                    "total_hours": round(r["total_minutes"] / 60, 1),
                    "action_count": r["action_count"],
                    "avg_minutes": round(r["total_minutes"] / max(r["action_count"], 1), 1),
                }
                for r in type_rows
            ]

            # Session stats
            session_stats = self.store.get_session_stats(days=days)

            total_minutes = sum(r["total_minutes"] for r in mod_rows)

            return {
                "by_module": by_module,
                "by_activity_type": by_activity_type,
                "total_minutes": total_minutes,
                "total_hours": round(total_minutes / 60, 1),
                "session_stats": session_stats,
            }

    def get_provider_workload(self, days: int = 30) -> list[dict]:
        """Per-provider action counts, time, efficiency.

        Returns:
            List of dicts sorted by total_activities descending
        """
        return self.store.get_provider_workload(days=days)
