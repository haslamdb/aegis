"""Tests for shared FHIR client infrastructure."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from apps.core.fhir import (
    BaseFHIRClient,
    EpicFHIRClient,
    HAPIFHIRClient,
    get_fhir_client,
)
from apps.core.fhir.parsers import (
    extract_bundle_entries,
    extract_encounter_location,
    extract_patient_mrn,
    extract_patient_name,
    parse_fhir_datetime,
    parse_susceptibility_observation,
)


# ---------------------------------------------------------------
# extract_bundle_entries
# ---------------------------------------------------------------

class ExtractBundleEntriesTest(TestCase):
    """Tests for extract_bundle_entries()."""

    def test_valid_bundle(self):
        bundle = {
            "resourceType": "Bundle",
            "entry": [
                {"resource": {"resourceType": "Patient", "id": "1"}},
                {"resource": {"resourceType": "Patient", "id": "2"}},
            ],
        }
        entries = extract_bundle_entries(bundle)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["id"], "1")
        self.assertEqual(entries[1]["id"], "2")

    def test_empty_bundle(self):
        bundle = {"resourceType": "Bundle", "entry": []}
        entries = extract_bundle_entries(bundle)
        self.assertEqual(entries, [])

    def test_bundle_no_entries_key(self):
        bundle = {"resourceType": "Bundle"}
        entries = extract_bundle_entries(bundle)
        self.assertEqual(entries, [])

    def test_not_a_bundle(self):
        resource = {"resourceType": "Patient", "id": "1"}
        entries = extract_bundle_entries(resource)
        self.assertEqual(entries, [])

    def test_entry_without_resource(self):
        bundle = {
            "resourceType": "Bundle",
            "entry": [
                {"search": {"mode": "match"}},
                {"resource": {"resourceType": "Patient", "id": "1"}},
            ],
        }
        entries = extract_bundle_entries(bundle)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["id"], "1")


# ---------------------------------------------------------------
# parse_fhir_datetime
# ---------------------------------------------------------------

class ParseFHIRDatetimeTest(TestCase):
    """Tests for parse_fhir_datetime()."""

    def test_z_suffix(self):
        result = parse_fhir_datetime("2024-01-15T10:30:00Z")
        self.assertIsNotNone(result)
        self.assertEqual(result.year, 2024)
        self.assertEqual(result.month, 1)
        self.assertEqual(result.day, 15)
        self.assertEqual(result.hour, 10)
        self.assertEqual(result.minute, 30)
        self.assertEqual(result.tzinfo, timezone.utc)

    def test_offset(self):
        result = parse_fhir_datetime("2024-06-01T14:00:00+05:00")
        self.assertIsNotNone(result)
        self.assertEqual(result.hour, 14)

    def test_date_only(self):
        result = parse_fhir_datetime("2024-01-15")
        self.assertIsNotNone(result)
        self.assertEqual(result.year, 2024)
        self.assertEqual(result.month, 1)
        self.assertEqual(result.day, 15)

    def test_none_input(self):
        result = parse_fhir_datetime(None)
        self.assertIsNone(result)

    def test_empty_string(self):
        result = parse_fhir_datetime("")
        self.assertIsNone(result)

    def test_invalid_string(self):
        result = parse_fhir_datetime("not-a-date")
        self.assertIsNone(result)


# ---------------------------------------------------------------
# extract_patient_name
# ---------------------------------------------------------------

class ExtractPatientNameTest(TestCase):
    """Tests for extract_patient_name()."""

    def test_normal_name(self):
        patient = {
            "name": [{"given": ["John", "Michael"], "family": "Smith"}],
        }
        self.assertEqual(extract_patient_name(patient), "John Michael Smith")

    def test_family_only(self):
        patient = {"name": [{"family": "Garcia"}]}
        self.assertEqual(extract_patient_name(patient), "Garcia")

    def test_given_only(self):
        patient = {"name": [{"given": ["Aiden"]}]}
        self.assertEqual(extract_patient_name(patient), "Aiden")

    def test_missing_name(self):
        patient = {}
        self.assertEqual(extract_patient_name(patient), "Unknown")

    def test_empty_name_list(self):
        patient = {"name": []}
        self.assertEqual(extract_patient_name(patient), "Unknown")

    def test_empty_name_entry(self):
        patient = {"name": [{}]}
        self.assertEqual(extract_patient_name(patient), "Unknown")


# ---------------------------------------------------------------
# extract_patient_mrn
# ---------------------------------------------------------------

class ExtractPatientMRNTest(TestCase):
    """Tests for extract_patient_mrn()."""

    def test_mrn_system(self):
        patient = {
            "identifier": [
                {"system": "http://hospital.org/mrn", "value": "MRN-12345"},
            ],
        }
        self.assertEqual(extract_patient_mrn(patient), "MRN-12345")

    def test_type_code_mr(self):
        patient = {
            "identifier": [
                {
                    "type": {"coding": [{"code": "MR"}]},
                    "value": "9876",
                },
            ],
        }
        self.assertEqual(extract_patient_mrn(patient), "9876")

    def test_fallback_first_identifier(self):
        patient = {
            "identifier": [
                {"system": "http://hospital.org/other", "value": "ABC-999"},
            ],
        }
        self.assertEqual(extract_patient_mrn(patient), "ABC-999")

    def test_no_identifiers(self):
        patient = {}
        self.assertEqual(extract_patient_mrn(patient), "Unknown")

    def test_empty_identifiers(self):
        patient = {"identifier": []}
        self.assertEqual(extract_patient_mrn(patient), "Unknown")

    def test_mrn_system_preferred_over_other(self):
        patient = {
            "identifier": [
                {"system": "http://hospital.org/ssn", "value": "SSN-111"},
                {"system": "http://hospital.org/mrn", "value": "MRN-222"},
            ],
        }
        self.assertEqual(extract_patient_mrn(patient), "MRN-222")


# ---------------------------------------------------------------
# extract_encounter_location
# ---------------------------------------------------------------

class ExtractEncounterLocationTest(TestCase):
    """Tests for extract_encounter_location()."""

    def test_location_with_service_provider(self):
        encounter = {
            "location": [
                {"location": {"display": "PICU G3-B12"}},
            ],
            "serviceProvider": {"display": "CCHMC"},
        }
        result = extract_encounter_location(encounter)
        self.assertEqual(result["unit"], "PICU G3-B12")
        self.assertEqual(result["facility"], "CCHMC")

    def test_location_only(self):
        encounter = {
            "location": [
                {"location": {"display": "NICU G1-A5"}},
            ],
        }
        result = extract_encounter_location(encounter)
        self.assertEqual(result["unit"], "NICU G1-A5")
        self.assertEqual(result["facility"], "NICU G1-A5")

    def test_no_location(self):
        encounter = {}
        result = extract_encounter_location(encounter)
        self.assertIsNone(result["unit"])
        self.assertIsNone(result["facility"])


# ---------------------------------------------------------------
# parse_susceptibility_observation
# ---------------------------------------------------------------

class ParseSusceptibilityObservationTest(TestCase):
    """Tests for parse_susceptibility_observation()."""

    def test_full_observation(self):
        obs = {
            "code": {"text": "Vancomycin [Susceptibility]"},
            "interpretation": [
                {"coding": [{"code": "S", "display": "Susceptible"}]},
            ],
            "valueQuantity": {
                "value": 1.0,
                "unit": "ug/mL",
                "comparator": "<=",
            },
        }
        result = parse_susceptibility_observation(obs)
        self.assertIsNotNone(result)
        self.assertEqual(result["antibiotic"], "vancomycin")
        self.assertEqual(result["result"], "S")
        self.assertEqual(result["mic"], "<=1.0 ug/mL")

    def test_resistant_from_display(self):
        obs = {
            "code": {"coding": [{"display": "Ampicillin"}]},
            "interpretation": [
                {"coding": [{"display": "Resistant"}]},
            ],
        }
        result = parse_susceptibility_observation(obs)
        self.assertIsNotNone(result)
        self.assertEqual(result["antibiotic"], "ampicillin")
        self.assertEqual(result["result"], "R")
        self.assertIsNone(result["mic"])

    def test_interpretation_from_value_codeable_concept(self):
        obs = {
            "code": {"text": "Meropenem"},
            "valueCodeableConcept": {
                "coding": [{"code": "I"}],
            },
        }
        result = parse_susceptibility_observation(obs)
        self.assertIsNotNone(result)
        self.assertEqual(result["result"], "I")

    def test_no_antibiotic_returns_none(self):
        obs = {
            "code": {},
            "interpretation": [{"coding": [{"code": "S"}]}],
        }
        result = parse_susceptibility_observation(obs)
        self.assertIsNone(result)

    def test_no_interpretation_returns_none(self):
        obs = {
            "code": {"text": "Vancomycin"},
        }
        result = parse_susceptibility_observation(obs)
        self.assertIsNone(result)


# ---------------------------------------------------------------
# HAPIFHIRClient construction
# ---------------------------------------------------------------

class HAPIFHIRClientTest(TestCase):
    """Tests for HAPIFHIRClient."""

    def test_default_base_url(self):
        client = HAPIFHIRClient()
        self.assertEqual(client.base_url, "http://localhost:8081/fhir")

    def test_custom_base_url(self):
        client = HAPIFHIRClient(base_url="http://fhir.example.com/R4")
        self.assertEqual(client.base_url, "http://fhir.example.com/R4")

    def test_trailing_slash_stripped(self):
        client = HAPIFHIRClient(base_url="http://fhir.example.com/R4/")
        self.assertEqual(client.base_url, "http://fhir.example.com/R4")

    @override_settings(FHIR_BASE_URL="http://settings-url:8082/fhir")
    def test_base_url_from_settings(self):
        client = HAPIFHIRClient()
        self.assertEqual(client.base_url, "http://settings-url:8082/fhir")

    def test_session_headers(self):
        client = HAPIFHIRClient()
        self.assertEqual(client.session.headers["Accept"], "application/fhir+json")

    def test_is_base_fhir_client(self):
        client = HAPIFHIRClient()
        self.assertIsInstance(client, BaseFHIRClient)

    def test_extract_entries_available(self):
        """extract_entries should be available as both static and instance method."""
        client = HAPIFHIRClient()
        bundle = {
            "resourceType": "Bundle",
            "entry": [{"resource": {"id": "1"}}],
        }
        self.assertEqual(len(client.extract_entries(bundle)), 1)
        self.assertEqual(len(client._extract_entries(bundle)), 1)

    def test_custom_timeout(self):
        client = HAPIFHIRClient(timeout=60)
        self.assertEqual(client.timeout, 60)


# ---------------------------------------------------------------
# get_fhir_client factory
# ---------------------------------------------------------------

class GetFHIRClientTest(TestCase):
    """Tests for get_fhir_client() factory."""

    def test_defaults_to_hapi(self):
        client = get_fhir_client()
        self.assertIsInstance(client, HAPIFHIRClient)

    @override_settings(
        EPIC_FHIR_BASE_URL="https://epic.example.com/FHIR/R4",
        EPIC_CLIENT_ID="test-client-id",
        EPIC_PRIVATE_KEY_PATH="",
    )
    def test_epic_settings_returns_epic_client(self):
        client = get_fhir_client()
        self.assertIsInstance(client, EpicFHIRClient)

    @override_settings(
        GUIDELINE_ADHERENCE={"FHIR_BASE_URL": "http://custom:8083/fhir"},
    )
    def test_module_specific_base_url(self):
        client = get_fhir_client(module_settings_key="GUIDELINE_ADHERENCE")
        self.assertIsInstance(client, HAPIFHIRClient)
        self.assertEqual(client.base_url, "http://custom:8083/fhir")

    def test_module_key_without_fhir_url(self):
        client = get_fhir_client(module_settings_key="NONEXISTENT_MODULE")
        self.assertIsInstance(client, HAPIFHIRClient)
        self.assertEqual(client.base_url, "http://localhost:8081/fhir")


# ---------------------------------------------------------------
# EpicFHIRClient
# ---------------------------------------------------------------

class EpicFHIRClientTest(TestCase):
    """Tests for EpicFHIRClient."""

    def test_is_base_fhir_client(self):
        client = EpicFHIRClient(
            base_url="https://epic.example.com/FHIR/R4",
            client_id="test",
        )
        self.assertIsInstance(client, BaseFHIRClient)

    def test_token_url_from_setting(self):
        client = EpicFHIRClient(
            base_url="https://epic.example.com/FHIR/R4",
            client_id="test",
            token_url="https://epic.example.com/oauth2/token",
        )
        self.assertEqual(
            client._get_token_url(),
            "https://epic.example.com/oauth2/token",
        )

    def test_token_url_derived(self):
        client = EpicFHIRClient(
            base_url="https://epic.example.com/FHIR/R4",
            client_id="test",
        )
        self.assertEqual(
            client._get_token_url(),
            "https://epic.example.com/oauth2/token",
        )

    def test_token_caching(self):
        """Cached token should be returned without re-authenticating."""
        client = EpicFHIRClient(
            base_url="https://epic.example.com/FHIR/R4",
            client_id="test",
        )
        client.access_token = "cached-token"
        client.token_expires_at = datetime.now() + __import__("datetime").timedelta(hours=1)

        # _get_access_token should return cached value without calling jwt
        token = client._get_access_token()
        self.assertEqual(token, "cached-token")

    def test_no_private_key_raises(self):
        client = EpicFHIRClient(
            base_url="https://epic.example.com/FHIR/R4",
            client_id="test",
        )
        client.access_token = None
        client.token_expires_at = None
        with self.assertRaises(ValueError):
            client._get_access_token()
