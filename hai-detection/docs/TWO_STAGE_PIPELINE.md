# Two-Stage Classification Pipeline

This document describes the two-stage LLM classification pipeline for HAI detection, including performance profiling, escalation tracking, and training data collection for future model fine-tuning.

## Overview

The two-stage pipeline reduces classification latency by using a fast triage model (7B) to screen cases before invoking the full extraction model (70B).

```
┌─────────────────────────────────────────────────────────────────┐
│                    Two-Stage Pipeline                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Stage 1: Fast Triage (Qwen2.5-7B, ~1 second)                  │
│  ┌─────────────────────────────────────────────┐               │
│  │ - Quick assessment of documentation         │               │
│  │ - Identify obvious HAI / non-HAI signals    │               │
│  │ - Detect complexity indicators              │               │
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
│  │ Fast Path (~1s)     │  │ Stage 2: Full (70B, ~60s)   │     │
│  │ Use triage results  │  │ Complete extraction         │     │
│  └─────────────────────┘  └─────────────────────────────┘     │
│            │                          │                         │
│            └──────────┬───────────────┘                        │
│                       ▼                                         │
│              ┌──────────────────┐                              │
│              │   Rules Engine   │                              │
│              │   (Deterministic)│                              │
│              └──────────────────┘                              │
│                       │                                         │
│                       ▼                                         │
│              ┌──────────────────┐                              │
│              │  Classification  │                              │
│              └──────────────────┘                              │
└─────────────────────────────────────────────────────────────────┘
```

## Performance Benchmarks

### Model Comparison (January 2026)

| Model | Role | Speed | Triage Time | Full Extraction |
|-------|------|-------|-------------|-----------------|
| qwen2.5:7b | Triage | 119 tok/s | ~1s | N/A |
| gemma2:27b | Alt Triage | 38 tok/s | ~4s | N/A |
| llama3.3:70b | Full Extraction | 15 tok/s | N/A | ~60-90s |

### Hardware

- **GPU 1**: NVIDIA RTX A6000 (48GB VRAM)
- **GPU 2**: NVIDIA RTX A5000 (24GB VRAM)

### Time Breakdown (70B Model)

From profiling data:
- **Prefill (context processing)**: ~1-5% of time
- **Generation (output tokens)**: ~85-90% of time
- **Model loading (cold start)**: +6-8 seconds

Key insight: Context reduction has minimal impact. The bottleneck is output token generation.

## Escalation Triggers

Cases are escalated from triage to full extraction when ANY of these conditions are detected:

| Trigger | Rationale |
|---------|-----------|
| Documentation quality: poor/limited | Not enough info for confident triage |
| Alternate infection source mentioned | Needs evaluation for secondary BSI |
| Contamination mentioned | Requires careful assessment |
| MBI-LCBI factors present | Complex immunocompromised logic |
| Multiple organisms | Polymicrobial requires full analysis |
| Clinical impression ambiguous | Team uncertainty requires deep dive |

## Usage

### Enabling Two-Stage Pipeline

```python
from hai_src.classifiers.clabsi_classifier_v2 import CLABSIClassifierV2

# Enable two-stage with default triage model (qwen2.5:7b)
classifier = CLABSIClassifierV2(use_triage=True)

# Or specify triage model
classifier = CLABSIClassifierV2(
    use_triage=True,
    triage_model="qwen2.5:7b"
)

# Classify a candidate
classification = classifier.classify(candidate, notes)

# Check which path was taken
metrics = classifier.last_metrics
print(f"Path: {metrics.path}")  # triage_only, triage_escalated, or full_only
print(f"Triage time: {metrics.triage_ms}ms")
```

### Profiling

```bash
# Run profiling demo
python scripts/profile_llm.py demo --scenario clabsi -n 5

# View summary of collected profiles
python scripts/profile_llm.py summary

# Run context size benchmark
python scripts/profile_llm.py benchmark

# Export profiles for analysis
python scripts/profile_llm.py export -o profiles.json
```

### Testing Triage

```bash
# Test triage extractor only
python scripts/test_triage_pipeline.py --triage-only

# Test full two-stage pipeline
python scripts/test_triage_pipeline.py

# Compare with/without triage
python scripts/test_triage_pipeline.py --no-triage
```

## Escalation Tracking

The system tracks escalation statistics for analysis and model improvement.

### Tracked Metrics

- Escalation rate by HAI type
- Escalation triggers distribution
- Fast path accuracy (when human review available)
- Time savings from fast path

### Accessing Escalation Stats

```python
from hai_src.extraction.training_collector import get_escalation_stats

stats = get_escalation_stats()
print(f"Overall escalation rate: {stats['escalation_rate']:.1%}")
print(f"By HAI type: {stats['by_hai_type']}")
print(f"By trigger: {stats['by_trigger']}")
```

---

## Training Data Collection

All extractions are logged for future model fine-tuning. This enables:
1. Distilling 70B knowledge into smaller models
2. Learning CCHMC-specific terminology and note formats
3. Creating HAI-specific extraction models

### Data Collection Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Every Extraction (70B or reviewed 7B)                  │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Clinical Notes ──┬──► LLM Extraction ──► JSON Output   │
│                   │           │                 │       │
│              [input]     [model output]    [extraction] │
│                   │           │                 │       │
│                   ▼           ▼                 ▼       │
│              ┌─────────────────────────────────────┐   │
│              │     Training Data Store (JSONL)     │   │
│              │                                     │   │
│              │  - input: clinical notes            │   │
│              │  - output: extraction JSON          │   │
│              │  - hai_type: CLABSI/CAUTI/etc       │   │
│              │  - human_review: IP decision        │   │
│              │  - escalated: bool                  │   │
│              │  - timestamp                        │   │
│              └─────────────────────────────────────┘   │
│                              │                          │
│                              ▼                          │
│              ┌─────────────────────────────────────┐   │
│              │      After N cases (~500-2000)      │   │
│              │      Fine-tune smaller model        │   │
│              └─────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### Training Data Format

Each training example is stored as JSONL:

```json
{
  "id": "uuid",
  "timestamp": "2026-01-31T10:30:00Z",
  "hai_type": "CLABSI",
  "case_id": "candidate-123",

  "input": {
    "clinical_notes": "...",
    "patient_context": "...",
    "structured_data": {}
  },

  "output": {
    "extraction": {},
    "model": "llama3.3:70b",
    "tokens_in": 6234,
    "tokens_out": 847,
    "latency_ms": 75000
  },

  "triage": {
    "model": "qwen2.5:7b",
    "decision": "needs_full_analysis",
    "escalation_triggers": ["mbi_factors_present"],
    "latency_ms": 1100
  },

  "human_review": {
    "reviewer": "IP_nurse_1",
    "decision": "HAI_CONFIRMED",
    "reviewed_at": "2026-01-31T14:00:00Z",
    "corrections": null
  },

  "classification": {
    "decision": "HAI_CONFIRMED",
    "confidence": 0.92,
    "path": "triage_escalated"
  }
}
```

### Storage Location

```
hai-detection/
├── data/
│   └── training/
│       ├── extractions_2026_01.jsonl    # Monthly files
│       ├── extractions_2026_02.jsonl
│       └── escalation_stats.json        # Aggregated statistics
```

---

## Fine-Tuning Strategy

### Phase 1: Data Collection (Current)

Collect high-quality training examples:
- 70B extractions (teacher model)
- Human-reviewed cases (gold labels)
- Escalation decisions and triggers

**Target**: 500-2000 examples before first fine-tune attempt.

### Phase 2: Distillation

Fine-tune a smaller model to replicate 70B extraction quality:

```python
# Conceptual training setup (using QLoRA)
from trl import SFTTrainer
from peft import LoraConfig

lora_config = LoraConfig(
    r=16,
    lora_alpha=32,
    target_modules=["q_proj", "v_proj", "k_proj", "o_proj"],
    lora_dropout=0.05,
)

trainer = SFTTrainer(
    model="Qwen/Qwen2.5-7B-Instruct",
    train_dataset=extractions_dataset,  # Your collected data
    peft_config=lora_config,
    max_seq_length=4096,
)
trainer.train()
```

### Hardware Requirements

| Resource | Requirement |
|----------|-------------|
| GPU VRAM | 20-24GB (A5000 sufficient) |
| Training examples | 500-2000 |
| Training time | 2-8 hours |
| Approach | QLoRA (trains ~1-2% of parameters) |

### Expected Benefits

| Benefit | Impact |
|---------|--------|
| Consistent JSON schema | Fewer parsing errors |
| CCHMC terminology | Learns local note formats |
| Shorter prompts | No few-shot examples needed |
| Implicit NHSN logic | Better edge case handling |
| Potential for 3B model | Even faster inference |

---

## TODO: Accuracy Validation

Before production use of two-stage pipeline, validate:

1. **Fast-path accuracy**: Compare triage-only classifications to what full extraction would produce
2. **Escalation sensitivity**: Ensure complex cases are correctly escalated
3. **False confidence detection**: Identify cases where triage was confident but wrong

### Validation Script (To Be Implemented)

```bash
# Run labeled cases through both paths
python scripts/validate_triage_accuracy.py \
    --test-set tests/data/gold_standard/ \
    --compare-paths
```

### Metrics to Track

| Metric | Target | Description |
|--------|--------|-------------|
| Escalation rate | 20-40% | Too high = no speedup, too low = missing complexity |
| Fast-path agreement | >95% | Triage-only should match full extraction |
| False negative rate | <2% | Cases that should escalate but didn't |

---

## Files Added/Modified

### New Files

| File | Purpose |
|------|---------|
| `hai_src/extraction/triage_extractor.py` | Fast triage extraction with 7B model |
| `hai_src/extraction/training_collector.py` | Training data and escalation tracking |
| `scripts/profile_llm.py` | LLM profiling utilities |
| `scripts/test_triage_pipeline.py` | Two-stage pipeline testing |
| `docs/TWO_STAGE_PIPELINE.md` | This documentation |

### Modified Files

| File | Changes |
|------|---------|
| `hai_src/llm/base.py` | Added `LLMProfile`, `StructuredLLMResponse` |
| `hai_src/llm/ollama.py` | Added profiling, timing breakdown |
| `hai_src/classifiers/clabsi_classifier_v2.py` | Added two-stage pipeline support |
| `hai_src/extraction/*_extractor.py` | Added profile_context to all extractors |

---

*Last updated: January 2026*
