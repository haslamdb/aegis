"""Medication-based element checker for antibiotic timing, fluid bolus, etc."""

import re
from datetime import datetime
import logging

from apps.guideline_adherence.logic import config
from apps.guideline_adherence.models import ElementCheckStatus
from .base import ElementChecker, CheckResult

logger = logging.getLogger(__name__)


# Broad-spectrum antibiotics for sepsis bundle
BROAD_SPECTRUM_ANTIBIOTICS = [
    # Beta-lactams
    'piperacillin', 'piperacillin-tazobactam', 'zosyn',
    'meropenem', 'imipenem', 'ertapenem',
    'cefepime', 'ceftazidime',
    'ampicillin-sulbactam',
    # Aminoglycosides
    'gentamicin', 'tobramycin', 'amikacin',
    # Fluoroquinolones
    'ciprofloxacin', 'levofloxacin',
    # Other
    'vancomycin', 'linezolid',
]

# Fluid bolus medications (crystalloids)
FLUID_BOLUS_MEDICATIONS = [
    'normal saline', '0.9% sodium chloride', 'ns',
    'lactated ringer', "ringer's lactate", 'lr',
    'plasmalyte', 'plasma-lyte',
]


class MedicationChecker(ElementChecker):
    """Check medication-based bundle elements.

    Handles antibiotic administration timing and fluid bolus checks
    for sepsis and other bundles.
    """

    def check(
        self,
        element,
        patient_id: str,
        trigger_time: datetime,
        **kwargs,
    ) -> CheckResult:
        """Check if a medication-based element has been completed.

        Routes to antibiotic or fluid bolus checker based on element_id.

        Args:
            element: BundleElement to check.
            patient_id: FHIR patient ID.
            trigger_time: When the bundle was triggered.

        Returns:
            CheckResult with status.
        """
        if 'abx' in element.element_id or 'antibiotic' in element.element_id.lower():
            return self._check_antibiotic(element, patient_id, trigger_time)
        elif 'fluid' in element.element_id or 'bolus' in element.element_id:
            return self._check_fluid_bolus(element, patient_id, trigger_time)
        else:
            logger.warning("Unknown medication element type: %s", element.element_id)
            return self._create_result(
                element=element,
                status=ElementCheckStatus.PENDING,
                trigger_time=trigger_time,
                notes='Unknown medication element type',
            )

    def _check_antibiotic(
        self,
        element,
        patient_id: str,
        trigger_time: datetime,
    ) -> CheckResult:
        """Check if broad-spectrum antibiotics were given within time window.

        Queries FHIR MedicationAdministration and filters against the
        BROAD_SPECTRUM_ANTIBIOTICS list.
        """
        med_admins = self.fhir_client.get_medication_administrations(
            patient_id=patient_id,
            since_time=trigger_time,
        )

        # Filter to antibiotics
        antibiotic_admins = []
        for admin in med_admins:
            med_name = admin.get('medication_name', '').lower()
            if any(abx in med_name for abx in BROAD_SPECTRUM_ANTIBIOTICS):
                antibiotic_admins.append(admin)

        if not antibiotic_admins:
            if self._is_within_window(trigger_time, element.time_window_hours):
                return self._create_result(
                    element=element,
                    status=ElementCheckStatus.PENDING,
                    trigger_time=trigger_time,
                    notes='No broad-spectrum antibiotic administered yet',
                )
            else:
                return self._create_result(
                    element=element,
                    status=ElementCheckStatus.NOT_MET,
                    trigger_time=trigger_time,
                    notes='Time window expired - no broad-spectrum antibiotic within required time',
                )

        # Check if any antibiotic was given within the window
        deadline = self._calculate_deadline(trigger_time, element.time_window_hours)
        for admin in sorted(antibiotic_admins, key=lambda x: x.get('admin_time', datetime.max)):
            admin_time = admin.get('admin_time')
            if admin_time and (deadline is None or admin_time <= deadline):
                med_name = admin.get('medication_name', 'Unknown')
                return self._create_result(
                    element=element,
                    status=ElementCheckStatus.MET,
                    trigger_time=trigger_time,
                    completed_at=admin_time,
                    value=med_name,
                    notes=f'Antibiotic administered: {med_name}',
                )

        # Antibiotics given but not within window
        if self._is_within_window(trigger_time, element.time_window_hours):
            return self._create_result(
                element=element,
                status=ElementCheckStatus.PENDING,
                trigger_time=trigger_time,
                notes='Antibiotics administered but awaiting confirmation within window',
            )

        return self._create_result(
            element=element,
            status=ElementCheckStatus.NOT_MET,
            trigger_time=trigger_time,
            notes='Time window expired - antibiotic not given within required timeframe',
        )

    def _check_fluid_bolus(
        self,
        element,
        patient_id: str,
        trigger_time: datetime,
        requires_shock_criteria: bool = True,
    ) -> CheckResult:
        """Check if fluid bolus was given within time window.

        First checks for shock/hypoperfusion criteria (if required),
        then validates crystalloid administration with bolus-level dosing.
        """
        # First check if shock criteria are met (if required)
        if requires_shock_criteria:
            has_shock = self._check_shock_criteria(patient_id, trigger_time)
            if not has_shock:
                return self._create_result(
                    element=element,
                    status=ElementCheckStatus.NOT_APPLICABLE,
                    trigger_time=trigger_time,
                    notes='No hypotension/hypoperfusion criteria - fluid bolus not required',
                )

        med_admins = self.fhir_client.get_medication_administrations(
            patient_id=patient_id,
            since_time=trigger_time,
        )

        # Filter to fluids with bolus-level dosing
        fluid_admins = []
        for admin in med_admins:
            med_name = admin.get('medication_name', '').lower()
            if any(fluid in med_name for fluid in FLUID_BOLUS_MEDICATIONS):
                dose = admin.get('dose', '')
                if dose and self._is_bolus_dose(dose):
                    fluid_admins.append(admin)

        if not fluid_admins:
            if self._is_within_window(trigger_time, element.time_window_hours):
                return self._create_result(
                    element=element,
                    status=ElementCheckStatus.PENDING,
                    trigger_time=trigger_time,
                    notes='Shock criteria met - awaiting fluid bolus',
                )
            else:
                return self._create_result(
                    element=element,
                    status=ElementCheckStatus.NOT_MET,
                    trigger_time=trigger_time,
                    notes='Time window expired - no fluid bolus given despite shock criteria',
                )

        # Check if fluid given within window
        deadline = self._calculate_deadline(trigger_time, element.time_window_hours)
        for admin in sorted(fluid_admins, key=lambda x: x.get('admin_time', datetime.max)):
            admin_time = admin.get('admin_time')
            if admin_time and (deadline is None or admin_time <= deadline):
                dose = admin.get('dose', 'Unknown')
                return self._create_result(
                    element=element,
                    status=ElementCheckStatus.MET,
                    trigger_time=trigger_time,
                    completed_at=admin_time,
                    value=dose,
                    notes=f'Fluid bolus administered: {dose}',
                )

        if self._is_within_window(trigger_time, element.time_window_hours):
            return self._create_result(
                element=element,
                status=ElementCheckStatus.PENDING,
                trigger_time=trigger_time,
                notes='Shock criteria met - fluid administered but awaiting confirmation',
            )

        return self._create_result(
            element=element,
            status=ElementCheckStatus.NOT_MET,
            trigger_time=trigger_time,
            notes='Time window expired - fluid bolus not given within required timeframe',
        )

    def _check_shock_criteria(
        self,
        patient_id: str,
        trigger_time: datetime,
    ) -> bool:
        """Check if patient meets shock/hypoperfusion criteria.

        Checks vital signs for:
        - SBP < 90 (simplified; should be age-adjusted for peds)
        - MAP < 65
        - Lactate > 4.0 mmol/L

        Returns:
            True if shock criteria are met.
        """
        vitals = self.fhir_client.get_vital_signs(
            patient_id=patient_id,
            since_time=trigger_time,
        )

        for vital in vitals:
            vital_type = vital.get('code', '')
            value = vital.get('value')
            if value is None:
                continue

            # Systolic BP < 90
            if config.LOINC_SBP in vital_type or 'systolic' in vital_type.lower():
                if value < 90:
                    return True

            # MAP < 65
            if config.LOINC_MAP in vital_type or 'mean' in vital_type.lower():
                if value < 65:
                    return True

        # Lactate > 4 as sign of hypoperfusion
        labs = self.fhir_client.get_lab_results(
            patient_id=patient_id,
            loinc_codes=[config.LOINC_LACTATE],
            since_time=trigger_time,
        )
        for lab in labs:
            value = lab.get('value')
            if value is not None:
                try:
                    if float(value) > 4:
                        return True
                except (ValueError, TypeError):
                    pass

        return False

    def _is_bolus_dose(self, dose: str) -> bool:
        """Check if a dose represents a bolus (significant volume).

        Bolus criteria:
        - mL/kg dosing (typical for peds bolus orders)
        - Volume >= 100 mL

        Args:
            dose: Dose string (e.g., "1000 mL", "20 mL/kg").

        Returns:
            True if this appears to be a bolus dose.
        """
        dose_lower = dose.lower()

        # mL/kg dosing is typical for bolus
        if 'ml/kg' in dose_lower or 'ml per kg' in dose_lower:
            return True

        # Check for significant volume (>= 100 mL)
        try:
            match = re.search(r'(\d+)\s*(ml|milliliter)', dose_lower)
            if match:
                volume = int(match.group(1))
                return volume >= 100
        except (ValueError, AttributeError):
            pass

        return False
