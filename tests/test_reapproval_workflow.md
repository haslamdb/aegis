# Re-approval Workflow Test Plan

## Overview

This document outlines the testing procedure for the antibiotic approval duration tracking and automatic re-approval workflow.

## Test Environment Setup

### Prerequisites
1. Running FHIR server with test patient data
2. ABX approvals database initialized
3. Email server configured (or mock email for testing)
4. Dashboard application running

### Test Data Requirements
- Test patient with active antibiotic order
- Test patient MRN: TBD
- Test antibiotic: Meropenem 1g IV q8h

## Test Scenarios

### Scenario 1: Basic Approval with Duration

**Objective:** Verify that approval with duration is recorded correctly

**Steps:**
1. Navigate to `/abx-approvals/new`
2. Search for test patient
3. Fill out approval form:
   - Antibiotic: Meropenem
   - Decision: Approved
   - Duration: 72 hours (3 days)
   - Reviewer: Test Pharmacist
4. Submit decision

**Expected Results:**
- ✓ Request created successfully
- ✓ `approval_duration_hours` = 72
- ✓ `planned_end_date` = approval date + 72 hours + 1 day grace period
- ✓ `recheck_status` = 'pending'
- ✓ Detail page shows "Planned End Date" and "Recheck Status"

**Validation SQL:**
```sql
SELECT id, antibiotic_name, approval_duration_hours,
       planned_end_date, recheck_status
FROM abx_approval_requests
WHERE patient_mrn = 'TEST_MRN'
ORDER BY created_at DESC LIMIT 1;
```

---

### Scenario 2: Custom Duration Input

**Objective:** Verify custom duration input works correctly

**Steps:**
1. Navigate to approval form
2. Select "Custom (enter days)" from duration dropdown
3. Enter 10 days
4. Submit decision as Approved

**Expected Results:**
- ✓ `approval_duration_hours` = 240 (10 * 24)
- ✓ `planned_end_date` calculated correctly

---

### Scenario 3: Weekend Handling

**Objective:** Verify weekend date adjustment works

**Steps:**
1. Create approval with duration that ends on Saturday
2. Check calculated `planned_end_date`

**Expected Results:**
- ✓ If end date falls on Saturday (day 5) or Sunday (day 6), planned_end_date is moved to Friday before

**Test SQL:**
```sql
-- Test the weekend calculation
SELECT
    approval_duration_hours,
    decision_at as approval_date,
    planned_end_date,
    strftime('%w', planned_end_date) as day_of_week
FROM abx_approval_requests
WHERE planned_end_date IS NOT NULL;
```

---

### Scenario 4: Automatic Recheck (Patient Still on Antibiotic)

**Objective:** Verify automatic re-approval creation when patient still on antibiotic

**Setup:**
1. Create approval with short duration (24 hours for testing)
2. Manually update `planned_end_date` to yesterday:
   ```sql
   UPDATE abx_approval_requests
   SET planned_end_date = datetime('now', '-1 day')
   WHERE id = 'TEST_ID';
   ```
3. Ensure patient still has active antibiotic order in FHIR

**Steps:**
1. Run recheck scheduler:
   ```bash
   python3 scripts/run_approval_recheck.py
   ```

**Expected Results:**
- ✓ Script logs "Still on antibiotic" for test approval
- ✓ New approval request created with:
  - `is_reapproval` = true
  - `parent_approval_id` = original approval ID
  - `approval_chain_count` = 1
  - Status = PENDING
- ✓ Original approval `recheck_status` updated to 'extended'
- ✓ Email notification sent
- ✓ Re-approval appears in dashboard "Pending Re-approval Requests" section

**Validation SQL:**
```sql
-- Check re-approval was created
SELECT * FROM abx_approval_requests
WHERE parent_approval_id = 'ORIGINAL_ID';

-- Check original approval status
SELECT recheck_status FROM abx_approval_requests
WHERE id = 'ORIGINAL_ID';
```

---

### Scenario 5: Automatic Recheck (Patient Discontinued)

**Objective:** Verify proper handling when patient no longer on antibiotic

**Setup:**
1. Create approval with short duration
2. Manually update `planned_end_date` to yesterday
3. Ensure patient does NOT have active antibiotic order in FHIR (discontinue in FHIR)

**Steps:**
1. Run recheck scheduler

**Expected Results:**
- ✓ Script logs "Discontinued" for test approval
- ✓ No new approval request created
- ✓ Original approval `recheck_status` updated to 'completed'
- ✓ No email notification sent

---

### Scenario 6: Re-approval Chain

**Objective:** Verify multiple sequential re-approvals are tracked correctly

**Steps:**
1. Create initial approval (chain count = 0)
2. Trigger recheck → creates 1st re-approval (chain count = 1)
3. Approve 1st re-approval with duration
4. Trigger recheck → creates 2nd re-approval (chain count = 2)
5. Approve 2nd re-approval

**Expected Results:**
- ✓ Each re-approval increments `approval_chain_count`
- ✓ Each re-approval links to previous via `parent_approval_id`
- ✓ Dashboard shows correct chain count badges:
  - "1st Re-approval"
  - "2nd Re-approval"
  - "3rd Re-approval"
- ✓ Detail page shows chain link to parent approval

---

### Scenario 7: Dashboard Display

**Objective:** Verify dashboard correctly separates new and re-approval requests

**Steps:**
1. Create mix of new approvals and re-approvals
2. Navigate to dashboard

**Expected Results:**
- ✓ "Pending Re-approval Requests" section shows only re-approvals
- ✓ "Pending New Requests" section shows only non-re-approvals
- ✓ Re-approval rows have yellow highlight
- ✓ Chain count badges display correctly
- ✓ Review button is yellow for re-approvals

---

### Scenario 8: Analytics & Reporting

**Objective:** Verify re-approval analytics are calculated correctly

**Steps:**
1. Navigate to `/abx-approvals/reports`
2. Review re-approval analytics section

**Expected Results:**
- ✓ Total re-approvals count is accurate
- ✓ Re-approval rate percentage calculated correctly
- ✓ Most re-approved antibiotics list is accurate
- ✓ Average chain length matches data
- ✓ Compliance rate shows stopped vs continued breakdown
- ✓ Average approval duration is accurate

**Validation SQL:**
```sql
-- Manual calculation for validation
SELECT
    COUNT(CASE WHEN is_reapproval = 1 THEN 1 END) as reapprovals,
    COUNT(*) as total,
    ROUND(COUNT(CASE WHEN is_reapproval = 1 THEN 1 END) * 100.0 / COUNT(*), 1) as reapproval_rate
FROM abx_approval_requests
WHERE created_at >= datetime('now', '-30 days');
```

---

### Scenario 9: Decision Types

**Objective:** Verify all new decision types work correctly

**Steps:**
1. Test each decision type:
   - Approved (with duration)
   - Suggested Alternate (with alternate antibiotic)
   - Suggested Discontinue
   - Requested ID Consult
   - Deferred
   - No Action Needed
   - Spoke with Team

**Expected Results:**
- ✓ Each decision type saves correctly
- ✓ Appropriate fields shown/hidden based on decision
- ✓ Badges display with correct colors
- ✓ Audit log records correct decision

---

### Scenario 10: Email Notifications

**Objective:** Verify email notifications for re-approvals

**Expected Email Content:**
- Subject: "ABX Re-approval Request: [Patient Name] - [Antibiotic]"
- Body includes:
  - Patient name and MRN
  - Location
  - Antibiotic details
  - Original approval date and reviewer
  - Previous duration
  - Re-approval number
  - Link to review request

---

## Regression Testing

### Backward Compatibility
- ✓ Existing approvals (without duration) still display correctly
- ✓ Old decision types (changed_therapy, denied) still work
- ✓ Existing queries and reports don't break

### Database Migration
- ✓ Migration script runs without errors
- ✓ New columns are nullable and have appropriate defaults
- ✓ Indexes are created correctly

---

## Performance Testing

### Load Testing
1. Create 1000 approval requests
2. Run recheck scheduler
3. Measure execution time

**Acceptance Criteria:**
- Recheck job completes in < 5 minutes for 1000 approvals
- No database locks or timeouts
- Memory usage stays reasonable

---

## Error Handling

### Test Error Scenarios

1. **FHIR Server Unavailable**
   - Expected: Log warning, skip recheck, continue with next approval

2. **Email Server Unavailable**
   - Expected: Log warning, continue without sending email

3. **Database Connection Lost**
   - Expected: Fail gracefully with error message

4. **Invalid Duration Input**
   - Expected: Form validation prevents submission

---

## Checklist Summary

- [ ] Basic approval with duration works
- [ ] Custom duration input works
- [ ] Weekend handling works correctly
- [ ] Recheck creates re-approval when patient still on antibiotic
- [ ] Recheck marks completed when patient discontinued
- [ ] Re-approval chains track correctly
- [ ] Dashboard separates new vs re-approvals correctly
- [ ] Analytics calculate correctly
- [ ] All decision types work
- [ ] Email notifications send correctly
- [ ] Backward compatibility maintained
- [ ] Database migration successful
- [ ] Performance acceptable
- [ ] Error handling works
- [ ] Cron job runs successfully

---

## Sign-off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Developer | | | |
| QA Tester | | | |
| Pharmacist (UAT) | | | |
| Project Lead | | | |
