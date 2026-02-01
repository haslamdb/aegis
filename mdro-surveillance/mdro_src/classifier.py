"""MDRO Classification based on susceptibility patterns.

Identifies multi-drug resistant organisms from culture susceptibility data
following CDC/NHSN definitions. These definitions are aligned with the
NHSN AR (Antimicrobial Resistance) reporting module to ensure consistency
between real-time surveillance and quarterly NHSN reporting.

CDC/NHSN Phenotype Definitions:
- MRSA: Staph aureus + oxacillin/methicillin/nafcillin/cefoxitin R
- VRE: Enterococcus + vancomycin R
- CRE: Enterobacterales + meropenem/imipenem/ertapenem/doripenem R
- ESBL: E. coli/Klebsiella/Proteus + ceftriaxone/ceftazidime/cefotaxime/aztreonam R
- CRPA: Pseudomonas aeruginosa + carbapenem R
- CRAB: Acinetobacter baumannii + carbapenem R

Reference: CDC NHSN Antimicrobial Use and Resistance Module Protocol
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import re


class MDROType(Enum):
    """Types of multi-drug resistant organisms tracked."""
    MRSA = "mrsa"           # Methicillin-resistant Staph aureus
    VRE = "vre"             # Vancomycin-resistant Enterococcus
    CRE = "cre"             # Carbapenem-resistant Enterobacteriaceae
    ESBL = "esbl"           # Extended-spectrum beta-lactamase
    CRPA = "crpa"           # Carbapenem-resistant Pseudomonas
    CRAB = "crab"           # Carbapenem-resistant Acinetobacter


@dataclass
class MDROClassification:
    """Result of MDRO classification for a culture."""
    is_mdro: bool
    mdro_type: Optional[MDROType] = None
    organism: str = ""
    resistant_antibiotics: list[str] = field(default_factory=list)
    classification_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "is_mdro": self.is_mdro,
            "mdro_type": self.mdro_type.value if self.mdro_type else None,
            "organism": self.organism,
            "resistant_antibiotics": self.resistant_antibiotics,
            "classification_reason": self.classification_reason,
        }


class MDROClassifier:
    """Classifies organisms as MDRO based on susceptibility patterns."""

    # Organism pattern matching
    STAPH_AUREUS_PATTERNS = [
        r"staphylococcus\s+aureus",
        r"s\.?\s*aureus",
        r"staph\s+aureus",
    ]

    ENTEROCOCCUS_PATTERNS = [
        r"enterococcus\s+(faecalis|faecium|species)",
        r"e\.?\s*(faecalis|faecium)",
        r"enterococcus",
    ]

    # Enterobacteriaceae / Enterobacterales
    ENTEROBACTERIACEAE_PATTERNS = [
        r"escherichia\s+coli",
        r"e\.?\s*coli",
        r"klebsiella",
        r"enterobacter",
        r"citrobacter",
        r"serratia",
        r"proteus",
        r"morganella",
        r"providencia",
        r"salmonella",
        r"shigella",
    ]

    PSEUDOMONAS_PATTERNS = [
        r"pseudomonas\s+aeruginosa",
        r"p\.?\s*aeruginosa",
        r"pseudomonas",
    ]

    ACINETOBACTER_PATTERNS = [
        r"acinetobacter\s+baumannii",
        r"a\.?\s*baumannii",
        r"acinetobacter",
    ]

    # Antibiotic categories for resistance detection
    METHICILLIN_AGENTS = [
        "oxacillin", "methicillin", "nafcillin", "cefoxitin",
    ]

    VANCOMYCIN_AGENTS = [
        "vancomycin",
    ]

    CARBAPENEM_AGENTS = [
        "meropenem", "imipenem", "ertapenem", "doripenem",
    ]

    ESBL_INDICATOR_AGENTS = [
        "ceftriaxone", "ceftazidime", "cefotaxime", "aztreonam",
    ]

    ESBL_SPARED_AGENTS = [
        "cefepime",  # 4th gen often retained
    ]

    def __init__(self):
        # Compile regex patterns
        self._staph_re = self._compile_patterns(self.STAPH_AUREUS_PATTERNS)
        self._entero_re = self._compile_patterns(self.ENTEROCOCCUS_PATTERNS)
        self._enterobact_re = self._compile_patterns(self.ENTEROBACTERIACEAE_PATTERNS)
        self._pseudo_re = self._compile_patterns(self.PSEUDOMONAS_PATTERNS)
        self._acine_re = self._compile_patterns(self.ACINETOBACTER_PATTERNS)

    def _compile_patterns(self, patterns: list[str]) -> re.Pattern:
        """Compile list of patterns into single regex."""
        combined = "|".join(f"({p})" for p in patterns)
        return re.compile(combined, re.IGNORECASE)

    def classify(
        self,
        organism: str,
        susceptibilities: list[dict],
    ) -> MDROClassification:
        """Classify an organism as MDRO based on susceptibility pattern.

        Args:
            organism: Organism name from culture
            susceptibilities: List of dicts with 'antibiotic' and 'result' keys
                             Result should be 'S', 'I', or 'R'

        Returns:
            MDROClassification with results
        """
        organism_lower = organism.lower().strip()

        # Build resistance map
        resistant_to = set()
        for susc in susceptibilities:
            abx = susc.get("antibiotic", "").lower().strip()
            result = susc.get("result", "").upper().strip()
            if result == "R":
                resistant_to.add(abx)

        # Check for MRSA
        if self._staph_re.search(organism_lower):
            mrsa_result = self._check_mrsa(organism, resistant_to)
            if mrsa_result.is_mdro:
                return mrsa_result

        # Check for VRE
        if self._entero_re.search(organism_lower):
            vre_result = self._check_vre(organism, resistant_to)
            if vre_result.is_mdro:
                return vre_result

        # Check for CRE / ESBL in Enterobacteriaceae
        if self._enterobact_re.search(organism_lower):
            cre_result = self._check_cre(organism, resistant_to)
            if cre_result.is_mdro:
                return cre_result

            esbl_result = self._check_esbl(organism, resistant_to)
            if esbl_result.is_mdro:
                return esbl_result

        # Check for CRPA (Carbapenem-resistant Pseudomonas)
        if self._pseudo_re.search(organism_lower):
            crpa_result = self._check_crpa(organism, resistant_to)
            if crpa_result.is_mdro:
                return crpa_result

        # Check for CRAB (Carbapenem-resistant Acinetobacter)
        if self._acine_re.search(organism_lower):
            crab_result = self._check_crab(organism, resistant_to)
            if crab_result.is_mdro:
                return crab_result

        # Not MDRO
        return MDROClassification(
            is_mdro=False,
            organism=organism,
        )

    def _check_mrsa(self, organism: str, resistant_to: set[str]) -> MDROClassification:
        """Check for Methicillin-resistant Staph aureus."""
        for agent in self.METHICILLIN_AGENTS:
            if agent in resistant_to:
                return MDROClassification(
                    is_mdro=True,
                    mdro_type=MDROType.MRSA,
                    organism=organism,
                    resistant_antibiotics=[agent],
                    classification_reason=f"Staph aureus resistant to {agent}",
                )
        return MDROClassification(is_mdro=False, organism=organism)

    def _check_vre(self, organism: str, resistant_to: set[str]) -> MDROClassification:
        """Check for Vancomycin-resistant Enterococcus."""
        if "vancomycin" in resistant_to:
            return MDROClassification(
                is_mdro=True,
                mdro_type=MDROType.VRE,
                organism=organism,
                resistant_antibiotics=["vancomycin"],
                classification_reason="Enterococcus resistant to vancomycin",
            )
        return MDROClassification(is_mdro=False, organism=organism)

    def _check_cre(self, organism: str, resistant_to: set[str]) -> MDROClassification:
        """Check for Carbapenem-resistant Enterobacteriaceae."""
        carbapenem_resistant = [
            agent for agent in self.CARBAPENEM_AGENTS
            if agent in resistant_to
        ]
        if carbapenem_resistant:
            return MDROClassification(
                is_mdro=True,
                mdro_type=MDROType.CRE,
                organism=organism,
                resistant_antibiotics=carbapenem_resistant,
                classification_reason=f"Enterobacteriaceae resistant to {', '.join(carbapenem_resistant)}",
            )
        return MDROClassification(is_mdro=False, organism=organism)

    def _check_esbl(self, organism: str, resistant_to: set[str]) -> MDROClassification:
        """Check for ESBL-producing Enterobacteriaceae.

        CDC/NHSN Definition: Resistance to at least one extended-spectrum
        cephalosporin (ceftriaxone, ceftazidime, cefotaxime) or aztreonam
        in E. coli, Klebsiella spp, or Proteus mirabilis.

        Note: CRE takes precedence - organisms resistant to carbapenems
        are classified as CRE, not ESBL (check order in classify() method).
        """
        esbl_resistant = [
            agent for agent in self.ESBL_INDICATOR_AGENTS
            if agent in resistant_to
        ]
        # CDC/NHSN: Resistance to at least 1 ESBL indicator agent
        if len(esbl_resistant) >= 1:
            return MDROClassification(
                is_mdro=True,
                mdro_type=MDROType.ESBL,
                organism=organism,
                resistant_antibiotics=esbl_resistant,
                classification_reason=f"ESBL pattern: resistant to {', '.join(esbl_resistant)}",
            )
        return MDROClassification(is_mdro=False, organism=organism)

    def _check_crpa(self, organism: str, resistant_to: set[str]) -> MDROClassification:
        """Check for Carbapenem-resistant Pseudomonas aeruginosa."""
        carbapenem_resistant = [
            agent for agent in self.CARBAPENEM_AGENTS
            if agent in resistant_to
        ]
        if carbapenem_resistant:
            return MDROClassification(
                is_mdro=True,
                mdro_type=MDROType.CRPA,
                organism=organism,
                resistant_antibiotics=carbapenem_resistant,
                classification_reason=f"Pseudomonas resistant to {', '.join(carbapenem_resistant)}",
            )
        return MDROClassification(is_mdro=False, organism=organism)

    def _check_crab(self, organism: str, resistant_to: set[str]) -> MDROClassification:
        """Check for Carbapenem-resistant Acinetobacter baumannii."""
        carbapenem_resistant = [
            agent for agent in self.CARBAPENEM_AGENTS
            if agent in resistant_to
        ]
        if carbapenem_resistant:
            return MDROClassification(
                is_mdro=True,
                mdro_type=MDROType.CRAB,
                organism=organism,
                resistant_antibiotics=carbapenem_resistant,
                classification_reason=f"Acinetobacter resistant to {', '.join(carbapenem_resistant)}",
            )
        return MDROClassification(is_mdro=False, organism=organism)


# Convenience function
def classify_mdro(organism: str, susceptibilities: list[dict]) -> MDROClassification:
    """Classify an organism as MDRO based on susceptibility pattern.

    Args:
        organism: Organism name from culture
        susceptibilities: List of dicts with 'antibiotic' and 'result' keys

    Returns:
        MDROClassification with results
    """
    classifier = MDROClassifier()
    return classifier.classify(organism, susceptibilities)
