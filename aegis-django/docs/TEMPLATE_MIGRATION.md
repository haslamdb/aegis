# Template Migration — Flask CSS & Shared Base Template

**Completed:** 2026-02-09
**Commit:** `fceae6a` — 89 files changed, 3,611 insertions, 6,319 deletions

## Overview

Replaced all inline `<style>` CSS (~6,300 lines) across 12 Django modules with a shared `style.css` (4,081 lines from Flask dashboard) and a new `style-supplements.css` (~300 lines). Created a global Django base template with dynamic navbar, footer, flash messages, and auto-refresh JavaScript.

## Architecture

### Template Inheritance

```
_base.html                          ← Global: CSS links, navbar, footer, messages, JS
  └── {module}/base.html            ← Thin wrapper: {% extends "_base.html" %}, title block
        └── {module}/{page}.html    ← Child: content block only
```

### Design Decisions

1. **Components:** Flask Jinja2 macros → Django `{% include "..." with var=val %}` partials
2. **Navigation:** Context processor + `_includes/navbar.html` partial (uses `current_module` and `current_view`)
3. **Flash messages:** Django messages framework (`{% for message in messages %}`)
4. **Module bases:** 2-3 line thin wrappers extending `_base.html`
5. **Supplemental CSS:** Module-specific classes in `style-supplements.css` rather than modifying Flask CSS

### CSS Sources

| File | Lines | Purpose |
|------|-------|---------|
| `static/style.css` | 4,081 | Flask dashboard CSS (BEM components, CCHMC brand) |
| `static/style-supplements.css` | ~300 | Module-specific CSS not in Flask (HAI tabs, dosing comparison, timelines, login) |

## CSS Class Mapping

| Old (inline) | New (style.css) |
|---|---|
| `.stats-row` | `.stat-cards` |
| `.stat-box` | `{% include "_includes/stat_card.html" %}` |
| `.badge.critical` | `{% include "_includes/badge.html" with color="red" %}` |
| `.badge.high` / `.badge.medium` | `{% include "_includes/badge.html" with color="yellow" %}` |
| `.badge.low` | `{% include "_includes/badge.html" with color="blue" %}` |
| `.badge.pending` | `{% include "_includes/badge.html" with color="gray" %}` |
| `.badge.resolved` | `{% include "_includes/badge.html" with color="green" %}` |
| `.alert-box` | `.action-card` |
| `.detail-main` | `.detail-layout__main` |
| `.detail-sidebar` | `.detail-layout__sidebar` |
| `.btn-primary` | `.btn.btn--primary` |
| `.btn-success` | `.btn.btn--success` |
| `.btn-warning` | `.btn.btn--secondary` |
| `.btn-danger` | `.btn.btn--danger` |
| `.filters` | `.filter-bar` + `.filter-form` + `.filter-group` |
| bare `<table>` | `<table class="data-table">` |
| `.patient-info` | `.detail-section` |
| `.card` / `.card-header` | `.detail-section` / `.detail-section__title` |
| `.timeline` | `.sp-timeline` (surgical prophylaxis, avoids conflict) |

## Files Created (9)

| File | Purpose |
|------|---------|
| `templates/_base.html` | Global base: `{% load static %}`, CSS links, favicon, blocks, JS (timeAgo, autoRefresh) |
| `templates/_includes/navbar.html` | Per-module nav links with active state, shield SVG brand, user display |
| `templates/_includes/messages.html` | Django messages framework → `flash-message flash-{{ message.tags }}` |
| `templates/_includes/footer.html` | CCHMC footer + demo disclaimer banner |
| `templates/_includes/stat_card.html` | `.stat-card.stat-card--{{ color }}` with value, title, optional subtitle |
| `templates/_includes/badge.html` | `.badge.badge--{{ color }}` with text |
| `templates/_includes/empty_state.html` | Empty state with title, message, optional icon |
| `aegis_project/context_processors.py` | `navigation_context()` → `current_module`, `current_view`, `module_display_name` |
| `static/style-supplements.css` | HAI tabs, dosing comparison, compliance bars, timelines, login, sidebar cards |

## Files Modified (80)

### Module Base Templates (12 — all replaced with thin wrappers)

| Module | Old Lines | New Lines |
|--------|-----------|-----------|
| `asp_alerts/base.html` | 261 | 2 |
| `drug_bug/base.html` | 250 | 2 |
| `hai_detection/base.html` | 293 | 2 |
| `outbreak_detection/base.html` | 233 | 2 |
| `mdro/base.html` | 231 | 2 |
| `dosing/base.html` | 266 | 2 |
| `antimicrobial_usage/base.html` | 286 | 2 |
| `action_analytics/base.html` | 33 | 2 |
| `surgical_prophylaxis/base.html` | 272 | 2 |
| `guideline_adherence/base.html` | 194 | 2 |
| `nhsn_reporting/base.html` | 175 | 2 |
| `abx_indications/base.html` (APP_DIRS) | 139 | 2 |

### Child Templates (64)

All updated with: stat_card includes, badge includes, `.data-table`, `.filter-bar`, `.detail-layout__main/__sidebar`, `.btn--*` BEM classes, removal of inline `<style>` blocks.

| Module | Templates |
|--------|-----------|
| ASP Alerts | active, detail, history, reports, help, culture_detail, medications |
| Drug-Bug Mismatch | dashboard, history, help |
| HAI Detection | dashboard, candidate_detail, history, reports, help |
| Outbreak Detection | dashboard, clusters, cluster_detail, alerts, help |
| MDRO Surveillance | dashboard, cases, case_detail, case_not_found, analytics, help |
| Dosing Verification | dashboard, detail, history, reports, help |
| Antimicrobial Usage | dashboard, detail, history, help |
| ABX Indications | dashboard, detail, history, help |
| Guideline Adherence | dashboard, active_episodes, episode_detail, bundle_detail, history, metrics, help |
| NHSN Reporting | dashboard, au_detail, ar_detail, hai_events, denominators, submission, help |
| Surgical Prophylaxis | dashboard, case_detail, compliance, realtime, help |
| Action Analytics | overview, by_module, time_spent, productivity |
| Authentication | login (overrides navbar block to empty) |

### Test Files (4)

Updated assertions that referenced inline CSS colors or old heading text:
- `apps/abx_indications/tests.py` — removed `#d4a017` assertion
- `apps/antimicrobial_usage/tests.py` — `Antimicrobial Usage Alerts` → `Antimicrobial Usage`, removed `#00796B`
- `apps/surgical_prophylaxis/tests.py` — removed `#0d7377`, `85.0%` → `85.0`, `75.0%` → `75.0`
- `apps/guideline_adherence/tests.py` — `75.0` → `75%`, `70.0` → `70%` (stat_card uses `stringformat:"d"`)

### Settings (1)

`aegis_project/settings/base.py` — added `aegis_project.context_processors.navigation_context` to `TEMPLATES[0]['OPTIONS']['context_processors']`

## Supplement CSS Sections

`static/style-supplements.css` covers module-specific classes not in Flask `style.css`:

| Section | Classes | Used by |
|---------|---------|---------|
| HAI Detection | `.hai-type-tabs`, `.confidence-bar`, `.confidence-high/medium/low` | HAI dashboard, reports |
| Dosing | `.dose-comparison`, `.dose-actual`, `.dose-expected` | Dosing detail |
| Compliance | `.compliance-bar`, `.compliance-fill` | Surgical prophylaxis, guideline adherence |
| Duration | `.duration-bar-container`, `.duration-bar-fill`, `.duration-bar-threshold` | Antimicrobial usage detail |
| Surgical Prophylaxis | `.element-grid`, `.element-card`, `.sp-timeline`, `.sp-timeline-item` | Case detail, dashboard |
| Guideline Adherence | `.bundle-grid`, `.bundle-card`, `.element-list`, `.progress-bar`, `.icd-badge`, `.alert-banner` | Dashboard, bundle detail, episode detail |
| Login | `.login-page`, `.login-container`, `.login-header`, `.btn-login`, `.error-list` | Login page |
| Shared | `.sidebar-card`, `.alert-details`, `.recommendations`, `.audit-log`, `.form-textarea`, `.nav-user` | Multiple modules |

## Reference Files

| File | Purpose |
|------|---------|
| `dashboard/templates/base.html` | Flask base template (authoritative reference for navbar, footer, JS) |
| `dashboard/templates/_components/*.html` | Flask component macros (reference for include partials) |
| `dashboard/static/style.css` | All target CSS class names (4,081 lines) |

## Verification

```bash
python manage.py check 2>/dev/null          # System check passes
python manage.py test 2>/dev/null            # All 1120 tests pass
python manage.py collectstatic --noinput     # CSS collected to staticfiles/
```
