"""Allergy cross-reactivity rules and recommendation filtering logic.

Clinical references:
- Penicillin-cephalosporin cross-reactivity is ~1-2% overall, higher for 1st gen
- Carbapenem cross-reactivity with penicillin is ~1%
- Aztreonam (monobactam) is safe in penicillin allergy except ceftazidime allergy
- Sulfa drug cross-reactivity is rare between antibiotics and non-antibiotics
"""

from .models import (
    AntibioticClass,
    AllergyConflict,
    CrossReactivityRisk,
    SafeRecommendation,
)


# =============================================================================
# Antibiotic Classification
# =============================================================================

ANTIBIOTIC_CLASSES: dict[str, AntibioticClass] = {
    # Penicillins
    "penicillin": AntibioticClass.PENICILLIN,
    "amoxicillin": AntibioticClass.PENICILLIN,
    "ampicillin": AntibioticClass.PENICILLIN,
    "piperacillin": AntibioticClass.PENICILLIN,
    "piperacillin-tazobactam": AntibioticClass.PENICILLIN,
    "piperacillin/tazobactam": AntibioticClass.PENICILLIN,
    "pip-tazo": AntibioticClass.PENICILLIN,
    "zosyn": AntibioticClass.PENICILLIN,
    "nafcillin": AntibioticClass.PENICILLIN,
    "oxacillin": AntibioticClass.PENICILLIN,
    "dicloxacillin": AntibioticClass.PENICILLIN,
    "ampicillin-sulbactam": AntibioticClass.PENICILLIN,
    "amoxicillin-clavulanate": AntibioticClass.PENICILLIN,
    "augmentin": AntibioticClass.PENICILLIN,
    "unasyn": AntibioticClass.PENICILLIN,

    # Cephalosporins - 1st generation
    "cefazolin": AntibioticClass.CEPHALOSPORIN,
    "ancef": AntibioticClass.CEPHALOSPORIN,
    "cephalexin": AntibioticClass.CEPHALOSPORIN,
    "keflex": AntibioticClass.CEPHALOSPORIN,
    "cefadroxil": AntibioticClass.CEPHALOSPORIN,

    # Cephalosporins - 2nd generation
    "cefuroxime": AntibioticClass.CEPHALOSPORIN,
    "cefoxitin": AntibioticClass.CEPHALOSPORIN,
    "cefotetan": AntibioticClass.CEPHALOSPORIN,
    "cefprozil": AntibioticClass.CEPHALOSPORIN,
    "cefaclor": AntibioticClass.CEPHALOSPORIN,

    # Cephalosporins - 3rd generation
    "ceftriaxone": AntibioticClass.CEPHALOSPORIN,
    "rocephin": AntibioticClass.CEPHALOSPORIN,
    "ceftazidime": AntibioticClass.CEPHALOSPORIN,
    "cefotaxime": AntibioticClass.CEPHALOSPORIN,
    "cefpodoxime": AntibioticClass.CEPHALOSPORIN,
    "cefdinir": AntibioticClass.CEPHALOSPORIN,
    "cefixime": AntibioticClass.CEPHALOSPORIN,

    # Cephalosporins - 4th generation
    "cefepime": AntibioticClass.CEPHALOSPORIN,
    "maxipime": AntibioticClass.CEPHALOSPORIN,

    # Cephalosporins - 5th generation
    "ceftaroline": AntibioticClass.CEPHALOSPORIN,
    "teflaro": AntibioticClass.CEPHALOSPORIN,
    "ceftobiprole": AntibioticClass.CEPHALOSPORIN,

    # Cephalosporin combinations
    "ceftazidime-avibactam": AntibioticClass.CEPHALOSPORIN,
    "avycaz": AntibioticClass.CEPHALOSPORIN,
    "ceftolozane-tazobactam": AntibioticClass.CEPHALOSPORIN,
    "zerbaxa": AntibioticClass.CEPHALOSPORIN,

    # Carbapenems
    "meropenem": AntibioticClass.CARBAPENEM,
    "merrem": AntibioticClass.CARBAPENEM,
    "imipenem": AntibioticClass.CARBAPENEM,
    "imipenem-cilastatin": AntibioticClass.CARBAPENEM,
    "primaxin": AntibioticClass.CARBAPENEM,
    "ertapenem": AntibioticClass.CARBAPENEM,
    "invanz": AntibioticClass.CARBAPENEM,
    "doripenem": AntibioticClass.CARBAPENEM,
    "meropenem-vaborbactam": AntibioticClass.CARBAPENEM,

    # Monobactams (safe in penicillin allergy)
    "aztreonam": AntibioticClass.MONOBACTAM,
    "azactam": AntibioticClass.MONOBACTAM,

    # Fluoroquinolones
    "ciprofloxacin": AntibioticClass.FLUOROQUINOLONE,
    "cipro": AntibioticClass.FLUOROQUINOLONE,
    "levofloxacin": AntibioticClass.FLUOROQUINOLONE,
    "levaquin": AntibioticClass.FLUOROQUINOLONE,
    "moxifloxacin": AntibioticClass.FLUOROQUINOLONE,
    "avelox": AntibioticClass.FLUOROQUINOLONE,
    "ofloxacin": AntibioticClass.FLUOROQUINOLONE,
    "delafloxacin": AntibioticClass.FLUOROQUINOLONE,

    # Aminoglycosides
    "gentamicin": AntibioticClass.AMINOGLYCOSIDE,
    "tobramycin": AntibioticClass.AMINOGLYCOSIDE,
    "amikacin": AntibioticClass.AMINOGLYCOSIDE,
    "streptomycin": AntibioticClass.AMINOGLYCOSIDE,
    "neomycin": AntibioticClass.AMINOGLYCOSIDE,
    "plazomicin": AntibioticClass.AMINOGLYCOSIDE,

    # Glycopeptides
    "vancomycin": AntibioticClass.GLYCOPEPTIDE,
    "vancocin": AntibioticClass.GLYCOPEPTIDE,
    "telavancin": AntibioticClass.GLYCOPEPTIDE,
    "dalbavancin": AntibioticClass.GLYCOPEPTIDE,
    "oritavancin": AntibioticClass.GLYCOPEPTIDE,

    # Lipopeptides
    "daptomycin": AntibioticClass.LIPOPEPTIDE,
    "cubicin": AntibioticClass.LIPOPEPTIDE,

    # Oxazolidinones
    "linezolid": AntibioticClass.OXAZOLIDINONE,
    "zyvox": AntibioticClass.OXAZOLIDINONE,
    "tedizolid": AntibioticClass.OXAZOLIDINONE,

    # Macrolides
    "azithromycin": AntibioticClass.MACROLIDE,
    "zithromax": AntibioticClass.MACROLIDE,
    "erythromycin": AntibioticClass.MACROLIDE,
    "clarithromycin": AntibioticClass.MACROLIDE,
    "biaxin": AntibioticClass.MACROLIDE,
    "fidaxomicin": AntibioticClass.MACROLIDE,

    # Tetracyclines
    "doxycycline": AntibioticClass.TETRACYCLINE,
    "minocycline": AntibioticClass.TETRACYCLINE,
    "tetracycline": AntibioticClass.TETRACYCLINE,
    "tigecycline": AntibioticClass.TETRACYCLINE,
    "eravacycline": AntibioticClass.TETRACYCLINE,
    "omadacycline": AntibioticClass.TETRACYCLINE,

    # Sulfonamides
    "sulfamethoxazole": AntibioticClass.SULFONAMIDE,
    "trimethoprim-sulfamethoxazole": AntibioticClass.SULFONAMIDE,
    "tmp-smx": AntibioticClass.SULFONAMIDE,
    "bactrim": AntibioticClass.SULFONAMIDE,
    "septra": AntibioticClass.SULFONAMIDE,
    "sulfadiazine": AntibioticClass.SULFONAMIDE,

    # Nitroimidazoles
    "metronidazole": AntibioticClass.NITROIMIDAZOLE,
    "flagyl": AntibioticClass.NITROIMIDAZOLE,
    "tinidazole": AntibioticClass.NITROIMIDAZOLE,

    # Antifungal azoles
    "fluconazole": AntibioticClass.ANTIFUNGAL_AZOLE,
    "diflucan": AntibioticClass.ANTIFUNGAL_AZOLE,
    "voriconazole": AntibioticClass.ANTIFUNGAL_AZOLE,
    "vfend": AntibioticClass.ANTIFUNGAL_AZOLE,
    "posaconazole": AntibioticClass.ANTIFUNGAL_AZOLE,
    "isavuconazole": AntibioticClass.ANTIFUNGAL_AZOLE,
    "itraconazole": AntibioticClass.ANTIFUNGAL_AZOLE,

    # Echinocandins
    "micafungin": AntibioticClass.ANTIFUNGAL_ECHINOCANDIN,
    "mycamine": AntibioticClass.ANTIFUNGAL_ECHINOCANDIN,
    "caspofungin": AntibioticClass.ANTIFUNGAL_ECHINOCANDIN,
    "cancidas": AntibioticClass.ANTIFUNGAL_ECHINOCANDIN,
    "anidulafungin": AntibioticClass.ANTIFUNGAL_ECHINOCANDIN,

    # Polyenes
    "amphotericin": AntibioticClass.ANTIFUNGAL_POLYENE,
    "amphotericin b": AntibioticClass.ANTIFUNGAL_POLYENE,
    "ambisome": AntibioticClass.ANTIFUNGAL_POLYENE,
    "abelcet": AntibioticClass.ANTIFUNGAL_POLYENE,

    # Other
    "clindamycin": AntibioticClass.OTHER,
    "cleocin": AntibioticClass.OTHER,
    "nitrofurantoin": AntibioticClass.OTHER,
    "macrobid": AntibioticClass.OTHER,
    "fosfomycin": AntibioticClass.OTHER,
    "colistin": AntibioticClass.OTHER,
    "polymyxin b": AntibioticClass.OTHER,
    "rifampin": AntibioticClass.OTHER,
    "rifampicin": AntibioticClass.OTHER,
}


# =============================================================================
# Cross-Reactivity Rules
# =============================================================================

# Cross-reactivity risk between drug classes
# Key: (allergy_class, drug_class) -> risk level
CROSS_REACTIVITY_RULES: dict[tuple[AntibioticClass, AntibioticClass], CrossReactivityRisk] = {
    # Penicillin allergy cross-reactivity
    (AntibioticClass.PENICILLIN, AntibioticClass.PENICILLIN): CrossReactivityRisk.CONTRAINDICATED,
    (AntibioticClass.PENICILLIN, AntibioticClass.CEPHALOSPORIN): CrossReactivityRisk.LOW,  # ~1-2%
    (AntibioticClass.PENICILLIN, AntibioticClass.CARBAPENEM): CrossReactivityRisk.LOW,  # ~1%
    (AntibioticClass.PENICILLIN, AntibioticClass.MONOBACTAM): CrossReactivityRisk.NONE,  # Safe

    # Cephalosporin allergy cross-reactivity
    (AntibioticClass.CEPHALOSPORIN, AntibioticClass.CEPHALOSPORIN): CrossReactivityRisk.CONTRAINDICATED,
    (AntibioticClass.CEPHALOSPORIN, AntibioticClass.PENICILLIN): CrossReactivityRisk.MODERATE,
    (AntibioticClass.CEPHALOSPORIN, AntibioticClass.CARBAPENEM): CrossReactivityRisk.LOW,
    # Note: Ceftazidime shares side chain with aztreonam
    (AntibioticClass.CEPHALOSPORIN, AntibioticClass.MONOBACTAM): CrossReactivityRisk.LOW,

    # Carbapenem allergy
    (AntibioticClass.CARBAPENEM, AntibioticClass.CARBAPENEM): CrossReactivityRisk.CONTRAINDICATED,
    (AntibioticClass.CARBAPENEM, AntibioticClass.PENICILLIN): CrossReactivityRisk.MODERATE,
    (AntibioticClass.CARBAPENEM, AntibioticClass.CEPHALOSPORIN): CrossReactivityRisk.LOW,

    # Sulfonamide allergy (antibiotics)
    (AntibioticClass.SULFONAMIDE, AntibioticClass.SULFONAMIDE): CrossReactivityRisk.CONTRAINDICATED,

    # Fluoroquinolone allergy
    (AntibioticClass.FLUOROQUINOLONE, AntibioticClass.FLUOROQUINOLONE): CrossReactivityRisk.CONTRAINDICATED,

    # Macrolide allergy
    (AntibioticClass.MACROLIDE, AntibioticClass.MACROLIDE): CrossReactivityRisk.CONTRAINDICATED,

    # Aminoglycoside allergy
    (AntibioticClass.AMINOGLYCOSIDE, AntibioticClass.AMINOGLYCOSIDE): CrossReactivityRisk.CONTRAINDICATED,

    # Glycopeptide allergy
    (AntibioticClass.GLYCOPEPTIDE, AntibioticClass.GLYCOPEPTIDE): CrossReactivityRisk.CONTRAINDICATED,

    # Tetracycline allergy
    (AntibioticClass.TETRACYCLINE, AntibioticClass.TETRACYCLINE): CrossReactivityRisk.CONTRAINDICATED,

    # Azole antifungal allergy
    (AntibioticClass.ANTIFUNGAL_AZOLE, AntibioticClass.ANTIFUNGAL_AZOLE): CrossReactivityRisk.CONTRAINDICATED,
}


# =============================================================================
# Alternative Suggestions for Allergy Scenarios
# =============================================================================

# When a class is contraindicated, suggest these alternatives
ALTERNATIVE_SUGGESTIONS: dict[AntibioticClass, dict[str, list[str]]] = {
    AntibioticClass.PENICILLIN: {
        # Alternatives for gram-positive coverage
        "gram_positive": ["vancomycin", "daptomycin", "linezolid"],
        # Alternatives for gram-negative coverage
        "gram_negative": ["aztreonam", "fluoroquinolone", "aminoglycoside"],
        # Broad spectrum alternatives
        "broad_spectrum": ["aztreonam + vancomycin", "fluoroquinolone + vancomycin"],
    },
    AntibioticClass.CEPHALOSPORIN: {
        "gram_positive": ["vancomycin", "daptomycin", "linezolid"],
        "gram_negative": ["aztreonam", "fluoroquinolone", "aminoglycoside"],
        "broad_spectrum": ["aztreonam + vancomycin", "meropenem (if no severe beta-lactam allergy)"],
    },
    AntibioticClass.CARBAPENEM: {
        "gram_positive": ["vancomycin", "daptomycin", "linezolid"],
        "gram_negative": ["aztreonam", "aminoglycoside", "ceftazidime-avibactam"],
        "broad_spectrum": ["aztreonam + vancomycin + metronidazole"],
    },
    AntibioticClass.FLUOROQUINOLONE: {
        "gram_negative": ["cephalosporin", "aminoglycoside", "aztreonam"],
        "respiratory": ["cephalosporin", "macrolide"],
    },
    AntibioticClass.SULFONAMIDE: {
        "uti": ["nitrofurantoin", "fosfomycin", "fluoroquinolone"],
        "pcp_prophylaxis": ["dapsone", "atovaquone", "pentamidine"],
    },
    AntibioticClass.GLYCOPEPTIDE: {
        "mrsa": ["daptomycin", "linezolid", "ceftaroline"],
    },
}


# =============================================================================
# Core Functions
# =============================================================================

def get_antibiotic_class(antibiotic_name: str) -> AntibioticClass:
    """Get the drug class for an antibiotic by name."""
    name_lower = antibiotic_name.lower().strip()

    # Direct lookup
    if name_lower in ANTIBIOTIC_CLASSES:
        return ANTIBIOTIC_CLASSES[name_lower]

    # Try partial matching
    for known_name, drug_class in ANTIBIOTIC_CLASSES.items():
        if known_name in name_lower or name_lower in known_name:
            return drug_class

    return AntibioticClass.OTHER


def get_cross_reactivity_risk(
    allergy_class: AntibioticClass,
    drug_class: AntibioticClass,
) -> CrossReactivityRisk:
    """Get the cross-reactivity risk between an allergy and a drug class."""
    # Same class is always contraindicated
    if allergy_class == drug_class:
        return CrossReactivityRisk.CONTRAINDICATED

    # Look up specific rule
    risk = CROSS_REACTIVITY_RULES.get((allergy_class, drug_class))
    if risk:
        return risk

    # Default: no known cross-reactivity
    return CrossReactivityRisk.NONE


def check_allergy_conflict(
    antibiotic_name: str,
    allergy_substance: str,
    allergy_severity: str | None = None,
) -> AllergyConflict | None:
    """
    Check if an antibiotic conflicts with a patient's drug allergy.

    Args:
        antibiotic_name: Name of the antibiotic being recommended
        allergy_substance: Name of the substance the patient is allergic to
        allergy_severity: Severity of the allergy (e.g., 'life-threatening')

    Returns:
        AllergyConflict if there's a conflict, None if safe
    """
    antibiotic_class = get_antibiotic_class(antibiotic_name)
    allergy_class = get_antibiotic_class(allergy_substance)

    # If we can't classify either, be conservative
    if antibiotic_class == AntibioticClass.OTHER and allergy_class == AntibioticClass.OTHER:
        # Check for exact name match
        if antibiotic_name.lower().strip() == allergy_substance.lower().strip():
            return AllergyConflict(
                antibiotic=antibiotic_name,
                antibiotic_class=antibiotic_class,
                allergy_substance=allergy_substance,
                allergy_class=allergy_class,
                cross_reactivity_risk=CrossReactivityRisk.CONTRAINDICATED,
                is_anaphylaxis_history=(allergy_severity == "life-threatening"),
                warning_message=f"Patient allergic to {allergy_substance}",
            )
        return None

    risk = get_cross_reactivity_risk(allergy_class, antibiotic_class)

    if risk == CrossReactivityRisk.NONE:
        return None

    is_anaphylaxis = allergy_severity == "life-threatening"

    # Generate warning message
    if risk == CrossReactivityRisk.CONTRAINDICATED:
        if is_anaphylaxis:
            msg = f"CONTRAINDICATED: Anaphylaxis to {allergy_substance} ({allergy_class.value})"
        else:
            msg = f"AVOID: Patient allergic to {allergy_substance} ({allergy_class.value})"
    elif risk == CrossReactivityRisk.HIGH:
        msg = f"HIGH RISK: Cross-reactivity with {allergy_substance} allergy"
    elif risk == CrossReactivityRisk.MODERATE:
        msg = f"MODERATE RISK: Possible cross-reactivity with {allergy_substance}"
    else:  # LOW
        if is_anaphylaxis:
            msg = f"CAUTION: Low cross-reactivity but anaphylaxis history to {allergy_substance}"
        else:
            msg = f"Low cross-reactivity with {allergy_substance} (~1-2%)"

    return AllergyConflict(
        antibiotic=antibiotic_name,
        antibiotic_class=antibiotic_class,
        allergy_substance=allergy_substance,
        allergy_class=allergy_class,
        cross_reactivity_risk=risk,
        is_anaphylaxis_history=is_anaphylaxis,
        warning_message=msg,
    )


def filter_recommendations_by_allergies(
    recommended_antibiotics: list[str],
    allergies: list[dict],
) -> SafeRecommendation:
    """
    Filter antibiotic recommendations based on patient allergies.

    Args:
        recommended_antibiotics: List of antibiotic names being recommended
        allergies: List of allergy dicts with 'substance' and optional 'severity'

    Returns:
        SafeRecommendation with safe options, excluded items, and alternatives
    """
    safe = []
    excluded = []
    caution = []

    for antibiotic in recommended_antibiotics:
        worst_conflict = None

        for allergy in allergies:
            substance = allergy.get("substance", "")
            severity = allergy.get("severity")

            conflict = check_allergy_conflict(antibiotic, substance, severity)

            if conflict:
                if worst_conflict is None:
                    worst_conflict = conflict
                elif conflict.is_contraindicated and not worst_conflict.is_contraindicated:
                    worst_conflict = conflict

        if worst_conflict is None:
            safe.append(antibiotic)
        elif worst_conflict.is_contraindicated:
            excluded.append(worst_conflict)
        else:
            caution.append(worst_conflict)

    # Generate alternative suggestions based on excluded drug classes
    alternatives = []
    excluded_classes = set(c.allergy_class for c in excluded)

    for excluded_class in excluded_classes:
        if excluded_class in ALTERNATIVE_SUGGESTIONS:
            # Add broad spectrum alternatives if available
            alt_dict = ALTERNATIVE_SUGGESTIONS[excluded_class]
            if "broad_spectrum" in alt_dict:
                alternatives.extend(alt_dict["broad_spectrum"])
            elif "gram_positive" in alt_dict:
                alternatives.extend(alt_dict["gram_positive"][:2])

    # Deduplicate alternatives
    alternatives = list(dict.fromkeys(alternatives))

    # Generate warning text if needed
    warning_text = None
    if excluded:
        allergy_names = set(c.allergy_substance for c in excluded)
        warning_text = f"Patient has allergy to: {', '.join(allergy_names)}"

    return SafeRecommendation(
        original_recommendations=recommended_antibiotics,
        safe_recommendations=safe,
        excluded_antibiotics=excluded,
        caution_antibiotics=caution,
        alternative_suggestions=alternatives[:3],  # Top 3 alternatives
        warning_text=warning_text,
    )


def get_safe_alternatives(
    organism_category: str,
    allergies: list[dict],
) -> list[str]:
    """
    Get safe antibiotic alternatives for an organism category given patient allergies.

    Args:
        organism_category: Type of organism (e.g., 'mrsa', 'pseudomonas', 'gram_negative')
        allergies: List of allergy dicts

    Returns:
        List of safe antibiotic options
    """
    # Map organism categories to typical antibiotic options
    ORGANISM_OPTIONS = {
        "mrsa": ["vancomycin", "daptomycin", "linezolid", "ceftaroline", "trimethoprim-sulfamethoxazole"],
        "mssa": ["cefazolin", "nafcillin", "oxacillin", "vancomycin", "daptomycin"],
        "vre": ["daptomycin", "linezolid"],
        "vse": ["ampicillin", "vancomycin", "daptomycin", "linezolid"],
        "pseudomonas": ["cefepime", "piperacillin-tazobactam", "meropenem", "ciprofloxacin", "aztreonam", "tobramycin"],
        "gram_negative": ["ceftriaxone", "cefepime", "piperacillin-tazobactam", "meropenem", "ciprofloxacin", "aztreonam"],
        "candida": ["micafungin", "caspofungin", "fluconazole", "voriconazole", "amphotericin b"],
        "gpc_clusters": ["vancomycin", "daptomycin", "linezolid"],  # Empiric staph
        "gnr": ["cefepime", "piperacillin-tazobactam", "meropenem", "aztreonam"],  # Empiric gram neg
    }

    options = ORGANISM_OPTIONS.get(organism_category.lower(), [])
    if not options:
        return []

    # Filter by allergies
    result = filter_recommendations_by_allergies(options, allergies)
    return result.safe_recommendations


def adjust_recommendation_for_allergies(
    original_recommendation: str,
    susceptible_options: list[str],
    allergies: list[dict],
) -> dict:
    """
    Adjust a recommendation text and options based on patient allergies.

    Args:
        original_recommendation: Original recommendation text
        susceptible_options: List of susceptible antibiotic options from culture
        allergies: List of allergy dicts with 'substance' and 'severity'

    Returns:
        Dict with:
        - recommendation: Adjusted recommendation text
        - safe_options: List of safe susceptible options
        - excluded_options: List of options excluded due to allergy
        - caution_options: List of options that require caution
        - has_allergy_conflicts: Boolean
        - allergy_warnings: List of warning strings
    """
    if not allergies:
        return {
            "recommendation": original_recommendation,
            "safe_options": susceptible_options,
            "excluded_options": [],
            "caution_options": [],
            "has_allergy_conflicts": False,
            "allergy_warnings": [],
        }

    result = filter_recommendations_by_allergies(susceptible_options, allergies)

    warnings = []
    for conflict in result.excluded_antibiotics:
        warnings.append(conflict.warning_message)
    for conflict in result.caution_antibiotics:
        warnings.append(conflict.warning_message)

    # Build adjusted recommendation
    if result.safe_recommendations:
        if result.excluded_antibiotics:
            excluded_names = [c.antibiotic for c in result.excluded_antibiotics]
            adjusted = (
                f"{original_recommendation} "
                f"ALLERGY ALERT: Avoid {', '.join(excluded_names)}. "
                f"Safe options: {', '.join(result.safe_recommendations)}."
            )
        else:
            adjusted = original_recommendation
    else:
        # No safe options from susceptibility panel
        adjusted = (
            f"{original_recommendation} "
            f"ALLERGY ALERT: All susceptible options conflict with patient allergies. "
            f"Consider ID consult."
        )
        if result.alternative_suggestions:
            adjusted += f" Possible alternatives: {', '.join(result.alternative_suggestions)}."

    return {
        "recommendation": adjusted,
        "safe_options": result.safe_recommendations,
        "excluded_options": [c.antibiotic for c in result.excluded_antibiotics],
        "caution_options": [(c.antibiotic, c.warning_message) for c in result.caution_antibiotics],
        "has_allergy_conflicts": result.has_conflicts,
        "allergy_warnings": warnings,
    }
