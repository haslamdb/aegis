# AEGIS HAI Detection Optimization Guide

## Overview

This document provides a structured approach to optimizing AEGIS (Automated Evaluation and Guidance for Infection Surveillance) for improved throughput and accuracy. Work through each section sequentially with Claude CLI.

**Current State:**
- Hardware: RTX A6000 (48GB) + RTX A5000 (24GB)
- Model: llama3.3:70b Q4_K_M via Ollama
- Context: ~24K tokens (concatenated clinical notes)
- Latency: ~90 seconds per case review
- Architecture: Extraction (LLM) → Rules Engine (deterministic)

**Goals:**
- Reduce per-case latency to <30 seconds
- Maintain or improve classification accuracy
- Prepare for production Epic integration

---

## Phase 1: Baseline Assessment

### 1.1 Profile Current Performance

First, establish accurate baselines.

```bash
# Create a profiling script
# Location: hai-detection/scripts/profile_performance.py
```

**Task for Claude CLI:**
> Create a profiling script at `hai-detection/scripts/profile_performance.py` that:
> 1. Loads 10-20 synthetic test cases
> 2. Runs each through the full classification pipeline
> 3. Records timing for each stage: note retrieval, extraction, rules engine
> 4. Measures GPU memory usage during inference
> 5. Outputs a summary report with mean, median, p95 latencies

### 1.2 Identify Bottlenecks

After running the profiler, analyze where time is spent:

| Stage | Expected % of Time | Optimization Potential |
|-------|-------------------|----------------------|
| Note retrieval/prep | 5-10% | Low |
| LLM tokenization | 5-10% | Medium |
| LLM inference | 70-80% | High |
| Rules engine | 1-5% | Low |
| Result formatting | 1-2% | Low |

**Task for Claude CLI:**
> Analyze the profiling results and identify the top 3 bottlenecks. For each, propose specific optimizations.

---

## Phase 2: Context Reduction Strategies

The biggest win will come from reducing the context sent to the LLM. Current: ~24K tokens. Target: <8K tokens.

### 2.1 Maximize Structured Data from FHIR

Move extraction of discrete data from LLM to direct FHIR queries.

**Currently extracted by LLM (move to FHIR):**
- [ ] Temperature/fever (Observation)
- [ ] WBC/ANC values (Observation)
- [ ] Antibiotic administration (MedicationAdministration)
- [ ] Culture results with dates (DiagnosticReport/Observation)
- [ ] Device insertion/removal dates (Procedure/Device)
- [ ] Vital signs (Observation)

**Must remain LLM-extracted (unstructured):**
- Clinical team impressions
- Suspected diagnoses
- Symptoms documented in narrative
- Exit site assessments (often in nursing notes)
- Alternative infection sources mentioned

**Task for Claude CLI:**
> Review `hai-detection/hai_src/data/fhir_source.py` and create new methods to extract:
> 1. Temperature observations (fever >38°C or hypothermia <36°C) within a date range
> 2. WBC and ANC lab values within a date range
> 3. Antibiotic administrations (filter to IV/PO antimicrobials) within a date range
> 
> Use FHIR R4 resource queries. Add these to a new file `hai-detection/hai_src/data/fhir_structured.py`

### 2.2 Implement Keyword-Based Note Filtering

Filter notes to relevant sections before LLM processing.

```python
# Target location: hai-detection/hai_src/notes/filters.py

HAI_KEYWORDS = {
    "clabsi": [
        "central line", "PICC", "port", "hickman", "broviac", "CVC",
        "blood culture", "bacteremia", "sepsis", "line infection",
        "exit site", "tunnel", "catheter", "contaminant", "CLABSI",
        "line days", "dwell time"
    ],
    "cauti": [
        "foley", "catheter", "urinary", "UTI", "urine culture",
        "dysuria", "suprapubic", "CVA tenderness", "bacteriuria",
        "pyuria", "colony", "CFU"
    ],
    "vae": [
        "ventilator", "intubat", "extubat", "FiO2", "PEEP",
        "respiratory", "secretions", "sputum", "BAL", "tracheal",
        "pneumonia", "VAP", "VAE", "IVAC"
    ],
    "ssi": [
        "wound", "incision", "surgical site", "dehiscence", "drainage",
        "erythema", "purulent", "abscess", "reoperation", "SSI",
        "post-op", "operative"
    ],
    "cdi": [
        "C. diff", "difficile", "diarrhea", "stool", "toxin",
        "CDI", "vancomycin", "fidaxomicin", "metronidazole"
    ]
}
```

**Task for Claude CLI:**
> Create `hai-detection/hai_src/notes/filters.py` with:
> 1. `HAI_KEYWORDS` dictionary as shown above
> 2. `filter_note_by_keywords(note_content: str, hai_type: str, context_lines: int = 3) -> str`
>    - Returns only paragraphs/sections containing keywords
>    - Includes `context_lines` before/after matching paragraphs
> 3. `filter_notes_for_candidate(notes: list[ClinicalNote], hai_type: HAIType) -> list[ClinicalNote]`
>    - Filters and truncates notes, returns only relevant content
>    - Preserves note metadata (date, type, author)

### 2.3 Implement Section-Based Note Parsing

Clinical notes have structure. Parse and extract only relevant sections.

**Common note sections to prioritize:**
- Assessment/Plan (highest value)
- Infectious Disease notes
- Nursing assessments (for device/wound documentation)
- Microbiology results discussion

**Sections to deprioritize/skip:**
- Social history
- Family history
- Review of systems (unless infection-related)
- Medication reconciliation lists
- Boilerplate text

**Task for Claude CLI:**
> Extend `hai-detection/hai_src/notes/chunker.py` to:
> 1. Parse common note section headers (Assessment, Plan, ID Consult, etc.)
> 2. Implement `extract_priority_sections(note_content: str, hai_type: HAIType) -> str`
> 3. Add section-based truncation that keeps high-value sections and drops low-value ones
> 4. Target output: <2000 chars per note, <6000 chars total across all notes

---

## Phase 3: Two-Stage Extraction Pipeline

Implement a fast first-pass with a smaller model, escalating to 70B only when needed.

### 3.1 Architecture Design

```
┌─────────────────────────────────────────────────────────────────┐
│                    Two-Stage Extraction                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Stage 1: Fast Triage (8B model, ~5 seconds)                   │
│  ┌─────────────────────────────────────────────┐               │
│  │ - Extract obvious findings                   │               │
│  │ - Flag documentation quality                 │               │
│  │ - Identify if complex reasoning needed       │               │
│  └─────────────────────────────────────────────┘               │
│                         │                                       │
│                         ▼                                       │
│              ┌──────────────────────┐                          │
│              │ Needs full analysis? │                          │
│              └──────────────────────┘                          │
│                    │           │                                │
│              No    │           │  Yes                          │
│                    ▼           ▼                                │
│  ┌─────────────────────┐  ┌─────────────────────────────┐     │
│  │ Use Stage 1 results │  │ Stage 2: Full Analysis (70B)│     │
│  │ → Rules Engine      │  │ ~60 seconds                  │     │
│  └─────────────────────┘  └─────────────────────────────┘     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Escalation triggers (go to Stage 2):**
- Documentation quality = "poor" or "limited"
- Possible alternate infection source mentioned
- Contamination signals present
- MBI-LCBI factors detected
- Clinical team impression ambiguous

### 3.2 Implement Fast Triage Extractor

**Task for Claude CLI:**
> Create `hai-detection/hai_src/extraction/triage_extractor.py` with:
> 1. `TriageExtraction` dataclass with simplified fields:
>    - `documentation_quality: str`
>    - `obvious_hai_signals: bool`
>    - `obvious_not_hai_signals: bool`
>    - `alternate_source_mentioned: bool`
>    - `contamination_mentioned: bool`
>    - `mbi_factors_present: bool`
>    - `needs_full_analysis: bool`
>    - `quick_reasoning: str`
> 2. `TriageExtractor` class that:
>    - Uses a smaller/faster model (configurable, default llama3.1:8b)
>    - Has a simplified prompt (~1000 tokens)
>    - Returns `TriageExtraction` in <10 seconds
> 3. `should_escalate(triage: TriageExtraction) -> bool` function

### 3.3 Integrate Two-Stage Pipeline

**Task for Claude CLI:**
> Modify `hai-detection/hai_src/classifiers/clabsi_classifier_v2.py` to:
> 1. Add `use_triage: bool = True` parameter to `__init__`
> 2. In `classify()`, first run triage extraction
> 3. If `should_escalate()` returns False, use triage results directly
> 4. If escalation needed, run full extraction
> 5. Log which path was taken for analysis
> 
> Create similar modifications for other classifiers (CAUTI, VAE, SSI, CDI)

---

## Phase 4: Model and Inference Optimization

### 4.1 Evaluate Alternative Quantizations

Test different quantization levels for speed/accuracy tradeoff.

| Quantization | VRAM (70B) | Speed | Quality |
|--------------|-----------|-------|---------|
| Q4_K_M | ~40GB | Baseline | Good |
| Q5_K_M | ~48GB | -10% | Better |
| Q4_K_S | ~38GB | +10% | Slightly worse |
| Q3_K_M | ~32GB | +20% | Noticeably worse |

**Task for Claude CLI:**
> Create `hai-detection/scripts/evaluate_quantizations.py` that:
> 1. Loads a test set of 20 cases with known classifications
> 2. Runs each through extraction with different model quantizations
> 3. Compares extraction quality (using a scoring rubric)
> 4. Reports speed vs accuracy tradeoff for each

### 4.2 Optimize Ollama Settings

Current Ollama configuration may not be optimal.

**Task for Claude CLI:**
> Review and update `hai-detection/hai_src/llm/ollama.py`:
> 1. Add `num_gpu` parameter to control GPU layer offloading
> 2. Add `num_batch` parameter for batch size tuning
> 3. Experiment with `num_ctx` values (4096, 8192, 16384) and document impact
> 4. Add `mirostat` sampling option for potentially better quality
> 5. Create a configuration guide documenting optimal settings

### 4.3 Evaluate ExLlamaV2 as Alternative Backend

ExLlamaV2 handles mixed VRAM better than vLLM and may be faster than Ollama.

**Task for Claude CLI:**
> Create `hai-detection/hai_src/llm/exllamav2_client.py`:
> 1. Implement `ExLlamaV2Client(BaseLLMClient)`
> 2. Support loading models with explicit VRAM allocation per GPU
> 3. Implement `generate()` and `generate_structured()` methods
> 4. Add to factory in `hai-detection/hai_src/llm/factory.py`
> 
> Note: This requires installing exllamav2 package

---

## Phase 5: Accuracy Improvements

### 5.1 Improve Extraction Prompts

Current prompts may be leaving accuracy on the table.

**Task for Claude CLI:**
> Review the extraction prompts in `hai-detection/prompts/` and improve:
> 1. Add few-shot examples showing correct extractions
> 2. Add explicit instructions for edge cases
> 3. Clarify confidence level definitions with examples
> 4. Add chain-of-thought reasoning instructions
> 5. Test improved prompts against baseline

### 5.2 Implement Confidence Calibration

LLM confidence levels may not be well-calibrated.

**Task for Claude CLI:**
> Create `hai-detection/hai_src/calibration/confidence.py`:
> 1. `ConfidenceCalibrator` class that learns from validated cases
> 2. `calibrate(raw_confidence: float, hai_type: HAIType) -> float`
> 3. `plot_calibration_curve()` for visualization
> 4. Integration point in classifiers to apply calibration

### 5.3 Add Extraction Validation

Catch obvious extraction errors before they reach the rules engine.

**Task for Claude CLI:**
> Create `hai-detection/hai_src/extraction/validators.py`:
> 1. `validate_clabsi_extraction(extraction: ClinicalExtraction) -> list[str]`
>    - Check for logical inconsistencies
>    - Flag impossible combinations
>    - Return list of warnings
> 2. Similar validators for each HAI type
> 3. Integration into classifiers with option to re-extract on validation failure

---

## Phase 6: Testing and Validation

### 6.1 Create Gold Standard Test Dataset

**Task for Claude CLI:**
> Create `hai-detection/tests/data/gold_standard/` with:
> 1. 10 clear CLABSI cases (should classify as HAI)
> 2. 10 clear non-CLABSI cases (secondary BSI, contamination)
> 3. 10 edge cases (MBI-LCBI, multiple possible sources)
> 4. Similar sets for CAUTI, VAE, SSI, CDI
> 5. JSON format with candidate data, notes, expected classification, and rationale

### 6.2 Implement Accuracy Metrics

**Task for Claude CLI:**
> Create `hai-detection/scripts/evaluate_accuracy.py`:
> 1. Load gold standard cases
> 2. Run through full pipeline
> 3. Calculate metrics:
>    - Sensitivity (true positive rate)
>    - Specificity (true negative rate)
>    - PPV/NPV
>    - Agreement with gold standard
> 4. Stratify by HAI type and documentation quality

### 6.3 Implement Regression Testing

**Task for Claude CLI:**
> Create `hai-detection/tests/test_regression.py`:
> 1. Pytest-based regression tests
> 2. Tests that specific known cases produce expected outputs
> 3. Tests that optimizations don't break accuracy
> 4. CI-friendly output format

---

## Phase 7: Integration Preparation

### 7.1 Epic FHIR Requirements Documentation

**Task for Claude CLI:**
> Create `hai-detection/docs/EPIC_INTEGRATION.md`:
> 1. Document required FHIR resources and scopes
> 2. List Epic-specific considerations
> 3. Authentication flow (SMART on FHIR)
> 4. Rate limiting and error handling requirements
> 5. Data refresh strategy (real-time vs batch)

### 7.2 Monitoring and Logging

**Task for Claude CLI:**
> Create `hai-detection/hai_src/monitoring/metrics.py`:
> 1. Track per-case processing time
> 2. Track model inference latency
> 3. Track escalation rate (triage → full)
> 4. Track classification distribution
> 5. Optional: Prometheus-compatible metrics export

---

## Optimization Checklist

### Quick Wins (Do First)
- [ ] Profile current performance
- [ ] Implement keyword-based note filtering
- [ ] Pull structured data from FHIR (temps, labs, meds)
- [ ] Reduce default context window in Ollama

### Medium Effort (High Impact)
- [ ] Implement two-stage triage pipeline
- [ ] Section-based note parsing
- [ ] Improve extraction prompts with examples
- [ ] Test alternative quantizations

### Larger Investments (If Needed)
- [ ] Implement ExLlamaV2 backend
- [ ] Embedding-based note retrieval (ChromaDB/FAISS)
- [ ] Fine-tune smaller model for triage
- [ ] Batch processing optimization

---

## Success Metrics

| Metric | Current | Target | Stretch |
|--------|---------|--------|---------|
| Per-case latency | 90s | <30s | <15s |
| Cases/hour | 40 | 120 | 240 |
| Sensitivity | TBD | >95% | >98% |
| Specificity | TBD | >90% | >95% |
| Escalation rate | N/A | <30% | <20% |

---

## Notes

Use this section to track observations and decisions as you work through optimizations.

### Observations
- 

### Decisions Made
- 

### Performance Log
| Date | Change | Latency Before | Latency After | Notes |
|------|--------|---------------|---------------|-------|
| | | | | |

---

*Last updated: January 2026*
