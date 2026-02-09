"""Serializers for the Surgical Prophylaxis API."""

from rest_framework import serializers

from apps.surgical_prophylaxis.models import (
    SurgicalCase, ProphylaxisEvaluation, ProphylaxisMedication,
)


class ProphylaxisMedicationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProphylaxisMedication
        fields = [
            'id', 'medication_type', 'medication_name', 'dose_mg',
            'route', 'event_time', 'frequency', 'duration_hours',
            'created_at',
        ]


class ProphylaxisEvaluationSerializer(serializers.ModelSerializer):
    element_results_list = serializers.ReadOnlyField()

    class Meta:
        model = ProphylaxisEvaluation
        fields = [
            'id', 'evaluation_time', 'bundle_compliant', 'compliance_score',
            'elements_met', 'elements_total', 'flags', 'recommendations',
            'excluded', 'exclusion_reason',
            'indication_result', 'agent_result', 'timing_result',
            'dosing_result', 'redosing_result', 'postop_result',
            'discontinuation_result',
            'element_results_list',
            'created_at',
        ]


class CaseListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""
    surgery_duration_hours = serializers.FloatField(read_only=True)

    class Meta:
        model = SurgicalCase
        fields = [
            'id', 'case_id', 'patient_mrn', 'patient_name',
            'procedure_description', 'procedure_category',
            'scheduled_or_time', 'actual_incision_time', 'surgery_end_time',
            'surgery_duration_hours',
            'is_emergency', 'created_at',
        ]


class CaseDetailSerializer(serializers.ModelSerializer):
    """Full serializer with nested evaluation and medications."""
    latest_evaluation = serializers.SerializerMethodField()
    medications = ProphylaxisMedicationSerializer(many=True, read_only=True)
    surgery_duration_hours = serializers.FloatField(read_only=True)

    class Meta:
        model = SurgicalCase
        fields = [
            'id', 'case_id', 'patient_mrn', 'patient_name', 'encounter_id',
            'cpt_codes', 'procedure_description', 'procedure_category',
            'surgeon_id', 'surgeon_name', 'location',
            'scheduled_or_time', 'actual_incision_time', 'surgery_end_time',
            'surgery_duration_hours',
            'patient_weight_kg', 'patient_age_years',
            'allergies', 'has_beta_lactam_allergy', 'mrsa_colonized',
            'is_emergency', 'already_on_therapeutic_abx', 'documented_infection',
            'created_at', 'updated_at',
            'latest_evaluation', 'medications',
        ]

    def get_latest_evaluation(self, obj):
        evaluation = obj.evaluations.order_by('-evaluation_time').first()
        if evaluation:
            return ProphylaxisEvaluationSerializer(evaluation).data
        return None
