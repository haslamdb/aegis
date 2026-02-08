"""HAI Detection business logic.

This package contains the core HAI detection pipeline migrated from the
Flask standalone application. Import paths have been adapted for the
Django project structure.

Subpackages:
    candidates - Rule-based HAI candidate detection
    classifiers - LLM-based HAI classification
    rules - NHSN rules engine for deterministic classification
    extraction - LLM clinical information extraction
    notes - Clinical note processing utilities
    llm - LLM backend abstraction layer
    data - Data source abstractions (FHIR, Clarity)
    alerters - Notification alerters (Teams, email)
    review - Human-in-the-loop review workflow
"""
