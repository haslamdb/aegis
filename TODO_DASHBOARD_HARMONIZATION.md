# Dashboard & Detail Page Harmonization

## Goal
Standardize the layout, styling, and workflows across all AEGIS modules for a consistent user experience.

## Current State (Jan 2026)

| Module | Dashboard | Detail Page | Review Workflow |
|--------|-----------|-------------|-----------------|
| HAI Detection | Table + filters | Good LLM evidence layout | Confirm/Reject with notes |
| Surgical Prophylaxis | Table + metrics | Good metadata grid (`info-grid`) | Compliance scoring |
| ABX Indications | Table + filters | Hybrid (new evidence sources) | Confirm/Override with notes |
| CDI | Table | Basic | Confirm/Reject |

## Design Patterns to Standardize

### 1. Metadata Display
Adopt the `info-grid` pattern from Surgical Prophylaxis:
```html
<div class="info-grid">
    <div class="info-item">
        <span class="info-label">LABEL</span>
        <span class="info-value">Value</span>
    </div>
</div>
```

### 2. LLM Evidence Display
Adopt the evidence sources pattern from ABX Indications / HAI:
- Note type badge (PROGRESS_NOTE, ID_CONSULT, etc.)
- Date and provider attribution
- Relevance explanation
- Supporting quotes

### 3. Review Workflow
Standardize across modules:
- Reviewer name input
- Primary action buttons (Confirm, Reject)
- Override options with required reason
- Optional notes field
- Status transitions: pending → reviewed → (confirmed/rejected)

### 4. Post-Review Handling
Define consistent behavior for reviewed items:
- Move to "Reviewed" tab or separate view?
- How long to retain in active dashboard?
- Archive/export workflow for reporting

## Modules to Update

- [ ] HAI Detection - Add `info-grid` for patient/culture metadata
- [ ] CDI - Add evidence sources display, improve metadata layout
- [ ] CAUTI - Same as CDI
- [ ] VAE - Same as CDI
- [ ] SSI - Already good, minor tweaks
- [ ] Surgical Prophylaxis - Add LLM evidence display if applicable
- [ ] ABX Indications - Already updated (Jan 2026)

## Shared Components to Extract

Consider extracting to reusable Jinja macros or includes:
- `_info_grid.html` - Metadata display component
- `_evidence_sources.html` - LLM evidence with attribution
- `_review_form.html` - Standard review workflow
- `_classification_badge.html` - Status/classification badges

## CSS Standardization

Move common styles to `static/css/components.css`:
- `.info-grid`, `.info-item`, `.info-label`, `.info-value`
- `.evidence-sources`, `.evidence-item`, `.evidence-header`
- `.badge-*` variants
- `.review-form`, `.confirm-buttons`, `.override-buttons`

## Priority
Medium - Not blocking current work, but will improve maintainability and UX consistency.

## Notes
- Started harmonization with ABX Indications detail page (Jan 2026)
- Evidence source attribution pattern now in ABX Indications
- LLM is primary classification source for ABX Indications
