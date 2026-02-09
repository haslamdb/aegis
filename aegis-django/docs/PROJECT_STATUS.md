# AEGIS Django Migration - Project Status

**Last Updated:** 2026-02-09
**Phase:** 6 - Testing & Quality Assurance COMPLETE
**Priority:** Active Development

## Current Status

Django migration Phase 3 is COMPLETE. All 12 modules have been migrated from Flask to Django:

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
11. **Guideline Adherence** - 9-bundle clinical guideline compliance monitoring with tiered NLP and 3-mode operation (Phase 3)
12. **NHSN Reporting** - CDC NHSN data submission with AU/AR extraction, CDA generation, DIRECT protocol (Phase 3)

Foundation code audit is complete — 10 bugs identified and fixed across framework infrastructure, authentication, and Action Analytics. The codebase is now solid for building additional modules.

**Phase 3 is now complete.** All Flask modules have been migrated to Django.

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
- [x] Guideline Adherence (`apps/guideline_adherence/`) - 9-bundle clinical guideline compliance with tiered NLP, 3 monitoring modes, human review workflow
- [x] NHSN Reporting (`apps/nhsn_reporting/`) - 11 Django models, AU/AR extraction from Clarity, CDA R2 generation, DIRECT protocol submission, 104 tests

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

## Next Steps — Phases 4-9

Phase 3 (module migration) is complete. The remaining phases focus on production hardening, integration, and deployment at CCHMC. See `docs/DJANGO_MIGRATION_PLAN.md` for full details.

### Phase 4: Background Tasks & Scheduling (COMPLETE)
- [x] Celery app initialization (`aegis_project/celery.py` + `__init__.py` import)
- [x] Task routing: 3 queues (`default` FHIR polling, `llm` GPU-bound, `batch` nightly Clarity)
- [x] Beat schedule: 15 periodic tasks with code-managed defaults
- [x] Worker tuning: `CELERY_TASK_ACKS_LATE`, `WORKER_PREFETCH_MULTIPLIER=1`
- [x] Service extraction: `MDROMonitorService`, `DosingMonitorService`, `DrugBugMonitorService`
- [x] Created `tasks.py` in 10 modules (15 Celery tasks total)
- [x] Management commands updated to use service classes
- [x] Flower monitoring dashboard (flower==2.0.1 in requirements)
- [x] Celery logging configuration (celery + celery.task loggers)
- [x] 22 unit tests passing (autodiscovery, routing, schedule, all 15 task functions)
- [x] Operations guide: `docs/CELERY_OPERATIONS.md`
- [x] HL7 ADT listener stays as systemd service (not converted to Celery)

### Phase 5: Unified API & Integration (COMPLETE)
- [x] Created `apps/api/` app with versioned URL namespace at `/api/v1/`
- [x] 11 router-registered DRF ViewSets + 2 auth APIViews
- [x] Token authentication via `rest_framework.authtoken`
- [x] Rate limiting: 100/min reads, 30/min writes per authenticated user (DRF throttling)
- [x] PHI-safe exception handler strips patient data from error responses
- [x] 7 DRF permission classes delegating to `User.can_manage_*()` methods
- [x] API documentation via drf-spectacular → Swagger UI at `/api/docs/`, OpenAPI schema at `/api/schema/`
- [x] Centralized FHIR client at `apps/core/fhir/` (BaseFHIRClient ABC, HAPIFHIRClient, EpicFHIRClient with JWT bearer flow)
- [x] FHIR parsers: bundle extraction, datetime parsing, patient/medication extraction
- [x] `get_fhir_client()` factory for HAPI vs Epic selection
- [x] 242 Phase 5 tests, 1082 total project tests passing
- [ ] Epic CDS Hooks endpoint (deferred to Phase 5b or Phase 6)

### Phase 6: Testing & Quality Assurance (COMPLETE)
- [x] Fill test gaps: foundation (core, auth, alerts, metrics) + remaining modules (HAI, MDRO, ASP, Dosing, Outbreak)
- [x] 1082 total tests, all passing (target was 800+)
- [x] Zero empty test stubs remaining (was 8 of 16 modules)
- [x] Cross-module integration tests: HAI→Alert, MDRO→Alert, Alert lifecycle, management commands
- [x] Security audit tests: API auth required, PHI safety, token auth, CSRF protection
- [x] Management command smoke tests with DB verification
- [ ] LLM validation: 25 CLABSI + 30 indication gold standard cases (>90% sensitivity target) — deferred to Phase 8
- [ ] Performance: 500 patients, 50 concurrent users, page load < 2s, API < 500ms — deferred to Phase 7
- [ ] UAT sign-off from all 4 roles (pharmacist, IP, physician, admin) — deferred to Phase 8

### Phase 7: Deployment & Infrastructure
- [ ] PostgreSQL 16 migration (replace SQLite, import existing data, connection pooling, nightly backups)
- [ ] Docker Compose: web, celery (2 queues), celery-beat, hl7-listener, redis, postgres, nginx, ollama
- [ ] TLS: Nginx with HSTS, OCSP stapling (Let's Encrypt or CCHMC cert)
- [ ] CI/CD: GitHub Actions — test on PR, deploy staging on develop, deploy prod on main (manual gate)
- [ ] Monitoring: Sentry (errors), structured JSON logs, `/health/` endpoint, uptime monitoring

### Phase 8: CCHMC IT Integration
- [ ] SSO: Connect SAML backend to CCHMC IdP (ADFS/Azure AD), AD group → role mapping
- [ ] Epic access: FHIR R4 API (read-only), Clarity (read-only), HL7 ADT feed, NHSN DIRECT registration
- [ ] Network: deploy on CCHMC internal network, firewall rules, internal DNS (`aegis.cchmc.org`)
- [ ] Security: vulnerability scan (Qualys/Nessus), penetration test, CSP nonce-based (remove `unsafe-inline`)
- [ ] HIPAA documentation: security architecture diagram, data flow diagram, risk assessment, DR plan, incident response
- [ ] User training: guides for pharmacists, IPs, physicians, admins + on-call runbook

### Phase 9: Cutover & Flask Decommission
- [ ] Pre-cutover checklist: all phases complete, CCHMC approval, UAT signed off
- [ ] Cutover execution: Flask read-only → data export → PostgreSQL import → DNS switch → verify all 12 modules
- [ ] Rollback plan: revert DNS within 48 hours if critical issues found
- [ ] Post-cutover: 2-week monitoring, user feedback, performance tuning
- [ ] Archive Flask codebase (`flask-final` tag), remove after 30-day grace period

### Backlog (Lower Priority)
- [ ] Remove dead `MultiAuthBackend` class from `backends.py`
- [ ] FHIR Subscription support (R4 topic-based) for real-time notifications
- [ ] SMART on FHIR launch context for EHR-embedded views
- [ ] Multi-site analytics data model design
- [ ] Allergy delabeling opportunity tracker (#14)
- [ ] Epic Communicator integration for secure messaging (#16)

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

**2026-02-08 (cont.):**
- Migrated Guideline Adherence module from Flask to Django (29 new files, 8 templates)
- Most complex monitoring module: 5 custom Django models, 9 guideline bundles, 3 coordinated monitoring modes
- Core models: BundleEpisode (episode tracking + adherence calculation), ElementResult (per-element status), EpisodeAssessment (LLM analysis), EpisodeReview (human review + override), MonitorState (polling checkpoints)
- 9 evidence-based guideline bundles: Pediatric Sepsis, CAP, Febrile Infant (AAP 2021), Neonatal HSV, C.diff Testing Stewardship, Febrile Neutropenia, Surgical Prophylaxis, UTI, SSTI
- 3 monitoring modes: trigger monitoring (FHIR polling), episode monitoring (deadline violations), adherence monitoring (element completion)
- 7 element checkers: base, lab, medication, note, febrile_infant (AAP 2021 age-stratified), hsv (classification-based), cdiff_testing (diagnostic stewardship)
- Tiered NLP pipeline: 7B triage (qwen2.5:7b) → 70B full analysis (llama3.3:70b) with 5 escalation triggers
- NLP extractors: clinical_impression, triage_extractor, gi_symptoms (C.diff criteria)
- Services: GuidelineAdherenceService (3-mode orchestrator, checker routing, alert dedup, review workflow)
- 2 AlertTypes: GUIDELINE_ADHERENCE, BUNDLE_INCOMPLETE
- Views: dashboard, active_episodes, episode_detail, bundle_detail, metrics, history, help + 4 API endpoints
- Templates: blue/navy clinical theme (#1a4b8c, #0d2b5e)
- Management commands: monitor_guidelines (--trigger/--episodes/--adherence/--all/--once/--continuous/--stats/--dry-run/--bundle), create_demo_guidelines (5 CCHMC scenarios)
- Demo data: 5 scenarios — Febrile Infant 14d well (100%), Sepsis 3y (50%, 2 alerts), HSV 10d (72.7%, 1 critical), Febrile Infant 10d ill (92.3%), C.diff 8y (100%)
- GUIDELINE_ADHERENCE settings dict: FHIR URL, dual LLM models (70B + 7B), 8 enabled bundles
- Decorator: can_manage_guideline_adherence (ASP_PHARMACIST or ADMIN)
- 70 unit tests passing
- Eleven modules now migrated total

**2026-02-09:**
- Migrated NHSN Reporting module from Flask to Django (26 new files, 8 templates)
- Final module in Phase 3 — all 12 Flask modules now fully migrated to Django
- 11 custom Django models: NHSNEvent, DenominatorDaily, DenominatorMonthly, AUMonthlySummary, AUAntimicrobialUsage, AUPatientLevel, ARQuarterlySummary, ARIsolate, ARSusceptibility, ARPhenotypeSummary, SubmissionAudit
- 4 enums: HAIEventType (CLABSI/CAUTI/SSI/VAE), AntimicrobialRoute, SusceptibilityResult, ResistancePhenotype (9 values)
- 3 reporting domains: Antibiotic Usage (AU - DOT/DDD), Antimicrobial Resistance (AR - isolates/phenotypes), HAI Event Submission (CDA/DIRECT)
- Logic layer: config.py, au_extractor.py (Clarity MAR queries), ar_extractor.py (culture results, first-isolate rule, phenotype detection), denominator.py (recursive CTE for patient-days)
- CDA generation: BSICDADocument + CDAGenerator — HL7 CDA R2 XML with LOINC/SNOMED codes, NHSN OIDs
- DIRECT protocol: DirectConfig + DirectClient — SMTP/HISP submission with TLS, MIME with CDA attachments
- Services: NHSNReportingService — stats, CSV export (4 types), event creation from HAICandidates, CDA generation, DIRECT submission, audit logging
- Views: 7 page views (dashboard, AU detail, AR detail, HAI events, denominators, submission, help) + 7 API endpoints
- Templates: green/teal CDC theme (#2e7d32, #1b5e20), checkboxable event tables, phenotype badges, duration bars
- Management commands: nhsn_extract (--au/--ar/--denominators/--all/--stats/--month/--quarter/--location/--dry-run/--create-events), create_demo_nhsn (6 months of data across 6 CCHMC locations)
- AlertType: NHSN_SUBMISSION
- NHSNEvent FK to HAICandidate (confirmed events become NHSN submissions)
- Primary data source: Clarity (Epic reporting DB), with mock SQLite support for development
- Decorator: can_manage_nhsn_reporting (INFECTION_PREVENTIONIST or ADMIN)
- 104 unit tests passing
- Twelve modules now migrated total — Phase 3 COMPLETE

**2026-02-09 (cont.):**
- Completed Phase 5: Unified API & Integration
- Created `apps/api/` app with DRF ViewSets, routers, serializers, and filters at `/api/v1/`
- 11 router-registered ViewSets: alerts, hai/candidates, outbreaks/clusters, guidelines/episodes, surgical/cases, indications/candidates, nhsn/events, nhsn/denominators, nhsn/au-summaries, nhsn/ar-summaries, nhsn/stats
- 2 auth APIViews: auth/me/ (GET/PATCH current user), auth/token/ (POST obtain token)
- 7 DRF permission classes: IsPhysicianOrHigher, CanEditAlerts, CanManageHAIDetection, CanManageOutbreakDetection, CanManageSurgicalProphylaxis, CanManageGuidelineAdherence, CanManageNHSNReporting
- PHI-safe exception handler scrubs patient_mrn, patient_name, etc. from validation errors
- Centralized FHIR client at `apps/core/fhir/`: BaseFHIRClient (ABC), HAPIFHIRClient, EpicFHIRClient (JWT bearer RS384)
- FHIR parsers: extract_bundle_entries, parse_fhir_datetime, extract_patient_name/mrn, parse_susceptibility_observation
- Token authentication via `rest_framework.authtoken`, DRF throttling (100/min read, 30/min write)
- Swagger UI at `/api/docs/`, OpenAPI schema at `/api/schema/`
- Added `apps/__init__.py` for proper test autodiscovery (fixes namespace package issue)
- 242 new Phase 5 tests, 1082 total project tests passing

**2026-02-09 (cont.):**
- Completed Phase 6: Testing & Quality Assurance
- 4 parallel work packages implemented via agent team:
  - WP1: Foundation tests — Core base models (128 total), Authentication (72), Alerts (50)
  - WP2: HAI Detection (54), Outbreak Detection (31), MDRO Surveillance (54)
  - WP3: Dosing Verification (64), Drug-Bug Mismatch (26), Antimicrobial Usage (16), ASP Alerts (48)
  - WP4: Action Analytics (21), Metrics (12), Integration tests, Security audit tests
- New test files: `apps/core/tests_integration.py` (cross-module integration), `apps/core/tests_security.py` (security audit)
- Zero empty test stubs remaining (was 8 of 16 module test files)
- 1082 total tests, all passing (was 585)
- Per-module test counts:
  - core: 128, authentication: 72, alerts: 50, api: 194
  - hai_detection: 54, outbreak_detection: 31, mdro: 54, drug_bug: 26
  - antimicrobial_usage: 16, dosing: 64, asp_alerts: 48, abx_indications: 64
  - surgical_prophylaxis: 66, guideline_adherence: 70, nhsn_reporting: 104
  - action_analytics: 21, metrics: 12

**2026-02-09 (cont.):**
- Completed Phase 4: Background Tasks & Scheduling with Celery
- Created `aegis_project/celery.py` (Celery app) and updated `__init__.py` (celery_app export)
- Configured 3 task queues: `default` (4 workers, FHIR polling), `llm` (2 workers, GPU-bound), `batch` (1 worker, nightly Clarity)
- Beat schedule with 15 periodic tasks: 6 FHIR polling (5-30 min), 7 LLM tasks (5 min - 1 hour), 2 nightly batch (2:00 AM / 3:00 AM)
- Extracted 3 service classes from management commands: `MDROMonitorService`, `DosingMonitorService`, `DrugBugMonitorService`
- Created `tasks.py` in 10 modules with consistent pattern: `@shared_task(bind=True, max_retries=3, autoretry_for=..., retry_backoff=True)`
- Updated 3 management commands to use new service classes (MDRO, dosing, drug-bug)
- Added Flower monitoring dashboard (flower==2.0.1) to dev and prod requirements
- Added celery + celery.task loggers to LOGGING config
- 22 unit tests passing: Celery app integration (autodiscovery, routing, schedule, worker settings) + 15 task function tests
- Created `docs/CELERY_OPERATIONS.md` with worker startup, queue descriptions, systemd examples, troubleshooting

### Key Files (Phase 5 — Unified API)

| Component | Location |
|-----------|----------|
| API app | `apps/api/` |
| API app config | `apps/api/apps.py` |
| Permissions (7 classes) | `apps/api/permissions.py` |
| Throttling (read/write) | `apps/api/throttling.py` |
| PHI-safe exception handler | `apps/api/exceptions.py` |
| Audit log mixin | `apps/api/mixins.py` |
| Root API URLs | `apps/api/urls.py` |
| v1 router + URL registration | `apps/api/v1/urls.py` |
| Alert ViewSet | `apps/api/v1/alerts/views.py` |
| HAI Candidate ViewSet | `apps/api/v1/hai/views.py` |
| Outbreak Cluster ViewSet | `apps/api/v1/outbreaks/views.py` |
| Guideline Episode ViewSet | `apps/api/v1/guidelines/views.py` |
| Surgical Case ViewSet | `apps/api/v1/surgical/views.py` |
| Indication Candidate ViewSet | `apps/api/v1/indications/views.py` |
| NHSN ViewSets (5) | `apps/api/v1/nhsn/views.py` |
| Auth views (me, token) | `apps/api/v1/auth/views.py` |
| FHIR base client (ABC) | `apps/core/fhir/base.py` |
| FHIR Epic OAuth client | `apps/core/fhir/oauth.py` |
| FHIR parsers | `apps/core/fhir/parsers.py` |
| FHIR client factory | `apps/core/fhir/factory.py` |
| FHIR tests (48) | `apps/core/fhir/tests.py` |
| Permission tests (25) | `apps/api/tests/test_permissions.py` |
| Infrastructure tests (8) | `apps/api/tests/test_infrastructure.py` |

### Key Files (Guideline Adherence)

| Component | Location |
|-----------|----------|
| Guideline Adherence app | `apps/guideline_adherence/` |
| Guideline Adherence models | `apps/guideline_adherence/models.py` (5 models) |
| Bundle definitions | `apps/guideline_adherence/bundles.py` (9 bundles) |
| Element checkers | `apps/guideline_adherence/logic/checkers/` (7 files) |
| NLP extractors | `apps/guideline_adherence/logic/nlp/` (3 extractors) |
| FHIR client | `apps/guideline_adherence/fhir_client.py` |
| Services | `apps/guideline_adherence/services.py` |
| Views | `apps/guideline_adherence/views.py` |
| Templates | `templates/guideline_adherence/` (8 files) |
| Demo data | `apps/guideline_adherence/management/commands/create_demo_guidelines.py` |
| Monitor command | `apps/guideline_adherence/management/commands/monitor_guidelines.py` |

### Key Files (NHSN Reporting)

| Component | Location |
|-----------|----------|
| NHSN Reporting app | `apps/nhsn_reporting/` |
| NHSN models (11) | `apps/nhsn_reporting/models.py` |
| Config helpers | `apps/nhsn_reporting/logic/config.py` |
| AU extractor | `apps/nhsn_reporting/logic/au_extractor.py` |
| AR extractor | `apps/nhsn_reporting/logic/ar_extractor.py` |
| Denominator calculator | `apps/nhsn_reporting/logic/denominator.py` |
| CDA generator | `apps/nhsn_reporting/cda/generator.py` |
| DIRECT client | `apps/nhsn_reporting/direct/client.py` |
| Services | `apps/nhsn_reporting/services.py` |
| Views | `apps/nhsn_reporting/views.py` |
| Templates (8) | `templates/nhsn_reporting/` |
| Demo data | `apps/nhsn_reporting/management/commands/create_demo_nhsn.py` |
| Batch extraction | `apps/nhsn_reporting/management/commands/nhsn_extract.py` |
| Tests (104) | `apps/nhsn_reporting/tests.py` |

### Key Files (Phase 4 — Celery)

| Component | Location |
|-----------|----------|
| Celery app | `aegis_project/celery.py` |
| Celery init | `aegis_project/__init__.py` |
| Task routing + beat schedule | `aegis_project/settings/base.py` (CELERY_TASK_ROUTES, CELERY_BEAT_SCHEDULE) |
| MDRO service | `apps/mdro/services.py` |
| Dosing service | `apps/dosing/services.py` |
| Drug-Bug service | `apps/drug_bug/services.py` |
| HAI tasks | `apps/hai_detection/tasks.py` |
| Outbreak tasks | `apps/outbreak_detection/tasks.py` |
| MDRO tasks | `apps/mdro/tasks.py` |
| Drug-Bug tasks | `apps/drug_bug/tasks.py` |
| Dosing tasks | `apps/dosing/tasks.py` |
| Usage tasks | `apps/antimicrobial_usage/tasks.py` |
| ABX Indications tasks | `apps/abx_indications/tasks.py` |
| Prophylaxis tasks | `apps/surgical_prophylaxis/tasks.py` |
| Guideline tasks | `apps/guideline_adherence/tasks.py` |
| NHSN tasks | `apps/nhsn_reporting/tasks.py` |
| Celery tests (22) | `apps/core/tests.py` |
| Operations guide | `docs/CELERY_OPERATIONS.md` |
