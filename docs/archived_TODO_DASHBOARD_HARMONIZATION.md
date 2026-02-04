# Dashboard & Detail Page Harmonization

## Status: COMPLETED (2026-01-31)

All major harmonization work completed. Shared component macros extracted and in use across modules.

## Completed Items

### 1. Metadata Display
- [x] `info_grid` macro extracted to `macros/components.html`
- [x] `detail_list` macro for vertical label/value pairs
- [x] Used in: HAI, ABX Indications, Surgical Prophylaxis, Guideline Adherence

### 2. LLM Evidence Display
- [x] `evidence_sources_full` - Full attribution format (ABX style)
- [x] `evidence_sources_simple` - Simple format (HAI style)
- [x] `extraction_meta` - Confidence, model, token display
- [x] Used in: HAI, ABX Indications, Guideline Adherence

### 3. Review Workflow Components
- [x] `reviewer_input` - Pre-populates from session
- [x] `decision_badge` - LLM/reviewer decisions
- [x] `status_badge` - Status with color coding
- [x] Override workflows with required reasons
- [x] Used in: HAI, ABX Indications, Guideline Adherence

### 4. Classification & Status Badges
- [x] `classification_badge` - A/S/N/P badges
- [x] `hai_type_badge` - CLABSI, CAUTI, SSI, VAE, CDI
- [x] `priority_badge` - Priority score with color coding

### 5. HAI Type-Specific Details
- [x] `hai_type_details` macro with sub-macros for each type
- [x] CLABSI: device days, line site/type, insertion/removal dates
- [x] SSI: procedure, NHSN category, wound class, implant, surveillance window
- [x] CDI: test type, onset type, recurrence info
- [x] CAUTI: catheter days, CFU/mL, organism, catheter info
- [x] VAE: VAC onset, vent day, FiO2/PEEP criteria, baseline/worsening periods

### 6. Dashboard Components
- [x] `stat_card`, `stats_grid` - Statistics display
- [x] `dashboard_card`, `report_card` - Card containers
- [x] `data_table` - Consistent table rendering
- [x] `bar_chart` - Horizontal bar charts
- [x] `filter_form`, `filter_select` - Filter controls
- [x] `quick_links` - Action button rows
- [x] `page_header` - Title with actions
- [x] `empty_state` - Empty state messages
- [x] `alert_box` - Notification boxes

### 7. Clinical Context Components
- [x] `clinical_context_card` - MDR history, allergies, renal status
- [x] `culture_card`, `culture_list` - Culture display with susceptibilities
- [x] `susceptibility_table` - Standalone susceptibility table
- [x] Allergy exclusion display in susceptibility results

## Shared Macros Location

All shared components in: `dashboard/templates/macros/components.html`

Import with:
```jinja2
{% from "macros/components.html" import info_grid, evidence_sources_full, ... %}
```

## Modules Using Shared Components

| Module | info_grid | evidence | review | badges | hai_details |
|--------|-----------|----------|--------|--------|-------------|
| HAI Detection | Yes | Yes | Yes | Yes | Yes |
| ABX Indications | Yes | Yes | Yes | Yes | - |
| Surgical Prophylaxis | Yes | - | Yes | - | - |
| Guideline Adherence | Yes | Yes | Yes | Yes | - |
| Drug-Bug Mismatch | Yes | - | Yes | - | - |

## Date Created: 2026-01-26
## Date Completed: 2026-01-31
