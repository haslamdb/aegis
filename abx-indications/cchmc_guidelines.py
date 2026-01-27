"""CCHMC Guidelines Engine for antibiotic appropriateness checking.

This module provides disease-specific antibiotic recommendations based on
Cincinnati Children's Hospital Pocket Docs (Bugs & Drugs) guidelines.

Complements the Chua ICD-10 classification:
- Chua answers: "Is this diagnosis an indication for antibiotics?"
- CCHMC answers: "What antibiotic should be used for this indication?"
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class AgentCategory(Enum):
    """Category for prescribed antibiotic relative to guideline."""
    FIRST_LINE = "first_line"
    ALTERNATIVE = "alternative"
    OFF_GUIDELINE = "off_guideline"
    NOT_ASSESSED = "not_assessed"


@dataclass
class AgentRecommendation:
    """Result of checking agent appropriateness against CCHMC guidelines."""
    disease_matched: str | None = None
    disease_id: str | None = None
    current_agent: str | None = None
    current_agent_category: AgentCategory = AgentCategory.NOT_ASSESSED
    first_line_agents: list[str] = field(default_factory=list)
    alternative_agents: list[str] = field(default_factory=list)
    recommendation: str = ""
    age_specific_notes: str = ""
    allergy_alternatives: list[str] = field(default_factory=list)
    duration_recommendation: str | None = None
    consults_recommended: list[str] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "disease_matched": self.disease_matched,
            "disease_id": self.disease_id,
            "current_agent": self.current_agent,
            "current_agent_category": self.current_agent_category.value,
            "first_line_agents": self.first_line_agents,
            "alternative_agents": self.alternative_agents,
            "recommendation": self.recommendation,
            "age_specific_notes": self.age_specific_notes,
            "allergy_alternatives": self.allergy_alternatives,
            "duration_recommendation": self.duration_recommendation,
            "consults_recommended": self.consults_recommended,
            "confidence": self.confidence,
        }


@dataclass
class DosingRecommendation:
    """Dosing recommendation for a specific drug."""
    drug_name: str
    drug_class: str
    route: str
    dose_mg_kg: str | float | None = None
    dose_mg_kg_day: str | float | None = None
    frequency: str | None = None
    max_single_dose_mg: int | None = None
    max_daily_dose_mg: int | None = None
    age_group: str | None = None
    indication: str | None = None
    notes: str = ""
    formulation: str | None = None
    renal_adjustment_required: bool = False
    hepatic_adjustment_required: bool = False
    therapeutic_monitoring_required: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "drug_name": self.drug_name,
            "drug_class": self.drug_class,
            "route": self.route,
            "dose_mg_kg": self.dose_mg_kg,
            "dose_mg_kg_day": self.dose_mg_kg_day,
            "frequency": self.frequency,
            "max_single_dose_mg": self.max_single_dose_mg,
            "max_daily_dose_mg": self.max_daily_dose_mg,
            "age_group": self.age_group,
            "indication": self.indication,
            "notes": self.notes,
            "formulation": self.formulation,
            "renal_adjustment_required": self.renal_adjustment_required,
            "hepatic_adjustment_required": self.hepatic_adjustment_required,
            "therapeutic_monitoring_required": self.therapeutic_monitoring_required,
        }


class CCHMCGuidelinesEngine:
    """Engine for CCHMC-specific antibiotic guidelines."""

    def __init__(
        self,
        disease_guidelines_path: str | Path | None = None,
        dosing_path: str | Path | None = None,
    ):
        """Initialize the CCHMC guidelines engine.

        Args:
            disease_guidelines_path: Path to cchmc_disease_guidelines.json
            dosing_path: Path to cchmc_antimicrobial_dosing.json
        """
        base_path = Path(__file__).parent / "data"

        if disease_guidelines_path is None:
            disease_guidelines_path = base_path / "cchmc_disease_guidelines.json"
        if dosing_path is None:
            dosing_path = base_path / "cchmc_antimicrobial_dosing.json"

        self.disease_guidelines_path = Path(disease_guidelines_path)
        self.dosing_path = Path(dosing_path)

        self.disease_guidelines: dict = {}
        self.dosing_data: dict = {}
        self.agent_normalization: dict[str, list[str]] = {}

        self._load_guidelines()
        self._load_dosing()
        self._build_icd10_index()

    def _load_guidelines(self) -> None:
        """Load disease guidelines from JSON."""
        if not self.disease_guidelines_path.exists():
            logger.warning(f"Disease guidelines not found: {self.disease_guidelines_path}")
            return

        with open(self.disease_guidelines_path, "r") as f:
            self.disease_guidelines = json.load(f)

        # Build agent normalization map
        self.agent_normalization = self.disease_guidelines.get("agent_normalization", {})

        logger.info(
            f"Loaded CCHMC disease guidelines: "
            f"{sum(len(sys.get('diseases', [])) for sys in self.disease_guidelines.get('body_systems', {}).values())} diseases"
        )

    def _load_dosing(self) -> None:
        """Load dosing data from JSON."""
        if not self.dosing_path.exists():
            logger.warning(f"Dosing data not found: {self.dosing_path}")
            return

        with open(self.dosing_path, "r") as f:
            self.dosing_data = json.load(f)

        logger.info(f"Loaded CCHMC dosing data: {len(self.dosing_data.get('drugs', []))} drugs")

    def _build_icd10_index(self) -> None:
        """Build index of ICD-10 codes to diseases for fast lookup."""
        self._icd10_index: dict[str, list[dict]] = {}

        body_systems = self.disease_guidelines.get("body_systems", {})
        for system_id, system_data in body_systems.items():
            for disease in system_data.get("diseases", []):
                # Index by exact codes
                for code in disease.get("icd10_codes", []):
                    if code not in self._icd10_index:
                        self._icd10_index[code] = []
                    self._icd10_index[code].append({
                        "system": system_id,
                        "disease": disease,
                    })

                # Index by patterns (prefixes)
                for pattern in disease.get("icd10_patterns", []):
                    key = f"pattern:{pattern}"
                    if key not in self._icd10_index:
                        self._icd10_index[key] = []
                    self._icd10_index[key].append({
                        "system": system_id,
                        "disease": disease,
                    })

    def _normalize_agent(self, agent_name: str) -> str:
        """Normalize an agent name to its canonical form.

        Args:
            agent_name: The agent name to normalize (e.g., "Augmentin")

        Returns:
            Canonical agent name (e.g., "amoxicillin_clavulanate")
        """
        if not agent_name:
            return ""

        agent_lower = agent_name.lower().strip()

        # Check if already canonical
        if agent_lower in self.agent_normalization:
            return agent_lower

        # Check aliases
        for canonical, aliases in self.agent_normalization.items():
            for alias in aliases:
                if alias.lower() == agent_lower or alias.lower() in agent_lower:
                    return canonical

        # Try partial matching for common patterns
        # Handle "ampicillin/sulbactam" style
        if "/" in agent_lower:
            parts = agent_lower.replace("/", "_").replace("-", "_")
            for canonical in self.agent_normalization.keys():
                if canonical == parts:
                    return canonical

        # Return lowercase version if no match
        return agent_lower.replace(" ", "_").replace("/", "_").replace("-", "_")

    def match_disease_from_icd10(self, icd10_codes: list[str]) -> list[dict]:
        """Match ICD-10 codes to CCHMC disease entities.

        Args:
            icd10_codes: List of ICD-10 diagnosis codes

        Returns:
            List of matched disease dictionaries with confidence scores
        """
        matches = []
        seen_disease_ids = set()

        for code in icd10_codes:
            code_upper = code.upper().strip()

            # Try exact match first
            if code_upper in self._icd10_index:
                for entry in self._icd10_index[code_upper]:
                    disease = entry["disease"]
                    disease_id = disease.get("disease_id")
                    if disease_id not in seen_disease_ids:
                        seen_disease_ids.add(disease_id)
                        matches.append({
                            "disease": disease,
                            "system": entry["system"],
                            "matched_code": code_upper,
                            "match_type": "exact",
                            "confidence": 1.0,
                        })

            # Try pattern matching
            for key, entries in self._icd10_index.items():
                if key.startswith("pattern:"):
                    pattern = key[8:]  # Remove "pattern:" prefix
                    if code_upper.startswith(pattern):
                        for entry in entries:
                            disease = entry["disease"]
                            disease_id = disease.get("disease_id")
                            if disease_id not in seen_disease_ids:
                                seen_disease_ids.add(disease_id)
                                matches.append({
                                    "disease": disease,
                                    "system": entry["system"],
                                    "matched_code": code_upper,
                                    "match_type": "pattern",
                                    "confidence": 0.9,
                                })

        # Sort by confidence (exact matches first)
        matches.sort(key=lambda x: x["confidence"], reverse=True)
        return matches

    def check_agent_appropriateness(
        self,
        icd10_codes: list[str],
        prescribed_agent: str,
        patient_age_months: int | None = None,
        allergies: list[str] | None = None,
    ) -> AgentRecommendation:
        """Check if prescribed antibiotic is appropriate for the indication.

        Args:
            icd10_codes: Patient's ICD-10 diagnosis codes
            prescribed_agent: The antibiotic that was prescribed
            patient_age_months: Patient age in months
            allergies: List of known allergies

        Returns:
            AgentRecommendation with appropriateness assessment
        """
        result = AgentRecommendation(
            current_agent=prescribed_agent,
            current_agent_category=AgentCategory.NOT_ASSESSED,
        )

        # Match diseases from ICD-10 codes
        disease_matches = self.match_disease_from_icd10(icd10_codes)

        if not disease_matches:
            result.recommendation = "No CCHMC guideline match for provided ICD-10 codes"
            return result

        # Use the highest confidence match
        best_match = disease_matches[0]
        disease = best_match["disease"]

        result.disease_matched = disease.get("name")
        result.disease_id = disease.get("disease_id")
        result.confidence = best_match["confidence"]
        result.consults_recommended = disease.get("consults", [])

        # Extract first-line and alternative agents
        first_line = disease.get("first_line", [])
        alternatives = disease.get("alternatives", [])
        allergy_alts = disease.get("allergy_alternatives", [])

        # Build lists of agent names
        first_line_agents = []
        for agent_entry in first_line:
            agent_name = agent_entry.get("agent", "")
            if agent_name and agent_name != "none":
                first_line_agents.append(agent_name)

        alternative_agents = []
        for agent_entry in alternatives:
            agent_name = agent_entry.get("agent", "")
            if agent_name:
                alternative_agents.append(agent_name)

        allergy_alternatives = []
        for agent_entry in allergy_alts:
            agent_name = agent_entry.get("agent", "")
            if agent_name:
                allergy_alternatives.append(agent_name)

        result.first_line_agents = first_line_agents
        result.alternative_agents = alternative_agents
        result.allergy_alternatives = allergy_alternatives

        # Check age-specific modifications
        age_mods = disease.get("age_modifications", [])
        if patient_age_months is not None and age_mods:
            for mod in age_mods:
                age_group = mod.get("age_group", "")
                if self._age_matches(patient_age_months, age_group):
                    mod_agents = mod.get("agents", [])
                    mod_notes = mod.get("notes", "")
                    if mod_agents:
                        result.age_specific_notes = f"For {age_group}: prefer {', '.join(mod_agents)}"
                        if mod_notes:
                            result.age_specific_notes += f". {mod_notes}"
                        # Add age-specific agents to first line
                        for agent in mod_agents:
                            if agent not in first_line_agents:
                                first_line_agents.append(agent)

        # Extract duration recommendation
        duration = None
        for agent_entry in first_line:
            dur = agent_entry.get("duration_days")
            if dur:
                duration = str(dur) + " days"
                break
        if duration:
            result.duration_recommendation = duration

        # Normalize the prescribed agent
        normalized_prescribed = self._normalize_agent(prescribed_agent)

        # Check if prescribed agent matches first-line
        is_first_line = False
        is_alternative = False
        is_allergy_alt = False

        for first_agent in first_line_agents:
            normalized_first = self._normalize_agent(first_agent)
            if self._agents_match(normalized_prescribed, normalized_first):
                is_first_line = True
                break

        if not is_first_line:
            for alt_agent in alternative_agents:
                normalized_alt = self._normalize_agent(alt_agent)
                if self._agents_match(normalized_prescribed, normalized_alt):
                    is_alternative = True
                    break

        if not is_first_line and not is_alternative and allergies:
            for allergy_agent in allergy_alternatives:
                normalized_allergy = self._normalize_agent(allergy_agent)
                if self._agents_match(normalized_prescribed, normalized_allergy):
                    is_allergy_alt = True
                    break

        # Determine category and recommendation
        if is_first_line:
            result.current_agent_category = AgentCategory.FIRST_LINE
            result.recommendation = f"{prescribed_agent} is a first-line agent for {result.disease_matched}"
        elif is_alternative:
            result.current_agent_category = AgentCategory.ALTERNATIVE
            result.recommendation = (
                f"{prescribed_agent} is an acceptable alternative for {result.disease_matched}. "
                f"First-line options: {', '.join(first_line_agents)}"
            )
        elif is_allergy_alt:
            result.current_agent_category = AgentCategory.ALTERNATIVE
            result.recommendation = (
                f"{prescribed_agent} is an allergy alternative for {result.disease_matched}"
            )
        else:
            result.current_agent_category = AgentCategory.OFF_GUIDELINE
            if first_line_agents:
                result.recommendation = (
                    f"{prescribed_agent} is not a guideline-recommended agent for {result.disease_matched}. "
                    f"Recommended: {', '.join(first_line_agents)}"
                )
            else:
                result.recommendation = (
                    f"No specific antibiotic recommended for {result.disease_matched} per CCHMC guidelines"
                )

        # Add notes from disease
        notes = disease.get("notes", "")
        if notes and result.recommendation:
            result.recommendation += f". Note: {notes}"

        return result

    def _age_matches(self, age_months: int, age_group: str) -> bool:
        """Check if patient age matches an age group specification.

        Args:
            age_months: Patient age in months
            age_group: Age group string (e.g., "<8 years", ">=6 months", "neonates")

        Returns:
            True if age matches the specification
        """
        age_group_lower = age_group.lower()

        # Convert months to relevant units
        age_days = age_months * 30
        age_years = age_months / 12

        # Handle common patterns
        if "neonate" in age_group_lower or age_group_lower == "<1 month":
            return age_months < 1
        if "<3 months" in age_group_lower:
            return age_months < 3
        if "<6 months" in age_group_lower:
            return age_months < 6
        if ">=6 months" in age_group_lower or ">= 6 months" in age_group_lower:
            return age_months >= 6
        if "<8 years" in age_group_lower:
            return age_years < 8
        if ">=8 years" in age_group_lower or ">= 8 years" in age_group_lower:
            return age_years >= 8
        if "<5 years" in age_group_lower:
            return age_years < 5
        if ">=5 years" in age_group_lower:
            return age_years >= 5
        if "sickle cell" in age_group_lower:
            return False  # Requires separate check
        if "<12 years" in age_group_lower:
            return age_years < 12
        if ">=12 years" in age_group_lower:
            return age_years >= 12

        return False

    def _agents_match(self, agent1: str, agent2: str) -> bool:
        """Check if two agent names refer to the same drug.

        Args:
            agent1: First agent name (normalized)
            agent2: Second agent name (normalized)

        Returns:
            True if they match
        """
        if not agent1 or not agent2:
            return False

        # Direct match
        if agent1 == agent2:
            return True

        # Check if one contains the other (for partial matches)
        if agent1 in agent2 or agent2 in agent1:
            return True

        # Normalize both and compare
        norm1 = self._normalize_agent(agent1)
        norm2 = self._normalize_agent(agent2)

        return norm1 == norm2

    def get_dosing_recommendation(
        self,
        drug_name: str,
        age_months: int | None = None,
        weight_kg: float | None = None,
        indication: str | None = None,
    ) -> DosingRecommendation | None:
        """Get dosing recommendation for a drug.

        Args:
            drug_name: Name of the drug
            age_months: Patient age in months
            weight_kg: Patient weight in kg (for dose calculations)
            indication: Specific indication (e.g., "meningitis")

        Returns:
            DosingRecommendation or None if not found
        """
        drugs = self.dosing_data.get("drugs", [])
        normalized_drug = self._normalize_agent(drug_name)

        # Find matching drug entry
        drug_entry = None
        for drug in drugs:
            generic_name = drug.get("generic_name", "").lower()
            drug_id = drug.get("drug_id", "").lower()
            brand_names = [b.lower() for b in drug.get("brand_names", [])]

            if (
                normalized_drug == generic_name
                or normalized_drug in drug_id
                or normalized_drug in brand_names
                or any(b in normalized_drug for b in brand_names)
            ):
                drug_entry = drug
                break

        if not drug_entry:
            return None

        # Find appropriate dosing entry
        dosing_entries = drug_entry.get("dosing", [])
        best_dosing = None

        for dosing in dosing_entries:
            # Check indication match
            dosing_indication = dosing.get("indication", "").lower()
            if indication and indication.lower() in dosing_indication:
                # Indication-specific match
                if age_months is not None:
                    age_group = dosing.get("age_group", "all")
                    if age_group == "all" or self._age_matches(age_months, age_group):
                        best_dosing = dosing
                        break
                else:
                    best_dosing = dosing
                    break
            elif not indication and dosing_indication in ["standard", ""]:
                # Standard dosing
                if age_months is not None:
                    age_group = dosing.get("age_group", "all")
                    if age_group == "all" or self._age_matches(age_months, age_group):
                        best_dosing = dosing
                        break
                else:
                    best_dosing = dosing
                    break

        # Fall back to first dosing entry if no specific match
        if best_dosing is None and dosing_entries:
            best_dosing = dosing_entries[0]

        if best_dosing is None:
            return None

        return DosingRecommendation(
            drug_name=drug_entry.get("generic_name", drug_name),
            drug_class=drug_entry.get("drug_class", ""),
            route=drug_entry.get("route", ""),
            dose_mg_kg=best_dosing.get("dose_mg_kg"),
            dose_mg_kg_day=best_dosing.get("dose_mg_kg_day"),
            frequency=best_dosing.get("frequency"),
            max_single_dose_mg=best_dosing.get("max_single_dose_mg"),
            max_daily_dose_mg=best_dosing.get("max_daily_dose_mg"),
            age_group=best_dosing.get("age_group"),
            indication=best_dosing.get("indication"),
            notes=best_dosing.get("notes", ""),
            formulation=best_dosing.get("formulation"),
            renal_adjustment_required=drug_entry.get("renal_adjustment", False),
            hepatic_adjustment_required=drug_entry.get("hepatic_adjustment", False),
            therapeutic_monitoring_required=drug_entry.get("therapeutic_monitoring", False),
        )

    def get_diseases_for_agent(self, agent_name: str) -> list[dict]:
        """Find all diseases where an agent is first-line or alternative.

        Args:
            agent_name: The antibiotic to search for

        Returns:
            List of disease info dictionaries
        """
        normalized_agent = self._normalize_agent(agent_name)
        matches = []

        body_systems = self.disease_guidelines.get("body_systems", {})
        for system_id, system_data in body_systems.items():
            for disease in system_data.get("diseases", []):
                # Check first-line
                for agent_entry in disease.get("first_line", []):
                    entry_agent = self._normalize_agent(agent_entry.get("agent", ""))
                    if self._agents_match(normalized_agent, entry_agent):
                        matches.append({
                            "disease_name": disease.get("name"),
                            "disease_id": disease.get("disease_id"),
                            "system": system_id,
                            "category": "first_line",
                            "indication": agent_entry.get("indication"),
                        })
                        break

                # Check alternatives
                for agent_entry in disease.get("alternatives", []):
                    entry_agent = self._normalize_agent(agent_entry.get("agent", ""))
                    if self._agents_match(normalized_agent, entry_agent):
                        matches.append({
                            "disease_name": disease.get("name"),
                            "disease_id": disease.get("disease_id"),
                            "system": system_id,
                            "category": "alternative",
                            "indication": agent_entry.get("indication"),
                        })
                        break

        return matches


# Module-level instance for convenience
_engine: CCHMCGuidelinesEngine | None = None


def get_guidelines_engine() -> CCHMCGuidelinesEngine:
    """Get or create the module-level guidelines engine instance."""
    global _engine
    if _engine is None:
        _engine = CCHMCGuidelinesEngine()
    return _engine


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)

    engine = CCHMCGuidelinesEngine()

    # Test disease matching
    print("=" * 70)
    print("CCHMC Guidelines Engine Test")
    print("=" * 70)

    # Test cases
    test_cases = [
        {
            "icd10_codes": ["J18.9"],
            "agent": "amoxicillin",
            "age_months": 36,
            "description": "CAP with amoxicillin (first-line)",
        },
        {
            "icd10_codes": ["J18.9"],
            "agent": "azithromycin",
            "age_months": 84,
            "description": "CAP with azithromycin (alternative for atypical)",
        },
        {
            "icd10_codes": ["A41.9"],
            "agent": "ceftriaxone",
            "age_months": 24,
            "description": "Sepsis with ceftriaxone (first-line)",
        },
        {
            "icd10_codes": ["L03.90"],
            "agent": "vancomycin",
            "age_months": 60,
            "description": "Cellulitis with vancomycin (may be off-guideline for non-purulent)",
        },
        {
            "icd10_codes": ["H66.009"],
            "agent": "ciprofloxacin",
            "age_months": 24,
            "description": "AOM with ciprofloxacin (off-guideline)",
        },
    ]

    for tc in test_cases:
        print(f"\n--- {tc['description']} ---")
        result = engine.check_agent_appropriateness(
            icd10_codes=tc["icd10_codes"],
            prescribed_agent=tc["agent"],
            patient_age_months=tc["age_months"],
        )
        print(f"ICD-10: {tc['icd10_codes']}, Agent: {tc['agent']}, Age: {tc['age_months']}mo")
        print(f"Disease: {result.disease_matched}")
        print(f"Category: {result.current_agent_category.value}")
        print(f"Recommendation: {result.recommendation}")
        if result.first_line_agents:
            print(f"First-line: {', '.join(result.first_line_agents)}")

    # Test dosing lookup
    print("\n" + "=" * 70)
    print("Dosing Lookup Test")
    print("=" * 70)

    dosing_tests = [
        ("amoxicillin", 36, "pneumonia"),
        ("ceftriaxone", 24, "meningitis"),
        ("vancomycin", 6, "bacteremia"),
    ]

    for drug, age, indication in dosing_tests:
        print(f"\n--- {drug} for {indication} (age {age}mo) ---")
        dosing = engine.get_dosing_recommendation(drug, age, indication=indication)
        if dosing:
            print(f"Dose: {dosing.dose_mg_kg or dosing.dose_mg_kg_day} mg/kg")
            print(f"Frequency: {dosing.frequency}")
            print(f"Max single dose: {dosing.max_single_dose_mg} mg")
            if dosing.notes:
                print(f"Notes: {dosing.notes}")
        else:
            print("No dosing found")
