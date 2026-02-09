# AEGIS Django Migration - Project Status

**Last Updated:** 2026-02-08
**Phase:** 3 - Module Migration (continued)
**Priority:** Active Development

## Current Status

Django migration is in progress. Foundation (Phase 1) is complete and audited. Ten modules have been migrated:

1. **Action Analytics** - Read-only analytics dashboard (Phase 2, audited and fixed)
2. **ASP Alerts** - Complete ASP bacteremia/stewardship alerts with clinical features (Phase 2)
3. **MDRO Surveillance** - MDRO detection and case management (Phase 3)
4. **Drug-Bug Mismatch** - Susceptibility-based coverage mismatch detection (Phase 3)
5. **Dosing Verification** - Antimicrobial dosing rules engine with 9 clinical rule modules (Phase 3)
6. **HAI Detection** - Full HAI surveillance with 5 HAI types, LLM classification, IP review (Phase 3)
7. **Outbreak Detection** - Cluster-based outbreak detection aggregating MDRO and HAI data (Phase 3)
8. **Antimicrobial Usage Alerts** - Broad-spectrum antibiotic duration monitoring (Phase 3)
9. **ABX Indications** - Antibiotic indication documentation monitoring with LLM extraction (Phase 3)
10. **Surgical Prophylaxis** - ASHP bundle compliance evaluation with real-time HL7 ADT monitoring (Phase 3)

Foundation code audit is complete — 10 bugs identified and fixed across framework infrastructure, authentication, and Action Analytics. The codebase is now solid for building additional modules.

## Completed Work

### Phase 1 - Foundation
- [x] Django project scaffolding (`aegis_project/`)
- [x] Custom User model with roles (`apps/authentication/`)
- [x] `physician_or_higher_required` decorator
- [x] Core base models: `TimeStampedModel`, `UUIDModel`, `SoftDeletableModel`
- [x] Unified Alert model with AlertAudit (`apps/alerts/`)
- [x] Metrics app: ProviderActivity, DailySnapshot (`apps/metrics/`)
- [x] Notifications app (`apps/notifications/`)
- [x] Audit middleware for HIPAA compliance
- [x] Authentication views and URLs (login/logout)

### Phase 2 - Module Migration
- [x] Action Analytics (`apps/action_analytics/`) - read-only dashboard
- [x] ASP Alerts (`apps/asp_alerts/`) - full clinical alert management

### Phase 3 - Module Migration (continued)
- [x] MDRO Surveillance (`apps/mdro/`) - MDRO detection, case tracking, analytics
- [x] Drug-Bug Mismatch (`apps/drug_bug/`) - susceptibility coverage mismatch detection
- [x] Dosing Verification (`apps/dosing/`) - 9-rule antimicrobial dosing engine
- [x] HAI Detection (`apps/hai_detection/`) - 5 HAI types, LLM classification, IP review with override tracking
- [x] Outbreak Detection (`apps/outbreak_detection/`) - Cluster-based outbreak detection aggregating MDRO/HAI data
- [x] Antimicrobial Usage Alerts (`apps/antimicrobial_usage/`) - Broad-spectrum duration monitoring (meropenem/vancomycin 72h threshold)
- [x] ABX Indications (`apps/abx_indications/`) - Antibiotic indication documentation with LLM extraction, CCHMC guidelines engine
- [x] Surgical Prophylaxis (`apps/surgical_prophylaxis/`) - 7-element ASHP bundle compliance + real-time HL7 ADT surgical pathway monitoring

### Code Audit & Bug Fixes (2026-02-07)

**Action Analytics fixes:**
- [x] Added `@physician_or_higher_required` to all 4 JSON API endpoints (security fix)
- [x] Replaced `datetime.now()` with `timezone.now()` throughout (timezone bug)
- [x] Safe `int()` parsing for `days` query parameter with bounds clamping (crash fix)
- [x] Replaced deprecated `.extra()` with `TruncDate` in analytics.py

**Framework fixes:**
- [x] `SoftDeletableModel.delete()` now accepts and sets `deleted_by` parameter (HIPAA audit fix)
- [x] Auth URLs wired into main urlpatterns (`/auth/login/`, `/auth/logout/`)
- [x] Created login view, template, and URL configuration

**Authentication fixes:**
- [x] `account_not_locked` decorator: `redirect('login')` → `redirect('authentication:login')` (crash fix)
- [x] `create_user_session` signal: guard against None `session_key` before creating UserSession
- [x] AuditMiddleware: thread-local user cleanup in `try/finally` (identity leak fix)
- [x] SAMLAuthBackend: consolidated two `save()` calls into single `save(update_fields=[...])` on login

### ASP Alerts Module (2026-02-07)
- [x] Added BACTEREMIA alert type to AlertType enum
- [x] Added 6 ASP-specific resolution reasons (MESSAGED_TEAM, DISCUSSED_WITH_TEAM, THERAPY_CHANGED, THERAPY_STOPPED, SUGGESTED_ALTERNATIVE, CULTURE_PENDING)
- [x] `recommendations` property on Alert model (reads from details JSON)
- [x] `create_audit_entry()` helper + automatic audit logging on acknowledge/resolve/snooze
- [x] Coverage rules module ported from Flask (organism categorization, antibiotic coverage rules)
- [x] Views updated: all 7 ASP alert types, stats cards, fixed audit log references, resolution reason choices
- [x] Templates enhanced: stats dashboard, susceptibility panel, two-column detail layout, type-specific sections
- [x] Demo data command: `python manage.py create_demo_alerts` (8 realistic scenarios)
- [x] Migration 0002_add_bacteremia_type applied
- [x] All API actions create AlertAudit entries with IP address

### Drug-Bug Mismatch Module (2026-02-08)
- [x] App scaffolding: `apps/drug_bug/` with AppConfig (no custom models — uses Alert model)
- [x] Business logic ported from Flask: `data_models.py`, `matcher.py`, `antibiotic_map.py` (35+ RxNorm mappings)
- [x] FHIR client adapted for Django settings: `fhir_client.py` (HAPI + Epic OAuth)
- [x] Views: dashboard (active mismatches + stats), history (resolved), help, api_stats, api_export
- [x] Templates: base (orange theme), dashboard (stats cards, filters, mismatch table), history, help
- [x] Management commands: `create_demo_mismatches` (8 scenarios: MRSA, VRE, ESBL, Pseudomonas, Candida, etc.), `monitor_drug_bug` (--once/--continuous FHIR polling)
- [x] 7 matcher unit tests passing (resistant, intermediate, susceptible, no_coverage, no_data, effective_coverage, full_assessment)
- [x] Severity mapping: Flask `critical` → Django `HIGH`, Flask `warning` → Django `MEDIUM`
- [x] Detail view links to existing `asp_alerts:detail` (no duplicate detail page needed)
- [x] URL routing at `/drug-bug/` with `app_name='drug_bug'`

## Next Steps

### Immediate (next session)
- [ ] Guideline Adherence module migration (time-window episode monitoring, NLP)
- [ ] Unit tests for foundation code (models, views, decorators)

### Upcoming
- [ ] NHSN Reporting module migration (Clarity batch jobs, CDA generation)
- [ ] Epic FHIR API integration layer
- [ ] Celery background tasks (alert scanning, auto-recheck)

### Lower Priority
- [ ] CSP `unsafe-inline` removal (nonce-based CSP) in production settings
- [ ] Remove dead `MultiAuthBackend` class from backends.py

### Dosing Verification Module (2026-02-08)
- [x] App scaffolding: `apps/dosing/` with AppConfig (no custom models — uses Alert model)
- [x] 9 clinical rule modules ported from Flask (pure Python, import path updates only):
  - Allergy (drug classes + cross-reactivity), Age (neonatal/pediatric/geriatric), Renal (GFR-tiered, 15 drugs)
  - Weight (IBW/ABW/obesity), Route (vancomycin CDI, daptomycin pneumonia), Indication (9 syndromes)
  - Interaction (17 drug pairs + class mappings), Duration (12 infection types), Extended Infusion (10 beta-lactams)
- [x] Rules engine orchestrator: `DosingRulesEngine` evaluates all 9 modules in priority order
- [x] FHIR client adapted for Django settings: `fhir_client.py`
- [x] Data models: `MedicationOrder`, `PatientContext` dataclasses; `DoseFlagType` (16 types), `DoseAlertSeverity`, `DoseAssessment`
- [x] Views: dashboard (active alerts + stats + filters), detail (2-column: patient factors sidebar + dose comparison), history, reports (clinical impact metrics), help (9 rule categories documented)
- [x] API endpoints: stats (GET), acknowledge (POST), resolve (POST), add_note (POST)
- [x] CSV exports: active alerts, history (StreamingHttpResponse)
- [x] Templates: 6 files with blue theme (base, dashboard, detail, history, reports, help)
- [x] Management commands: `create_demo_dosing` (10 scenarios across all 9 rule categories), `monitor_dosing` (--once/--continuous FHIR polling)
- [x] 6 new ResolutionReason values: DOSE_ADJUSTED, INTERVAL_ADJUSTED, ROUTE_CHANGED, CLINICAL_JUSTIFICATION, ESCALATED_TO_ATTENDING, NO_ACTION_NEEDED
- [x] DoseFlagType → AlertType mapping: 16 flag types → 9 DOSING_* alert types
- [x] Severity mapping: Flask MODERATE → Django MEDIUM, all others direct
- [x] URL routing at `/dosing/` with `app_name='dosing'`
- [x] Migration 0003_alter_alert_resolution_reason applied
- [x] All 5 page templates verified rendering, all 9 rule modules import successfully

## Key Files

| Component | Location |
|-----------|----------|
| Django project | `aegis-django/` |
| Settings | `aegis_project/settings/development.py` |
| Alert models | `apps/alerts/models.py` |
| ASP Alerts views | `apps/asp_alerts/views.py` |
| ASP Alerts templates | `templates/asp_alerts/` |
| Coverage rules | `apps/asp_alerts/coverage_rules.py` |
| Demo data command | `apps/asp_alerts/management/commands/create_demo_alerts.py` |
| MDRO Surveillance | `apps/mdro/` |
| Drug-Bug Mismatch views | `apps/drug_bug/views.py` |
| Drug-Bug Mismatch matcher | `apps/drug_bug/matcher.py` |
| Drug-Bug Mismatch templates | `templates/drug_bug/` |
| Drug-Bug demo data | `apps/drug_bug/management/commands/create_demo_mismatches.py` |
| Drug-Bug FHIR monitor | `apps/drug_bug/management/commands/monitor_drug_bug.py` |
| Dosing Verification views | `apps/dosing/views.py` |
| Dosing rules engine | `apps/dosing/rules_engine.py` |
| Dosing 9 rule modules | `apps/dosing/rules/*.py` |
| Dosing alert models | `apps/dosing/alert_models.py` |
| Dosing templates | `templates/dosing/` |
| Dosing demo data | `apps/dosing/management/commands/create_demo_dosing.py` |
| Dosing FHIR monitor | `apps/dosing/management/commands/monitor_dosing.py` |
| HAI Detection app | `apps/hai_detection/` |
| HAI Detection models | `apps/hai_detection/models.py` |
| HAI Detection views | `apps/hai_detection/views.py` |
| HAI Detection services | `apps/hai_detection/services.py` |
| HAI business logic | `apps/hai_detection/logic/` (61 files) |
| HAI prompt templates | `apps/hai_detection/prompts/` (6 files) |
| HAI Detection templates | `templates/hai_detection/` (6 files) |
| HAI demo data | `apps/hai_detection/management/commands/create_demo_hai.py` |
| HAI monitor command | `apps/hai_detection/management/commands/monitor_hai.py` |
| Outbreak Detection app | `apps/outbreak_detection/` |
| Outbreak models | `apps/outbreak_detection/models.py` |
| Outbreak services | `apps/outbreak_detection/services.py` |
| Outbreak views | `apps/outbreak_detection/views.py` |
| Outbreak templates | `templates/outbreak_detection/` (6 files) |
| Outbreak demo data | `apps/outbreak_detection/management/commands/create_demo_outbreaks.py` |
| Outbreak monitor | `apps/outbreak_detection/management/commands/detect_outbreaks.py` |
| Antimicrobial Usage app | `apps/antimicrobial_usage/` |
| Antimicrobial Usage views | `apps/antimicrobial_usage/views.py` |
| Antimicrobial Usage services | `apps/antimicrobial_usage/services.py` |
| Antimicrobial Usage FHIR | `apps/antimicrobial_usage/fhir_client.py` |
| Antimicrobial Usage templates | `templates/antimicrobial_usage/` (5 files) |
| Antimicrobial Usage demo | `apps/antimicrobial_usage/management/commands/create_demo_usage.py` |
| Antimicrobial Usage monitor | `apps/antimicrobial_usage/management/commands/monitor_usage.py` |
| ABX Indications app | `apps/abx_indications/` |
| ABX Indications models | `apps/abx_indications/models.py` |
| ABX Indications services | `apps/abx_indications/services.py` |
| ABX Indications logic | `apps/abx_indications/logic/` (taxonomy, extractor, guidelines) |
| ABX Indications templates | `templates/abx_indications/` (6 files) |
| ABX Indications demo | `apps/abx_indications/management/commands/create_demo_indications.py` |
| ABX Indications monitor | `apps/abx_indications/management/commands/monitor_indications.py` |
| Surgical Prophylaxis app | `apps/surgical_prophylaxis/` |
| Surgical Prophylaxis models | `apps/surgical_prophylaxis/models.py` (9 models) |
| Surgical Prophylaxis evaluator | `apps/surgical_prophylaxis/logic/evaluator.py` (7 ASHP elements) |
| Surgical Prophylaxis guidelines | `apps/surgical_prophylaxis/logic/guidelines.py` |
| Surgical Prophylaxis HL7 | `apps/surgical_prophylaxis/logic/hl7/` (parser, listener, location_tracker) |
| Surgical Prophylaxis realtime | `apps/surgical_prophylaxis/realtime/` (state_manager, preop_checker, schedule_monitor, escalation_engine, service) |
| Surgical Prophylaxis services | `apps/surgical_prophylaxis/services.py` |
| Surgical Prophylaxis FHIR | `apps/surgical_prophylaxis/fhir_client.py` |
| Surgical Prophylaxis views | `apps/surgical_prophylaxis/views.py` |
| Surgical Prophylaxis templates | `templates/surgical_prophylaxis/` (6 files) |
| Surgical Prophylaxis demo | `apps/surgical_prophylaxis/management/commands/create_demo_prophylaxis.py` |
| Surgical Prophylaxis monitor | `apps/surgical_prophylaxis/management/commands/monitor_prophylaxis.py` |
| Surgical Prophylaxis realtime cmd | `apps/surgical_prophylaxis/management/commands/run_realtime_prophylaxis.py` |
| Action Analytics | `apps/action_analytics/` |
| Authentication | `apps/authentication/` |
| Core models | `apps/core/models.py` |
| Auth URLs | `apps/authentication/urls.py` |
| Login template | `templates/authentication/login.html` |

## Known Issues

- `MultiAuthBackend` in `backends.py` is dead code (not in `AUTHENTICATION_BACKENDS`) — can be removed
- CSP uses `unsafe-inline` in production settings (has TODO comment)
- Notification system models exist but no sending logic implemented yet
- No ProviderActivity creation code yet — analytics will return empty until modules populate it

## Session Log

**2026-02-07:**
- Completed ASP Alerts full Django migration (Steps 1-6 of migration plan)
- Fixed bugs: audit_entries -> audit_log, WARNING -> HIGH severity, removed nonexistent FK references (created_by, assigned_to)
- Added susceptibility panels, coverage rules, type-specific detail rendering
- Created demo data management command with 8 clinical scenarios
- Full code audit of Action Analytics module and Django framework infrastructure
- Fixed 10 bugs across action_analytics, core, authentication, and settings
- Created auth views/URLs/templates (login/logout)
- Foundation is audited and solid — ready for next module migrations

**2026-02-08:**
- Migrated Drug-Bug Mismatch module from Flask to Django (16 new files, 2,567 lines)
- Pure Python business logic copied with minimal changes (import paths, Django settings)
- No custom models needed — all data in Alert model with alert_type=DRUG_BUG_MISMATCH
- 8 demo scenarios covering MRSA, E. coli, Pseudomonas, Klebsiella, VRE, MSSA, ESBL E. coli, Candida
- 7 matcher unit tests all passing
- Four modules now migrated total (Action Analytics, ASP Alerts, MDRO, Drug-Bug Mismatch)
- Migrated Dosing Verification module from Flask to Django (24 new files, ~7,200 lines business logic)
- 9 clinical rule modules copied as pure Python with import path updates only
- DosingRulesEngine orchestrates allergy → age → interaction → route → indication → renal → weight → duration → extended infusion
- No custom models — all data in Alert model with 9 DOSING_* alert types + details JSONField
- 2-column detail view: patient factors sidebar (renal function, weight, allergies) + dose comparison panel
- 10 demo scenarios covering all rule categories (3 CRITICAL, 4 HIGH, 1 MEDIUM, 2 resolved)
- Five modules now migrated total (Action Analytics, ASP Alerts, MDRO, Drug-Bug Mismatch, Dosing Verification)
- Migrated HAI Detection module from Flask to Django (76 Python files, 6 templates, 6 prompt templates)
- 4 custom Django models: HAICandidate, HAIClassification, HAIReview, LLMAuditLog (first module needing custom models)
- 61 business logic files copied to logic/ subdirectory with import path fixes (candidates, classifiers, rules, extraction, notes, LLM, data)
- Multi-stage pipeline preserved: Rule-based detection → LLM extraction → NHSN rules engine → IP review with override tracking
- Views: dashboard (stats + HAI type filter tabs), candidate detail (multi-section with LLM classification + review form), history, reports (override analytics), help
- 5 API endpoints: stats, candidates list, submit review (with override detection), override stats, recent overrides
- Management commands: monitor_hai (--once/--continuous/--stats/--classify/--dry-run), create_demo_hai (20+ scenarios across all 5 HAI types)
- HAI_DETECTION settings dict in base.py (LLM backend, FHIR URL, thresholds)
- Six modules now migrated total (Action Analytics, ASP Alerts, MDRO, Drug-Bug Mismatch, Dosing Verification, HAI Detection)
- Migrated Outbreak Detection module from Flask to Django (15 new files, 6 templates)
- 2 custom Django models: OutbreakCluster, ClusterCase (cluster-based detection)
- Data sources replaced: SQLite queries → Django ORM queries against MDROCase + HAICandidate
- Services layer: OutbreakDetectionService combines detector + data sources + alert creation
- 5 page views + 3 API endpoints with purple/maroon IP theme
- Management commands: detect_outbreaks (--once/--continuous/--stats), create_demo_outbreaks (6 CCHMC-unit scenarios)
- Demo data: 6 clusters (MRSA/G3NE, VRE/A6N, CRE/G5NE, CDI/A4N, CLABSI/G6SE, ESBL/G1NE), 19 cases, 5 alerts
- Seven modules now migrated total
- Migrated Antimicrobial Usage Alerts module from Flask to Django (16 new files, 5 templates)
- No custom models needed — all data in Alert model with alert_type=BROAD_SPECTRUM_USAGE (already existed)
- Adapted from Flask au_alerts_src/: data_models.py (3 dataclasses), fhir_client.py (trimmed for duration only), services.py (BroadSpectrumMonitorService)
- Deduplication via JSONField lookup: Alert.objects.filter(details__medication_fhir_id=order_id)
- Severity mapping: Flask WARNING → Django HIGH, Flask CRITICAL → Django CRITICAL (≥144h)
- Views: dashboard (stats + medication filter), detail (duration progress bar + resolve form), history, help + 5 API endpoints
- Templates: teal theme (#00796B), duration bar visualization, de-escalation workflow docs
- Management commands: monitor_usage (--once/--continuous/--stats/--dry-run), create_demo_usage (8 CCHMC-unit scenarios)
- Demo data: 8 scenarios — Meropenem/Vancomycin at G3NE, G1NE, A6N, G6SE, A4N, G5NE, A5N1, A3N (2 CRITICAL, 4 HIGH, 2 resolved)
- ANTIMICROBIAL_USAGE settings dict: 72h threshold, 2 monitored medications (Meropenem/Vancomycin), 300s poll interval
- 7 unit tests passing (data models, service stats, template rendering, alert type)
- Eight modules now migrated total
- Migrated ABX Indications module from Flask to Django (25+ new files, 6 templates)
- 3 custom Django models: IndicationCandidate, IndicationReview, IndicationLLMAuditLog
- Logic layer: taxonomy.py (41 syndromes), extractor.py (LLM extraction via Ollama), guidelines.py (CCHMC engine with 57 disease guidelines)
- Data files: cchmc_disease_guidelines.json (57 diseases), cchmc_antimicrobial_dosing.json
- FHIR client: MedicationRequest, DocumentReference, Condition, Encounter queries
- Services layer: IndicationMonitorService (check_new_alerts, auto_accept_old, get_stats)
- 3 AlertTypes: ABX_NO_INDICATION, ABX_NEVER_APPROPRIATE, ABX_OFF_GUIDELINE
- Views: dashboard (stats + syndrome filter), candidate detail (LLM extraction panel + review form), compliance, history, help + 6 API endpoints
- Templates: amber/gold theme (#d4a017), syndrome breakdown, guideline comparison panel
- Management commands: monitor_indications (--once/--continuous/--stats/--auto-accept/--dry-run), create_demo_indications (10 CCHMC scenarios)
- 64 unit tests passing
- Nine modules now migrated total
- Migrated Surgical Prophylaxis module from Flask to Django (30+ new files, 6 templates)
- Most complex module: 9 custom Django models, 7-element ASHP bundle evaluation, real-time HL7 ADT monitoring
- Core models: SurgicalCase, ProphylaxisEvaluation (7 JSONField element results), ProphylaxisMedication, ComplianceMetric
- Realtime models: SurgicalJourney (state machine), PatientLocation, PreOpCheck, AlertEscalation
- Logic: evaluator.py (7 ASHP elements), guidelines.py (CCHMC JSON + 13 antibiotic dosing), config.py
- HL7 v2.x: parser.py (ADT/ORM/SIU parsing), listener.py (async MLLP TCP server), location_tracker.py (state machine)
- Realtime: state_manager (ORM), preop_checker, schedule_monitor (FHIR Appointments), escalation_engine (multi-level routing), service.py (orchestrator)
- Two operational modes: batch evaluation (FHIR polling) + real-time monitoring (HL7 ADT listener)
- Alert triggers: T-24h, T-2h, T-60min, T-0, Pre-op Arrival, OR Entry with escalation (pharmacy → preop_rn → anesthesia → surgeon → ASP)
- Single AlertType: SURGICAL_PROPHYLAXIS with violation details in JSONField
- Views: dashboard (compliance stats + element bars), case_detail (7-element cards + meds timeline), compliance (per-element + per-category), realtime (active journeys + escalations), help + 5 API endpoints
- Templates: teal theme (#0d7377, #095c5e), compliance bars, element grid cards
- Management commands: monitor_prophylaxis (--once/--continuous/--stats/--dry-run/--hours), run_realtime_prophylaxis (HL7 daemon), create_demo_prophylaxis (8 CCHMC scenarios)
- Demo data: 8 scenarios (VSD repair compliant, spinal fusion MRSA+, appendectomy timing fail, colectomy wrong agent, cochlear implant missing prophylaxis, cholecystectomy withheld, emergency craniotomy excluded, perforated appendectomy excluded)
- SURGICAL_PROPHYLAXIS settings dict: FHIR + HL7 configuration, trigger enable/disable, notification channels
- 66 unit tests passing
- Ten modules now migrated total
