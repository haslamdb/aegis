"""Clinical knowledge base for antibiotic coverage rules.

This module encodes which antibiotics provide adequate coverage for
specific organisms identified in blood cultures.

NOTE: These rules are simplified for demonstration purposes.
Real clinical decision support would need:
- Local antibiogram data
- Susceptibility-guided adjustments
- Patient-specific factors (allergies, renal function, etc.)
- More granular organism identification
"""

from dataclasses import dataclass
from enum import Enum


class OrganismCategory(Enum):
    """Broad categories of organisms."""
    MRSA = "mrsa"
    MSSA = "mssa"
    VRE = "vre"
    VSE = "vse"  # Vancomycin-susceptible Enterococcus
    PSEUDOMONAS = "pseudomonas"
    ESBL = "esbl"  # Extended-spectrum beta-lactamase producers
    GRAM_NEG_SUSCEPTIBLE = "gram_neg_susceptible"
    CANDIDA = "candida"
    GPC_CLUSTERS = "gpc_clusters"  # Gram positive cocci in clusters (empiric)
    GPC_CHAINS = "gpc_chains"  # Gram positive cocci in chains (empiric)
    GNR = "gnr"  # Gram negative rods (empiric)
    UNKNOWN = "unknown"


@dataclass
class CoverageRule:
    """Rule for antibiotic coverage of an organism category."""
    organism_category: OrganismCategory
    adequate_antibiotics: set[str]  # RxNorm codes that provide coverage
    inadequate_antibiotics: set[str]  # RxNorm codes that definitely don't cover
    recommendation: str  # What to recommend if coverage is inadequate


# RxNorm codes for common antibiotics
RXNORM = {
    # Anti-MRSA agents
    "vancomycin": "11124",
    "daptomycin": "190376",
    "linezolid": "190521",
    "ceftaroline": "1009148",

    # Beta-lactams
    "cefazolin": "4053",
    "ceftriaxone": "2193",
    "cefepime": "2180",
    "piperacillin_tazobactam": "152834",
    "meropenem": "29561",
    "ampicillin": "733",
    "ampicillin_sulbactam": "57962",
    "nafcillin": "7233",
    "oxacillin": "7980",

    # Aminoglycosides
    "gentamicin": "4413",
    "tobramycin": "10627",
    "amikacin": "641",

    # Fluoroquinolones
    "ciprofloxacin": "2551",
    "levofloxacin": "82122",
    "moxifloxacin": "139462",

    # Antifungals
    "fluconazole": "4450",
    "micafungin": "327361",
    "caspofungin": "285661",
    "amphotericin_b": "732",
    "voriconazole": "121243",

    # Others
    "metronidazole": "6922",
    "trimethoprim_sulfamethoxazole": "10831",
}

# Reverse lookup: code -> name
RXNORM_NAMES = {v: k for k, v in RXNORM.items()}


# Coverage rules by organism category
COVERAGE_RULES: dict[OrganismCategory, CoverageRule] = {
    OrganismCategory.MRSA: CoverageRule(
        organism_category=OrganismCategory.MRSA,
        adequate_antibiotics={
            RXNORM["vancomycin"],
            RXNORM["daptomycin"],
            RXNORM["linezolid"],
            RXNORM["ceftaroline"],
        },
        inadequate_antibiotics={
            RXNORM["cefazolin"],
            RXNORM["ceftriaxone"],
            RXNORM["nafcillin"],
            RXNORM["oxacillin"],
            RXNORM["ampicillin"],
            RXNORM["piperacillin_tazobactam"],
        },
        recommendation="Add vancomycin or daptomycin for MRSA coverage",
    ),

    OrganismCategory.MSSA: CoverageRule(
        organism_category=OrganismCategory.MSSA,
        adequate_antibiotics={
            RXNORM["cefazolin"],
            RXNORM["nafcillin"],
            RXNORM["oxacillin"],
            RXNORM["vancomycin"],
            RXNORM["daptomycin"],
            RXNORM["ceftriaxone"],
        },
        inadequate_antibiotics=set(),
        recommendation="Add anti-staphylococcal beta-lactam (cefazolin, nafcillin)",
    ),

    OrganismCategory.VRE: CoverageRule(
        organism_category=OrganismCategory.VRE,
        adequate_antibiotics={
            RXNORM["daptomycin"],
            RXNORM["linezolid"],
        },
        inadequate_antibiotics={
            RXNORM["vancomycin"],
            RXNORM["ampicillin"],
        },
        recommendation="Add daptomycin or linezolid for VRE coverage",
    ),

    OrganismCategory.VSE: CoverageRule(
        organism_category=OrganismCategory.VSE,
        adequate_antibiotics={
            RXNORM["ampicillin"],
            RXNORM["vancomycin"],
            RXNORM["daptomycin"],
            RXNORM["linezolid"],
        },
        inadequate_antibiotics={
            RXNORM["cefazolin"],
            RXNORM["ceftriaxone"],
            RXNORM["cefepime"],
        },
        recommendation="Add ampicillin or vancomycin for enterococcal coverage",
    ),

    OrganismCategory.PSEUDOMONAS: CoverageRule(
        organism_category=OrganismCategory.PSEUDOMONAS,
        adequate_antibiotics={
            RXNORM["cefepime"],
            RXNORM["piperacillin_tazobactam"],
            RXNORM["meropenem"],
            RXNORM["ciprofloxacin"],
            RXNORM["levofloxacin"],
            RXNORM["tobramycin"],
            RXNORM["amikacin"],
        },
        inadequate_antibiotics={
            RXNORM["ceftriaxone"],
            RXNORM["cefazolin"],
            RXNORM["ampicillin_sulbactam"],
        },
        recommendation="Add anti-pseudomonal agent (cefepime, pip-tazo, meropenem)",
    ),

    OrganismCategory.GRAM_NEG_SUSCEPTIBLE: CoverageRule(
        organism_category=OrganismCategory.GRAM_NEG_SUSCEPTIBLE,
        adequate_antibiotics={
            RXNORM["ceftriaxone"],
            RXNORM["cefepime"],
            RXNORM["piperacillin_tazobactam"],
            RXNORM["meropenem"],
            RXNORM["ciprofloxacin"],
            RXNORM["levofloxacin"],
            RXNORM["gentamicin"],
        },
        inadequate_antibiotics={
            RXNORM["cefazolin"],
            RXNORM["vancomycin"],
        },
        recommendation="Add gram-negative coverage (ceftriaxone, cefepime)",
    ),

    OrganismCategory.CANDIDA: CoverageRule(
        organism_category=OrganismCategory.CANDIDA,
        adequate_antibiotics={
            RXNORM["fluconazole"],
            RXNORM["micafungin"],
            RXNORM["caspofungin"],
            RXNORM["amphotericin_b"],
            RXNORM["voriconazole"],
        },
        inadequate_antibiotics=set(),  # All antibacterials are inadequate
        recommendation="Add antifungal therapy (micafungin, fluconazole) for candidemia",
    ),

    # Empiric coverage for gram stain only
    OrganismCategory.GPC_CLUSTERS: CoverageRule(
        organism_category=OrganismCategory.GPC_CLUSTERS,
        adequate_antibiotics={
            RXNORM["vancomycin"],
            RXNORM["daptomycin"],
            RXNORM["linezolid"],
        },
        inadequate_antibiotics={
            RXNORM["cefazolin"],
            RXNORM["ceftriaxone"],
            RXNORM["piperacillin_tazobactam"],
        },
        recommendation="Add empiric MRSA coverage (vancomycin) for GPC in clusters",
    ),

    OrganismCategory.GPC_CHAINS: CoverageRule(
        organism_category=OrganismCategory.GPC_CHAINS,
        adequate_antibiotics={
            RXNORM["vancomycin"],
            RXNORM["ampicillin"],
            RXNORM["ceftriaxone"],
        },
        inadequate_antibiotics=set(),
        recommendation="Ensure streptococcal/enterococcal coverage",
    ),

    OrganismCategory.GNR: CoverageRule(
        organism_category=OrganismCategory.GNR,
        adequate_antibiotics={
            RXNORM["cefepime"],
            RXNORM["piperacillin_tazobactam"],
            RXNORM["meropenem"],
            RXNORM["ceftriaxone"],
        },
        inadequate_antibiotics={
            RXNORM["cefazolin"],
            RXNORM["vancomycin"],
        },
        recommendation="Add empiric gram-negative coverage for GNR",
    ),
}


def categorize_organism(organism_text: str, gram_stain: str | None = None) -> OrganismCategory:
    """
    Categorize an organism based on culture result text.

    Args:
        organism_text: The organism identification from the culture
        gram_stain: Gram stain result if organism not yet identified

    Returns:
        OrganismCategory enum value
    """
    if not organism_text:
        organism_text = ""
    organism_lower = organism_text.lower()

    # Check for specific organisms first
    if "mrsa" in organism_lower:
        return OrganismCategory.MRSA
    if "methicillin resistant" in organism_lower and "staphylococcus" in organism_lower:
        return OrganismCategory.MRSA

    if "mssa" in organism_lower or "methicillin susceptible" in organism_lower:
        if "staphylococcus" in organism_lower:
            return OrganismCategory.MSSA

    if "staphylococcus aureus" in organism_lower:
        # Default to MRSA if not specified (safer assumption)
        return OrganismCategory.MRSA

    if "vre" in organism_lower or "vancomycin resistant" in organism_lower:
        if "enterococcus" in organism_lower:
            return OrganismCategory.VRE

    if "enterococcus" in organism_lower:
        # Default to VSE if VRE not specified
        return OrganismCategory.VSE

    if "pseudomonas" in organism_lower:
        return OrganismCategory.PSEUDOMONAS

    if "candida" in organism_lower:
        return OrganismCategory.CANDIDA

    # Common gram-negative organisms
    gram_neg_organisms = [
        "escherichia coli", "e. coli", "e.coli",
        "klebsiella", "enterobacter", "serratia",
        "proteus", "citrobacter", "salmonella",
    ]
    for org in gram_neg_organisms:
        if org in organism_lower:
            return OrganismCategory.GRAM_NEG_SUSCEPTIBLE

    # Fall back to gram stain interpretation
    if gram_stain:
        gram_lower = gram_stain.lower()
        if "gram positive cocci" in gram_lower:
            if "cluster" in gram_lower:
                return OrganismCategory.GPC_CLUSTERS
            if "chain" in gram_lower:
                return OrganismCategory.GPC_CHAINS
        if "gram negative" in gram_lower and "rod" in gram_lower:
            return OrganismCategory.GNR

    # If we have "pending" or no useful info
    if "pending" in organism_lower or not organism_text.strip():
        return OrganismCategory.UNKNOWN

    return OrganismCategory.UNKNOWN


def get_coverage_rule(category: OrganismCategory) -> CoverageRule | None:
    """Get the coverage rule for an organism category."""
    return COVERAGE_RULES.get(category)


def get_antibiotic_name(rxnorm_code: str) -> str:
    """Get antibiotic name from RxNorm code."""
    return RXNORM_NAMES.get(rxnorm_code, f"Unknown ({rxnorm_code})")
