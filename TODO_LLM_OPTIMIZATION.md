# LLM Optimization TODO

## Status: COMPLETED (2026-01-31)

All items addressed in the January 2026 sprint.

## Completed Items

### 1. HAI Detection - Optimize LLM Usage
- [x] **Tiered approach** - qwen2.5:7b for triage, llama3.3:70b for full extraction
- [x] **Pre-filter note types** - only send relevant notes
- [x] **Training data capture** - override reasons and extraction errors collected

### 2. Antibiotic Indications
- [x] ICD-10 Chua classification as primary (instant)
- [x] LLM syndrome extraction for JC-compliant workflow
- [x] Training data capture with syndrome corrections and agent appropriateness

### 3. Guideline Adherence - Tiered LLM Approach
- [x] **Triage extractor added** - faster initial pass for clinical appearance
- [x] **Training data capture** - ClinicalAppearanceTrainingCollector, GuidelineReviewCollector
- [x] **Override detection** - HAI-style review workflow with override tracking
- [x] **Episode assessments** - automatic LLM analysis with periodic reassessment

### 4. Module LLM Strategy (Final)

| Module | Primary Method | LLM Role | Training Capture |
|--------|---------------|----------|------------------|
| HAI Detection | LLM extraction | Tiered (7B/70B) | Yes |
| Antibiotic Indications | ICD-10 + LLM syndrome | Primary | Yes |
| Guideline Adherence | LLM clinical impression | Tiered | Yes |
| Drug-Bug Mismatch | Rule-based susceptibility | None | N/A |
| Surgical Prophylaxis | CPT/procedure rules | None | N/A |

## Performance Baseline (2026-01-24)
- llama3.3:70b on RTX A5000 + A6000 (tensor parallel)
- ~85 sec/note for full extraction
- qwen2.5:7b triage: ~5-10 sec/note

## Date Created: 2026-01-24
## Date Completed: 2026-01-31
