# Clinical Coverage Rules

## Overview

This document describes the clinical decision logic used to determine whether a patient's antibiotic regimen provides adequate coverage for organisms identified in blood cultures.

**IMPORTANT**: These rules are simplified for demonstration purposes. Production clinical decision support requires:
- Local antibiogram data
- Susceptibility-guided adjustments
- Patient-specific factors (allergies, renal function)
- Infectious disease specialist review

## Organism Categories

### MRSA (Methicillin-Resistant Staphylococcus aureus)

**Adequate Coverage:**
- Vancomycin
- Daptomycin
- Linezolid
- Ceftaroline

**Inadequate Coverage:**
- Cefazolin
- Ceftriaxone
- Nafcillin
- Oxacillin
- Ampicillin
- Piperacillin-tazobactam

**Recommendation:** Add vancomycin or daptomycin for MRSA coverage

### MSSA (Methicillin-Susceptible Staphylococcus aureus)

**Adequate Coverage:**
- Cefazolin (preferred)
- Nafcillin
- Oxacillin
- Vancomycin
- Daptomycin
- Ceftriaxone

**Recommendation:** Anti-staphylococcal beta-lactam preferred (cefazolin, nafcillin)

### VRE (Vancomycin-Resistant Enterococcus)

**Adequate Coverage:**
- Daptomycin
- Linezolid

**Inadequate Coverage:**
- Vancomycin
- Ampicillin

**Recommendation:** Add daptomycin or linezolid for VRE coverage

### VSE (Vancomycin-Susceptible Enterococcus)

**Adequate Coverage:**
- Ampicillin (preferred)
- Vancomycin
- Daptomycin
- Linezolid

**Inadequate Coverage:**
- Cefazolin
- Ceftriaxone
- Cefepime

**Recommendation:** Ampicillin or vancomycin for enterococcal coverage

### Pseudomonas aeruginosa

**Adequate Coverage:**
- Cefepime
- Piperacillin-tazobactam
- Meropenem
- Ciprofloxacin
- Levofloxacin
- Tobramycin
- Amikacin

**Inadequate Coverage:**
- Ceftriaxone
- Cefazolin
- Ampicillin-sulbactam

**Recommendation:** Add anti-pseudomonal agent (cefepime, pip-tazo, meropenem)

### Susceptible Gram-Negative Organisms

Includes: E. coli, Klebsiella, Enterobacter, Serratia, Proteus, Citrobacter, Salmonella

**Adequate Coverage:**
- Ceftriaxone
- Cefepime
- Piperacillin-tazobactam
- Meropenem
- Ciprofloxacin
- Levofloxacin
- Gentamicin

**Inadequate Coverage:**
- Cefazolin
- Vancomycin

**Recommendation:** Add gram-negative coverage (ceftriaxone, cefepime)

### Candida (Fungemia)

**Adequate Coverage:**
- Fluconazole
- Micafungin
- Caspofungin
- Amphotericin B
- Voriconazole

**Inadequate Coverage:**
- All antibacterial agents

**Recommendation:** Add antifungal therapy (micafungin, fluconazole) for candidemia

## Empiric Coverage (Gram Stain Only)

When organism identification is pending but gram stain is available:

### Gram-Positive Cocci in Clusters

Suggestive of Staphylococcus species. Treat empirically for MRSA until susceptibilities available.

**Adequate Coverage:** Vancomycin, Daptomycin, Linezolid

**Recommendation:** Add empiric MRSA coverage (vancomycin) for GPC in clusters

### Gram-Positive Cocci in Chains

Suggestive of Streptococcus or Enterococcus species.

**Adequate Coverage:** Vancomycin, Ampicillin, Ceftriaxone

**Recommendation:** Ensure streptococcal/enterococcal coverage

### Gram-Negative Rods

Suggestive of Enterobacteriaceae or non-fermenters.

**Adequate Coverage:** Cefepime, Piperacillin-tazobactam, Meropenem, Ceftriaxone

**Recommendation:** Add empiric gram-negative coverage for GNR

## RxNorm Codes

The system uses RxNorm codes for medication matching:

| Antibiotic | RxNorm Code |
|------------|-------------|
| Vancomycin | 11124 |
| Daptomycin | 190376 |
| Linezolid | 190521 |
| Ceftaroline | 1009148 |
| Cefazolin | 4053 |
| Ceftriaxone | 2193 |
| Cefepime | 2180 |
| Piperacillin-tazobactam | 152834 |
| Meropenem | 29561 |
| Ampicillin | 733 |
| Fluconazole | 4450 |
| Micafungin | 327361 |
| Caspofungin | 285661 |

## Extending the Rules

To add new organisms or antibiotics, edit `src/coverage_rules.py`:

1. Add RxNorm code to `RXNORM` dictionary
2. Add organism category to `OrganismCategory` enum
3. Create `CoverageRule` in `COVERAGE_RULES` dictionary
4. Update `categorize_organism()` function to recognize new organism text

## Limitations

- Does not account for drug allergies
- Does not consider renal/hepatic dosing adjustments
- Does not integrate susceptibility test results
- Does not consider combination therapy synergy
- Simplified organism categorization (no species-level granularity)

These limitations should be addressed before production deployment.
