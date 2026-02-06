#!/usr/bin/env python3
"""
Validation script for re-approval workflow setup.

This script validates that all components of the re-approval workflow
are correctly set up and configured.
"""

import sys
import os
from pathlib import Path
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def validate_database_schema():
    """Validate database schema has all required columns."""
    print("Validating database schema...")

    try:
        from common.abx_approvals import AbxApprovalStore

        store = AbxApprovalStore()

        # Try to query with new columns
        with store._connect() as conn:
            cursor = conn.execute(
                """
                SELECT approval_duration_hours, planned_end_date, is_reapproval,
                       parent_approval_id, approval_chain_count, recheck_status,
                       last_recheck_date
                FROM abx_approval_requests
                LIMIT 1
                """
            )

        print("✓ Database schema validated - all columns present")
        return True

    except Exception as e:
        print(f"✗ Database schema validation failed: {e}")
        print("  Run migration script: common/abx_approvals/migrate_add_duration_tracking.sql")
        return False


def validate_models():
    """Validate data models have new fields."""
    print("\nValidating data models...")

    try:
        from common.abx_approvals.models import ApprovalRequest, ApprovalDecision

        # Check ApprovalRequest has new fields
        required_fields = [
            'approval_duration_hours',
            'planned_end_date',
            'is_reapproval',
            'parent_approval_id',
            'approval_chain_count',
            'recheck_status',
            'last_recheck_date'
        ]

        sample = ApprovalRequest(
            id="test",
            patient_id="test",
            patient_mrn="test",
            antibiotic_name="test"
        )

        for field in required_fields:
            if not hasattr(sample, field):
                print(f"✗ Missing field: {field}")
                return False

        # Check ApprovalDecision has new types
        new_decisions = [
            'APPROVED',
            'SUGGESTED_ALTERNATE',
            'SUGGESTED_DISCONTINUE',
            'REQUESTED_ID_CONSULT',
            'NO_ACTION_NEEDED',
            'SPOKE_WITH_TEAM'
        ]

        for decision in new_decisions:
            if not hasattr(ApprovalDecision, decision):
                print(f"✗ Missing decision type: {decision}")
                return False

        print("✓ Data models validated")
        return True

    except Exception as e:
        print(f"✗ Model validation failed: {e}")
        return False


def validate_recheck_scheduler():
    """Validate recheck scheduler module exists and is importable."""
    print("\nValidating recheck scheduler...")

    try:
        from common.abx_approvals.recheck_scheduler import RecheckScheduler

        print("✓ Recheck scheduler module validated")
        return True

    except Exception as e:
        print(f"✗ Recheck scheduler validation failed: {e}")
        return False


def validate_store_methods():
    """Validate AbxApprovalStore has new methods."""
    print("\nValidating store methods...")

    try:
        from common.abx_approvals import AbxApprovalStore

        store = AbxApprovalStore()

        # Check for new methods
        required_methods = [
            'calculate_planned_end_date',
            'list_approvals_needing_recheck',
        ]

        for method in required_methods:
            if not hasattr(store, method):
                print(f"✗ Missing method: {method}")
                return False

        # Test calculate_planned_end_date
        now = datetime.now()
        end_date = store.calculate_planned_end_date(now, 72, grace_period_days=1)

        # Should be 72 hours + 1 day from now
        expected_min = now + timedelta(hours=72, days=1) - timedelta(minutes=1)
        expected_max = now + timedelta(hours=72, days=1) + timedelta(minutes=1)

        if not (expected_min <= end_date <= expected_max):
            print(f"✗ calculate_planned_end_date returned unexpected value: {end_date}")
            return False

        print("✓ Store methods validated")
        return True

    except Exception as e:
        print(f"✗ Store methods validation failed: {e}")
        return False


def validate_templates():
    """Validate template files exist."""
    print("\nValidating templates...")

    template_dir = Path(__file__).parent.parent / "dashboard" / "templates" / "abx_approvals"

    required_templates = [
        "dashboard.html",
        "approval_form.html",
        "approval_detail.html",
        "reports.html"
    ]

    all_exist = True
    for template in required_templates:
        template_path = template_dir / template
        if not template_path.exists():
            print(f"✗ Missing template: {template}")
            all_exist = False

    if all_exist:
        print("✓ Templates validated")
        return True
    else:
        return False


def validate_scripts():
    """Validate cron scripts exist."""
    print("\nValidating scripts...")

    scripts_dir = Path(__file__).parent.parent / "scripts"

    required_files = [
        "run_approval_recheck.py",
        "cron.d/aegis-recheck",
        "README-cron-setup.md"
    ]

    all_exist = True
    for script in required_files:
        script_path = scripts_dir / script
        if not script_path.exists():
            print(f"✗ Missing script: {script}")
            all_exist = False
        elif script.endswith('.py'):
            # Check if executable
            if not os.access(script_path, os.X_OK):
                print(f"⚠ Script not executable: {script}")
                print(f"  Run: chmod +x {script_path}")

    if all_exist:
        print("✓ Scripts validated")
        return True
    else:
        return False


def main():
    """Run all validations."""
    print("=" * 60)
    print("AEGIS Re-approval Workflow Validation")
    print("=" * 60)

    validations = [
        validate_database_schema,
        validate_models,
        validate_recheck_scheduler,
        validate_store_methods,
        validate_templates,
        validate_scripts,
    ]

    results = [v() for v in validations]

    print("\n" + "=" * 60)
    print("Validation Summary")
    print("=" * 60)

    passed = sum(results)
    total = len(results)

    print(f"Passed: {passed}/{total}")

    if passed == total:
        print("\n✓ All validations passed!")
        print("\nNext steps:")
        print("1. Run database migration if this is an existing database")
        print("2. Test manually with a test patient")
        print("3. Set up cron job (see scripts/README-cron-setup.md)")
        return 0
    else:
        print("\n✗ Some validations failed. Please fix the issues above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
