"""
MDRO Surveillance - Tests
"""

from django.test import TestCase


class MDROClassifierTest(TestCase):
    """Tests for MDRO classification logic."""

    def test_mrsa_detection(self):
        from .classifier import MDROClassifier, MDROType
        classifier = MDROClassifier()
        result = classifier.classify(
            "Staphylococcus aureus",
            [{"antibiotic": "oxacillin", "result": "R"}]
        )
        self.assertTrue(result.is_mdro)
        self.assertEqual(result.mdro_type, MDROType.MRSA)

    def test_vre_detection(self):
        from .classifier import MDROClassifier, MDROType
        classifier = MDROClassifier()
        result = classifier.classify(
            "Enterococcus faecium",
            [{"antibiotic": "vancomycin", "result": "R"}]
        )
        self.assertTrue(result.is_mdro)
        self.assertEqual(result.mdro_type, MDROType.VRE)

    def test_not_mdro(self):
        from .classifier import MDROClassifier
        classifier = MDROClassifier()
        result = classifier.classify(
            "Staphylococcus aureus",
            [{"antibiotic": "oxacillin", "result": "S"}]
        )
        self.assertFalse(result.is_mdro)
