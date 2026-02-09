"""Lab-based element checker for blood cultures, lactate, etc."""

from datetime import datetime
import logging

from apps.guideline_adherence.logic import config
from apps.guideline_adherence.models import ElementCheckStatus
from .base import ElementChecker, CheckResult

logger = logging.getLogger(__name__)


class LabChecker(ElementChecker):
    """Check lab-based bundle elements (blood cultures, lactate, UA, etc.).

    Maps element IDs to LOINC codes and queries FHIR for lab results
    within the required time window.
    """

    # Map element IDs to LOINC codes for FHIR queries
    ELEMENT_LOINC_MAP = {
        # Sepsis bundle
        'sepsis_blood_cx': [config.LOINC_BLOOD_CULTURE, '600-7'],
        'sepsis_lactate': [config.LOINC_LACTATE, '2524-7'],
        'sepsis_repeat_lactate': [config.LOINC_LACTATE, '2524-7'],
        # Febrile neutropenia bundle
        'fn_blood_cx_peripheral': [config.LOINC_BLOOD_CULTURE],
        'fn_blood_cx_central': [config.LOINC_BLOOD_CULTURE],
        # UTI bundle
        'uti_ua_obtained': ['5767-9', '5799-2'],
        'uti_culture_obtained': ['630-4'],
        # Febrile infant bundle
        'fi_ua': [config.LOINC_UA, config.LOINC_UA_WBC],
        'fi_blood_culture': [config.LOINC_BLOOD_CULTURE],
        'fi_inflammatory_markers': [config.LOINC_ANC, config.LOINC_CRP],
        'fi_procalcitonin': [config.LOINC_PROCALCITONIN],
        'fi_urine_culture': [config.LOINC_URINE_CULTURE],
        'fi_csf_studies': [config.LOINC_CSF_WBC, config.LOINC_CSF_RBC],
        # CAP bundle
        'cap_blood_cx': [config.LOINC_BLOOD_CULTURE],
        'cap_cxr': [config.LOINC_CXR],
    }

    def check(
        self,
        element,
        patient_id: str,
        trigger_time: datetime,
        **kwargs,
    ) -> CheckResult:
        """Check if a lab-based element has been completed.

        Args:
            element: BundleElement to check.
            patient_id: FHIR patient ID.
            trigger_time: When the bundle was triggered.

        Returns:
            CheckResult with status.
        """
        # Handle repeat lactate specially
        if element.element_id == 'sepsis_repeat_lactate':
            initial_lactate = kwargs.get('initial_lactate')
            return self.check_repeat_lactate(element, patient_id, trigger_time, initial_lactate)

        # Get LOINC codes for this element
        loinc_codes = self.ELEMENT_LOINC_MAP.get(element.element_id, [])
        if not loinc_codes:
            logger.warning("No LOINC codes configured for element %s", element.element_id)
            return self._create_result(
                element=element,
                status=ElementCheckStatus.PENDING,
                trigger_time=trigger_time,
                notes='No LOINC codes configured for this element',
            )

        # Query FHIR for lab results
        labs = self.fhir_client.get_lab_results(
            patient_id=patient_id,
            loinc_codes=loinc_codes,
            since_time=trigger_time,
        )

        if not labs:
            if self._is_within_window(trigger_time, element.time_window_hours):
                return self._create_result(
                    element=element,
                    status=ElementCheckStatus.PENDING,
                    trigger_time=trigger_time,
                    notes='No results yet, still within time window',
                )
            else:
                return self._create_result(
                    element=element,
                    status=ElementCheckStatus.NOT_MET,
                    trigger_time=trigger_time,
                    notes='Time window expired without lab result',
                )

        # Find the earliest result within the window
        deadline = self._calculate_deadline(trigger_time, element.time_window_hours)
        for lab in sorted(labs, key=lambda x: x.get('effective_time', datetime.max)):
            effective_time = lab.get('effective_time')
            if effective_time and (deadline is None or effective_time <= deadline):
                value = lab.get('value')
                return self._create_result(
                    element=element,
                    status=ElementCheckStatus.MET,
                    trigger_time=trigger_time,
                    completed_at=effective_time,
                    value=value,
                    notes=f'Result: {value}' if value else 'Result obtained',
                )

        # Results exist but not within window
        if self._is_within_window(trigger_time, element.time_window_hours):
            return self._create_result(
                element=element,
                status=ElementCheckStatus.PENDING,
                trigger_time=trigger_time,
                notes='Results found but not yet within time window',
            )
        else:
            return self._create_result(
                element=element,
                status=ElementCheckStatus.NOT_MET,
                trigger_time=trigger_time,
                notes='Time window expired - no result within required timeframe',
            )

    def check_repeat_lactate(
        self,
        element,
        patient_id: str,
        trigger_time: datetime,
        initial_lactate: float | None,
    ) -> CheckResult:
        """Check repeat lactate requirement (only if initial > 2.0).

        Per Surviving Sepsis, repeat lactate is only required if
        initial lactate is elevated (> 2.0 mmol/L).

        Args:
            element: BundleElement to check.
            patient_id: FHIR patient ID.
            trigger_time: When the bundle was triggered.
            initial_lactate: Initial lactate value (if available).

        Returns:
            CheckResult with status.
        """
        # If initial lactate not elevated, element is N/A
        if initial_lactate is None or initial_lactate <= 2.0:
            return self._create_result(
                element=element,
                status=ElementCheckStatus.NOT_APPLICABLE,
                trigger_time=trigger_time,
                notes=(
                    f"Initial lactate {'not available' if initial_lactate is None else f'{initial_lactate} <= 2.0'}"
                    ' - repeat not required'
                ),
            )

        # Initial lactate was elevated, need repeat
        loinc_codes = self.ELEMENT_LOINC_MAP.get('sepsis_lactate', [config.LOINC_LACTATE])
        labs = self.fhir_client.get_lab_results(
            patient_id=patient_id,
            loinc_codes=loinc_codes,
            since_time=trigger_time,
        )

        # Need at least 2 lactate results (initial + repeat)
        if len(labs) < 2:
            if self._is_within_window(trigger_time, element.time_window_hours):
                return self._create_result(
                    element=element,
                    status=ElementCheckStatus.PENDING,
                    trigger_time=trigger_time,
                    notes=f'Initial lactate {initial_lactate} elevated - awaiting repeat',
                )
            else:
                return self._create_result(
                    element=element,
                    status=ElementCheckStatus.NOT_MET,
                    trigger_time=trigger_time,
                    notes=f'Initial lactate {initial_lactate} elevated but no repeat within 6h',
                )

        # Check if repeat was obtained within window
        deadline = self._calculate_deadline(trigger_time, element.time_window_hours)
        sorted_labs = sorted(labs, key=lambda x: x.get('effective_time', datetime.max))

        if len(sorted_labs) >= 2:
            repeat_lab = sorted_labs[1]
            repeat_time = repeat_lab.get('effective_time')
            repeat_value = repeat_lab.get('value')

            if repeat_time and (deadline is None or repeat_time <= deadline):
                return self._create_result(
                    element=element,
                    status=ElementCheckStatus.MET,
                    trigger_time=trigger_time,
                    completed_at=repeat_time,
                    value=repeat_value,
                    notes=f'Repeat lactate: {repeat_value}',
                )

        if self._is_within_window(trigger_time, element.time_window_hours):
            return self._create_result(
                element=element,
                status=ElementCheckStatus.PENDING,
                trigger_time=trigger_time,
                notes=f'Initial lactate {initial_lactate} elevated - awaiting repeat within window',
            )

        return self._create_result(
            element=element,
            status=ElementCheckStatus.NOT_MET,
            trigger_time=trigger_time,
            notes=f'Initial lactate {initial_lactate} elevated but repeat not within 6h window',
        )
