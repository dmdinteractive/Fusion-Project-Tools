"""
naming_logic.py - the "rules" of DMD Project Tools, kept separate from Fusion.

Nothing in this file talks to Fusion. It only takes plain text and numbers
in and gives text back. Keeping it separate means the rules can be tested
outside Fusion, and you can change your naming conventions here without
touching the dialog code.
"""

import re

# How many digits the part number uses: 3 -> CMD-HELLO-001, 4 -> CMD-HELLO-0001
PART_NUMBER_DIGITS = 3

# Number reserved for the top-level assembly of every project.
TOP_ASSEMBLY_NUMBER = 0

# Folder layout created in every project. The first one holds the
# top-level assembly. Rename here if you ever change your layout.
FOLDERS = [
    "00 ASSEMBLY",
    "01 SUBASSEMBLIES",
    "02 FABRICATED",
    "03 PURCHASED",
    "04 DRAWINGS",
    "99 ARCHIVE",
]

# Which folder each kind of new file goes in.
PART_TYPES = ["Fabricated", "Purchased", "Subassembly"]
ASSEMBLY_TYPES = ["Subassembly", "Purchased"]     # choices when naming an assembly file
TOP_LEVEL = "Top-level"
FOLDER_FOR_TYPE = {
    "Fabricated": "02 FABRICATED",
    "Purchased": "03 PURCHASED",
    "Subassembly": "01 SUBASSEMBLIES",
    TOP_LEVEL: "00 ASSEMBLY",
}

# Assemblies are named noun + this word, then modifiers:
# "KIOSK ASSEMBLY, PHONE" (the form ASME Y14.100 is cited as preferring).
ASSEMBLY_WORD = "ASSEMBLY"
_ASSEMBLY_ENDINGS = (" SUBASSEMBLY", " ASSEMBLY", " SUBASSY", " ASSY")

# Project name format: "CMD-HELLO - Hello Exhibit"
PROJECT_NAME_SEPARATOR = " - "

# Project settings are written into the top-level assembly file's
# description (visible in the Data Panel), starting with this marker.
SETTINGS_MARKER = "[DMD]"

# Words that pick out your everyday shop materials in the material list.
# A material shows under "Shop materials" if its name contains any of these.
# Any material library you create yourself in Fusion is always included too.
SHOP_MATERIAL_KEYWORDS = [
    "PLYWOOD", "ALUMINUM", "STEEL", "STAINLESS",
]

# Separator between the noun and its modifiers in the component name.
NAME_SEPARATOR = ", "

# Separator between sections of the description.
DESC_SEPARATOR = " | "

# Starter list for the "Common nouns" dropdown. Edit freely.
COMMON_NOUNS = [
    "ANGLE", "BASE", "BEARING", "BLOCK", "BRACKET", "BUTTON", "CABLE",
    "CHANNEL", "CLEAT", "COVER", "DOOR", "ENCLOSURE", "FRAME", "GRAPHIC",
    "GUSSET", "HINGE", "KNOB", "LABEL", "LED", "MAGNET", "MOTOR", "NUT",
    "PANEL", "PCB", "PIN", "PLATE", "RAIL", "SCREW", "SHAFT", "SHELF",
    "SIGN", "SPACER", "SPEAKER", "STANDOFF", "TUBE", "WASHER",
]

# Vendors for purchased parts. The role ("DIST" = distributor,
# "MFR" = manufacturer) is written into the description so it is always
# clear the number belongs to someone else, not to your project.
VENDORS = [
    ("McMaster-Carr", "DIST"),
    ("Digi-Key", "DIST"),
    ("Mouser", "DIST"),
    ("Amazon", "DIST"),
    ("Other manufacturer", "MFR"),
    ("Other distributor", "DIST"),
]


# Words that describe WHERE a part sits rather than WHAT it is. They are
# ambiguous as soon as the assembly is viewed from another side, so the
# dialog warns when they appear in a name. Edit freely.
POSITION_WORDS = [
    "TOP", "BOTTOM", "LEFT", "RIGHT", "FRONT", "BACK", "REAR", "UPPER",
    "LOWER", "MIDDLE", "CENTER", "CENTRE", "INNER", "OUTER", "NORTH",
    "SOUTH", "EAST", "WEST", "FIRST", "SECOND", "THIRD",
]

# Hand options. LH/RH are always defined by the design's reference view.
HANDS = ["None", "LH", "RH"]
OPPOSITE_HAND = {"LH": "RH", "RH": "LH"}


def find_position_words(text):
    """Return the position words found in text, in the order they appear."""
    words = re.findall(r"[A-Za-z]+", text or "")
    found = []
    for w in words:
        if w.upper() in POSITION_WORDS and w.upper() not in found:
            found.append(w.upper())
    return found


def position_warning(text):
    found = find_position_words(text)
    if not found:
        return ""
    advice = "Name uses position words ({}). Prefer what the part does or a defining feature " \
             "(e.g. ACCESS, MOTOR MOUNT, W/ CABLE PASS-THRU).".format(", ".join(found))
    if any(w in ("LEFT", "RIGHT") for w in found):
        advice += " For mirror-image parts use the Hand option instead."
    return advice


def split_hand(name_modifiers):
    """If the last filled-in modifier is LH or RH, pull it out.
    Returns (modifiers_without_hand, hand)."""
    mods = list(name_modifiers)
    for i in range(len(mods) - 1, -1, -1):
        if mods[i].strip():
            if mods[i].strip().upper() in OPPOSITE_HAND:
                hand = mods[i].strip().upper()
                mods[i] = ""
                return mods, hand
            break
    return mods, "None"


def vendor_role(vendor_label):
    for label, role in VENDORS:
        if label == vendor_label:
            return role
    return "DIST"


def compose_name(noun, modifiers, upper=True, hand="None"):
    """'panel', ['side', 'left'] -> 'PANEL, SIDE, LEFT'
    With hand='LH' the hand is added as the last modifier."""
    parts = [p.strip() for p in [noun] + list(modifiers) if p and p.strip()]
    if hand in OPPOSITE_HAND and parts:
        parts.append(hand)
    name = NAME_SEPARATOR.join(parts)
    return name.upper() if upper else name


def strip_assembly_word(noun):
    """'KIOSK ASSEMBLY' -> ('KIOSK', True);  'KIOSK' -> ('KIOSK', False)"""
    text = (noun or "").strip()
    for ending in _ASSEMBLY_ENDINGS:
        if text.upper().endswith(ending):
            return text[:-len(ending)].strip(), True
    return text, False


def assembly_noun(noun):
    """'kiosk' -> 'kiosk ASSEMBLY' (left alone if it already ends that way)."""
    base, _ = strip_assembly_word(noun)
    return "{} {}".format(base, ASSEMBLY_WORD) if base else ""


def contents_text(parts, subassemblies):
    """8, 2 -> '8 PARTS, 2 SUBASSEMBLIES'  (1 -> singular, 0 -> left out)"""
    out = []
    if parts:
        out.append("{} PART{}".format(parts, "" if parts == 1 else "S"))
    if subassemblies:
        out.append("{} SUBASSEMBL{}".format(subassemblies, "Y" if subassemblies == 1 else "IES"))
    return ", ".join(out)


def is_top_level_number(part_number, prefix):
    return parse_part_number(part_number, prefix)[0] == TOP_ASSEMBLY_NUMBER


def parse_name(name, modifier_slots=3):
    """Split an existing 'PANEL, SIDE, LEFT' name back into noun + modifiers.
    Anything beyond the available slots is kept together in the last slot."""
    pieces = [p.strip() for p in (name or "").split(",") if p.strip()]
    if not pieces:
        return "", [""] * modifier_slots
    noun, rest = pieces[0], pieces[1:]
    if len(rest) > modifier_slots:
        rest = rest[:modifier_slots - 1] + [", ".join(rest[modifier_slots - 1:])]
    rest += [""] * (modifier_slots - len(rest))
    return noun, rest


def clean_token(text):
    """Letters and numbers only, upper case: ' cmd ' -> 'CMD'"""
    return re.sub(r"[^A-Za-z0-9]", "", text or "").upper()


def make_code(org, project):
    """'cmd', 'hello' -> 'CMD-HELLO'"""
    org, project = clean_token(org), clean_token(project)
    return "{}-{}".format(org, project) if (org and project) else ""


def clean_code(code):
    """Normalise a typed code: ' cmd-hello ' -> 'CMD-HELLO'"""
    parts = [clean_token(p) for p in (code or "").split("-")]
    return "-".join(p for p in parts if p)


def split_code(code):
    """'CMD-HELLO' -> ('CMD', 'HELLO')"""
    parts = clean_code(code).split("-", 1)
    return (parts[0], parts[1]) if len(parts) == 2 else (parts[0] if parts else "", "")


def make_project_name(code, title):
    """'CMD-HELLO', 'Hello Exhibit' -> 'CMD-HELLO - Hello Exhibit'"""
    return "{}{}{}".format(clean_code(code), PROJECT_NAME_SEPARATOR, (title or "").strip())


def parse_project_name(name):
    """'CMD-HELLO - Hello Exhibit' -> ('CMD-HELLO', 'Hello Exhibit').
    Names that don't follow the format -> ('', original name)."""
    m = re.match(r"^\s*([A-Za-z0-9]+-[A-Za-z0-9]+)\s+-\s+(.+?)\s*$", name or "")
    if not m:
        return "", (name or "").strip()
    return m.group(1).upper(), m.group(2)


def clean_prefix(prefix):
    """Kept for compatibility: same as clean_code."""
    return clean_code(prefix)


def format_part_number(prefix, number, digits=PART_NUMBER_DIGITS):
    return "{}-{:0{}d}".format(prefix, number, digits)


def parse_part_number(part_number, prefix):
    """'CMD-HELLO-014-LH' -> (14, 'LH');  'CMD-HELLO-014' -> (14, 'None').
    Also works on file names that start with a part number:
    'CMD-HELLO-014-LH BRACKET, MOTOR MOUNT, LH' -> (14, 'LH').
    Anything else -> (None, 'None')."""
    if not prefix:
        return None, "None"
    m = re.match(r"^{}-(\d+)(?:-(LH|RH))?(?=\s|$)".format(re.escape(prefix)),
                 (part_number or "").strip(), re.IGNORECASE)
    if not m:
        return None, "None"
    return int(m.group(1)), (m.group(2).upper() if m.group(2) else "None")


def matches_prefix(part_number, prefix):
    """Return the number if part_number looks like PREFIX-### (or PREFIX-###-LH/RH)."""
    return parse_part_number(part_number, prefix)[0]


def base_part_number(part_number, prefix):
    """'CHE-014-LH' -> 'CHE-014'"""
    num, _ = parse_part_number(part_number, prefix)
    return format_part_number(prefix, num) if num is not None else (part_number or "")


def full_part_number(base, hand):
    """'CHE-014', 'LH' -> 'CHE-014-LH'"""
    base = (base or "").strip().upper()
    return "{}-{}".format(base, hand) if (base and hand in OPPOSITE_HAND) else base


def unpaired_mates(prefix, existing_part_numbers, hand):
    """Handed parts still missing their opposite. If you're making an RH
    part, this lists LH parts whose RH doesn't exist yet: ['CHE-014', ...]"""
    if hand not in OPPOSITE_HAND:
        return []
    have = {}
    for pn in existing_part_numbers:
        num, h = parse_part_number(pn, prefix)
        if num is not None and h in OPPOSITE_HAND:
            have.setdefault(num, set()).add(h)
    other = OPPOSITE_HAND[hand]
    return [format_part_number(prefix, n) for n in sorted(have)
            if other in have[n] and hand not in have[n]]


def next_part_number(prefix, existing_part_numbers):
    """Look at every part number (or file name) already in the project and
    return the next free one for this code. Gaps are not reused, so deleted
    parts never get their number recycled. 000 is the top-level assembly."""
    used = [n for n in (matches_prefix(pn, prefix) for pn in existing_part_numbers)
            if n is not None]
    used.append(TOP_ASSEMBLY_NUMBER)
    return format_part_number(prefix, max(used) + 1)


def file_name(part_number, name):
    """'CMD-HELLO-015', 'BRACKET, MOTOR MOUNT, LH' ->
    'CMD-HELLO-015 BRACKET, MOTOR MOUNT, LH' (files sort by number)."""
    part_number, name = (part_number or "").strip(), (name or "").strip()
    return "{} {}".format(part_number, name).strip()


def strip_part_number(text, prefix):
    """'CMD-HELLO-015 BRACKET, MOTOR MOUNT' -> 'BRACKET, MOTOR MOUNT'"""
    m = re.match(r"^{}-\d+(?:-(?:LH|RH))?\s*".format(re.escape(prefix)),
                 (text or "").strip(), re.IGNORECASE) if prefix else None
    return (text or "").strip()[m.end():] if m else (text or "").strip()


def encode_settings(settings):
    """{'REF VIEW': 'VIEWED FROM VISITOR SIDE'} ->
    '[DMD] REF VIEW: VIEWED FROM VISITOR SIDE'"""
    pairs = ["{}: {}".format(k, v) for k, v in settings.items() if v]
    return "{} {}".format(SETTINGS_MARKER, " ; ".join(pairs)).strip()


def decode_settings(description):
    """Reverse of encode_settings. Text before the marker is ignored."""
    text = description or ""
    if SETTINGS_MARKER not in text:
        return {}
    text = text.split(SETTINGS_MARKER, 1)[1]
    out = {}
    for pair in text.split(" ; "):
        if ":" in pair:
            k, v = pair.split(":", 1)
            out[k.strip().upper()] = v.strip()
    return out


def is_shop_material(name):
    upper = (name or "").upper()
    return any(k in upper for k in SHOP_MATERIAL_KEYWORDS)


def is_user_library(library_name):
    """Autodesk's own libraries start with 'Fusion' (e.g. 'Fusion Material
    Library'). Anything else is one you made, so it counts as shop materials."""
    return not (library_name or "").strip().lower().startswith(("fusion", "autodesk"))


def filter_materials(entries, query, limit=80):
    """entries: list of (library_name, material_name).
    No query: your libraries first, then shop keyword matches.
    With a query: every material whose name contains all the typed words."""
    words = [w for w in (query or "").upper().split() if w]
    if words:
        hits = [e for e in entries if all(w in e[1].upper() for w in words)]
    else:
        mine = [e for e in entries if is_user_library(e[0])]
        shop = [e for e in entries if not is_user_library(e[0]) and is_shop_material(e[1])]
        hits = mine + sorted(shop, key=lambda e: e[1].upper())
    seen, out = set(), []
    for e in hits:
        if e[1] not in seen:
            seen.add(e[1])
            out.append(e)
    return out[:limit]


def _trim(value, places):
    text = "{:.{}f}".format(value, places)
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def format_dims(dims, units):
    """[24, 0.25, 12] in 'in' -> '24 x 12 x 0.25 in' (largest first)."""
    places = 1 if units == "mm" else 3 if units in ("in", "ft") else 2
    ordered = sorted((d for d in dims if d > 1e-9), reverse=True)
    if not ordered:
        return ""
    return " x ".join(_trim(d, places) for d in ordered) + " " + units


def format_mass(kg, imperial):
    if kg <= 0:
        return ""
    if imperial:
        lb = kg * 2.20462
        return _trim(lb, 2) + " lb" if lb >= 0.1 else _trim(lb * 16, 2) + " oz"
    return _trim(kg, 3) + " kg" if kg >= 1 else _trim(kg * 1000, 1) + " g"


def vendor_text(vendor_label, vendor_name, vendor_pn):
    """McMaster example -> 'DIST PN (McMaster-Carr): 91251A540'"""
    pn = (vendor_pn or "").strip()
    if not pn:
        return ""
    who = (vendor_name or "").strip() if vendor_label.startswith("Other") else vendor_label
    who = who or "unspecified"
    return "{} PN ({}): {}".format(vendor_role(vendor_label), who, pn)


def hand_text(hand, ref_view):
    """'LH', 'viewed from visitor side' -> 'LH PER REF VIEW: VIEWED FROM VISITOR SIDE'"""
    if hand not in OPPOSITE_HAND:
        return ""
    return "{} PER REF VIEW: {}".format(hand, (ref_view or "").strip() or "UNDEFINED")


def location_text(location, ref_view):
    """Where the part sits, always tied to the reference view."""
    location = (location or "").strip()
    if not location:
        return ""
    view = (ref_view or "").strip() or "UNDEFINED"
    return "LOC: {} (REF VIEW: {})".format(location, view)


def compose_description(sections, upper=True):
    """sections is a list of strings; empty ones are skipped.
    Vendor part numbers keep their original case, since some are case
    sensitive; everything else follows the ALL CAPS setting."""
    out = []
    for text, keep_case in sections:
        text = (text or "").strip()
        if not text:
            continue
        out.append(text if (keep_case or not upper) else text.upper())
    return DESC_SEPARATOR.join(out)


# ---------------------------------------------------------------------------
# Project parameters
# ---------------------------------------------------------------------------

# Each project keeps its shared parameters in one file in 00 ASSEMBLY:
# "CMD-HELLO PARAMETERS". It has no part number, so it never takes a number,
# and it is only ever derived (never inserted), so it never shows in a BOM.
PARAMS_FILE_WORD = "PARAMETERS"
PARAMS_FILE_DESCRIPTION = "DMD PROJECT PARAMETERS"

# Units offered in the dialog. "" = no units (a plain number or count).
PARAM_UNITS = ["in", "mm", "ft", "cm", "deg", ""]


def params_file_name(code):
    """'CMD-HELLO' -> 'CMD-HELLO PARAMETERS'"""
    return "{} {}".format(clean_code(code), PARAMS_FILE_WORD).strip()


def clean_param_name(text):
    """Names describe the role, lowercase with underscores:
    'Ply Thickness' -> 'ply_thickness'. A decimal point becomes 'p'
    ('slot .75' -> 'slot_0p75') because Fusion would read '.75' as a number.
    Names must start with a letter."""
    t = (text or "").strip().lower()
    t = re.sub(r"(?<![0-9])\.(?=[0-9])", "0p", t)      # .75  -> 0p75
    t = t.replace(".", "p")                             # 0.75 -> 0p75
    t = re.sub(r"[\s\-/]+", "_", t)
    t = re.sub(r"[^a-z0-9_]", "", t)
    t = re.sub(r"_+", "_", t).strip("_")
    if t and not t[0].isalpha():
        t = "p_" + t
    return t


def param_name_problem(name):
    """Reason a cleaned name won't work, or ''."""
    if not name:
        return "Enter a parameter name."
    if len(name) == 1:
        return "Use a longer name; single letters can clash with unit symbols in Fusion."
    return ""


def param_line(name, expression, comment=""):
    """One line of the parameter list shown in the dialog."""
    line = "{} = {}".format(name, expression)
    return line + ("   // " + comment if comment else "")
