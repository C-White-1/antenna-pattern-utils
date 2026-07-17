"""Authoritative, immutable definitions for NSMA WG16.99.050."""

from dataclasses import asdict, dataclass

STANDARD_NAME = "NSMA WG16.99.050"
REVISION_DATE = "19990520"


@dataclass(frozen=True)
class FieldDefinition:
    """One field from WG16.99.050 Table 1."""

    abbreviation: str
    name: str
    required: bool
    max_length: int

    @property
    def prefix(self):
        """Return the tagged-record prefix, if the field has one."""

        return None if self.abbreviation == "/point" else f"{self.abbreviation}:,"


FIELDS = (
    FieldDefinition("REVNUM", "Revision Number", True, 42),
    FieldDefinition("REVDAT", "Revision Date", True, 16),
    FieldDefinition("COMNT1", "Comment1", False, 80),
    FieldDefinition("COMNT2", "Comment2", False, 80),
    FieldDefinition("ANTMAN", "Antenna Manufacturer", True, 42),
    FieldDefinition("MODNUM", "Model Number", True, 42),
    FieldDefinition("PATNUM", "Pattern ID Number", False, 42),
    FieldDefinition("FILNUM", "Pattern File Number", False, 13),
    FieldDefinition("FEDORN", "Feed Orientation", False, 13),
    FieldDefinition("DESCR1", "Description1", False, 80),
    FieldDefinition("DESCR2", "Description2", False, 80),
    FieldDefinition("DESCR3", "Description3", False, 80),
    FieldDefinition("DESCR4", "Description4", False, 80),
    FieldDefinition("DESCR5", "Description5", False, 80),
    FieldDefinition("DTDATA", "Date of data", False, 16),
    FieldDefinition("LOWFRQ", "Low Frequency (MHz)", True, 21),
    FieldDefinition("HGHFRQ", "High Frequency (MHz)", True, 21),
    FieldDefinition("GUNITS", "Gain Units", True, 15),
    FieldDefinition("LWGAIN", "Low-band gain", False, 12),
    FieldDefinition("MDGAIN", "Mid-band gain", True, 16),
    FieldDefinition("HGGAIN", "High-band gain", False, 12),
    FieldDefinition("AZWIDT", "Mid-band Az Bmwdth", False, 16),
    FieldDefinition("ELWIDT", "Mid-band El Bmwdth", False, 16),
    FieldDefinition("CONTYP", "Connector Type", False, 80),
    FieldDefinition("ATVSWR", "VSWR", False, 13),
    FieldDefinition("FRTOBA", "Front-to-back Ratio(dB)", False, 10),
    FieldDefinition("ELTILT", "Electrical Downtilt (deg)", True, 16),
    FieldDefinition("RADCTR", "Radiation Center (m)", False, 13),
    FieldDefinition("POTOPO", "Port-to-Port Iso (dB)", False, 12),
    FieldDefinition("MAXPOW", "Max Input Power (W)", False, 17),
    FieldDefinition("ANTLEN", "Antenna Length (m)", False, 14),
    FieldDefinition("ANTWID", "Antenna Width (m)", False, 14),
    FieldDefinition("ANTDEP", "Antenna Depth (m)", False, 14),
    FieldDefinition("ANTWGT", "Antenna Weight (kg)", False, 16),
    FieldDefinition("FIELD1", "Future Field", False, 80),
    FieldDefinition("FIELD2", "Future Field", False, 80),
    FieldDefinition("FIELD3", "Future Field", False, 80),
    FieldDefinition("FIELD4", "Future Field", False, 80),
    FieldDefinition("FIELD5", "Future Field", False, 80),
    FieldDefinition("PATTYP", "Pattern Type", True, 16),
    FieldDefinition("NOFREQ", "# Freq this file", True, 10),
    FieldDefinition("PATFRE", "Pattern Freq (Mhz)", True, 21),
    FieldDefinition("NUMCUT", "# Pattern cuts", True, 11),
    FieldDefinition("PATCUT", "Pattern Cut", True, 11),
    FieldDefinition("POLARI", "Polarization", True, 15),
    FieldDefinition("NUPOIN", "# Data Points", True, 13),
    FieldDefinition("FSTLST", "First & Last Angle", True, 25),
    FieldDefinition("XORIEN", "X-axis Orientation", False, 53),
    FieldDefinition("YORIEN", "Y-axis Orientation", False, 53),
    FieldDefinition("ZORIEN", "Z-axis Orientation", False, 53),
    FieldDefinition("/point", "Pattern cut data", True, 28),
    FieldDefinition("ENDFIL", "End of file", True, 11),
)

FIELDS_BY_ABBREVIATION = {field.abbreviation: field for field in FIELDS}
FIELD_ORDER = {field.abbreviation: index for index, field in enumerate(FIELDS)}


def validate_standard():
    """Raise ``ValueError`` if the built-in standard definition is inconsistent."""

    abbreviations = [field.abbreviation for field in FIELDS]
    if len(abbreviations) != len(set(abbreviations)):
        raise ValueError("NSMA standard contains duplicate field abbreviations")
    if any(field.max_length <= 0 for field in FIELDS):
        raise ValueError("NSMA field lengths must be positive")
    if FIELDS_BY_ABBREVIATION["REVNUM"].max_length != 42:
        raise ValueError("Unexpected REVNUM definition")
    if not FIELDS_BY_ABBREVIATION["ENDFIL"].required:
        raise ValueError("ENDFIL must be required")
    if FIELD_ORDER["ANTMAN"] >= FIELD_ORDER["MODNUM"]:
        raise ValueError("ANTMAN must precede MODNUM")
    if FIELDS[-1].abbreviation != "ENDFIL":
        raise ValueError("ENDFIL must be the final field definition")


def schema_rows():
    """Return serializable dictionaries for generated CSV and JSON artifacts."""

    return [asdict(field) for field in FIELDS]


validate_standard()
