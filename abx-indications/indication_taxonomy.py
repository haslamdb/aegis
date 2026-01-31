"""Clinical indication taxonomy for antibiotic stewardship.

This module defines the standardized indication vocabulary for LLM extraction
and guideline comparison. It maps clinical syndromes mentioned in notes to
CCHMC guideline disease IDs.

Joint Commission requires documentation of the clinical syndrome (e.g., "CAP"),
NOT ICD-10 codes. This taxonomy enables:
1. LLM extraction of clinical indication from notes
2. Mapping to local CCHMC guidelines
3. Guideline concordance assessment
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TherapyIntent(str, Enum):
    """Why the antibiotic was started."""
    EMPIRIC = "empiric"           # Suspected infection, no culture data yet
    DIRECTED = "directed"         # Based on culture/sensitivity
    PROPHYLAXIS = "prophylaxis"   # Prevention (surgical, medical)
    UNKNOWN = "unknown"           # Can't determine from notes


class IndicationCategory(str, Enum):
    """High-level infection category."""
    RESPIRATORY = "respiratory"
    BLOODSTREAM = "bloodstream"
    URINARY = "urinary"
    INTRAABDOMINAL = "intraabdominal"
    SKIN_SOFT_TISSUE = "skin_soft_tissue"
    CNS = "cns"
    BONE_JOINT = "bone_joint"
    ENT = "ent"
    EYE = "eye"
    FEBRILE_NEUTROPENIA = "febrile_neutropenia"
    PROPHYLAXIS = "prophylaxis"
    OTHER = "other"
    UNKNOWN = "unknown"


@dataclass
class IndicationMapping:
    """Maps clinical terms to guideline disease IDs."""
    indication_id: str                    # Canonical ID (e.g., "cap_pediatric")
    display_name: str                     # Human-readable (e.g., "Community-Acquired Pneumonia")
    category: IndicationCategory
    synonyms: list[str] = field(default_factory=list)  # Terms LLM might extract
    guideline_disease_ids: list[str] = field(default_factory=list)  # Maps to cchmc_disease_guidelines.json
    never_appropriate: bool = False       # Flag if abx never/rarely indicated
    notes: str = ""


# Master indication taxonomy
# Maps clinical syndromes to CCHMC guideline disease IDs
INDICATION_TAXONOMY: dict[str, IndicationMapping] = {

    # === RESPIRATORY ===
    "cap": IndicationMapping(
        indication_id="cap",
        display_name="Community-Acquired Pneumonia",
        category=IndicationCategory.RESPIRATORY,
        synonyms=[
            "CAP", "community pneumonia", "community acquired pneumonia",
            "pneumonia", "PNA", "lobar pneumonia", "bronchopneumonia",
            "walking pneumonia", "atypical pneumonia",
        ],
        guideline_disease_ids=["cap_infant_preschool", "cap_school_aged"],
        notes="Age-stratified guidelines. Most common pediatric indication.",
    ),
    "hap": IndicationMapping(
        indication_id="hap",
        display_name="Hospital-Acquired Pneumonia",
        category=IndicationCategory.RESPIRATORY,
        synonyms=[
            "HAP", "hospital pneumonia", "hospital acquired pneumonia",
            "nosocomial pneumonia", "healthcare associated pneumonia",
        ],
        guideline_disease_ids=["hap_vap"],
    ),
    "vap": IndicationMapping(
        indication_id="vap",
        display_name="Ventilator-Associated Pneumonia",
        category=IndicationCategory.RESPIRATORY,
        synonyms=[
            "VAP", "ventilator pneumonia", "vent associated pneumonia",
            "trach pneumonia",
        ],
        guideline_disease_ids=["hap_vap"],
    ),
    "aspiration_pneumonia": IndicationMapping(
        indication_id="aspiration_pneumonia",
        display_name="Aspiration Pneumonia",
        category=IndicationCategory.RESPIRATORY,
        synonyms=[
            "aspiration", "aspiration PNA", "aspiration pneumonitis",
        ],
        guideline_disease_ids=["aspiration_pneumonia"],
    ),
    "empyema": IndicationMapping(
        indication_id="empyema",
        display_name="Empyema / Parapneumonic Effusion",
        category=IndicationCategory.RESPIRATORY,
        synonyms=[
            "empyema", "parapneumonic effusion", "complicated pneumonia",
            "pleural empyema",
        ],
        guideline_disease_ids=["empyema_parapneumonic"],
    ),
    "bronchiolitis": IndicationMapping(
        indication_id="bronchiolitis",
        display_name="Bronchiolitis",
        category=IndicationCategory.RESPIRATORY,
        synonyms=["bronchiolitis", "RSV", "RSV bronchiolitis"],
        guideline_disease_ids=[],
        never_appropriate=True,
        notes="Viral - antibiotics not indicated. Flag for ASP review.",
    ),
    "viral_uri": IndicationMapping(
        indication_id="viral_uri",
        display_name="Viral Upper Respiratory Infection",
        category=IndicationCategory.RESPIRATORY,
        synonyms=[
            "URI", "viral URI", "cold", "common cold", "viral syndrome",
            "nasopharyngitis", "rhinitis",
        ],
        guideline_disease_ids=[],
        never_appropriate=True,
        notes="Viral - antibiotics not indicated. Flag for ASP review.",
    ),

    # === BLOODSTREAM ===
    "bacteremia_gpc": IndicationMapping(
        indication_id="bacteremia_gpc",
        display_name="Gram-Positive Bacteremia",
        category=IndicationCategory.BLOODSTREAM,
        synonyms=[
            "gram positive bacteremia", "GPC bacteremia", "staph bacteremia",
            "strep bacteremia", "enterococcal bacteremia",
        ],
        guideline_disease_ids=["clabsi_cons", "clabsi_enterococcus", "clabsi_s_aureus"],
    ),
    "bacteremia_gnr": IndicationMapping(
        indication_id="bacteremia_gnr",
        display_name="Gram-Negative Bacteremia",
        category=IndicationCategory.BLOODSTREAM,
        synonyms=[
            "gram negative bacteremia", "GNR bacteremia", "E. coli bacteremia",
            "Klebsiella bacteremia", "Pseudomonas bacteremia",
        ],
        guideline_disease_ids=["clabsi_gnr", "clabsi_pseudomonas"],
    ),
    "sepsis": IndicationMapping(
        indication_id="sepsis",
        display_name="Sepsis",
        category=IndicationCategory.BLOODSTREAM,
        synonyms=[
            "sepsis", "septicemia", "severe sepsis", "septic shock",
            "SIRS", "systemic infection",
        ],
        guideline_disease_ids=["neonatal_sepsis", "fever_neutropenia"],
        notes="Consider age-specific guidelines. Neonatal vs pediatric.",
    ),
    "line_infection": IndicationMapping(
        indication_id="line_infection",
        display_name="Central Line Infection / CLABSI",
        category=IndicationCategory.BLOODSTREAM,
        synonyms=[
            "CLABSI", "line infection", "line sepsis", "catheter infection",
            "port infection", "broviac infection", "PICC infection",
            "central line associated bloodstream infection",
        ],
        guideline_disease_ids=["clabsi_cons", "clabsi_enterococcus", "clabsi_s_aureus", "clabsi_gnr"],
    ),
    "endocarditis": IndicationMapping(
        indication_id="endocarditis",
        display_name="Endocarditis",
        category=IndicationCategory.BLOODSTREAM,
        synonyms=[
            "endocarditis", "infective endocarditis", "IE",
            "bacterial endocarditis", "SBE",
        ],
        guideline_disease_ids=["endocarditis"],
    ),

    # === URINARY ===
    "uti_simple": IndicationMapping(
        indication_id="uti_simple",
        display_name="Uncomplicated UTI / Cystitis",
        category=IndicationCategory.URINARY,
        synonyms=[
            "UTI", "simple UTI", "cystitis", "uncomplicated UTI",
            "bladder infection", "urinary tract infection",
        ],
        guideline_disease_ids=["simple_cystitis"],
    ),
    "uti_complicated": IndicationMapping(
        indication_id="uti_complicated",
        display_name="Complicated UTI / Pyelonephritis",
        category=IndicationCategory.URINARY,
        synonyms=[
            "pyelonephritis", "pyelo", "complicated UTI", "upper UTI",
            "kidney infection", "febrile UTI",
        ],
        guideline_disease_ids=["pyelonephritis", "febrile_uti"],
    ),
    "cauti": IndicationMapping(
        indication_id="cauti",
        display_name="Catheter-Associated UTI",
        category=IndicationCategory.URINARY,
        synonyms=[
            "CAUTI", "catheter UTI", "foley infection",
            "catheter associated UTI",
        ],
        guideline_disease_ids=["pyelonephritis", "febrile_uti"],
    ),
    "asymptomatic_bacteriuria": IndicationMapping(
        indication_id="asymptomatic_bacteriuria",
        display_name="Asymptomatic Bacteriuria",
        category=IndicationCategory.URINARY,
        synonyms=[
            "asymptomatic bacteriuria", "ASB", "positive UA no symptoms",
            "colonization",
        ],
        guideline_disease_ids=[],
        never_appropriate=True,
        notes="Treatment not indicated except in pregnancy or pre-urologic procedure.",
    ),

    # === INTRA-ABDOMINAL ===
    "appendicitis": IndicationMapping(
        indication_id="appendicitis",
        display_name="Appendicitis",
        category=IndicationCategory.INTRAABDOMINAL,
        synonyms=[
            "appendicitis", "appy", "perforated appendix",
            "ruptured appendix",
        ],
        guideline_disease_ids=["appendicitis_bowel_perforation"],
    ),
    "intraabdominal_infection": IndicationMapping(
        indication_id="intraabdominal_infection",
        display_name="Intra-abdominal Infection",
        category=IndicationCategory.INTRAABDOMINAL,
        synonyms=[
            "peritonitis", "intra-abdominal abscess", "IAI",
            "abdominal sepsis", "bowel perforation", "cholangitis",
            "cholecystitis",
        ],
        guideline_disease_ids=["appendicitis_bowel_perforation"],
    ),
    "cdiff": IndicationMapping(
        indication_id="cdiff",
        display_name="C. difficile Infection",
        category=IndicationCategory.INTRAABDOMINAL,
        synonyms=[
            "C diff", "C. diff", "CDI", "C difficile", "Clostridioides difficile",
            "clostridium difficile", "pseudomembranous colitis",
        ],
        guideline_disease_ids=["cdiff_infection"],
    ),

    # === SKIN/SOFT TISSUE ===
    "cellulitis": IndicationMapping(
        indication_id="cellulitis",
        display_name="Cellulitis",
        category=IndicationCategory.SKIN_SOFT_TISSUE,
        synonyms=[
            "cellulitis", "skin infection", "SSTI",
            "soft tissue infection", "erysipelas",
        ],
        guideline_disease_ids=["cellulitis_non_suppurative", "cellulitis_suppurative"],
    ),
    "abscess": IndicationMapping(
        indication_id="abscess",
        display_name="Skin Abscess",
        category=IndicationCategory.SKIN_SOFT_TISSUE,
        synonyms=[
            "abscess", "skin abscess", "furuncle", "carbuncle",
            "boil", "MRSA abscess",
        ],
        guideline_disease_ids=["skin_abscess"],
    ),
    "wound_infection": IndicationMapping(
        indication_id="wound_infection",
        display_name="Wound Infection / SSI",
        category=IndicationCategory.SKIN_SOFT_TISSUE,
        synonyms=[
            "wound infection", "SSI", "surgical site infection",
            "post-op infection", "incisional infection",
        ],
        guideline_disease_ids=["ssi_wound_infection"],
    ),
    "necrotizing_fasciitis": IndicationMapping(
        indication_id="necrotizing_fasciitis",
        display_name="Necrotizing Fasciitis",
        category=IndicationCategory.SKIN_SOFT_TISSUE,
        synonyms=[
            "necrotizing fasciitis", "nec fasc", "flesh eating",
            "necrotizing soft tissue infection",
        ],
        guideline_disease_ids=["necrotizing_fasciitis"],
    ),

    # === CNS ===
    "meningitis": IndicationMapping(
        indication_id="meningitis",
        display_name="Bacterial Meningitis",
        category=IndicationCategory.CNS,
        synonyms=[
            "meningitis", "bacterial meningitis", "pyogenic meningitis",
        ],
        guideline_disease_ids=["bacterial_meningitis", "neonatal_meningitis"],
    ),
    "shunt_infection": IndicationMapping(
        indication_id="shunt_infection",
        display_name="VP Shunt Infection",
        category=IndicationCategory.CNS,
        synonyms=[
            "shunt infection", "VP shunt infection", "ventriculitis",
            "shunt meningitis", "CSF shunt infection",
        ],
        guideline_disease_ids=["vp_shunt_infection"],
    ),
    "brain_abscess": IndicationMapping(
        indication_id="brain_abscess",
        display_name="Brain Abscess",
        category=IndicationCategory.CNS,
        synonyms=[
            "brain abscess", "intracranial abscess", "cerebral abscess",
        ],
        guideline_disease_ids=["brain_abscess"],
    ),

    # === BONE/JOINT ===
    "osteomyelitis": IndicationMapping(
        indication_id="osteomyelitis",
        display_name="Osteomyelitis",
        category=IndicationCategory.BONE_JOINT,
        synonyms=[
            "osteomyelitis", "osteo", "bone infection",
            "acute hematogenous osteomyelitis",
        ],
        guideline_disease_ids=["osteomyelitis_acute"],
    ),
    "septic_arthritis": IndicationMapping(
        indication_id="septic_arthritis",
        display_name="Septic Arthritis",
        category=IndicationCategory.BONE_JOINT,
        synonyms=[
            "septic arthritis", "septic joint", "joint infection",
            "pyogenic arthritis",
        ],
        guideline_disease_ids=["septic_arthritis_under5", "septic_arthritis_over5"],
    ),

    # === ENT ===
    "acute_otitis_media": IndicationMapping(
        indication_id="acute_otitis_media",
        display_name="Acute Otitis Media",
        category=IndicationCategory.ENT,
        synonyms=[
            "AOM", "otitis media", "ear infection", "acute otitis media",
        ],
        guideline_disease_ids=["aom_otitis_media"],
    ),
    "sinusitis": IndicationMapping(
        indication_id="sinusitis",
        display_name="Acute Bacterial Sinusitis",
        category=IndicationCategory.ENT,
        synonyms=[
            "sinusitis", "sinus infection", "acute sinusitis",
            "bacterial sinusitis",
        ],
        guideline_disease_ids=["acute_bacterial_sinusitis"],
    ),
    "peritonsillar_abscess": IndicationMapping(
        indication_id="peritonsillar_abscess",
        display_name="Peritonsillar Abscess",
        category=IndicationCategory.ENT,
        synonyms=[
            "peritonsillar abscess", "PTA", "quinsy",
            "tonsillar abscess",
        ],
        guideline_disease_ids=["peritonsillar_abscess"],
    ),
    "strep_pharyngitis": IndicationMapping(
        indication_id="strep_pharyngitis",
        display_name="Strep Pharyngitis",
        category=IndicationCategory.ENT,
        synonyms=[
            "strep throat", "strep pharyngitis", "GAS pharyngitis",
            "streptococcal pharyngitis",
        ],
        guideline_disease_ids=["strep_pharyngitis"],
    ),
    "mastoiditis": IndicationMapping(
        indication_id="mastoiditis",
        display_name="Acute Mastoiditis",
        category=IndicationCategory.ENT,
        synonyms=[
            "mastoiditis", "acute mastoiditis",
        ],
        guideline_disease_ids=["acute_mastoiditis"],
    ),

    # === EYE ===
    "orbital_cellulitis": IndicationMapping(
        indication_id="orbital_cellulitis",
        display_name="Orbital Cellulitis",
        category=IndicationCategory.EYE,
        synonyms=[
            "orbital cellulitis", "postseptal cellulitis",
        ],
        guideline_disease_ids=["orbital_cellulitis"],
    ),
    "periorbital_cellulitis": IndicationMapping(
        indication_id="periorbital_cellulitis",
        display_name="Periorbital / Preseptal Cellulitis",
        category=IndicationCategory.EYE,
        synonyms=[
            "periorbital cellulitis", "preseptal cellulitis",
        ],
        guideline_disease_ids=["periorbital_cellulitis"],
    ),

    # === FEBRILE NEUTROPENIA ===
    "febrile_neutropenia": IndicationMapping(
        indication_id="febrile_neutropenia",
        display_name="Febrile Neutropenia",
        category=IndicationCategory.FEBRILE_NEUTROPENIA,
        synonyms=[
            "febrile neutropenia", "FN", "neutropenic fever",
            "fever and neutropenia", "ANC < 500 with fever",
        ],
        guideline_disease_ids=["fever_neutropenia"],
        notes="Oncology patients. Time-critical - empiric therapy within 1 hour.",
    ),

    # === PROPHYLAXIS ===
    "surgical_prophylaxis": IndicationMapping(
        indication_id="surgical_prophylaxis",
        display_name="Surgical Prophylaxis",
        category=IndicationCategory.PROPHYLAXIS,
        synonyms=[
            "surgical prophylaxis", "perioperative prophylaxis",
            "pre-op antibiotics", "surgical abx",
        ],
        guideline_disease_ids=["surgical_prophylaxis"],
    ),
    "pcp_prophylaxis": IndicationMapping(
        indication_id="pcp_prophylaxis",
        display_name="PCP Prophylaxis",
        category=IndicationCategory.PROPHYLAXIS,
        synonyms=[
            "PCP prophylaxis", "pneumocystis prophylaxis", "PJP prophylaxis",
        ],
        guideline_disease_ids=[],
    ),
    "sbp_prophylaxis": IndicationMapping(
        indication_id="sbp_prophylaxis",
        display_name="SBP Prophylaxis",
        category=IndicationCategory.PROPHYLAXIS,
        synonyms=[
            "SBP prophylaxis", "spontaneous bacterial peritonitis prophylaxis",
        ],
        guideline_disease_ids=[],
    ),

    # === OTHER / UNKNOWN ===
    "empiric_unknown": IndicationMapping(
        indication_id="empiric_unknown",
        display_name="Empiric - Source Unknown",
        category=IndicationCategory.UNKNOWN,
        synonyms=[
            "empiric", "empiric therapy", "source unknown", "fever workup",
            "rule out sepsis", "broad coverage",
        ],
        guideline_disease_ids=[],
        notes="Needs refinement - ASP should follow up on indication clarification.",
    ),
    "culture_directed": IndicationMapping(
        indication_id="culture_directed",
        display_name="Culture-Directed Therapy",
        category=IndicationCategory.OTHER,
        synonyms=[
            "culture directed", "directed therapy", "based on susceptibilities",
            "de-escalated", "narrowed",
        ],
        guideline_disease_ids=[],
    ),
}


def get_indication_by_synonym(term: str) -> IndicationMapping | None:
    """Look up indication by synonym (case-insensitive).

    Args:
        term: Clinical term to look up (e.g., "CAP", "UTI")

    Returns:
        IndicationMapping if found, None otherwise
    """
    term_lower = term.lower().strip()

    for indication in INDICATION_TAXONOMY.values():
        if term_lower == indication.indication_id.lower():
            return indication
        if term_lower == indication.display_name.lower():
            return indication
        for syn in indication.synonyms:
            if term_lower == syn.lower():
                return indication

    return None


def get_indications_by_category(category: IndicationCategory) -> list[IndicationMapping]:
    """Get all indications for a category.

    Args:
        category: IndicationCategory to filter by

    Returns:
        List of IndicationMapping objects
    """
    return [
        ind for ind in INDICATION_TAXONOMY.values()
        if ind.category == category
    ]


def get_never_appropriate_indications() -> list[IndicationMapping]:
    """Get indications where antibiotics are never/rarely appropriate.

    These should trigger ASP alerts when antibiotics are prescribed.
    """
    return [
        ind for ind in INDICATION_TAXONOMY.values()
        if ind.never_appropriate
    ]


# Export key items
__all__ = [
    "TherapyIntent",
    "IndicationCategory",
    "IndicationMapping",
    "INDICATION_TAXONOMY",
    "get_indication_by_synonym",
    "get_indications_by_category",
    "get_never_appropriate_indications",
]
