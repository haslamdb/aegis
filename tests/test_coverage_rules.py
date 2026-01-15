"""Tests for coverage rules."""

import pytest
from src.coverage_rules import (
    OrganismCategory,
    categorize_organism,
    get_coverage_rule,
    RXNORM,
)


class TestOrganismCategorization:
    """Test organism categorization logic."""

    def test_mrsa_explicit(self):
        assert categorize_organism("MRSA") == OrganismCategory.MRSA
        assert categorize_organism("MRSA - Methicillin resistant Staphylococcus aureus") == OrganismCategory.MRSA

    def test_mrsa_from_staph_aureus(self):
        # Default assumption for S. aureus without susceptibility
        assert categorize_organism("Staphylococcus aureus") == OrganismCategory.MRSA

    def test_mssa(self):
        assert categorize_organism("MSSA - Methicillin susceptible Staphylococcus aureus") == OrganismCategory.MSSA

    def test_vre(self):
        assert categorize_organism("VRE - Vancomycin resistant Enterococcus faecium") == OrganismCategory.VRE

    def test_vse(self):
        assert categorize_organism("Enterococcus faecalis") == OrganismCategory.VSE

    def test_pseudomonas(self):
        assert categorize_organism("Pseudomonas aeruginosa") == OrganismCategory.PSEUDOMONAS

    def test_candida(self):
        assert categorize_organism("Candida albicans") == OrganismCategory.CANDIDA
        assert categorize_organism("Candida glabrata") == OrganismCategory.CANDIDA

    def test_gram_neg_organisms(self):
        assert categorize_organism("Escherichia coli") == OrganismCategory.GRAM_NEG_SUSCEPTIBLE
        assert categorize_organism("E. coli") == OrganismCategory.GRAM_NEG_SUSCEPTIBLE
        assert categorize_organism("Klebsiella pneumoniae") == OrganismCategory.GRAM_NEG_SUSCEPTIBLE

    def test_gram_stain_gpc_clusters(self):
        assert categorize_organism(
            "Pending identification",
            gram_stain="Gram positive cocci in clusters"
        ) == OrganismCategory.GPC_CLUSTERS

    def test_gram_stain_gpc_chains(self):
        assert categorize_organism(
            "Pending identification",
            gram_stain="Gram positive cocci in chains"
        ) == OrganismCategory.GPC_CHAINS

    def test_gram_stain_gnr(self):
        assert categorize_organism(
            "Pending identification",
            gram_stain="Gram negative rods"
        ) == OrganismCategory.GNR

    def test_unknown_organism(self):
        assert categorize_organism("") == OrganismCategory.UNKNOWN
        assert categorize_organism("Pending") == OrganismCategory.UNKNOWN


class TestCoverageRules:
    """Test that coverage rules are properly defined."""

    def test_mrsa_rule_exists(self):
        rule = get_coverage_rule(OrganismCategory.MRSA)
        assert rule is not None
        assert RXNORM["vancomycin"] in rule.adequate_antibiotics
        assert RXNORM["cefazolin"] in rule.inadequate_antibiotics

    def test_pseudomonas_rule_exists(self):
        rule = get_coverage_rule(OrganismCategory.PSEUDOMONAS)
        assert rule is not None
        assert RXNORM["cefepime"] in rule.adequate_antibiotics
        assert RXNORM["ceftriaxone"] in rule.inadequate_antibiotics

    def test_candida_rule_exists(self):
        rule = get_coverage_rule(OrganismCategory.CANDIDA)
        assert rule is not None
        assert RXNORM["micafungin"] in rule.adequate_antibiotics
        assert RXNORM["fluconazole"] in rule.adequate_antibiotics

    def test_vre_rule_excludes_vancomycin(self):
        rule = get_coverage_rule(OrganismCategory.VRE)
        assert rule is not None
        assert RXNORM["vancomycin"] in rule.inadequate_antibiotics
        assert RXNORM["daptomycin"] in rule.adequate_antibiotics
