"""Drug-drug interaction rules for antimicrobials.

Detects clinically significant drug-drug interactions between antimicrobials
and co-medications or between multiple antimicrobials.
"""

import logging
from typing import Any

from common.dosing_verification import (
    DoseAlertSeverity,
    DoseFlag,
    DoseFlagType,
)
from ..models import PatientContext, MedicationOrder
from ..rules_engine import BaseRuleModule

logger = logging.getLogger(__name__)


# Drug interaction rules with severity and mechanisms
DRUG_INTERACTIONS = [
    # Carbapenems
    {
        "antimicrobial": "meropenem",
        "interacting_drug": "valproic acid",
        "severity": DoseAlertSeverity.CRITICAL,
        "mechanism": "Meropenem significantly reduces valproic acid serum concentrations (50-100% decrease), increasing seizure risk",
        "recommendation": "Avoid combination if possible. If unavoidable, monitor valproic acid levels closely and consider alternative antibiotic or antiepileptic.",
        "source": "Clin Infect Dis 2005;41:1197-1204",
    },
    {
        "antimicrobial": "imipenem",
        "interacting_drug": "valproic acid",
        "severity": DoseAlertSeverity.CRITICAL,
        "mechanism": "Imipenem significantly reduces valproic acid serum concentrations, increasing seizure risk",
        "recommendation": "Avoid combination if possible. Consider alternative antibiotic.",
        "source": "Clin Infect Dis 2005;41:1197-1204",
    },
    {
        "antimicrobial": "ertapenem",
        "interacting_drug": "valproic acid",
        "severity": DoseAlertSeverity.CRITICAL,
        "mechanism": "Ertapenem may reduce valproic acid serum concentrations",
        "recommendation": "Monitor valproic acid levels if combination necessary",
        "source": "Package insert",
    },

    # Oxazolidinones
    {
        "antimicrobial": "linezolid",
        "interacting_drug": "ssri",
        "severity": DoseAlertSeverity.CRITICAL,
        "mechanism": "Linezolid is a reversible MAO inhibitor. SSRIs increase serotonin syndrome risk (hyperthermia, confusion, rigidity, autonomic instability)",
        "recommendation": "Avoid combination. If unavoidable, use lowest SSRI dose and monitor closely for serotonin syndrome. Consider stopping SSRI 2 weeks before linezolid.",
        "source": "FDA Safety Alert 2011, IDSA MRSA Guidelines",
    },
    {
        "antimicrobial": "linezolid",
        "interacting_drug": "snri",
        "severity": DoseAlertSeverity.CRITICAL,
        "mechanism": "Linezolid is a reversible MAO inhibitor. SNRIs increase serotonin syndrome risk",
        "recommendation": "Avoid combination. Monitor closely if unavoidable.",
        "source": "FDA Safety Alert 2011",
    },
    {
        "antimicrobial": "linezolid",
        "interacting_drug": "tricyclic antidepressant",
        "severity": DoseAlertSeverity.HIGH,
        "mechanism": "Potential serotonergic interaction",
        "recommendation": "Monitor for serotonin syndrome if combination used",
        "source": "FDA Safety Alert 2011",
    },

    # Rifamycins
    {
        "antimicrobial": "rifampin",
        "interacting_drug": "warfarin",
        "severity": DoseAlertSeverity.HIGH,
        "mechanism": "Rifampin induces CYP2C9, increasing warfarin metabolism and reducing anticoagulant effect",
        "recommendation": "Monitor INR closely. May need to increase warfarin dose significantly (2-3x) during rifampin therapy",
        "source": "CHEST Antithrombotic Guidelines",
    },
    {
        "antimicrobial": "rifampin",
        "interacting_drug": "antiretroviral",
        "severity": DoseAlertSeverity.HIGH,
        "mechanism": "Rifampin induces CYP3A4, reducing antiretroviral levels",
        "recommendation": "Consult infectious disease/HIV specialist. May need to adjust antiretroviral regimen or use rifabutin instead",
        "source": "DHHS HIV Guidelines",
    },
    {
        "antimicrobial": "rifampin",
        "interacting_drug": "azole antifungal",
        "severity": DoseAlertSeverity.HIGH,
        "mechanism": "Rifampin induces CYP3A4, significantly reducing azole levels",
        "recommendation": "Avoid combination if possible. Consider alternative antibiotic or antifungal",
        "source": "IDSA Fungal Infection Guidelines",
    },
    {
        "antimicrobial": "rifampin",
        "interacting_drug": "immunosuppressant",
        "severity": DoseAlertSeverity.HIGH,
        "mechanism": "Rifampin induces CYP3A4, reducing tacrolimus/cyclosporine/sirolimus levels",
        "recommendation": "Monitor immunosuppressant levels closely. May need dose increases up to 3-5x baseline",
        "source": "Transplant Guidelines",
    },

    # Azole Antifungals
    {
        "antimicrobial": "voriconazole",
        "interacting_drug": "cyp3a4 substrate",
        "severity": DoseAlertSeverity.HIGH,
        "mechanism": "Voriconazole inhibits CYP3A4, increasing substrate drug levels",
        "recommendation": "Check for dose adjustments of CYP3A4 substrates (e.g., tacrolimus, sirolimus, calcium channel blockers)",
        "source": "IDSA Aspergillosis Guidelines",
    },
    {
        "antimicrobial": "voriconazole",
        "interacting_drug": "phenytoin",
        "severity": DoseAlertSeverity.CRITICAL,
        "mechanism": "Phenytoin induces CYP450, reducing voriconazole levels. Voriconazole inhibits CYP2C9/19, increasing phenytoin levels",
        "recommendation": "Avoid combination. Use alternative antifungal or antiepileptic",
        "source": "IDSA Aspergillosis Guidelines",
    },
    {
        "antimicrobial": "fluconazole",
        "interacting_drug": "warfarin",
        "severity": DoseAlertSeverity.HIGH,
        "mechanism": "Fluconazole inhibits CYP2C9, reducing warfarin metabolism and increasing INR",
        "recommendation": "Monitor INR closely. May need to reduce warfarin dose by 25-50%",
        "source": "CHEST Antithrombotic Guidelines",
    },

    # Metronidazole
    {
        "antimicrobial": "metronidazole",
        "interacting_drug": "warfarin",
        "severity": DoseAlertSeverity.HIGH,
        "mechanism": "Metronidazole inhibits warfarin metabolism, increasing INR and bleeding risk",
        "recommendation": "Monitor INR closely. Consider reducing warfarin dose by 25-35%",
        "source": "CHEST Antithrombotic Guidelines",
    },
    {
        "antimicrobial": "metronidazole",
        "interacting_drug": "lithium",
        "severity": DoseAlertSeverity.HIGH,
        "mechanism": "Metronidazole may increase lithium levels, causing toxicity",
        "recommendation": "Monitor lithium levels during concurrent therapy",
        "source": "Package insert",
    },

    # Fluoroquinolones
    {
        "antimicrobial": "fluoroquinolone",
        "interacting_drug": "qt prolonging agent",
        "severity": DoseAlertSeverity.HIGH,
        "mechanism": "Additive QT prolongation increases torsades de pointes risk",
        "recommendation": "Monitor ECG if combination necessary. Avoid in patients with prolonged QTc >500ms",
        "source": "FDA Drug Safety Communication 2016",
    },
    {
        "antimicrobial": "ciprofloxacin",
        "interacting_drug": "theophylline",
        "severity": DoseAlertSeverity.HIGH,
        "mechanism": "Ciprofloxacin inhibits theophylline metabolism, increasing toxicity risk",
        "recommendation": "Monitor theophylline levels. Reduce theophylline dose by 50%",
        "source": "Package insert",
    },
]


# Drug class mappings for pattern matching
DRUG_CLASS_MAPPINGS = {
    "ssri": ["fluoxetine", "sertraline", "paroxetine", "citalopram", "escitalopram", "fluvoxamine"],
    "snri": ["venlafaxine", "duloxetine", "desvenlafaxine"],
    "tricyclic antidepressant": ["amitriptyline", "nortriptyline", "desipramine", "imipramine"],
    "antiretroviral": ["atazanavir", "darunavir", "ritonavir", "lopinavir", "efavirenz", "dolutegravir"],
    "azole antifungal": ["fluconazole", "voriconazole", "posaconazole", "isavuconazole", "itraconazole"],
    "immunosuppressant": ["tacrolimus", "cyclosporine", "sirolimus", "everolimus"],
    "cyp3a4 substrate": ["tacrolimus", "sirolimus", "cyclosporine", "amlodipine", "simvastatin", "midazolam"],
    "qt prolonging agent": ["amiodarone", "sotalol", "dronedarone", "quinidine", "procainamide", "disopyramide", "haloperidol", "ziprasidone"],
    "fluoroquinolone": ["ciprofloxacin", "levofloxacin", "moxifloxacin", "delafloxacin"],
}


class DrugInteractionRules(BaseRuleModule):
    """Check for drug-drug interactions between antimicrobials and co-medications."""

    def evaluate(self, context: PatientContext) -> list[DoseFlag]:
        """Check for drug-drug interactions.

        Args:
            context: Patient clinical context

        Returns:
            List of DoseFlag objects for detected interactions
        """
        flags: list[DoseFlag] = []

        # Get list of all co-medication names (normalized to lowercase)
        co_med_names = [med.drug_name.lower() for med in context.co_medications]

        # Check each antimicrobial against interaction rules
        for antimicrobial in context.antimicrobials:
            abx_name = antimicrobial.drug_name.lower()

            for rule in DRUG_INTERACTIONS:
                # Check if this rule applies to this antimicrobial
                if not self._drug_matches(abx_name, rule["antimicrobial"]):
                    continue

                # Check if patient is on the interacting drug
                interacting_drug = rule["interacting_drug"]

                if self._patient_on_interacting_drug(co_med_names, interacting_drug):
                    flag = DoseFlag(
                        drug=antimicrobial.drug_name,
                        indication=context.indication,
                        flag_type=DoseFlagType.DRUG_INTERACTION,
                        severity=rule["severity"],
                        message=f"{antimicrobial.drug_name} + {interacting_drug}: {rule['mechanism']}",
                        actual=f"{antimicrobial.drug_name} + {self._format_interacting_drug_list(co_med_names, interacting_drug)}",
                        expected=rule["recommendation"],
                        rule_source=rule["source"],
                    )
                    flags.append(flag)
                    logger.info(
                        f"DDI detected: {antimicrobial.drug_name} + {interacting_drug} "
                        f"for {context.patient_mrn} ({rule['severity'].value})"
                    )

        return flags

    def _drug_matches(self, drug_name: str, pattern: str) -> bool:
        """Check if drug name matches the pattern.

        Args:
            drug_name: Actual drug name (lowercase)
            pattern: Pattern to match (may be specific drug or class)

        Returns:
            True if drug matches pattern
        """
        # Exact match
        if pattern in drug_name:
            return True

        # Check if pattern is a drug class
        if pattern in DRUG_CLASS_MAPPINGS:
            class_members = DRUG_CLASS_MAPPINGS[pattern]
            return any(member in drug_name for member in class_members)

        return False

    def _patient_on_interacting_drug(self, co_med_names: list[str], interacting_drug: str) -> bool:
        """Check if patient is on an interacting drug.

        Args:
            co_med_names: List of co-medication names (lowercase)
            interacting_drug: Drug or class to check for

        Returns:
            True if patient is on interacting drug
        """
        # Check for exact match
        if any(interacting_drug in med for med in co_med_names):
            return True

        # Check if it's a drug class
        if interacting_drug in DRUG_CLASS_MAPPINGS:
            class_members = DRUG_CLASS_MAPPINGS[interacting_drug]
            for member in class_members:
                if any(member in med for med in co_med_names):
                    return True

        return False

    def _format_interacting_drug_list(self, co_med_names: list[str], interacting_drug: str) -> str:
        """Format the actual interacting drugs found.

        Args:
            co_med_names: List of co-medication names (lowercase)
            interacting_drug: Drug or class to check for

        Returns:
            Formatted string of actual drugs
        """
        found = []

        # Check for exact match
        for med in co_med_names:
            if interacting_drug in med:
                found.append(med)

        # Check if it's a drug class
        if interacting_drug in DRUG_CLASS_MAPPINGS:
            class_members = DRUG_CLASS_MAPPINGS[interacting_drug]
            for member in class_members:
                for med in co_med_names:
                    if member in med and med not in found:
                        found.append(med)

        return ", ".join(found) if found else interacting_drug
