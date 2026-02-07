"""FHIR client for dosing verification data fetching.

Extends the DrugBugFHIRClient pattern with additional methods for:
- Patient demographics (age, weight, height)
- Renal function (SCr, eGFR)
- Active antimicrobials with dosing details
- Allergies
- Co-medications
- Clinical indications
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Any

import requests

from .models import PatientContext, MedicationOrder

logger = logging.getLogger(__name__)


# Common antimicrobial classes for classification
ANTIMICROBIAL_KEYWORDS = [
    "penicillin", "amoxicillin", "ampicillin", "piperacillin", "ticarcillin", "nafcillin", "oxacillin",
    "cefazolin", "cefepime", "ceftriaxone", "ceftazidime", "cefuroxime", "cefotaxime", "cephalexin",
    "meropenem", "imipenem", "ertapenem", "doripenem",
    "aztreonam",
    "vancomycin", "daptomycin", "linezolid", "tedizolid",
    "ciprofloxacin", "levofloxacin", "moxifloxacin", "delafloxacin",
    "azithromycin", "clarithromycin", "erythromycin",
    "doxycycline", "minocycline", "tetracycline",
    "gentamicin", "tobramycin", "amikacin",
    "metronidazole", "clindamycin",
    "trimethoprim", "sulfamethoxazole", "bactrim",
    "nitrofurantoin", "fosfomycin",
    "fluconazole", "voriconazole", "posaconazole", "isavuconazole", "itraconazole",
    "amphotericin", "micafungin", "caspofungin", "anidulafungin",
    "acyclovir", "valacyclovir", "ganciclovir", "valganciclovir",
    "rifampin", "rifabutin", "isoniazid", "ethambutol", "pyrazinamide",
    "colistin", "polymyxin",
]


def is_antimicrobial(drug_name: str) -> bool:
    """Check if a drug is an antimicrobial based on name."""
    drug_lower = drug_name.lower()
    return any(keyword in drug_lower for keyword in ANTIMICROBIAL_KEYWORDS)


class DosingFHIRClient:
    """FHIR client for dosing verification data."""

    def __init__(self, fhir_url: str | None = None):
        """Initialize FHIR client.

        Args:
            fhir_url: Base URL for FHIR server. Defaults to FHIR_BASE_URL env var.
        """
        self.fhir_url = fhir_url or os.environ.get("FHIR_BASE_URL", "http://localhost:8081/fhir")
        logger.info(f"Initialized FHIR client: {self.fhir_url}")

    def _get(self, resource_type: str, params: dict | None = None) -> dict:
        """Execute FHIR GET request."""
        url = f"{self.fhir_url}/{resource_type}"
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"FHIR request failed: {e}")
            raise

    def get_patients_with_active_antimicrobials(self, lookback_hours: int = 24) -> list[str]:
        """Get list of patient MRNs with active antimicrobial orders.

        Args:
            lookback_hours: Hours to look back for orders

        Returns:
            List of patient MRNs
        """
        # TODO: Implement FHIR query for active antimicrobial MedicationRequests
        # For now, return empty list - will be implemented in Phase 2
        logger.warning("get_patients_with_active_antimicrobials not yet implemented")
        return []

    def get_patient_weight(self, patient_id: str) -> float | None:
        """Get most recent patient weight in kg."""
        try:
            result = self._get("Observation", {
                "patient": patient_id,
                "code": "29463-7",  # LOINC for body weight
                "_sort": "-date",
                "_count": "1"
            })
            if result.get("total", 0) > 0:
                obs = result["entry"][0]["resource"]
                return obs.get("valueQuantity", {}).get("value")
        except Exception as e:
            logger.debug(f"Failed to get weight for {patient_id}: {e}")
        return None

    def get_patient_height(self, patient_id: str) -> float | None:
        """Get most recent patient height in cm."""
        try:
            result = self._get("Observation", {
                "patient": patient_id,
                "code": "8302-2",  # LOINC for body height
                "_sort": "-date",
                "_count": "1"
            })
            if result.get("total", 0) > 0:
                obs = result["entry"][0]["resource"]
                return obs.get("valueQuantity", {}).get("value")
        except Exception as e:
            logger.debug(f"Failed to get height for {patient_id}: {e}")
        return None

    def get_serum_creatinine(self, patient_id: str) -> float | None:
        """Get most recent serum creatinine in mg/dL."""
        try:
            result = self._get("Observation", {
                "patient": patient_id,
                "code": "2160-0",  # LOINC for serum creatinine
                "_sort": "-date",
                "_count": "1"
            })
            if result.get("total", 0) > 0:
                obs = result["entry"][0]["resource"]
                return obs.get("valueQuantity", {}).get("value")
        except Exception as e:
            logger.debug(f"Failed to get SCr for {patient_id}: {e}")
        return None

    def get_egfr(self, patient_id: str) -> float | None:
        """Get most recent eGFR in mL/min."""
        try:
            result = self._get("Observation", {
                "patient": patient_id,
                "code": "33914-3",  # LOINC for eGFR
                "_sort": "-date",
                "_count": "1"
            })
            if result.get("total", 0) > 0:
                obs = result["entry"][0]["resource"]
                return obs.get("valueQuantity", {}).get("value")
        except Exception as e:
            logger.debug(f"Failed to get eGFR for {patient_id}: {e}")
        return None

    def get_all_active_medications(self, patient_id: str) -> list[MedicationOrder]:
        """Get all active medications for a patient.

        Returns:
            List of MedicationOrder objects
        """
        try:
            result = self._get("MedicationRequest", {
                "patient": patient_id,
                "status": "active"
            })

            medications = []
            if result.get("total", 0) > 0:
                for entry in result.get("entry", []):
                    med_req = entry["resource"]
                    try:
                        med_order = self._parse_medication_request(med_req)
                        if med_order:
                            medications.append(med_order)
                    except Exception as e:
                        logger.warning(f"Failed to parse medication: {e}")

            return medications

        except Exception as e:
            logger.error(f"Failed to get medications for {patient_id}: {e}")
            return []

    def _parse_medication_request(self, med_req: dict) -> MedicationOrder | None:
        """Parse FHIR MedicationRequest into MedicationOrder."""
        try:
            # Get medication name
            med_concept = med_req.get("medicationCodeableConcept", {})
            drug_name = med_concept.get("text", "Unknown")

            # Get dosing instruction
            dosage = med_req.get("dosageInstruction", [{}])[0]
            dose_and_rate = dosage.get("doseAndRate", [{}])[0]
            dose_qty = dose_and_rate.get("doseQuantity", {})

            dose_value = dose_qty.get("value", 0)
            dose_unit = dose_qty.get("unit", "mg")

            # Get interval from timing
            timing = dosage.get("timing", {})
            repeat = timing.get("repeat", {})
            period = repeat.get("period", 24)
            interval = f"q{int(period)}h"

            # Get route
            route_concept = dosage.get("route", {})
            route_coding = route_concept.get("coding", [{}])[0]
            route = route_coding.get("display", "IV")

            # Calculate frequency hours
            frequency_hours = int(period)

            # Get order details
            order_id = med_req.get("id", "")
            start_date = med_req.get("authoredOn", "")

            return MedicationOrder(
                drug_name=drug_name,
                dose_value=float(dose_value),
                dose_unit=dose_unit,
                interval=interval,
                route=route,
                frequency_hours=frequency_hours,
                daily_dose=0,  # Will be calculated
                daily_dose_per_kg=None,  # Will be calculated if weight available
                start_date=start_date,
                order_id=order_id,
                infusion_duration_minutes=None,
                rxnorm_code=None,
            )

        except Exception as e:
            logger.warning(f"Failed to parse medication request: {e}")
            return None

    def get_dialysis_status(self, patient_id: str) -> dict | None:
        """Get dialysis status for a patient."""
        # TODO: Query for dialysis procedures
        return None

    def get_allergies(self, patient_id: str) -> list[dict]:
        """Get patient allergies.

        Returns:
            List of dicts with substance, severity, reaction
        """
        try:
            result = self._get("AllergyIntolerance", {
                "patient": patient_id,
                "clinical-status": "active"
            })

            allergies = []
            if result.get("total", 0) > 0:
                for entry in result.get("entry", []):
                    allergy = entry["resource"]
                    try:
                        substance = allergy.get("code", {}).get("text", "Unknown")
                        reactions = allergy.get("reaction", [])
                        severity = "moderate"
                        reaction_text = "Unknown"

                        if reactions:
                            reaction = reactions[0]
                            severity = reaction.get("severity", "moderate")
                            manifestation = reaction.get("manifestation", [{}])[0]
                            reaction_text = manifestation.get("text", "Unknown")

                        allergies.append({
                            "substance": substance,
                            "severity": severity,
                            "reaction": reaction_text,
                        })
                    except Exception as e:
                        logger.warning(f"Failed to parse allergy: {e}")

            return allergies

        except Exception as e:
            logger.error(f"Failed to get allergies for {patient_id}: {e}")
            return []

    def build_patient_context(self, patient_mrn: str, indication: str = None) -> PatientContext | None:
        """Assemble complete PatientContext from FHIR for rules engine.

        Args:
            patient_mrn: Patient MRN
            indication: Optional indication (will be fetched from ABX Indications module if None)

        Returns:
            PatientContext object or None if patient not found
        """
        try:
            # Get patient by MRN
            result = self._get("Patient", {"identifier": patient_mrn})
            if result.get("total", 0) == 0:
                logger.warning(f"Patient {patient_mrn} not found")
                return None

            patient = result["entry"][0]["resource"]
            patient_id = patient["id"]

            # Get patient name
            name = patient.get("name", [{}])[0]
            patient_name = f"{name.get('given', [''])[0]} {name.get('family', '')}"

            # Calculate age from birthDate
            birth_date_str = patient.get("birthDate")
            age_years = None
            if birth_date_str:
                birth_date = datetime.fromisoformat(birth_date_str)
                age_years = (datetime.now() - birth_date).days / 365.25

            # Get patient factors
            weight_kg = self.get_patient_weight(patient_id)
            height_cm = self.get_patient_height(patient_id)
            scr = self.get_serum_creatinine(patient_id)
            gfr = self.get_egfr(patient_id)

            # Get medications
            all_meds = self.get_all_active_medications(patient_id)

            # Separate antimicrobials from co-medications
            antimicrobials = [med for med in all_meds if is_antimicrobial(med.drug_name)]
            co_medications = [med for med in all_meds if not is_antimicrobial(med.drug_name)]

            # Get allergies
            allergies = self.get_allergies(patient_id)

            # Get indication (from ABX Indications module if not provided)
            if indication is None:
                # TODO: Query ABX Indications database
                indication = None

            # Build context
            context = PatientContext(
                patient_id=patient_id,
                patient_mrn=patient_mrn,
                patient_name=patient_name,
                encounter_id=None,  # TODO: Get active encounter
                age_years=age_years,
                weight_kg=weight_kg,
                height_cm=height_cm,
                gestational_age_weeks=None,  # TODO: Get for neonates
                bsa=None,  # TODO: Calculate BSA
                scr=scr,
                gfr=gfr,
                crcl=None,  # TODO: Calculate CrCl
                is_on_dialysis=False,  # TODO: Check dialysis status
                dialysis_type=None,
                antimicrobials=antimicrobials,
                indication=indication,
                indication_confidence=None,
                indication_source=None,
                co_medications=co_medications,
                allergies=allergies,
            )

            return context

        except Exception as e:
            logger.error(f"Failed to build context for {patient_mrn}: {e}", exc_info=True)
            return None
