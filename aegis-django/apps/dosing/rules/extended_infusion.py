"""Extended infusion rules for antimicrobial dosing optimization.

Identifies opportunities to optimize beta-lactam dosing through extended or
continuous infusion strategies based on PK/PD principles (time-dependent killing).
"""

import logging
from typing import Any

from ..alert_models import DoseAlertSeverity, DoseFlagType, DoseFlag
from ..data_models import PatientContext, MedicationOrder
from ..rules_engine import BaseRuleModule

logger = logging.getLogger(__name__)


EXTENDED_INFUSION_DRUGS = {
    "piperacillin-tazobactam": {
        "rationale": "Time-dependent killing: Target >50% fT>MIC for beta-lactams",
        "standard_infusion_min": 30,
        "recommended_infusion_min": 240,
        "continuous_infusion": True,
        "indications": ["Pseudomonas aeruginosa", "severe sepsis", "septic shock", "ICU patients", "augmented renal clearance"],
        "evidence": "BLING-III trial (2023): Extended infusion improved clinical cure in Gram-negative infections",
        "source": "Lancet Infect Dis 2023; Roberts et al.",
    },
    "meropenem": {
        "rationale": "Time-dependent killing: Target >40% fT>MIC for carbapenems",
        "standard_infusion_min": 30,
        "recommended_infusion_min": 180,
        "continuous_infusion": True,
        "indications": ["Pseudomonas aeruginosa", "carbapenem-resistant organisms", "severe sepsis", "ICU patients", "febrile neutropenia"],
        "evidence": "Extended infusion improves target attainment, especially for MIC >= 2 mg/L",
        "source": "Crit Care Med 2020; Dulhunty et al.",
    },
    "cefepime": {
        "rationale": "Time-dependent killing: Target >60-70% fT>MIC for cephalosporins",
        "standard_infusion_min": 30,
        "recommended_infusion_min": 180,
        "continuous_infusion": True,
        "indications": ["Pseudomonas aeruginosa", "severe sepsis", "ICU patients", "febrile neutropenia"],
        "evidence": "Extended infusion reduces mortality in critically ill patients",
        "source": "Antimicrob Agents Chemother 2013; Rhodes et al.",
    },
    "ceftazidime": {
        "rationale": "Time-dependent killing: Target >60-70% fT>MIC",
        "standard_infusion_min": 30,
        "recommended_infusion_min": 180,
        "continuous_infusion": True,
        "indications": ["Pseudomonas aeruginosa", "severe sepsis", "ICU patients"],
        "evidence": "Extended infusion improves PK/PD target attainment",
        "source": "J Antimicrob Chemother 2018",
    },
    "ceftazidime-avibactam": {
        "rationale": "Time-dependent killing: Target >50% fT>MIC for beta-lactam/BLI",
        "standard_infusion_min": 120,
        "recommended_infusion_min": 180,
        "continuous_infusion": False,
        "indications": ["CRE (carbapenem-resistant Enterobacterales)", "MDR Pseudomonas aeruginosa", "severe sepsis"],
        "evidence": "Extended infusion enhances target attainment for high MIC pathogens",
        "source": "Antimicrob Agents Chemother 2019",
    },
    "ceftolozane-tazobactam": {
        "rationale": "Time-dependent killing: Target >40-50% fT>MIC",
        "standard_infusion_min": 60,
        "recommended_infusion_min": 180,
        "continuous_infusion": True,
        "indications": ["MDR Pseudomonas aeruginosa", "severe sepsis", "ICU patients"],
        "evidence": "Extended infusion recommended for severe infections and high MIC",
        "source": "Clin Infect Dis 2021",
    },
    "aztreonam": {
        "rationale": "Time-dependent killing: Target >40% fT>MIC for monobactams",
        "standard_infusion_min": 30,
        "recommended_infusion_min": 180,
        "continuous_infusion": True,
        "indications": ["Pseudomonas aeruginosa", "severe sepsis", "beta-lactam allergy (alternative)"],
        "evidence": "Continuous infusion improves target attainment",
        "source": "Antimicrob Agents Chemother",
    },
    "ampicillin": {
        "rationale": "Time-dependent killing: Target >50% fT>MIC for penicillins",
        "standard_infusion_min": 30,
        "recommended_infusion_min": 240,
        "continuous_infusion": True,
        "indications": ["Enterococcus faecalis", "Listeria monocytogenes", "meningitis"],
        "evidence": "Continuous infusion used for endocarditis and meningitis",
        "source": "Clinical practice guidelines",
    },
    "nafcillin": {
        "rationale": "Time-dependent killing: Target >40% fT>MIC",
        "standard_infusion_min": 30,
        "recommended_infusion_min": None,
        "continuous_infusion": True,
        "indications": ["MSSA bacteremia", "MSSA endocarditis", "severe MSSA infections"],
        "evidence": "Continuous infusion commonly used for serious MSSA infections",
        "source": "IDSA MRSA Guidelines",
    },
    "oxacillin": {
        "rationale": "Time-dependent killing: Target >40% fT>MIC",
        "standard_infusion_min": 30,
        "recommended_infusion_min": None,
        "continuous_infusion": True,
        "indications": ["MSSA bacteremia", "MSSA endocarditis"],
        "evidence": "Continuous infusion for serious MSSA infections",
        "source": "Clinical practice",
    },
}


HIGH_RISK_CONDITIONS = [
    "septic shock", "severe sepsis", "augmented renal clearance",
    "burns", "cystic fibrosis", "febrile neutropenia",
]


def get_infusion_duration(med: MedicationOrder, default_minutes: int) -> int:
    if med.infusion_duration_minutes is not None:
        return med.infusion_duration_minutes
    return default_minutes


class ExtendedInfusionRules(BaseRuleModule):
    """Check for extended infusion optimization opportunities."""

    def evaluate(self, context: PatientContext) -> list[DoseFlag]:
        flags: list[DoseFlag] = []

        for med in context.antimicrobials:
            drug_lower = med.drug_name.lower()

            matching_drug = None
            for drug_name in EXTENDED_INFUSION_DRUGS:
                if drug_name in drug_lower or drug_lower in drug_name:
                    matching_drug = drug_name
                    break

            if not matching_drug:
                continue

            rules = EXTENDED_INFUSION_DRUGS[matching_drug]

            current_duration = get_infusion_duration(
                med, default_minutes=rules["standard_infusion_min"]
            )

            recommended_duration = rules.get("recommended_infusion_min")

            if current_duration == 9999:
                continue

            if recommended_duration and current_duration < recommended_duration:
                severity = self._determine_severity(context, rules)

                if rules["continuous_infusion"]:
                    recommendation = f"Consider extended infusion ({recommended_duration // 60}h) or continuous infusion"
                else:
                    recommendation = f"Consider extended infusion ({recommended_duration // 60}h)"

                indication_match = self._check_indication_match(context, rules)
                indication_note = ""
                if indication_match:
                    indication_note = f" High-yield for: {indication_match}"

                flags.append(DoseFlag(
                    flag_type=DoseFlagType.EXTENDED_INFUSION_CANDIDATE,
                    severity=severity,
                    drug=med.drug_name,
                    message=f"{med.drug_name}: Extended infusion may improve outcomes ({current_duration} min current infusion)",
                    expected=recommendation,
                    actual=f"Standard infusion ({current_duration} minutes)",
                    rule_source=rules.get("source", "PK/PD guidelines"),
                    indication=context.indication,
                    details={
                        "current_infusion_min": current_duration,
                        "recommended_infusion_min": recommended_duration,
                        "continuous_infusion_supported": rules["continuous_infusion"],
                        "rationale": rules["rationale"],
                        "evidence": rules.get("evidence", ""),
                        "indication_match": indication_note,
                    },
                ))

        return flags

    def _determine_severity(self, context, rules):
        if context.indication:
            indication_lower = context.indication.lower()
            for condition in HIGH_RISK_CONDITIONS:
                if condition in indication_lower:
                    return DoseAlertSeverity.HIGH

        if self._check_indication_match(context, rules):
            return DoseAlertSeverity.MODERATE

        return DoseAlertSeverity.LOW

    def _check_indication_match(self, context, rules):
        if not context.indication:
            return None
        indication_lower = context.indication.lower()
        for target in rules.get("indications", []):
            if target.lower() in indication_lower:
                return target
        return None
