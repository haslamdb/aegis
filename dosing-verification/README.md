# Dosing Verification Module

Real-time antimicrobial dosing verification with allergy checking, drug-drug interaction detection, and indication-based dosing rules.

## Features

- **Critical Route Verification**: Alerts for IV vancomycin for C. difficile, daptomycin for pneumonia, etc.
- **Allergy Checking**: Direct contraindications + cross-reactivity (penicillin→cephalosporin)
- **Drug-Drug Interactions**: Linezolid + SSRIs, rifampin interactions, etc.
- **Indication-Based Dosing**: Meningitis, endocarditis, CDI dosing rules
- **Tiered Alerting**:
  - **CRITICAL**: Teams + Email (wrong route, severe allergy, dangerous DDI)
  - **HIGH**: Email + Dashboard (subtherapeutic dosing, no renal adjustment)
  - **MODERATE**: Dashboard only (duration optimization, extended infusion candidates)

## Quick Start

### 1. Generate Demo Patients

```bash
# Create patient with C. difficile on IV vancomycin (CRITICAL - wrong route)
python scripts/demo_dosing.py --scenario cdi-iv-vanc

# Create patient with penicillin allergy on cephalosporin (CRITICAL - cross-reactivity)
python scripts/demo_dosing.py --scenario pcn-allergy-cephalosporin

# Create patient with meningitis on low-dose ceftriaxone (CRITICAL - underdosing)
python scripts/demo_dosing.py --scenario meningitis-low-dose

# Create patient with linezolid + SSRI (CRITICAL - DDI risk)
python scripts/demo_dosing.py --scenario linezolid-ssri

# Create patient with meropenem + valproic acid (CRITICAL - DDI reduces VPA levels)
python scripts/demo_dosing.py --scenario meropenem-valproic

# List all scenarios
python scripts/demo_dosing.py --list

# Run all critical scenarios
python scripts/demo_dosing.py --all-critical
```

### 2. Run the Monitor

```bash
cd dosing-verification

# Single scan
python -m src.runner --once

# Continuous monitoring (every 15 minutes)
python -m src.runner --continuous

# Custom interval (every 30 minutes)
python -m src.runner --continuous --interval 30

# Check specific patient
python -m src.runner --patient MRN12345

# Dry run (no notifications)
python -m src.runner --once --dry-run
```

### 3. View Alerts

Visit the dashboard:
- **Active Alerts**: https://aegis-asp.com/dosing-verification/active
- **Alert Detail**: Click any alert to see full clinical context and resolution workflow
- **History**: https://aegis-asp.com/dosing-verification/history
- **Analytics**: https://aegis-asp.com/dosing-verification/reports

## Real-Time Alerting

### Notification Tiers

**CRITICAL Alerts** (Teams + Email):
- Wrong route (IV vancomycin for CDI, nitrofurantoin for bacteremia)
- Direct allergy match (patient allergic to exact drug ordered)
- Severe cross-reactivity (penicillin anaphylaxis + cephalosporin)
- Dangerous DDI (linezolid + SSRI serotonin syndrome risk)
- Contraindicated drugs (daptomycin for pneumonia)
- Critical underdosing (meningitis at standard dose instead of CNS dose)

**HIGH Alerts** (Email + Dashboard):
- Subtherapeutic dosing for severe infections
- No renal adjustment with impaired kidney function
- Moderate cross-reactivity (penicillin rash + cephalosporin)

**MODERATE Alerts** (Dashboard Only):
- Duration optimization opportunities
- Extended infusion candidates
- Minor dosing adjustments

### Setting Up Notifications

Configure in `.env`:

```env
# Email
SMTP_SERVER=smtp.example.com
SMTP_FROM=aegis@example.com
ASP_TEAM_EMAIL=asp-team@example.com

# Teams
TEAMS_WEBHOOK_URL=https://outlook.office.com/webhook/...

# Monitor Settings
MONITOR_INTERVAL_MINUTES=15
AUTO_ACCEPT_HOURS=72
```

### Cron Setup (Production)

```cron
# Run every 15 minutes
*/15 * * * * /home/aegis/venv/bin/python /home/aegis/dosing-verification/src/runner.py --once --lookback 24 >> /var/log/aegis/dosing-monitor.log 2>&1
```

## Dashboard Workflows

### ASP Review Workflow

1. **Alert appears** in dashboard (CRITICAL/HIGH also in ASP Alerts queue)
2. **Pharmacist reviews** - sees patient context, current vs expected dosing, guideline source
3. **Resolution options**:
   - Dose Adjusted
   - Interval Adjusted
   - Route Changed
   - Therapy Changed
   - Therapy Stopped
   - Discussed with Team
   - Clinical Justification (dose intentional, document reason)
   - Messaged Team
   - Escalated to Attending
   - No Action Needed
4. **Audit trail** tracks all actions with timestamps

### Integration with ASP Alerts

CRITICAL and HIGH alerts also appear in the main ASP Alerts queue (`/asp-alerts/active`) for centralized pharmacist review alongside:
- Bacteremia alerts
- Drug-bug mismatches
- HAI detections
- Guideline deviations

## Rules Engine

### Current Rules (Phase 1)

**RouteRules**:
- IV vancomycin for C. difficile → CRITICAL
- Daptomycin for pneumonia → CRITICAL
- Nitrofurantoin for bacteremia/pyelonephritis → CRITICAL

**AllergyRules**:
- Direct contraindication (exact drug match) → CRITICAL
- Penicillin → Cephalosporin (~1-3% cross-reactivity, higher for R1 side chain match)
- Penicillin → Carbapenem (~1%)
- Aztreonam safe for beta-lactam allergies (0%)
- Within-class: aminoglycosides, fluoroquinolones, macrolides

**IndicationRules**:
- Meningitis: Ceftriaxone 100 mg/kg/day, Vancomycin 60 mg/kg/day
- Endocarditis: Daptomycin 8-10 mg/kg (not 4-6 mg/kg)
- C. difficile: PO vancomycin 125 mg q6h (not IV)

### Upcoming Rules (Phase 2/3)

- Renal adjustment (meropenem, cefepime, vancomycin based on GFR)
- Weight-based dosing (obesity, pediatric calculations)
- Age-based dosing (neonatal vs pediatric vs adult)
- DDI rules (linezolid, rifampin, voriconazole, fluoroquinolones)
- Duration rules (flag short/long courses)
- Extended infusion candidates (pip-tazo, meropenem)

## Data Requirements

From FHIR:
- **Patient**: Demographics, age, weight, height
- **MedicationRequest**: Active antimicrobials with dose, interval, route
- **AllergyIntolerance**: Documented allergies with severity
- **Observation**: SCr, eGFR, vital signs
- **Condition**: ICD-10 diagnoses for indication
- **DocumentReference** (future): Clinical notes for LLM indication extraction

From ABX Indications Module:
- Clinical indication (extracted via LLM from notes)
- Indication confidence level

## Architecture

```
FHIR Server → DosingFHIRClient → PatientContext → DosingRulesEngine
                                                         ↓
                                                    Assessment
                                                         ↓
                                        ┌────────────────┴────────────────┐
                                        ↓                                 ↓
                                  DoseAlertStore                    AlertStore
                                  (Module-specific)                 (Cross-module)
                                        ↓                                 ↓
                                  Dashboard                         ASP Alerts Queue
                                        ↓
                        ┌───────────────┼───────────────┐
                        ↓               ↓               ↓
                    Critical          High          Moderate
                  Teams + Email     Email Only    Dashboard Only
```

## Files

### Backend
- `src/models.py` - PatientContext, MedicationOrder
- `src/rules_engine.py` - DosingRulesEngine, BaseRuleModule
- `src/rules/allergy_rules.py` - Allergy checking and cross-reactivity
- `src/rules/route_rules.py` - Critical route mismatches
- `src/rules/indication_rules.py` - Indication-specific dosing
- `src/fhir_client.py` - FHIR data fetching
- `src/monitor.py` - Real-time monitoring with alerting
- `src/runner.py` - CLI entry point

### Data Store
- `common/dosing_verification/models.py` - Enums, DoseFlag, DoseAlertRecord
- `common/dosing_verification/store.py` - DoseAlertStore with MetricsStore integration
- `common/dosing_verification/schema.sql` - SQLite schema

### Dashboard
- `dashboard/routes/dosing_verification.py` - Routes + API + CSV export
- `dashboard/templates/dosing_*.html` - 5 harmonized templates

### Demo/Testing
- `scripts/demo_dosing.py` - Generate demo patients with dosing issues

## Testing

```bash
# 1. Generate demo patients
python scripts/demo_dosing.py --all-critical

# 2. Run monitor once
cd dosing-verification
python -m src.runner --once --verbose

# 3. Check dashboard
open https://aegis-asp.com/dosing-verification/active

# 4. Review alerts and resolve
```

## Contributing

When adding new rules:

1. Add to appropriate rule module (allergy_rules.py, indication_rules.py, etc.)
2. Add flag type to DoseFlagType enum if needed
3. Add test scenario to demo_dosing.py
4. Update HARMONIZATION_AUDIT.md if adding new patterns
5. Document guideline source in rule definition

## References

- AAAAI Practice Parameter Update 2010 (allergy cross-reactivity)
- IDSA Meningitis Guidelines 2024
- IDSA/SHEA CDI Guidelines 2021
- IDSA MRSA Guidelines
- AHA Endocarditis Guidelines 2015
