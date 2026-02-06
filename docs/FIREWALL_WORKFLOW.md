# AEGIS Firewall Workflow Guide

## Overview

This document provides a practical implementation plan for developing AEGIS when the production/sandbox environment is behind a hospital firewall without internet access. The goal is to maintain development velocity while ensuring compliance with PHI security requirements.

## Core Strategy: Develop Outside, Deploy Inside

All primary development, architecture, and debugging happens in the unrestricted environment with synthetic data. Code is transferred to the firewall environment only for validation against real Epic data.

---

## 1. Synthetic Data Layer (HIGH PRIORITY)

### Goal
Create a comprehensive synthetic data generator that mirrors Epic FHIR structures closely enough to catch 90%+ of issues before deployment.

### Implementation Steps

#### Phase 1: Data Structure Mapping (Week 1)
- [ ] Document all Epic FHIR resources AEGIS consumes
  - Patient demographics
  - Encounter data
  - Medications (antibiotics, antivirals, antifungals)
  - Lab results (cultures, susceptibilities, CBC, metabolic panels)
  - Procedures
  - Devices (ventilators, central lines, urinary catheters)
  - Vital signs
- [ ] Document all Epic SQL queries (if any direct database access)
- [ ] Create `docs/EPIC_DATA_SCHEMA.md` with detailed field mappings

#### Phase 2: Synthetic Data Generator (Week 2-3)
- [ ] Create `src/aegis/testing/synthetic_data/` module
- [ ] Implement generators for each FHIR resource type
  - Use `Faker` for realistic names, dates, MRNs
  - Use medical-specific libraries (e.g., `mimesis[medical]`) for codes
  - Ensure temporal coherence (admission → cultures → antibiotics → outcomes)
- [ ] Create scenario generators:
  - CLABSI scenarios (with/without criteria met)
  - CAUTI scenarios
  - VAP scenarios
  - Negative cases
  - Edge cases (missing data, ambiguous criteria)
- [ ] Add data quality issues that mirror real Epic quirks:
  - Missing fields
  - Inconsistent coding systems
  - Temporal gaps
  - Duplicate entries

#### Phase 3: Validation Framework (Week 4)
- [ ] Create test suite that runs on synthetic data
- [ ] Document known differences between synthetic and real data
- [ ] Create `configs/synthetic_data_profile.yaml` for easy switching
- [ ] Validate against any existing Epic sandbox data you have now

**Files to Create:**
```
src/aegis/testing/synthetic_data/
├── __init__.py
├── fhir_generators.py
├── scenario_builder.py
├── edge_cases.py
└── validators.py
docs/EPIC_DATA_SCHEMA.md
configs/synthetic_data_profile.yaml
```

---

## 2. Robust Logging & Error Capture

### Goal
When issues occur behind the firewall, generate detailed, de-identified error reports that can be shared with Claude for debugging.

### Implementation Steps

#### Phase 1: Logging Infrastructure (Week 1)
- [ ] Implement structured logging throughout AEGIS
  ```python
  import structlog
  logger = structlog.get_logger()
  logger.info("processing_patient",
              patient_id_hash=hash(patient_id),  # Never log real MRN
              encounter_type=encounter_type,
              processing_stage="nhsn_criteria")
  ```
- [ ] Configure log levels for different environments:
  - Development: DEBUG
  - Testing: INFO
  - Production: WARNING + structured events
- [ ] Create PHI-safe logging helper:
  ```python
  def safe_log_patient(patient_id):
      """Returns first 6 chars of SHA256 hash"""
      return hashlib.sha256(patient_id.encode()).hexdigest()[:6]
  ```

#### Phase 2: Error Context Capture (Week 2)
- [ ] Implement exception handlers that capture:
  - Full stack trace
  - De-identified data state at error point
  - AEGIS version, config, environment
  - Recent log events leading to error
- [ ] Create error report generator:
  ```python
  # src/aegis/utils/error_reporter.py
  class ErrorReporter:
      def generate_report(self, exception, context):
          """Generates PHI-safe error report for external debugging"""
          return {
              'error_type': type(exception).__name__,
              'stack_trace': self._sanitize_trace(exception),
              'context': self._deidentify_context(context),
              'recent_logs': self._get_recent_logs(minutes=5),
              'config_snapshot': self._get_config(),
              'data_structure': self._describe_structure(context.data)
          }
  ```

#### Phase 3: Export Mechanism (Week 3)
- [ ] Create `aegis export-error-report <error_id>` CLI command
- [ ] Generates markdown report in `/tmp/aegis_error_reports/`
- [ ] Includes:
  - Sanitized stack trace
  - Data structure description (types, null counts, not values)
  - Configuration diff from default
  - Steps to reproduce with synthetic data
- [ ] Add validation check that scans for potential PHI before export

**Files to Create:**
```
src/aegis/utils/
├── error_reporter.py
├── phi_sanitizer.py
└── log_exporter.py
src/aegis/cli/export_error.py
```

---

## 3. Abstract Epic Integration Layer

### Goal
Isolate Epic-specific code so that all complex logic can be developed with mock data sources.

### Implementation Steps

#### Phase 1: Data Access Abstraction (Week 1)
- [ ] Create abstract base class for data access:
  ```python
  # src/aegis/data_sources/base.py
  from abc import ABC, abstractmethod

  class DataSource(ABC):
      @abstractmethod
      def get_patient(self, patient_id) -> Patient:
          pass

      @abstractmethod
      def get_encounters(self, patient_id, date_range) -> List[Encounter]:
          pass

      @abstractmethod
      def get_medications(self, encounter_id) -> List[Medication]:
          pass

      # ... other data access methods
  ```

- [ ] Implement Epic FHIR version:
  ```python
  # src/aegis/data_sources/epic_fhir.py
  class EpicFHIRDataSource(DataSource):
      def __init__(self, fhir_client):
          self.client = fhir_client

      def get_patient(self, patient_id):
          # Epic FHIR API calls here
          pass
  ```

- [ ] Implement synthetic version:
  ```python
  # src/aegis/data_sources/synthetic.py
  class SyntheticDataSource(DataSource):
      def __init__(self, scenario_file):
          self.scenarios = load_scenarios(scenario_file)

      def get_patient(self, patient_id):
          # Return synthetic data
          pass
  ```

#### Phase 2: Configuration-Based Switching (Week 1)
- [ ] Add data source configuration to `configs/`:
  ```yaml
  # configs/dev.yaml
  data_source:
    type: "synthetic"
    scenario_file: "test_scenarios/clabsi_cases.json"

  # configs/prod.yaml
  data_source:
    type: "epic_fhir"
    endpoint: "${EPIC_FHIR_ENDPOINT}"
    credentials: "${EPIC_CREDENTIALS_PATH}"
  ```

- [ ] Create factory pattern for data source instantiation:
  ```python
  # src/aegis/data_sources/factory.py
  def get_data_source(config):
      if config.data_source.type == "epic_fhir":
          return EpicFHIRDataSource(...)
      elif config.data_source.type == "synthetic":
          return SyntheticDataSource(...)
  ```

#### Phase 3: Integration Testing (Week 2)
- [ ] Create test suite that runs identical logic against both data sources
- [ ] Document expected behavior differences (if any)
- [ ] Create "smoke test" script for quick validation behind firewall

**Files to Create:**
```
src/aegis/data_sources/
├── __init__.py
├── base.py
├── epic_fhir.py
├── synthetic.py
└── factory.py
tests/integration/test_data_source_parity.py
```

---

## 4. Local LLM Coding Assistant (Behind Firewall)

### Goal
Provide basic coding assistance for quick fixes behind the firewall without internet access.

### Implementation Options

#### Option A: DeepSeek Coder (Recommended)
- **Model**: DeepSeek Coder 33B
- **Hardware**: Your existing GPU workstation
- **Capabilities**: Code completion, debugging, refactoring
- **Setup time**: ~2 hours
- **Use case**: Quick fixes, boilerplate, routine debugging

#### Option B: CodeLlama
- **Model**: CodeLlama 34B
- **Hardware**: GPU workstation
- **Capabilities**: Similar to DeepSeek
- **Use case**: Alternative if DeepSeek doesn't work well

#### Option C: Continue.dev + Local Model
- **Tool**: VS Code extension
- **Backend**: Ollama running DeepSeek/CodeLlama
- **Benefit**: IDE integration

### Implementation Steps

#### Phase 1: Setup (Before moving behind firewall)
- [ ] Install Ollama on GPU workstation
  ```bash
  curl -fsSL https://ollama.com/install.sh | sh
  ```
- [ ] Download model (while you have internet):
  ```bash
  ollama pull deepseek-coder:33b
  # or
  ollama pull codellama:34b
  ```
- [ ] Test model on AEGIS codebase:
  ```bash
  ollama run deepseek-coder:33b
  ```
- [ ] Install Continue.dev in VS Code
- [ ] Configure Continue to use local Ollama endpoint

#### Phase 2: Documentation (Week 1)
- [ ] Create `docs/LOCAL_LLM_USAGE.md` with:
  - When to use local LLM vs bringing problem outside
  - Example prompts that work well
  - Limitations and failure modes
  - How to format code context for best results

#### Phase 3: Testing (Week 2)
- [ ] Test on representative AEGIS tasks:
  - Debugging a stack trace
  - Adding logging to a function
  - Refactoring a class
  - Writing a unit test
- [ ] Document quality compared to Claude
- [ ] Create decision tree: "Local LLM or bring outside?"

**Decision Tree:**
```
Local LLM is good for:
- Adding print/log statements
- Simple refactoring (rename, extract method)
- Writing docstrings
- Routine unit tests
- Syntax errors and simple bugs

Bring to Claude outside for:
- Architecture decisions
- Complex debugging
- Algorithm design
- Performance optimization
- Anything that requires deep domain knowledge
```

---

## 5. Git-Based Workflow

### Goal
Use Git as the bridge between unrestricted and firewall environments with clear protocols.

### Implementation Steps

#### Phase 1: Repository Structure (Week 1)
- [ ] Create branch naming convention:
  ```
  dev/outside/<feature-name>    # Development outside firewall
  test/inside/<feature-name>    # Testing behind firewall
  fix/outside/<bug-id>          # Bug fixes developed outside
  hotfix/inside/<bug-id>        # Emergency fixes made inside
  ```
- [ ] Set up pre-commit hooks to check for PHI leakage:
  ```bash
  # .pre-commit-config.yaml
  repos:
    - repo: local
      hooks:
        - id: check-phi
          name: Check for PHI in commits
          entry: python scripts/check_phi_leak.py
          language: system
  ```

#### Phase 2: Transfer Protocol (Week 1)
- [ ] Create `scripts/prepare_for_transfer.sh`:
  ```bash
  #!/bin/bash
  # Prepares code for transfer to firewall environment
  # 1. Runs all tests on synthetic data
  # 2. Generates changelog
  # 3. Creates deployment package
  # 4. Verifies no PHI in logs/configs
  ```

- [ ] Create `scripts/return_from_firewall.sh`:
  ```bash
  #!/bin/bash
  # Processes code/logs returned from firewall
  # 1. Scans for PHI
  # 2. Extracts error reports
  # 3. Updates issue tracker
  ```

#### Phase 3: Error Report Workflow (Week 2)
- [ ] Create `logs/firewall_errors/` directory structure:
  ```
  logs/firewall_errors/
  ├── 2026-02-15_clabsi_detection_error/
  │   ├── error_report.md
  │   ├── sanitized_logs.txt
  │   ├── data_structure.json
  │   └── reproduce_synthetic.py
  ```

- [ ] Create template for error reports:
  ```markdown
  # Error Report: [Brief Description]

  ## Environment
  - AEGIS Version: vX.Y.Z
  - Python Version: 3.11.x
  - Date/Time: YYYY-MM-DD HH:MM
  - Config: [config profile name]

  ## Error
  ```
  [Sanitized stack trace]
  ```

  ## Context
  - Processing stage: [e.g., NHSN criteria evaluation]
  - Data structure: [types and shapes, not values]
  - Recent operations: [last 5 operations from logs]

  ## Reproduction
  ```python
  # Script to reproduce with synthetic data
  # Located at: reproduce_synthetic.py
  ```

  ## Hypothesis
  [Initial thoughts on what might be wrong]
  ```

#### Phase 4: Audit Trail (Week 3)
- [ ] Create `docs/DEPLOYMENT_LOG.md`:
  ```markdown
  # AEGIS Deployment Log

  ## 2026-02-15: Version 0.3.0 → Firewall Testing
  - **Deployed by**: David
  - **Branch**: dev/outside/clabsi-improvements
  - **Commit**: abc1234
  - **Changes**:
    - Added new CLABSI criteria
    - Improved logging
  - **Test results**: PASSED synthetic, TESTING real data
  - **Issues found**: None yet

  ## 2026-02-16: Bug fix returned
  - **Issue**: NoneType error in device tracking
  - **Fix location**: test/inside/clabsi-improvements
  - **Commit**: def5678
  - **Merged to**: dev/outside/clabsi-improvements
  - **Status**: Fix developed with Claude, ready for redeployment
  ```

**Files to Create:**
```
scripts/
├── prepare_for_transfer.sh
├── return_from_firewall.sh
├── check_phi_leak.py
└── git_workflow_helpers.sh
.pre-commit-config.yaml
logs/firewall_errors/.gitkeep
docs/DEPLOYMENT_LOG.md
templates/error_report_template.md
```

---

## Implementation Timeline

### Immediate (Before Firewall Access)
1. **Week 1-4**: Synthetic Data Layer (HIGHEST PRIORITY)
2. **Week 2-3**: Abstract Epic Integration Layer
3. **Week 3-4**: Logging Infrastructure

### Pre-Deployment (Final 2 Weeks Before Going Live)
4. **Week 5**: Git Workflow Setup
5. **Week 5**: Local LLM Installation & Testing
6. **Week 6**: End-to-end workflow test with existing sandbox (if available)

### Post-Deployment (Ongoing)
7. Refine synthetic data based on real data learnings
8. Optimize error reporting based on actual debugging needs
9. Document firewall workflow improvements

---

## Workflow Example: Feature Development

### Scenario: Add new CAUTI detection criteria

#### Outside Firewall (Development)
1. **Planning** (with Claude):
   - Design new criteria logic
   - Identify data requirements
   - Plan testing strategy

2. **Implementation** (with Claude):
   ```bash
   git checkout -b dev/outside/cauti-criteria-update
   # Develop feature with Claude assistance
   # Test against synthetic data
   pytest tests/ --cov=src/aegis/nhsn/cauti
   ```

3. **Pre-transfer validation**:
   ```bash
   ./scripts/prepare_for_transfer.sh dev/outside/cauti-criteria-update
   # Outputs: deployment_package_2026-02-15.zip
   ```

4. **Transfer**:
   - USB drive or approved file transfer to firewall environment
   - Or: Push to private Git server accessible from both sides

#### Inside Firewall (Testing)
5. **Deployment**:
   ```bash
   git checkout -b test/inside/cauti-criteria-update
   # Extract deployment package
   # Update configs for prod data source
   ```

6. **Testing**:
   ```bash
   # Run smoke tests
   aegis test --mode=smoke --real-data
   # Run full test suite
   aegis test --mode=full --real-data --date-range="2026-01-01:2026-01-31"
   ```

7. **Error encountered**:
   ```bash
   # Generate error report
   aegis export-error-report error_20260215_1432
   # Outputs: /tmp/aegis_error_reports/error_20260215_1432.md
   # + sanitized logs, data structure info, reproduction script
   ```

8. **Transfer back**:
   - Error report + logs moved to USB drive
   - Commit any emergency hotfixes to `hotfix/inside/` branch

#### Outside Firewall (Debugging)
9. **Analysis** (with Claude):
   ```bash
   # Copy error report to project
   cp /media/usb/error_20260215_1432.md logs/firewall_errors/
   # Load into Claude conversation
   # "Claude, help me debug this error report..."
   ```

10. **Fix** (with Claude):
    ```bash
    # Develop fix on original branch
    git checkout dev/outside/cauti-criteria-update
    # Create reproduction test from error report
    # Fix bug with Claude
    # Test fix against synthetic data
    git commit -m "Fix NoneType error in catheter day calculation"
    ```

11. **Prepare for redeployment**:
    ```bash
    ./scripts/prepare_for_transfer.sh dev/outside/cauti-criteria-update
    ```

12. **Repeat** until all tests pass on real data

---

## Decision Tree: When to Bring Problems Outside

```
Is this problem:
├─ Syntax error, typo, obvious fix?
│  └─ → Fix inside with local LLM or manually
├─ Missing log statement, docstring?
│  └─ → Fix inside with local LLM
├─ Logic error in criteria evaluation?
│  ├─ Can you reproduce with synthetic data?
│  │  ├─ Yes → Bring outside, fix with Claude, test inside
│  │  └─ No → Create error report, bring outside for Claude analysis
│  └─ → Bring outside for Claude
├─ Performance issue?
│  └─ → Bring outside with profiling data
├─ Architectural change needed?
│  └─ → Bring outside for Claude planning
└─ Data quality issue (not a code problem)?
   └─ → Document and handle separately
```

---

## PHI Safety Checklist

Before transferring ANY files from firewall environment:

- [ ] No MRNs, patient names, or identifiers in code
- [ ] No real dates (use relative dates or date ranges)
- [ ] Log files sanitized (no patient data)
- [ ] Error reports reviewed for PHI
- [ ] Test data does not contain real patient info
- [ ] Configuration files contain no PHI
- [ ] Git commits contain no PHI

**Tool**: Use `scripts/check_phi_leak.py` to scan files before transfer.

---

## Success Metrics

After 3 months of using this workflow, you should be able to:

1. **Develop 80%+ of features** without needing firewall access
2. **Debug 90%+ of issues** using error reports + Claude outside
3. **Turnaround time** for bug fixes: < 24 hours (outside → inside → outside → inside)
4. **Code quality**: No degradation from slower iteration cycle
5. **PHI safety**: Zero incidents of PHI leaving firewall environment

---

## Tools Summary

### Scripts to Create
- `scripts/prepare_for_transfer.sh` - Pre-deployment validation
- `scripts/return_from_firewall.sh` - Post-deployment processing
- `scripts/check_phi_leak.py` - PHI scanning
- `src/aegis/cli/export_error.py` - Error report generation

### Configuration Files
- `configs/synthetic_data_profile.yaml` - Synthetic data config
- `configs/dev.yaml` - Outside development config
- `configs/prod.yaml` - Inside production config
- `.pre-commit-config.yaml` - PHI leak prevention

### Documentation
- `docs/EPIC_DATA_SCHEMA.md` - Epic data structure reference
- `docs/LOCAL_LLM_USAGE.md` - Local LLM guide
- `docs/DEPLOYMENT_LOG.md` - Audit trail
- `templates/error_report_template.md` - Standard error report format

---

## Next Steps

1. **Review this document** with team/collaborators
2. **Prioritize implementation** based on when firewall access begins
3. **Start with synthetic data layer** - this is the foundation
4. **Test workflow** with current sandbox before real data access
5. **Create tracking issue** in GitHub Project Tracker

---

## Questions to Resolve

- [ ] What file transfer mechanism is approved for firewall boundary?
  - USB drive?
  - Secure file transfer portal?
  - Git server accessible from both sides?
- [ ] What are the formal PHI scanning requirements?
- [ ] Can we get a list of Epic FHIR quirks from Epic team before we start?
- [ ] Is there existing synthetic healthcare data we can use/adapt?
- [ ] What are the data retention policies for logs generated inside firewall?
- [ ] Do we need IRB approval for the error reporting workflow?

---

## References

- [FHIR R4 Specification](https://www.hl7.org/fhir/)
- [Epic on FHIR Documentation](https://fhir.epic.com/)
- [Synthea™ Patient Generator](https://synthetichealth.github.io/synthea/) - For synthetic data
- [Continue.dev](https://continue.dev/) - Local LLM IDE integration
- [Ollama](https://ollama.com/) - Local LLM runtime
