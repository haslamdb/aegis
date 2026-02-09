"""CDA document generator for NHSN HAI (BSI/CLABSI) reporting.

Generates HL7 CDA R2 compliant documents for submission to NHSN.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Any
from xml.etree import ElementTree as ET
from xml.dom import minidom

# CDA namespaces
CDA_NS = "urn:hl7-org:v3"
SDTC_NS = "urn:hl7-org:sdtc"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"

# NHSN OIDs
NHSN_ROOT_OID = "2.16.840.1.113883.3.117"
LOINC_OID = "2.16.840.1.113883.6.1"
SNOMED_OID = "2.16.840.1.113883.6.96"
CDC_NHSN_OID = "2.16.840.1.113883.3.117.1.1.5.2.1.1"

HAI_REPORT_CODES = {
    "bsi": "51897-7",
    "clabsi": "51897-7",
}

BSI_EVENT_CODES = {
    "clabsi": "1645-5",
    "lcbi": "1643-0",
}


@dataclass
class BSICDADocument:
    """Data structure for a BSI CDA document."""

    document_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    creation_time: datetime = field(default_factory=datetime.now)

    facility_id: str = ""
    facility_name: str = ""
    facility_oid: str = ""

    patient_id: str = ""
    patient_mrn: str = ""
    patient_name: str = ""
    patient_dob: date | None = None
    patient_gender: str = ""

    event_id: str = ""
    event_date: date | None = None
    event_type: str = "clabsi"
    location_code: str = ""

    organism: str = ""
    organism_code: str = ""
    device_type: str = "central_line"
    device_days: int | None = None

    is_clabsi: bool = True
    is_mbi_lcbi: bool = False
    secondary_bsi: bool = False

    author_name: str = ""
    author_id: str = ""


class CDAGenerator:
    """Generates CDA R2 documents for NHSN HAI submission."""

    def __init__(self, facility_id: str, facility_name: str, facility_oid: str | None = None):
        self.facility_id = facility_id
        self.facility_name = facility_name
        self.facility_oid = facility_oid or f"{NHSN_ROOT_OID}.{facility_id}"

    def generate_bsi_document(self, doc: BSICDADocument) -> str:
        """Generate a BSI CDA document XML string."""
        if not doc.facility_id:
            doc.facility_id = self.facility_id
        if not doc.facility_name:
            doc.facility_name = self.facility_name
        if not doc.facility_oid:
            doc.facility_oid = self.facility_oid

        root = self._create_cda_root()
        self._add_type_id(root)
        self._add_template_ids(root, "bsi")
        self._add_document_id(root, doc.document_id)
        self._add_code(root, HAI_REPORT_CODES["bsi"], "Healthcare Associated Infection Report")
        self._add_title(root, "BSI Event Report")
        self._add_effective_time(root, doc.creation_time)
        self._add_confidentiality_code(root)
        self._add_language_code(root)
        self._add_record_target(root, doc)
        self._add_author(root, doc)
        self._add_custodian(root, doc)
        self._add_bsi_body(root, doc)

        return self._to_xml_string(root)

    def generate_batch(self, documents: list[BSICDADocument]) -> list[str]:
        """Generate multiple CDA documents."""
        return [self.generate_bsi_document(doc) for doc in documents]

    def _create_cda_root(self) -> ET.Element:
        ET.register_namespace("", CDA_NS)
        ET.register_namespace("sdtc", SDTC_NS)
        ET.register_namespace("xsi", XSI_NS)
        return ET.Element(
            f"{{{CDA_NS}}}ClinicalDocument",
            {f"{{{XSI_NS}}}schemaLocation": f"{CDA_NS} CDA.xsd"},
        )

    def _add_type_id(self, root: ET.Element) -> None:
        ET.SubElement(root, f"{{{CDA_NS}}}typeId", root="2.16.840.1.113883.1.3", extension="POCD_HD000040")

    def _add_template_ids(self, root: ET.Element, report_type: str) -> None:
        ET.SubElement(root, f"{{{CDA_NS}}}templateId", root="2.16.840.1.113883.10.20.5.4.25")
        if report_type in ("bsi", "clabsi"):
            ET.SubElement(root, f"{{{CDA_NS}}}templateId", root="2.16.840.1.113883.10.20.5.36")

    def _add_document_id(self, root: ET.Element, doc_id: str) -> None:
        ET.SubElement(root, f"{{{CDA_NS}}}id", root=self.facility_oid, extension=doc_id)

    def _add_code(self, root: ET.Element, code: str, display_name: str) -> None:
        ET.SubElement(
            root, f"{{{CDA_NS}}}code",
            code=code, codeSystem=LOINC_OID, codeSystemName="LOINC", displayName=display_name,
        )

    def _add_title(self, root: ET.Element, title: str) -> None:
        elem = ET.SubElement(root, f"{{{CDA_NS}}}title")
        elem.text = title

    def _add_effective_time(self, root: ET.Element, dt: datetime) -> None:
        ET.SubElement(root, f"{{{CDA_NS}}}effectiveTime", value=dt.strftime("%Y%m%d%H%M%S"))

    def _add_confidentiality_code(self, root: ET.Element) -> None:
        ET.SubElement(root, f"{{{CDA_NS}}}confidentialityCode", code="N", codeSystem="2.16.840.1.113883.5.25")

    def _add_language_code(self, root: ET.Element) -> None:
        ET.SubElement(root, f"{{{CDA_NS}}}languageCode", code="en-US")

    def _add_record_target(self, root: ET.Element, doc: BSICDADocument) -> None:
        record_target = ET.SubElement(root, f"{{{CDA_NS}}}recordTarget")
        patient_role = ET.SubElement(record_target, f"{{{CDA_NS}}}patientRole")
        ET.SubElement(patient_role, f"{{{CDA_NS}}}id", root=doc.facility_oid, extension=doc.patient_mrn)
        patient = ET.SubElement(patient_role, f"{{{CDA_NS}}}patient")

        if doc.patient_name:
            name = ET.SubElement(patient, f"{{{CDA_NS}}}name")
            parts = doc.patient_name.split()
            if len(parts) >= 2:
                given = ET.SubElement(name, f"{{{CDA_NS}}}given")
                given.text = parts[0]
                family = ET.SubElement(name, f"{{{CDA_NS}}}family")
                family.text = parts[-1]
            else:
                given = ET.SubElement(name, f"{{{CDA_NS}}}given")
                given.text = doc.patient_name

        if doc.patient_gender:
            ET.SubElement(patient, f"{{{CDA_NS}}}administrativeGenderCode", code=doc.patient_gender, codeSystem="2.16.840.1.113883.5.1")

        if doc.patient_dob:
            ET.SubElement(patient, f"{{{CDA_NS}}}birthTime", value=doc.patient_dob.strftime("%Y%m%d"))

    def _add_author(self, root: ET.Element, doc: BSICDADocument) -> None:
        author = ET.SubElement(root, f"{{{CDA_NS}}}author")
        ET.SubElement(author, f"{{{CDA_NS}}}time", value=doc.creation_time.strftime("%Y%m%d%H%M%S"))
        assigned_author = ET.SubElement(author, f"{{{CDA_NS}}}assignedAuthor")
        ET.SubElement(assigned_author, f"{{{CDA_NS}}}id", root=doc.facility_oid, extension=doc.author_id or "system")

        if doc.author_name:
            assigned_person = ET.SubElement(assigned_author, f"{{{CDA_NS}}}assignedPerson")
            name = ET.SubElement(assigned_person, f"{{{CDA_NS}}}name")
            name_text = ET.SubElement(name, f"{{{CDA_NS}}}given")
            name_text.text = doc.author_name

        org = ET.SubElement(assigned_author, f"{{{CDA_NS}}}representedOrganization")
        ET.SubElement(org, f"{{{CDA_NS}}}id", root=doc.facility_oid)
        org_name = ET.SubElement(org, f"{{{CDA_NS}}}name")
        org_name.text = doc.facility_name

    def _add_custodian(self, root: ET.Element, doc: BSICDADocument) -> None:
        custodian = ET.SubElement(root, f"{{{CDA_NS}}}custodian")
        assigned = ET.SubElement(custodian, f"{{{CDA_NS}}}assignedCustodian")
        org = ET.SubElement(assigned, f"{{{CDA_NS}}}representedCustodianOrganization")
        ET.SubElement(org, f"{{{CDA_NS}}}id", root=doc.facility_oid)
        name = ET.SubElement(org, f"{{{CDA_NS}}}name")
        name.text = doc.facility_name

    def _add_bsi_body(self, root: ET.Element, doc: BSICDADocument) -> None:
        component = ET.SubElement(root, f"{{{CDA_NS}}}component")
        structured_body = ET.SubElement(component, f"{{{CDA_NS}}}structuredBody")
        section_component = ET.SubElement(structured_body, f"{{{CDA_NS}}}component")
        section = ET.SubElement(section_component, f"{{{CDA_NS}}}section")

        ET.SubElement(section, f"{{{CDA_NS}}}templateId", root="2.16.840.1.113883.10.20.5.4.26")
        ET.SubElement(
            section, f"{{{CDA_NS}}}code",
            code="51899-3", codeSystem=LOINC_OID, codeSystemName="LOINC", displayName="Details",
        )

        title = ET.SubElement(section, f"{{{CDA_NS}}}title")
        title.text = "Infection Details"

        text = ET.SubElement(section, f"{{{CDA_NS}}}text")
        self._add_bsi_narrative(text, doc)
        self._add_bsi_entries(section, doc)

    def _add_bsi_narrative(self, text: ET.Element, doc: BSICDADocument) -> None:
        table = ET.SubElement(text, "table")
        for label, value in [
            ("Event Date", doc.event_date.strftime("%Y-%m-%d") if doc.event_date else "Unknown"),
            ("Event Type", "CLABSI" if doc.is_clabsi else "BSI"),
            ("Organism", doc.organism or "Unknown"),
            ("Location", doc.location_code or "Unknown"),
        ]:
            tr = ET.SubElement(table, "tr")
            td1 = ET.SubElement(tr, "td")
            td1.text = label
            td2 = ET.SubElement(tr, "td")
            td2.text = value

        if doc.device_days is not None:
            tr = ET.SubElement(table, "tr")
            td1 = ET.SubElement(tr, "td")
            td1.text = "Device Days"
            td2 = ET.SubElement(tr, "td")
            td2.text = str(doc.device_days)

    def _add_bsi_entries(self, section: ET.Element, doc: BSICDADocument) -> None:
        entry = ET.SubElement(section, f"{{{CDA_NS}}}entry")
        observation = ET.SubElement(entry, f"{{{CDA_NS}}}observation", classCode="OBS", moodCode="EVN")
        ET.SubElement(observation, f"{{{CDA_NS}}}templateId", root="2.16.840.1.113883.10.20.5.6.139")

        event_code = BSI_EVENT_CODES.get(doc.event_type, BSI_EVENT_CODES["clabsi"])
        ET.SubElement(
            observation, f"{{{CDA_NS}}}code",
            code=event_code, codeSystem=CDC_NHSN_OID, displayName="BSI Event Type",
        )
        ET.SubElement(observation, f"{{{CDA_NS}}}statusCode", code="completed")

        if doc.event_date:
            ET.SubElement(observation, f"{{{CDA_NS}}}effectiveTime", value=doc.event_date.strftime("%Y%m%d"))

        if doc.organism:
            org_entry = ET.SubElement(section, f"{{{CDA_NS}}}entry")
            org_obs = ET.SubElement(org_entry, f"{{{CDA_NS}}}observation", classCode="OBS", moodCode="EVN")
            ET.SubElement(org_obs, f"{{{CDA_NS}}}code", code="41852-5", codeSystem=LOINC_OID, displayName="Microorganism identified")
            value = ET.SubElement(org_obs, f"{{{CDA_NS}}}value", {f"{{{XSI_NS}}}type": "CD"})
            value.set("displayName", doc.organism)
            if doc.organism_code:
                value.set("code", doc.organism_code)
                value.set("codeSystem", SNOMED_OID)

        if doc.location_code:
            loc_entry = ET.SubElement(section, f"{{{CDA_NS}}}entry")
            loc_obs = ET.SubElement(loc_entry, f"{{{CDA_NS}}}observation", classCode="OBS", moodCode="EVN")
            ET.SubElement(loc_obs, f"{{{CDA_NS}}}code", code="2250-8", codeSystem=LOINC_OID, displayName="Location")
            value = ET.SubElement(loc_obs, f"{{{CDA_NS}}}value", {f"{{{XSI_NS}}}type": "CD"})
            value.set("code", doc.location_code)
            value.set("codeSystem", CDC_NHSN_OID)

    def _to_xml_string(self, root: ET.Element) -> str:
        rough_string = ET.tostring(root, encoding="unicode")
        reparsed = minidom.parseString(rough_string)
        return reparsed.toprettyxml(indent="  ", encoding=None)


def create_bsi_document_from_candidate(
    candidate,
    facility_id: str,
    facility_name: str,
    author_name: str = "System",
) -> BSICDADocument:
    """Create a BSI CDA document from a Django HAICandidate model instance."""
    return BSICDADocument(
        document_id=str(uuid.uuid4()),
        creation_time=datetime.now(),
        facility_id=facility_id,
        facility_name=facility_name,
        patient_id=candidate.patient_id,
        patient_mrn=candidate.patient_mrn,
        patient_name=candidate.patient_name,
        event_id=str(candidate.id),
        event_date=candidate.culture_date.date() if candidate.culture_date else None,
        event_type=candidate.hai_type,
        location_code=candidate.patient_location or '',
        organism=candidate.organism or '',
        device_days=candidate.device_days_at_culture,
        is_clabsi=candidate.hai_type == 'clabsi',
        author_name=author_name,
    )
