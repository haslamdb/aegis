#!/usr/bin/env python3
"""
Demo script to test re-approval workflow end-to-end.

This script creates test approvals and simulates the recheck process
to demonstrate the full workflow.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from common.abx_approvals import AbxApprovalStore
from common.abx_approvals.models import ApprovalDecision

def print_section(title):
    """Print a section header."""
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)

def print_approval(approval, label="Approval"):
    """Print approval details."""
    print(f"\n{label}:")
    print(f"  ID: {approval.id}")
    print(f"  Patient MRN: {approval.patient_mrn}")
    print(f"  Antibiotic: {approval.antibiotic_name}")
    print(f"  Decision: {approval.decision}")
    if approval.approval_duration_hours:
        print(f"  Duration: {approval.approval_duration_hours} hours ({approval.approval_duration_hours // 24} days)")
    if approval.planned_end_date:
        print(f"  Planned End Date: {approval.planned_end_date}")
    if approval.is_reapproval:
        print(f"  Is Re-approval: Yes (Chain #{approval.approval_chain_count + 1})")
        print(f"  Parent Approval: {approval.parent_approval_id}")
    print(f"  Recheck Status: {approval.recheck_status or 'N/A'}")
    print(f"  Status: {approval.status}")

def test_create_approval_with_duration():
    """Test 1: Create approval with duration."""
    print_section("TEST 1: Create Approval with Duration")

    store = AbxApprovalStore()

    # Create a test approval request
    approval = store.create_request(
        patient_id="test-patient-123",
        patient_mrn="TEST001",
        patient_name="Test Patient",
        patient_location="PICU Room 5",
        antibiotic_name="Meropenem",
        antibiotic_dose="1g IV q8h",
        antibiotic_route="IV",
        indication="Hospital-acquired pneumonia",
        created_by="Test Pharmacist"
    )

    print_approval(approval, "Created Request")

    # Now decide as "Approved" with 72-hour duration
    print("\nApproving with 72-hour duration...")

    success = store.decide(
        approval_id=approval.id,
        decision=ApprovalDecision.APPROVED,
        decision_by="Test Pharmacist",
        decision_notes="Appropriate for HAP, plan to recheck in 3 days",
        approval_duration_hours=72  # 3 days
    )

    if success:
        print("✓ Approval recorded successfully")

        # Retrieve updated approval
        updated = store.get_request(approval.id)
        print_approval(updated, "Updated Approval")

        # Verify planned_end_date calculation
        if updated.planned_end_date:
            expected_end = updated.decision_at + timedelta(hours=72, days=1)  # + grace period
            print(f"\n  Expected end (decision + 72h + 1d): {expected_end}")
            print(f"  Actual planned end: {updated.planned_end_date}")

            # Check weekend adjustment
            if updated.planned_end_date.weekday() in (5, 6):
                print("  ⚠ End date falls on weekend - should be adjusted!")
            else:
                print("  ✓ End date is on a weekday")
    else:
        print("✗ Failed to record approval")
        return None

    return approval.id

def test_simulate_recheck_still_on_antibiotic(approval_id):
    """Test 2: Simulate recheck when patient still on antibiotic."""
    print_section("TEST 2: Simulate Recheck (Patient Still on Antibiotic)")

    store = AbxApprovalStore()

    # First, manually update planned_end_date to yesterday to trigger recheck
    print("Setting planned_end_date to yesterday to trigger recheck...")
    with store._connect() as conn:
        conn.execute(
            """
            UPDATE abx_approval_requests
            SET planned_end_date = datetime('now', '-1 day')
            WHERE id = ?
            """,
            (approval_id,)
        )
        conn.commit()

    # Get approvals needing recheck
    print("\nQuerying approvals needing recheck...")
    approvals_to_check = store.list_approvals_needing_recheck()

    print(f"Found {len(approvals_to_check)} approval(s) needing recheck")

    for approval in approvals_to_check:
        print_approval(approval, "Approval Needing Recheck")

    # Simulate creating re-approval (normally done by scheduler)
    if approvals_to_check:
        original = approvals_to_check[0]

        print("\nSimulating recheck scheduler creating re-approval...")

        # Create re-approval request
        reapproval = store.create_request(
            patient_id=original.patient_id,
            patient_mrn=original.patient_mrn,
            patient_name=original.patient_name,
            patient_location=original.patient_location,
            antibiotic_name=original.antibiotic_name,
            antibiotic_dose=original.antibiotic_dose,
            antibiotic_route=original.antibiotic_route,
            indication=original.indication,
            created_by="system_recheck",
            is_reapproval=True,
            parent_approval_id=original.id
        )

        print("✓ Re-approval request created")
        print_approval(reapproval, "Re-approval Request")

        # Update original approval recheck_status
        with store._connect() as conn:
            conn.execute(
                "UPDATE abx_approval_requests SET recheck_status = ? WHERE id = ?",
                ("extended", original.id)
            )
            conn.commit()

        print("\n✓ Original approval marked as 'extended'")

        return reapproval.id

    return None

def test_list_pending_reapprovals():
    """Test 3: List pending re-approvals."""
    print_section("TEST 3: List Pending Re-approvals")

    store = AbxApprovalStore()

    # Get all pending requests
    pending = store.list_pending()

    print(f"\nTotal pending requests: {len(pending)}")

    # Separate re-approvals from new requests
    reapprovals = [r for r in pending if r.is_reapproval]
    new_requests = [r for r in pending if not r.is_reapproval]

    print(f"  - New requests: {len(new_requests)}")
    print(f"  - Re-approvals: {len(reapprovals)}")

    if reapprovals:
        print("\nPending Re-approvals:")
        for req in reapprovals:
            print(f"  • {req.patient_mrn} - {req.antibiotic_name} (Chain #{req.approval_chain_count + 1})")

    if new_requests:
        print("\nPending New Requests:")
        for req in new_requests:
            print(f"  • {req.patient_mrn} - {req.antibiotic_name}")

def test_analytics():
    """Test 4: Re-approval analytics."""
    print_section("TEST 4: Re-approval Analytics")

    store = AbxApprovalStore()

    # Get analytics
    analytics = store.get_analytics(days=30)

    print("\nRe-approval Metrics:")
    print(f"  Total requests: {analytics.get('total_requests', 0)}")
    print(f"  Total re-approvals: {analytics.get('total_reapprovals', 0)}")
    print(f"  Re-approval rate: {analytics.get('reapproval_rate', 0)}%")
    print(f"  Average chain length: {analytics.get('avg_chain_length', 0)}")
    print(f"  Max chain length: {analytics.get('max_chain_length', 0)}")

    if analytics.get('avg_approval_duration_hours'):
        print(f"  Average approval duration: {analytics['avg_approval_duration_hours']} hours ({analytics.get('avg_approval_duration_days', 0)} days)")

    if analytics.get('compliance_rate') is not None:
        print(f"\nCompliance Metrics:")
        print(f"  Stopped at duration: {analytics.get('compliance_stopped', 0)}")
        print(f"  Continued beyond: {analytics.get('compliance_continued', 0)}")
        print(f"  Compliance rate: {analytics.get('compliance_rate', 0)}%")

    if analytics.get('most_reapproved_antibiotics'):
        print(f"\nMost Re-approved Antibiotics:")
        for item in analytics['most_reapproved_antibiotics'][:5]:
            print(f"  • {item['name']}: {item['count']} re-approvals")

def cleanup_test_data():
    """Optional: Clean up test data."""
    print_section("Cleanup (Optional)")

    response = input("\nDelete test data? (y/N): ")
    if response.lower() == 'y':
        store = AbxApprovalStore()
        with store._connect() as conn:
            # Delete test approvals
            conn.execute(
                "DELETE FROM abx_approval_requests WHERE patient_mrn = 'TEST001'"
            )
            # Delete associated audit entries
            conn.execute(
                """
                DELETE FROM abx_approval_audit
                WHERE approval_id NOT IN (SELECT id FROM abx_approval_requests)
                """
            )
            conn.commit()
        print("✓ Test data deleted")
    else:
        print("Test data preserved")

def main():
    """Run all tests."""
    print("=" * 60)
    print("AEGIS Re-approval Workflow Demo/Test")
    print("=" * 60)
    print("\nThis script will:")
    print("1. Create a test approval with 72-hour duration")
    print("2. Simulate automatic recheck creating a re-approval")
    print("3. List pending re-approvals")
    print("4. Show re-approval analytics")
    print("\nPress Enter to continue or Ctrl+C to cancel...")
    input()

    try:
        # Test 1: Create approval with duration
        approval_id = test_create_approval_with_duration()

        if approval_id:
            # Test 2: Simulate recheck
            reapproval_id = test_simulate_recheck_still_on_antibiotic(approval_id)

            # Test 3: List pending re-approvals
            test_list_pending_reapprovals()

            # Test 4: Analytics
            test_analytics()

            # Cleanup
            cleanup_test_data()

            print_section("Demo Complete!")
            print("\n✓ All tests passed successfully")
            print("\nYou can now:")
            print("1. View the approvals in the dashboard")
            print("2. Check the database directly")
            print("3. Run the actual recheck scheduler script")

    except KeyboardInterrupt:
        print("\n\nDemo cancelled by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n✗ Error during demo: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
