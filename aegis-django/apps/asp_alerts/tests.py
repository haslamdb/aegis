"""Tests for ASP Alerts module - coverage rules and organism categorization."""

from django.test import TestCase

from .coverage_rules import (
    CoverageRule,
    OrganismCategory,
    COVERAGE_RULES,
    RXNORM,
    RXNORM_NAMES,
    categorize_organism,
    get_coverage_rule,
    get_antibiotic_name,
)


# ===========================================================================
# OrganismCategory enum tests
# ===========================================================================

class OrganismCategoryTests(TestCase):
    """Test OrganismCategory enum."""

    def test_all_twelve_categories(self):
        expected = {
            "mrsa", "mssa", "vre", "vse", "pseudomonas", "esbl",
            "gram_neg_susceptible", "candida", "gpc_clusters",
            "gpc_chains", "gnr", "unknown",
        }
        actual = {c.value for c in OrganismCategory}
        self.assertEqual(actual, expected)

    def test_enum_value_access(self):
        self.assertEqual(OrganismCategory.MRSA.value, "mrsa")
        self.assertEqual(OrganismCategory.PSEUDOMONAS.value, "pseudomonas")
        self.assertEqual(OrganismCategory.CANDIDA.value, "candida")


# ===========================================================================
# Organism categorization tests
# ===========================================================================

class CategorizeOrganismTests(TestCase):
    """Test categorize_organism function."""

    def test_mrsa_text(self):
        self.assertEqual(
            categorize_organism("MRSA"),
            OrganismCategory.MRSA,
        )

    def test_methicillin_resistant_staphylococcus(self):
        self.assertEqual(
            categorize_organism("Methicillin resistant Staphylococcus aureus"),
            OrganismCategory.MRSA,
        )

    def test_staphylococcus_aureus_defaults_mrsa(self):
        """Unspecified S. aureus defaults to MRSA (safer)."""
        self.assertEqual(
            categorize_organism("Staphylococcus aureus"),
            OrganismCategory.MRSA,
        )

    def test_mssa(self):
        self.assertEqual(
            categorize_organism("MSSA Staphylococcus aureus"),
            OrganismCategory.MSSA,
        )

    def test_methicillin_susceptible_staph(self):
        self.assertEqual(
            categorize_organism("Methicillin susceptible Staphylococcus"),
            OrganismCategory.MSSA,
        )

    def test_vre(self):
        self.assertEqual(
            categorize_organism("VRE Enterococcus faecium"),
            OrganismCategory.VRE,
        )

    def test_vancomycin_resistant_enterococcus(self):
        self.assertEqual(
            categorize_organism("Vancomycin resistant Enterococcus"),
            OrganismCategory.VRE,
        )

    def test_enterococcus_defaults_vse(self):
        self.assertEqual(
            categorize_organism("Enterococcus faecalis"),
            OrganismCategory.VSE,
        )

    def test_pseudomonas(self):
        self.assertEqual(
            categorize_organism("Pseudomonas aeruginosa"),
            OrganismCategory.PSEUDOMONAS,
        )

    def test_candida(self):
        self.assertEqual(
            categorize_organism("Candida albicans"),
            OrganismCategory.CANDIDA,
        )

    def test_e_coli(self):
        self.assertEqual(
            categorize_organism("Escherichia coli"),
            OrganismCategory.GRAM_NEG_SUSCEPTIBLE,
        )

    def test_klebsiella(self):
        self.assertEqual(
            categorize_organism("Klebsiella pneumoniae"),
            OrganismCategory.GRAM_NEG_SUSCEPTIBLE,
        )

    def test_gram_stain_gpc_clusters(self):
        self.assertEqual(
            categorize_organism("", gram_stain="Gram positive cocci in clusters"),
            OrganismCategory.GPC_CLUSTERS,
        )

    def test_gram_stain_gpc_chains(self):
        self.assertEqual(
            categorize_organism("", gram_stain="Gram positive cocci in chains"),
            OrganismCategory.GPC_CHAINS,
        )

    def test_gram_stain_gnr(self):
        self.assertEqual(
            categorize_organism("", gram_stain="Gram negative rods"),
            OrganismCategory.GNR,
        )

    def test_pending_returns_unknown(self):
        self.assertEqual(
            categorize_organism("Pending"),
            OrganismCategory.UNKNOWN,
        )

    def test_empty_string_returns_unknown(self):
        self.assertEqual(
            categorize_organism(""),
            OrganismCategory.UNKNOWN,
        )

    def test_none_returns_unknown(self):
        self.assertEqual(
            categorize_organism(None),
            OrganismCategory.UNKNOWN,
        )


# ===========================================================================
# Coverage rules tests
# ===========================================================================

class CoverageRulesDefinitionTests(TestCase):
    """Test that coverage rules are defined for all expected categories."""

    def test_mrsa_rule_exists(self):
        rule = COVERAGE_RULES.get(OrganismCategory.MRSA)
        self.assertIsNotNone(rule)
        self.assertIsInstance(rule, CoverageRule)

    def test_pseudomonas_rule_exists(self):
        rule = COVERAGE_RULES.get(OrganismCategory.PSEUDOMONAS)
        self.assertIsNotNone(rule)

    def test_candida_rule_exists(self):
        rule = COVERAGE_RULES.get(OrganismCategory.CANDIDA)
        self.assertIsNotNone(rule)

    def test_all_rules_have_recommendations(self):
        for category, rule in COVERAGE_RULES.items():
            self.assertTrue(
                len(rule.recommendation) > 0,
                f"Missing recommendation for {category}",
            )

    def test_coverage_rules_count(self):
        """At least 10 organism categories have rules."""
        self.assertGreaterEqual(len(COVERAGE_RULES), 10)


class MRSACoverageTests(TestCase):
    """Test MRSA coverage rules."""

    def test_vancomycin_covers_mrsa(self):
        rule = COVERAGE_RULES[OrganismCategory.MRSA]
        self.assertIn(RXNORM["vancomycin"], rule.adequate_antibiotics)

    def test_daptomycin_covers_mrsa(self):
        rule = COVERAGE_RULES[OrganismCategory.MRSA]
        self.assertIn(RXNORM["daptomycin"], rule.adequate_antibiotics)

    def test_linezolid_covers_mrsa(self):
        rule = COVERAGE_RULES[OrganismCategory.MRSA]
        self.assertIn(RXNORM["linezolid"], rule.adequate_antibiotics)

    def test_ceftriaxone_does_not_cover_mrsa(self):
        rule = COVERAGE_RULES[OrganismCategory.MRSA]
        self.assertIn(RXNORM["ceftriaxone"], rule.inadequate_antibiotics)

    def test_cefazolin_does_not_cover_mrsa(self):
        rule = COVERAGE_RULES[OrganismCategory.MRSA]
        self.assertIn(RXNORM["cefazolin"], rule.inadequate_antibiotics)


class VRECoverageTests(TestCase):
    """Test VRE coverage rules."""

    def test_daptomycin_covers_vre(self):
        rule = COVERAGE_RULES[OrganismCategory.VRE]
        self.assertIn(RXNORM["daptomycin"], rule.adequate_antibiotics)

    def test_linezolid_covers_vre(self):
        rule = COVERAGE_RULES[OrganismCategory.VRE]
        self.assertIn(RXNORM["linezolid"], rule.adequate_antibiotics)

    def test_vancomycin_does_not_cover_vre(self):
        rule = COVERAGE_RULES[OrganismCategory.VRE]
        self.assertIn(RXNORM["vancomycin"], rule.inadequate_antibiotics)


class PseudomonasCoverageTests(TestCase):
    """Test Pseudomonas coverage rules."""

    def test_cefepime_covers_pseudomonas(self):
        rule = COVERAGE_RULES[OrganismCategory.PSEUDOMONAS]
        self.assertIn(RXNORM["cefepime"], rule.adequate_antibiotics)

    def test_meropenem_covers_pseudomonas(self):
        rule = COVERAGE_RULES[OrganismCategory.PSEUDOMONAS]
        self.assertIn(RXNORM["meropenem"], rule.adequate_antibiotics)

    def test_pip_tazo_covers_pseudomonas(self):
        rule = COVERAGE_RULES[OrganismCategory.PSEUDOMONAS]
        self.assertIn(RXNORM["piperacillin_tazobactam"], rule.adequate_antibiotics)

    def test_ceftriaxone_does_not_cover_pseudomonas(self):
        rule = COVERAGE_RULES[OrganismCategory.PSEUDOMONAS]
        self.assertIn(RXNORM["ceftriaxone"], rule.inadequate_antibiotics)


class CandidaCoverageTests(TestCase):
    """Test Candida coverage rules."""

    def test_fluconazole_covers_candida(self):
        rule = COVERAGE_RULES[OrganismCategory.CANDIDA]
        self.assertIn(RXNORM["fluconazole"], rule.adequate_antibiotics)

    def test_micafungin_covers_candida(self):
        rule = COVERAGE_RULES[OrganismCategory.CANDIDA]
        self.assertIn(RXNORM["micafungin"], rule.adequate_antibiotics)


# ===========================================================================
# RxNorm mapping tests
# ===========================================================================

class RxNormMappingTests(TestCase):
    """Test RxNorm code lookups."""

    def test_vancomycin_rxnorm(self):
        self.assertEqual(RXNORM["vancomycin"], "11124")

    def test_meropenem_rxnorm(self):
        self.assertEqual(RXNORM["meropenem"], "29561")

    def test_reverse_lookup(self):
        self.assertEqual(RXNORM_NAMES["11124"], "vancomycin")
        self.assertEqual(RXNORM_NAMES["29561"], "meropenem")

    def test_get_antibiotic_name_known(self):
        self.assertEqual(get_antibiotic_name("11124"), "vancomycin")

    def test_get_antibiotic_name_unknown(self):
        name = get_antibiotic_name("99999")
        self.assertIn("Unknown", name)

    def test_rxnorm_has_expected_entries(self):
        expected_keys = [
            "vancomycin", "meropenem", "ceftriaxone", "cefepime",
            "piperacillin_tazobactam", "fluconazole", "ciprofloxacin",
        ]
        for key in expected_keys:
            self.assertIn(key, RXNORM, f"Missing RxNorm entry for {key}")


# ===========================================================================
# Helper function tests
# ===========================================================================

class GetCoverageRuleTests(TestCase):
    """Test get_coverage_rule helper."""

    def test_returns_rule_for_known_category(self):
        rule = get_coverage_rule(OrganismCategory.MRSA)
        self.assertIsNotNone(rule)
        self.assertEqual(rule.organism_category, OrganismCategory.MRSA)

    def test_returns_none_for_unknown(self):
        rule = get_coverage_rule(OrganismCategory.UNKNOWN)
        self.assertIsNone(rule)

    def test_returns_none_for_esbl(self):
        """ESBL does not have a rule in the current coverage rules."""
        rule = get_coverage_rule(OrganismCategory.ESBL)
        self.assertIsNone(rule)
