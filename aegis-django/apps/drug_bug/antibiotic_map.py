"""RxNorm to susceptibility test name mapping for Drug-Bug Mismatch Detection."""

# Mapping from RxNorm codes to susceptibility test antibiotic names
# This maps medication orders to the corresponding susceptibility panel test names
ANTIBIOTIC_SUSCEPTIBILITY_MAP: dict[str, list[str]] = {
    # Glycopeptides
    "11124": ["vancomycin"],                    # Vancomycin

    # Carbapenems
    "29561": ["meropenem"],                     # Meropenem
    "1668240": ["ertapenem"],                   # Ertapenem
    "190376": ["imipenem"],                     # Imipenem

    # Cephalosporins
    "2193": ["ceftriaxone", "cefotaxime"],      # Ceftriaxone
    "2180": ["cefepime"],                       # Cefepime
    "4053": ["cefazolin"],                      # Cefazolin
    "2231": ["ceftazidime"],                    # Ceftazidime
    "1009148": ["ceftaroline"],                 # Ceftaroline

    # Penicillins
    "733": ["ampicillin"],                      # Ampicillin
    "7233": ["nafcillin", "oxacillin"],         # Nafcillin
    "7980": ["oxacillin", "nafcillin"],         # Oxacillin
    "152834": ["piperacillin-tazobactam", "piperacillin/tazobactam"],  # Pip-Tazo
    "57962": ["ampicillin-sulbactam", "ampicillin/sulbactam"],  # Unasyn

    # Aminoglycosides
    "4413": ["gentamicin"],                     # Gentamicin
    "10627": ["tobramycin"],                    # Tobramycin
    "641": ["amikacin"],                        # Amikacin

    # Fluoroquinolones
    "2551": ["ciprofloxacin"],                  # Ciprofloxacin
    "82122": ["levofloxacin"],                  # Levofloxacin
    "139462": ["moxifloxacin"],                 # Moxifloxacin

    # Oxazolidinones
    "190521": ["linezolid"],                    # Linezolid

    # Lipopeptides
    "203563": ["daptomycin"],                   # Daptomycin

    # Tetracyclines
    "10395": ["tetracycline"],                  # Tetracycline
    "1665088": ["doxycycline"],                 # Doxycycline

    # Sulfonamides
    "10831": ["trimethoprim-sulfamethoxazole", "trimethoprim/sulfamethoxazole", "tmp-smx"],

    # Macrolides
    "3640": ["erythromycin"],                   # Erythromycin
    "18631": ["azithromycin"],                  # Azithromycin
    "372684": ["clarithromycin"],               # Clarithromycin

    # Clindamycin
    "2582": ["clindamycin"],                    # Clindamycin

    # Metronidazole
    "6922": ["metronidazole"],                  # Metronidazole

    # Antifungals (for completeness)
    "4450": ["fluconazole"],                    # Fluconazole
    "327361": ["micafungin"],                   # Micafungin
    "285661": ["caspofungin"],                  # Caspofungin
    "732": ["amphotericin b", "amphotericin"],  # Amphotericin B
    "121243": ["voriconazole"],                 # Voriconazole
}

# Reverse lookup: susceptibility name -> RxNorm codes
SUSCEPTIBILITY_TO_RXNORM: dict[str, list[str]] = {}
for rxnorm, names in ANTIBIOTIC_SUSCEPTIBILITY_MAP.items():
    for name in names:
        name_lower = name.lower()
        if name_lower not in SUSCEPTIBILITY_TO_RXNORM:
            SUSCEPTIBILITY_TO_RXNORM[name_lower] = []
        SUSCEPTIBILITY_TO_RXNORM[name_lower].append(rxnorm)
