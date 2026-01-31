"""FHIR service for querying culture and medication data."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

import requests


@dataclass
class DrugAllergy:
    """Drug allergy record from AllergyIntolerance resource."""
    substance: str
    reaction: str | None = None
    severity: str | None = None  # low, moderate, high, life-threatening
    is_antibiotic: bool = False


@dataclass
class RenalStatus:
    """Renal function status aggregated from Conditions, Procedures, and Labs."""
    has_ckd: bool = False
    ckd_stage: str | None = None  # Stage 1-5
    has_aki: bool = False
    on_dialysis: bool = False
    dialysis_type: str | None = None  # hemodialysis, peritoneal
    latest_creatinine: float | None = None
    latest_gfr: float | None = None
    creatinine_date: datetime | None = None


@dataclass
class MDRHistory:
    """Multi-drug resistant organism history from culture results."""
    has_mrsa: bool = False
    has_vre: bool = False
    has_cre: bool = False  # carbapenem-resistant Enterobacteriaceae
    has_esbl: bool = False  # extended-spectrum beta-lactamase
    resistant_organisms: list[dict] = field(default_factory=list)
    # Each dict: {organism, antibiotic, date, culture_id}


@dataclass
class ClinicalContext:
    """Aggregated clinical context for antibiotic decisions."""
    patient_id: str
    allergies: list[DrugAllergy] = field(default_factory=list)
    renal_status: RenalStatus = field(default_factory=RenalStatus)
    mdr_history: MDRHistory = field(default_factory=MDRHistory)

    @property
    def has_critical_allergies(self) -> bool:
        """Check for penicillin/cephalosporin anaphylaxis."""
        critical_drugs = ["penicillin", "amoxicillin", "cephalosporin", "ceftriaxone",
                         "cefepime", "cefazolin", "ampicillin"]
        for allergy in self.allergies:
            if allergy.severity == "life-threatening":
                substance_lower = allergy.substance.lower()
                if any(drug in substance_lower for drug in critical_drugs):
                    return True
        return False

    @property
    def needs_renal_dosing(self) -> bool:
        """Check if patient needs renal-adjusted dosing (GFR < 30 or dialysis)."""
        if self.renal_status.on_dialysis:
            return True
        if self.renal_status.latest_gfr is not None and self.renal_status.latest_gfr < 30:
            return True
        if self.renal_status.ckd_stage in ["4", "5", "Stage 4", "Stage 5"]:
            return True
        return False

    @property
    def has_mdr_risk(self) -> bool:
        """Check for any MDR pathogen history."""
        return (self.mdr_history.has_mrsa or self.mdr_history.has_vre or
                self.mdr_history.has_cre or self.mdr_history.has_esbl)


@dataclass
class Susceptibility:
    """Antibiotic susceptibility result."""
    antibiotic: str
    result: str  # S, I, R
    result_display: str  # Susceptible, Intermediate, Resistant
    mic: Optional[str] = None


@dataclass
class CultureResult:
    """Blood culture result with susceptibilities."""
    id: str
    patient_id: str
    patient_name: str
    patient_mrn: str
    organism: str
    organism_code: Optional[str]
    collected_at: Optional[datetime]
    resulted_at: Optional[datetime]
    susceptibilities: list[Susceptibility]


@dataclass
class Medication:
    """Active medication order."""
    id: str
    name: str
    code: Optional[str]
    status: str
    ordered_at: Optional[datetime]
    dose: Optional[str] = None
    route: Optional[str] = None


@dataclass
class Patient:
    """Patient demographic information."""
    id: str
    mrn: str
    name: str
    birth_date: Optional[datetime] = None
    gender: Optional[str] = None
    location: Optional[str] = None
    location_display: Optional[str] = None


class FHIRService:
    """Service for FHIR queries from the dashboard."""

    # Common antibiotic keywords to identify antibiotics vs other medications
    ANTIBIOTIC_KEYWORDS = [
        "cillin", "mycin", "cycline", "floxacin", "azole", "oxacin",
        "sulfa", "meropenem", "imipenem", "cef", "pen", "vancomycin",
        "daptomycin", "linezolid", "metronidazole", "clindamycin",
        "azithromycin", "amoxicillin", "ampicillin", "ceftriaxone",
        "cefepime", "cefazolin", "piperacillin", "tazobactam",
        "gentamicin", "tobramycin", "amikacin", "levofloxacin",
        "ciprofloxacin", "moxifloxacin", "doxycycline", "minocycline",
        "trimethoprim", "sulfamethoxazole", "nitrofurantoin",
        "fosfomycin", "tigecycline", "colistin", "polymyxin",
        "rifampin", "micafungin", "caspofungin", "fluconazole",
        "voriconazole", "amphotericin", "nafcillin", "oxacillin",
        "dicloxacillin", "ceftazidime", "ceftaroline", "ertapenem",
        "doripenem", "aztreonam",
    ]

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/fhir+json",
            "Content-Type": "application/fhir+json",
        })

    def _get(self, path: str, params: dict | None = None) -> dict | None:
        """Make a GET request to the FHIR server."""
        try:
            response = self.session.get(
                f"{self.base_url}/{path}",
                params=params,
                timeout=10,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"FHIR request error: {e}")
            return None

    def _extract_entries(self, bundle: dict) -> list[dict]:
        """Extract resources from a FHIR Bundle."""
        if not bundle or bundle.get("resourceType") != "Bundle":
            return []
        return [
            entry.get("resource", {})
            for entry in bundle.get("entry", [])
            if "resource" in entry
        ]

    def get_culture_with_susceptibilities(self, culture_id: str) -> CultureResult | None:
        """Get a blood culture DiagnosticReport with its susceptibility results.

        Args:
            culture_id: The DiagnosticReport FHIR resource ID

        Returns:
            CultureResult with susceptibilities, or None if not found
        """
        # Get the DiagnosticReport
        report = self._get(f"DiagnosticReport/{culture_id}")
        if not report:
            return None

        # Extract patient reference
        patient_ref = report.get("subject", {}).get("reference", "")
        patient_id = patient_ref.replace("Patient/", "") if patient_ref else ""

        # Get patient details
        patient_name = "Unknown"
        patient_mrn = "Unknown"
        if patient_id:
            patient = self._get(f"Patient/{patient_id}")
            if patient:
                # Extract name
                names = patient.get("name", [])
                if names:
                    name = names[0]
                    given = " ".join(name.get("given", []))
                    family = name.get("family", "")
                    patient_name = f"{given} {family}".strip() or "Unknown"

                # Extract MRN
                for ident in patient.get("identifier", []):
                    type_coding = ident.get("type", {}).get("coding", [])
                    for coding in type_coding:
                        if coding.get("code") == "MR":
                            patient_mrn = ident.get("value", "Unknown")
                            break

        # Extract organism from conclusionCode
        organism = report.get("conclusion", "Unknown organism")
        organism_code = None
        conclusion_codes = report.get("conclusionCode", [])
        if conclusion_codes:
            coding = conclusion_codes[0].get("coding", [])
            if coding:
                organism = coding[0].get("display", organism)
                organism_code = coding[0].get("code")

        # Parse dates
        collected_at = None
        resulted_at = None
        if report.get("effectiveDateTime"):
            try:
                collected_at = datetime.fromisoformat(
                    report["effectiveDateTime"].replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass
        if report.get("issued"):
            try:
                resulted_at = datetime.fromisoformat(
                    report["issued"].replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass

        # Get susceptibility Observations
        # These are linked via note field containing "Culture: {culture_id}"
        susceptibilities = self._get_susceptibilities_for_culture(culture_id)

        return CultureResult(
            id=culture_id,
            patient_id=patient_id,
            patient_name=patient_name,
            patient_mrn=patient_mrn,
            organism=organism,
            organism_code=organism_code,
            collected_at=collected_at,
            resulted_at=resulted_at,
            susceptibilities=susceptibilities,
        )

    def _get_susceptibilities_for_culture(self, culture_id: str) -> list[Susceptibility]:
        """Get susceptibility Observations for a culture.

        In our demo data, these are linked via note field.
        In Epic, they would be linked via DiagnosticReport.result references.
        """
        susceptibilities = []

        # Search for Observations that reference this culture in notes
        # This is a workaround since HAPI FHIR doesn't support derivedFrom to DiagnosticReport
        # We search for lab Observations and filter by note content
        bundle = self._get("Observation", {
            "category": "laboratory",
            "_count": "100",
        })

        observations = self._extract_entries(bundle)

        for obs in observations:
            # Check if this observation references our culture in the note
            notes = obs.get("note", [])
            culture_match = False
            for note in notes:
                if note.get("text", "").startswith(f"Culture: {culture_id}"):
                    culture_match = True
                    break

            if not culture_match:
                continue

            # Extract antibiotic name from code
            code_text = obs.get("code", {}).get("text", "")
            antibiotic = code_text.replace(" Susceptibility", "")
            if not antibiotic:
                coding = obs.get("code", {}).get("coding", [])
                if coding:
                    antibiotic = coding[0].get("display", "Unknown")
                    antibiotic = antibiotic.replace(" [Susceptibility]", "")

            # Extract S/I/R result
            result = "?"
            result_display = "Unknown"
            interpretations = obs.get("interpretation", [])
            if interpretations:
                coding = interpretations[0].get("coding", [])
                if coding:
                    result = coding[0].get("code", "?")
                    result_display = coding[0].get("display", "Unknown")

            # Extract MIC value from component
            mic = None
            for component in obs.get("component", []):
                comp_code = component.get("code", {}).get("text", "")
                if comp_code == "MIC":
                    mic = component.get("valueString")
                    break

            susceptibilities.append(Susceptibility(
                antibiotic=antibiotic,
                result=result,
                result_display=result_display,
                mic=mic,
            ))

        # Sort by antibiotic name
        susceptibilities.sort(key=lambda s: s.antibiotic.lower())
        return susceptibilities

    def get_patient_medications(
        self,
        patient_id: str,
        antibiotics_only: bool = True,
        include_statuses: list[str] | None = None,
    ) -> list[Medication]:
        """Get medications for a patient.

        Args:
            patient_id: FHIR Patient resource ID
            antibiotics_only: If True, filter to likely antibiotics
            include_statuses: List of statuses to include (default: active, on-hold)

        Returns:
            List of Medication objects
        """
        if include_statuses is None:
            include_statuses = ["active", "on-hold"]

        medications = []

        for status in include_statuses:
            bundle = self._get("MedicationRequest", {
                "patient": patient_id,
                "status": status,
                "_count": "100",
            })

            for resource in self._extract_entries(bundle):
                # Extract medication name
                med_name = "Unknown"
                med_code = None
                med_concept = resource.get("medicationCodeableConcept", {})
                if med_concept:
                    med_name = med_concept.get("text", "")
                    coding = med_concept.get("coding", [])
                    if coding:
                        if not med_name:
                            med_name = coding[0].get("display", "Unknown")
                        med_code = coding[0].get("code")

                # Filter to antibiotics if requested
                if antibiotics_only:
                    name_lower = med_name.lower()
                    is_antibiotic = any(
                        kw in name_lower for kw in self.ANTIBIOTIC_KEYWORDS
                    )
                    if not is_antibiotic:
                        continue

                # Parse ordered date
                ordered_at = None
                if resource.get("authoredOn"):
                    try:
                        ordered_at = datetime.fromisoformat(
                            resource["authoredOn"].replace("Z", "+00:00")
                        )
                    except (ValueError, TypeError):
                        pass

                # Extract dosage info if available
                dose = None
                route = None
                dosage_instructions = resource.get("dosageInstruction", [])
                if dosage_instructions:
                    di = dosage_instructions[0]
                    dose_qty = di.get("doseAndRate", [{}])[0].get("doseQuantity", {})
                    if dose_qty:
                        dose = f"{dose_qty.get('value', '')} {dose_qty.get('unit', '')}".strip()
                    route_coding = di.get("route", {}).get("coding", [])
                    if route_coding:
                        route = route_coding[0].get("display")

                medications.append(Medication(
                    id=resource.get("id", ""),
                    name=med_name,
                    code=med_code,
                    status=resource.get("status", "unknown"),
                    ordered_at=ordered_at,
                    dose=dose,
                    route=route,
                ))

        # Sort by name
        medications.sort(key=lambda m: m.name.lower())
        return medications

    def search_patients(
        self,
        mrn: str | None = None,
        name: str | None = None,
        limit: int = 20,
    ) -> list[Patient]:
        """Search for patients by MRN or name.

        Args:
            mrn: MRN to search for (exact match)
            name: Name to search for (partial match)
            limit: Maximum number of results

        Returns:
            List of matching Patient objects
        """
        params = {"_count": str(limit)}

        if mrn:
            # Search by MRN identifier
            params["identifier"] = mrn
        if name:
            # Search by name (FHIR does partial matching)
            params["name"] = name

        bundle = self._get("Patient", params)
        patients = []

        for resource in self._extract_entries(bundle):
            patient = self._parse_patient(resource)
            if patient:
                patients.append(patient)

        return patients

    def get_patient(self, patient_id: str) -> Patient | None:
        """Get a patient by FHIR ID.

        Args:
            patient_id: FHIR Patient resource ID

        Returns:
            Patient object or None if not found
        """
        resource = self._get(f"Patient/{patient_id}")
        if not resource:
            return None
        return self._parse_patient(resource)

    def _parse_patient(self, resource: dict) -> Patient | None:
        """Parse a Patient resource into a Patient dataclass."""
        if not resource or resource.get("resourceType") != "Patient":
            return None

        patient_id = resource.get("id", "")

        # Extract MRN
        mrn = "Unknown"
        for ident in resource.get("identifier", []):
            type_coding = ident.get("type", {}).get("coding", [])
            for coding in type_coding:
                if coding.get("code") == "MR":
                    mrn = ident.get("value", "Unknown")
                    break

        # Extract name
        name = "Unknown"
        names = resource.get("name", [])
        if names:
            name_obj = names[0]
            given = " ".join(name_obj.get("given", []))
            family = name_obj.get("family", "")
            name = f"{given} {family}".strip() or "Unknown"

        # Extract birth date
        birth_date = None
        if resource.get("birthDate"):
            try:
                birth_date = datetime.fromisoformat(resource["birthDate"])
            except (ValueError, TypeError):
                pass

        # Extract gender
        gender = resource.get("gender")

        # Extract current location from active Encounter if available
        location = None
        location_display = None
        # Note: In a real implementation, we'd query for the active Encounter
        # and get the location from there. For now, return None.

        return Patient(
            id=patient_id,
            mrn=mrn,
            name=name,
            birth_date=birth_date,
            gender=gender,
            location=location,
            location_display=location_display,
        )

    def get_patient_cultures(
        self,
        patient_id: str,
        days_back: int = 30,
    ) -> list[CultureResult]:
        """Get recent cultures for a patient.

        Args:
            patient_id: FHIR Patient resource ID
            days_back: Number of days to look back

        Returns:
            List of CultureResult objects
        """
        from datetime import timedelta

        # Calculate date cutoff
        cutoff = datetime.now() - timedelta(days=days_back)
        cutoff_str = cutoff.strftime("%Y-%m-%d")

        # Query DiagnosticReport for microbiology cultures
        bundle = self._get("DiagnosticReport", {
            "patient": patient_id,
            "category": "microbiology",
            "date": f"ge{cutoff_str}",
            "_count": "50",
            "_sort": "-date",
        })

        cultures = []
        for resource in self._extract_entries(bundle):
            culture_id = resource.get("id")
            if not culture_id:
                continue

            # Get full culture with susceptibilities
            culture = self.get_culture_with_susceptibilities(culture_id)
            if culture:
                cultures.append(culture)

        return cultures

    # =====================================================
    # Clinical Context Methods for Antibiotic Decisions
    # =====================================================

    # ICD-10 codes for renal conditions
    RENAL_CONDITION_CODES = {
        "N18.1": ("CKD", "1"),
        "N18.2": ("CKD", "2"),
        "N18.3": ("CKD", "3"),
        "N18.30": ("CKD", "3a"),
        "N18.31": ("CKD", "3a"),
        "N18.32": ("CKD", "3b"),
        "N18.4": ("CKD", "4"),
        "N18.5": ("CKD", "5"),
        "N18.6": ("ESRD", "5"),
        "N17.0": ("AKI", None),
        "N17.1": ("AKI", None),
        "N17.2": ("AKI", None),
        "N17.8": ("AKI", None),
        "N17.9": ("AKI", None),
        "Z99.2": ("Dialysis", None),
    }

    # CPT/HCPCS codes for dialysis procedures
    DIALYSIS_PROCEDURE_CODES = {
        "90935": "hemodialysis",
        "90937": "hemodialysis",
        "90945": "peritoneal dialysis",
        "90947": "peritoneal dialysis",
        "90999": "dialysis",
    }

    # LOINC codes for renal labs
    RENAL_LAB_CODES = {
        "2160-0": "creatinine",
        "38483-4": "creatinine",
        "33914-3": "gfr",
        "48642-3": "gfr",
        "88293-6": "gfr",
        "77147-7": "gfr",
        "69405-9": "gfr",
    }

    # Organisms for MDR detection
    MRSA_ORGANISMS = ["staphylococcus aureus", "s. aureus", "s aureus", "staph aureus"]
    VRE_ORGANISMS = ["enterococcus faecium", "enterococcus faecalis", "e. faecium",
                     "e. faecalis", "enterococcus"]
    ENTEROBACTERIACEAE = ["e. coli", "escherichia coli", "klebsiella", "enterobacter",
                          "serratia", "citrobacter", "proteus", "morganella",
                          "providencia", "salmonella"]

    def get_patient_allergies(self, patient_id: str) -> list[DrugAllergy]:
        """Get drug allergies from AllergyIntolerance resources.

        Args:
            patient_id: FHIR Patient resource ID

        Returns:
            List of DrugAllergy objects
        """
        bundle = self._get("AllergyIntolerance", {
            "patient": patient_id,
            "clinical-status": "active",
            "_count": "100",
        })

        allergies = []
        for resource in self._extract_entries(bundle):
            # Extract substance name
            substance = "Unknown"
            code_concept = resource.get("code", {})
            coding = code_concept.get("coding", [])
            if coding:
                substance = coding[0].get("display", substance)
            if not substance or substance == "Unknown":
                substance = code_concept.get("text", "Unknown")

            # Extract reaction
            reaction = None
            severity = None
            reactions = resource.get("reaction", [])
            if reactions:
                rxn = reactions[0]
                manifestations = rxn.get("manifestation", [])
                if manifestations:
                    rxn_coding = manifestations[0].get("coding", [])
                    if rxn_coding:
                        reaction = rxn_coding[0].get("display")
                    else:
                        reaction = manifestations[0].get("text")

                # Map FHIR severity to our levels
                fhir_severity = rxn.get("severity", "")
                if fhir_severity == "severe":
                    severity = "life-threatening"
                elif fhir_severity == "moderate":
                    severity = "moderate"
                elif fhir_severity == "mild":
                    severity = "low"

            # Check criticality for life-threatening
            criticality = resource.get("criticality", "")
            if criticality == "high":
                severity = "life-threatening"

            # Determine if it's an antibiotic
            substance_lower = substance.lower()
            is_antibiotic = any(kw in substance_lower for kw in self.ANTIBIOTIC_KEYWORDS)

            allergies.append(DrugAllergy(
                substance=substance,
                reaction=reaction,
                severity=severity,
                is_antibiotic=is_antibiotic,
            ))

        return allergies

    def get_patient_conditions(self, patient_id: str) -> list[dict]:
        """Get active conditions from Condition resources.

        Args:
            patient_id: FHIR Patient resource ID

        Returns:
            List of condition dicts with code, display, category
        """
        bundle = self._get("Condition", {
            "patient": patient_id,
            "clinical-status": "active",
            "_count": "100",
        })

        conditions = []
        for resource in self._extract_entries(bundle):
            code_concept = resource.get("code", {})
            coding = code_concept.get("coding", [])

            for code_entry in coding:
                conditions.append({
                    "code": code_entry.get("code", ""),
                    "display": code_entry.get("display", ""),
                    "system": code_entry.get("system", ""),
                })

            # Also check text if no coding
            if not coding and code_concept.get("text"):
                conditions.append({
                    "code": "",
                    "display": code_concept.get("text", ""),
                    "system": "",
                })

        return conditions

    def get_patient_procedures(
        self,
        patient_id: str,
        days_back: int = 365,
    ) -> list[dict]:
        """Get procedures from Procedure resources.

        Args:
            patient_id: FHIR Patient resource ID
            days_back: Number of days to look back

        Returns:
            List of procedure dicts with code, display, date
        """
        cutoff = datetime.now() - timedelta(days=days_back)
        cutoff_str = cutoff.strftime("%Y-%m-%d")

        bundle = self._get("Procedure", {
            "patient": patient_id,
            "date": f"ge{cutoff_str}",
            "_count": "100",
        })

        procedures = []
        for resource in self._extract_entries(bundle):
            code_concept = resource.get("code", {})
            coding = code_concept.get("coding", [])

            # Parse date
            performed = None
            if resource.get("performedDateTime"):
                try:
                    performed = datetime.fromisoformat(
                        resource["performedDateTime"].replace("Z", "+00:00")
                    )
                except (ValueError, TypeError):
                    pass

            for code_entry in coding:
                procedures.append({
                    "code": code_entry.get("code", ""),
                    "display": code_entry.get("display", ""),
                    "system": code_entry.get("system", ""),
                    "date": performed,
                })

        return procedures

    def get_patient_labs(
        self,
        patient_id: str,
        loinc_codes: list[str] | None = None,
        days_back: int = 30,
    ) -> list[dict]:
        """Get lab observations for a patient.

        Args:
            patient_id: FHIR Patient resource ID
            loinc_codes: Optional list of LOINC codes to filter
            days_back: Number of days to look back

        Returns:
            List of lab dicts with code, value, unit, date
        """
        cutoff = datetime.now() - timedelta(days=days_back)
        cutoff_str = cutoff.strftime("%Y-%m-%d")

        params = {
            "patient": patient_id,
            "category": "laboratory",
            "date": f"ge{cutoff_str}",
            "_count": "100",
            "_sort": "-date",
        }

        if loinc_codes:
            params["code"] = ",".join(loinc_codes)

        bundle = self._get("Observation", params)

        labs = []
        for resource in self._extract_entries(bundle):
            code_concept = resource.get("code", {})
            coding = code_concept.get("coding", [])

            loinc_code = None
            display = code_concept.get("text", "Unknown")
            for code_entry in coding:
                if "loinc" in code_entry.get("system", "").lower():
                    loinc_code = code_entry.get("code")
                    display = code_entry.get("display", display)
                    break

            # Extract value
            value = None
            unit = None
            if resource.get("valueQuantity"):
                vq = resource["valueQuantity"]
                value = vq.get("value")
                unit = vq.get("unit", vq.get("code"))
            elif resource.get("valueString"):
                value = resource["valueString"]

            # Parse date
            effective_date = None
            if resource.get("effectiveDateTime"):
                try:
                    effective_date = datetime.fromisoformat(
                        resource["effectiveDateTime"].replace("Z", "+00:00")
                    )
                except (ValueError, TypeError):
                    pass

            labs.append({
                "loinc_code": loinc_code,
                "display": display,
                "value": value,
                "unit": unit,
                "date": effective_date,
            })

        return labs

    def get_renal_status(self, patient_id: str) -> RenalStatus:
        """Get aggregated renal status for a patient.

        Combines data from Conditions (CKD/AKI diagnoses), Procedures (dialysis),
        and Observations (creatinine/GFR labs).

        Args:
            patient_id: FHIR Patient resource ID

        Returns:
            RenalStatus object
        """
        status = RenalStatus()

        # Check conditions for CKD/AKI
        conditions = self.get_patient_conditions(patient_id)
        for condition in conditions:
            code = condition.get("code", "")
            if code in self.RENAL_CONDITION_CODES:
                condition_type, stage = self.RENAL_CONDITION_CODES[code]
                if condition_type == "CKD":
                    status.has_ckd = True
                    if stage:
                        status.ckd_stage = stage
                elif condition_type == "AKI":
                    status.has_aki = True
                elif condition_type == "ESRD":
                    status.has_ckd = True
                    status.ckd_stage = "5"
                elif condition_type == "Dialysis":
                    status.on_dialysis = True

        # Check procedures for dialysis
        procedures = self.get_patient_procedures(patient_id, days_back=90)
        for proc in procedures:
            code = proc.get("code", "")
            if code in self.DIALYSIS_PROCEDURE_CODES:
                status.on_dialysis = True
                status.dialysis_type = self.DIALYSIS_PROCEDURE_CODES[code]
                break

        # Get recent creatinine and GFR
        renal_loincs = list(self.RENAL_LAB_CODES.keys())
        labs = self.get_patient_labs(patient_id, loinc_codes=renal_loincs, days_back=30)

        for lab in labs:
            lab_type = self.RENAL_LAB_CODES.get(lab.get("loinc_code", ""))
            if lab_type == "creatinine" and status.latest_creatinine is None:
                try:
                    status.latest_creatinine = float(lab["value"])
                    status.creatinine_date = lab.get("date")
                except (ValueError, TypeError):
                    pass
            elif lab_type == "gfr" and status.latest_gfr is None:
                try:
                    status.latest_gfr = float(lab["value"])
                except (ValueError, TypeError):
                    pass

        return status

    def get_mdr_history(self, patient_id: str, days_back: int = 365) -> MDRHistory:
        """Scan patient's culture history for MDR organisms.

        Looks for resistant patterns in the past year:
        - MRSA: S. aureus with oxacillin/methicillin R
        - VRE: Enterococcus with vancomycin R
        - CRE: Enterobacteriaceae with meropenem/imipenem R
        - ESBL: Gram-negatives with cefepime R but meropenem S (suspected)

        Args:
            patient_id: FHIR Patient resource ID
            days_back: Number of days to look back (default 365)

        Returns:
            MDRHistory object
        """
        history = MDRHistory()

        # Get cultures from the past year
        cultures = self.get_patient_cultures(patient_id, days_back=days_back)

        for culture in cultures:
            organism_lower = culture.organism.lower()

            # Build susceptibility map for this culture
            susc_map = {}
            for sus in culture.susceptibilities:
                susc_map[sus.antibiotic.lower()] = sus.result

            # Check for MRSA
            if any(mrsa_org in organism_lower for mrsa_org in self.MRSA_ORGANISMS):
                # Check for oxacillin/methicillin resistance
                for abx in ["oxacillin", "methicillin", "nafcillin"]:
                    if susc_map.get(abx) == "R":
                        history.has_mrsa = True
                        history.resistant_organisms.append({
                            "organism": culture.organism,
                            "antibiotic": abx,
                            "date": culture.collected_at.isoformat() if culture.collected_at else None,
                            "culture_id": culture.id,
                        })
                        break

            # Check for VRE
            if any(vre_org in organism_lower for vre_org in self.VRE_ORGANISMS):
                if susc_map.get("vancomycin") == "R":
                    history.has_vre = True
                    history.resistant_organisms.append({
                        "organism": culture.organism,
                        "antibiotic": "vancomycin",
                        "date": culture.collected_at.isoformat() if culture.collected_at else None,
                        "culture_id": culture.id,
                    })

            # Check for CRE (carbapenem-resistant Enterobacteriaceae)
            if any(ent in organism_lower for ent in self.ENTEROBACTERIACEAE):
                for abx in ["meropenem", "imipenem", "ertapenem"]:
                    if susc_map.get(abx) == "R":
                        history.has_cre = True
                        history.resistant_organisms.append({
                            "organism": culture.organism,
                            "antibiotic": abx,
                            "date": culture.collected_at.isoformat() if culture.collected_at else None,
                            "culture_id": culture.id,
                        })
                        break

                # Check for ESBL (cefepime R but meropenem S)
                if (susc_map.get("cefepime") == "R" and
                    susc_map.get("meropenem") in ["S", None] and
                    not history.has_cre):
                    history.has_esbl = True
                    history.resistant_organisms.append({
                        "organism": culture.organism,
                        "antibiotic": "cefepime",
                        "date": culture.collected_at.isoformat() if culture.collected_at else None,
                        "culture_id": culture.id,
                    })

        return history

    def get_clinical_context(self, patient_id: str) -> ClinicalContext:
        """Get aggregated clinical context for antibiotic decisions.

        Combines allergies, renal status, and MDR history into a single
        ClinicalContext object for display in antibiotic approval/alert pages.

        Args:
            patient_id: FHIR Patient resource ID

        Returns:
            ClinicalContext object with all clinical alerts
        """
        context = ClinicalContext(patient_id=patient_id)

        # Get allergies
        try:
            context.allergies = self.get_patient_allergies(patient_id)
        except Exception as e:
            print(f"Error getting allergies for {patient_id}: {e}")

        # Get renal status
        try:
            context.renal_status = self.get_renal_status(patient_id)
        except Exception as e:
            print(f"Error getting renal status for {patient_id}: {e}")

        # Get MDR history
        try:
            context.mdr_history = self.get_mdr_history(patient_id)
        except Exception as e:
            print(f"Error getting MDR history for {patient_id}: {e}")

        return context
