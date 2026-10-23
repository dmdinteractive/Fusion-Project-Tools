"""
word_lists.py - the words offered in the drop-downs.

Nothing in this file talks to Fusion, so it can be tested on its own.

Two sources, merged every time a dialog opens:
1. The built-in lists below (they come with each new version of the add-in).
2. Your own file, "My Word Lists.txt", kept OUTSIDE the add-in folder so
   updating the add-in never wipes it:
       Mac:     ~/DMD Project Tools/My Word Lists.txt
       Windows: C:\\Users\\<you>\\DMD Project Tools\\My Word Lists.txt
   The "Edit my word lists" button in the dialogs creates and opens it.

Modifiers are "smart per noun": pick PANEL and the modifier drop-downs
offer ACCESS, SIDE, GRAPHIC ...; pick SCREW and they offer SOCKET HEAD,
1/4-20, M4 ... Nouns without their own list get the general modifiers.
None of the built-in modifiers are position words (TOP, LEFT ...), since
the dialogs warn about those.
"""

import os
import re

USER_DIR_NAME = "DMD Project Tools"
USER_FILE_NAME = "My Word Lists.txt"

# ---------------------------------------------------------------------------
# Built-in lists
# ---------------------------------------------------------------------------

# Nouns for part files (and the Hybrid/McMaster dialogs).
PART_NOUNS = [
    # structure / sheet goods
    "ANGLE", "BACKER", "BASE", "BATTEN", "BEAM", "BLOCK", "BRACE", "BRACKET",
    "CHANNEL", "CLEAT", "COLUMN", "COUNTERTOP", "COVER", "CROSSMEMBER", "DIVIDER", "FACE", "FILLER",
    "FOOT", "FRAME", "GUSSET", "LEG", "LID", "PANEL", "PLATE", "POST", "RAIL",
    "RIB", "SHELF", "SKIN", "SPACER", "STILE", "STRIP", "STRUT",
    "TRIM", "TUBE",
    # doors, access, hardware you make or buy
    "BUMPER", "CASTER", "CATCH", "DOOR", "DRAWER", "GROMMET", "HANDLE",
    "HINGE", "KNOB", "LATCH", "LEVELER", "LOCK", "MAGNET", "PULL",
    # fasteners
    "ANCHOR", "BOLT", "INSERT", "NUT", "PIN", "RIVET", "SCREW", "STANDOFF",
    "WASHER",
    # visitor-facing
    "BEZEL", "BUTTON", "GRAPHIC", "LABEL", "LENS", "MIRROR", "SIGN",
    "WINDOW",
    # motion
    "BEARING", "BELT", "BUSHING", "COUPLER", "CRANK", "GEAR", "PULLEY",
    "SHAFT", "SPRING", "SPROCKET",
    # electronics
    "CABLE", "CONNECTOR", "DISPLAY", "ENCLOSURE", "FAN", "HANDSET",
    "HEATSINK", "LED", "MICROPHONE", "MOTOR", "PCB", "POWER SUPPLY",
    "RELAY", "SENSOR", "SPEAKER", "SWITCH",
]

# Nouns for assembly files ("ASSEMBLY" gets added after the noun).
ASSEMBLY_NOUNS = [
    "ARCH", "BASE", "BENCH", "BOX", "CABINET", "CART", "CASE", "CONSOLE",
    "CRATE", "DISPLAY", "DOOR", "DRAWER", "ELECTRONICS", "ENCLOSURE",
    "FRAME", "HEADER", "INTERACTIVE", "KIOSK", "LIGHT BOX", "MECHANISM",
    "MOUNT", "PANEL", "PEDESTAL", "PLATFORM", "PLINTH", "RAMP", "RISER",
    "SHELF", "SIGN", "STAND", "STATION", "TABLE", "TOWER", "VITRINE", "WALL",
]

# Offered for every noun, after the noun's own words.
GENERAL_MODIFIERS = [
    "ACCESS", "ADJUSTABLE", "BLANK", "CABLE PASS-THRU", "COVER", "DECORATIVE",
    "GRAPHIC", "HINGED", "MAIN", "MOTOR MOUNT", "MOUNTING", "REMOVABLE",
    "SERVICE", "SPARE", "STRUCTURAL", "SUPPORT", "TEMPLATE", "W/ CUTOUT",
]

# Noun -> its most likely modifiers, most common first.
MODIFIERS_BY_NOUN = {
    "PANEL": ["SIDE", "END", "BACKER", "ACCESS", "FACE", "GRAPHIC", "DIVIDER",
              "KICK", "FASCIA", "INFILL", "W/ CUTOUT", "VENTED", "REMOVABLE"],
    "BRACKET": ["MOTOR MOUNT", "L", "Z", "U", "CORNER", "SHELF", "WALL MOUNT",
                "SENSOR MOUNT", "SPEAKER MOUNT", "PCB MOUNT", "CABLE TIE",
                "STIFFENER", "HINGE"],
    "PLATE": ["BASE", "MOUNTING", "COVER", "ADAPTER", "BACKING", "WEAR",
              "MOTOR MOUNT", "BEARING", "FACE", "SWITCH", "BLANK", "NAME"],
    "FRAME": ["WELDED", "FACE", "DOOR", "BASE", "SUB", "PERIMETER", "SCREEN",
              "GRAPHIC", "LADDER"],
    "DOOR": ["ACCESS", "SERVICE", "CABINET", "HINGED", "SLIDING", "LIFT-OFF",
             "LOCKING", "GLAZED", "VENTED"],
    "SHELF": ["FIXED", "ADJUSTABLE", "EQUIPMENT", "DISPLAY", "PULL-OUT",
              "KEYBOARD"],
    "COVER": ["ACCESS", "DUST", "CABLE", "MOTOR", "PCB", "SWITCH", "VENT",
              "HINGED", "CLEAR"],
    "COUNTERTOP": ["CABINET", "REMOVABLE", "LIFT-OFF", "W/ CUTOUT"],
    "BASE": ["CABINET", "KIOSK", "WEIGHTED", "PLINTH", "LEVELING", "MOTOR"],
    "CLEAT": ["FRENCH", "WALL", "PANEL", "HANGING"],
    "RAIL": ["GUIDE", "SLIDE", "HAND", "MOUNTING", "DIN", "T-SLOT", "FACE"],
    "TRIM": ["EDGE", "CORNER", "J", "L", "REVEAL", "BASE", "CAP"],
    "SPACER": ["NYLON", "ALUMINUM", "PCB", "SHIM", "STANDOFF"],
    "TUBE": ["SQUARE", "ROUND", "RECTANGULAR", "ACRYLIC", "SLEEVE", "VIEWING"],
    "ANGLE": ["EQUAL LEG", "UNEQUAL LEG", "STIFFENER", "LEDGER"],
    "CHANNEL": ["U", "C", "J", "CABLE", "GUIDE", "WIREWAY"],
    "GRAPHIC": ["TITLE", "INSTRUCTION", "HEADER", "LABEL", "DONOR", "IDEA",
                "DIRECT PRINT", "VINYL", "DIBOND", "BACKLIT", "DUROTRAN"],
    "SIGN": ["TITLE", "INSTRUCTION", "DIRECTIONAL", "WARNING", "DONOR",
             "OUT OF ORDER"],
    "LABEL": ["BUTTON", "CONTROL", "SERIAL", "WARNING", "CABLE"],
    "WINDOW": ["VIEWING", "ACRYLIC", "POLYCARBONATE", "TEMPERED GLASS", "MAGNIFIER"],
    "LENS": ["MAGNIFIER", "FRESNEL", "DIFFUSER", "LIGHT PIPE"],
    "BEZEL": ["SCREEN", "MONITOR", "BUTTON", "SPEAKER", "WINDOW"],
    "BUTTON": ["ARCADE", "PUSH", "ILLUMINATED", "STOP", "START", "MOMENTARY",
               "LATCHING", "VANDAL"],
    "KNOB": ["CONTROL", "VOLUME", "SELECTOR", "CLAMPING", "KNURLED"],
    "HANDLE": ["PULL", "CRANK", "LIFT", "CARRY", "DOOR"],
    "HINGE": ["PIANO", "CONCEALED", "BUTT", "LIFT-OFF", "SPRING", "SOSS"],
    "LATCH": ["CAM", "DRAW", "COMPRESSION", "MAGNETIC", "PUSH"],
    "LOCK": ["CAM", "KEYED ALIKE", "TAMPER-PROOF"],
    "MAGNET": ["NEODYMIUM", "CUP", "CATCH", "DISC", "BLOCK", "COUNTERSUNK"],
    "CASTER": ["LOCKING", "SWIVEL", "RIGID", "LEVELING"],
    "SCREW": ["SOCKET HEAD", "BUTTON HEAD", "FLAT HEAD", "PAN HEAD", "WOOD",
              "SHEET METAL", "SECURITY", "PIN-IN-HEX", "#6", "#8", "#10-24",
              "#10-32", "1/4-20", "5/16-18", "3/8-16", "M3", "M4", "M5", "M6"],
    "BOLT": ["HEX", "CARRIAGE", "SHOULDER", "EYE", "U", "1/4-20", "3/8-16",
             "1/2-13", "M6", "M8", "M10"],
    "NUT": ["HEX", "NYLOC", "T-NUT", "TEE", "WING", "FLANGE", "PEM", "COUPLING",
            "#10-32", "1/4-20", "M4", "M6"],
    "WASHER": ["FLAT", "FENDER", "LOCK", "SPLIT LOCK", "NYLON", "SHIM"],
    "INSERT": ["THREADED", "HEAT-SET", "KNIFE-THRU", "1/4-20", "M4", "M6"],
    "STANDOFF": ["PCB", "HEX", "ROUND", "M3", "#4-40", "#6-32", "NYLON"],
    "ANCHOR": ["WALL", "FLOOR", "TOGGLE", "SLEEVE", "WEDGE"],
    "PIN": ["DOWEL", "CLEVIS", "COTTER", "HINGE", "LOCATING", "SPRING"],
    "SHAFT": ["DRIVE", "OUTPUT", "IDLER", "KEYED", "D-PROFILE", "HOLLOW"],
    "BEARING": ["BALL", "FLANGED", "PILLOW BLOCK", "THRUST", "LINEAR", "SLEEVE"],
    "PULLEY": ["TIMING", "IDLER", "DRIVE", "V-BELT", "GT2"],
    "GEAR": ["SPUR", "BEVEL", "WORM", "RACK", "DRIVE", "DRIVEN"],
    "SPRING": ["COMPRESSION", "EXTENSION", "TORSION", "GAS"],
    "MOTOR": ["STEPPER", "DC GEAR", "SERVO", "BRUSHLESS", "NEMA 17", "NEMA 23"],
    "CABLE": ["POWER", "USB", "ETHERNET", "AUDIO", "HDMI", "RIBBON", "SIGNAL",
              "SAFETY", "WIRE ROPE", "HARNESS"],
    "CONNECTOR": ["POWER", "BARREL", "JST", "MOLEX", "XLR", "PANEL MOUNT",
                  "TERMINAL BLOCK"],
    "ENCLOSURE": ["ELECTRONICS", "CONTROLLER", "POWER SUPPLY", "JUNCTION BOX",
                  "SPEAKER", "BATTERY", "VENTED"],
    "PCB": ["MAIN", "CONTROLLER", "BUTTON", "LED DRIVER", "BREAKOUT", "SENSOR",
            "AUDIO", "POWER"],
    "LED": ["STRIP", "BUTTON", "INDICATOR", "SPOT", "PANEL", "RGB", "TUNABLE WHITE"],
    "SPEAKER": ["FULL RANGE", "EXCITER", "HANDSET", "SUBWOOFER", "GRILLE"],
    "DISPLAY": ["MONITOR", "LCD", "TOUCHSCREEN", "E-INK", "LED MATRIX", "FLIP DOT"],
    "SENSOR": ["PROXIMITY", "IR", "ULTRASONIC", "LIMIT SWITCH", "HALL EFFECT",
               "RFID", "LOAD CELL"],
    "SWITCH": ["LIMIT", "TOGGLE", "ROCKER", "KEY", "HOOK", "REED", "MICRO"],
    "POWER SUPPLY": ["12V", "24V", "5V", "DIN RAIL", "ENCLOSED"],
    "FAN": ["COOLING", "EXHAUST", "INTAKE", "120MM", "80MM"],
    "HANDSET": ["PHONE", "ARMORED CORD", "CRADLE"],
    # assembly nouns
    "KIOSK": ["PHONE", "TOUCHSCREEN", "INTERACTIVE", "INFORMATION", "FREESTANDING"],
    "CABINET": ["BASE", "WALL", "ELECTRONICS", "STORAGE", "DISPLAY"],
    "CONSOLE": ["CONTROL", "OPERATOR", "BUTTON", "GAME"],
    "TABLE": ["ACTIVITY", "LIGHT", "SAND", "WATER", "BUILD", "WORK"],
    "WALL": ["FREESTANDING", "GRAPHIC", "ACTIVITY", "MAGNET", "PEG"],
    "PEDESTAL": ["DISPLAY", "VITRINE", "SPEAKER", "WEIGHTED"],
    "MECHANISM": ["DRIVE", "LIFT", "CRANK", "WINCH", "LINKAGE", "SPOOL"],
    "ELECTRONICS": ["CONTROL", "AUDIO", "LIGHTING", "POWER"],
    "STATION": ["ACTIVITY", "DOCUMENTATION", "LISTENING", "BUILD"],
}

# Reference views offered in the Reference view drop-down.
REFERENCE_VIEWS = [
    "VIEWED FROM VISITOR SIDE",
    "VIEWED FROM VISITOR SIDE, GRAPHIC FACE TOWARD YOU",
    "VIEWED FROM SERVICE SIDE",
    "VIEWED FROM ABOVE, VISITOR SIDE AT BOTTOM",
    "VIEWED FROM FRONT OF CABINET",
    "AS INSTALLED, FACING THE WALL",
    "AS MODELED, FUSION FRONT VIEW",
]


# ---------------------------------------------------------------------------
# Your own file
# ---------------------------------------------------------------------------

USER_FILE_TEMPLATE = """\
# DMD Project Tools - my word lists
#
# Words here are added to the drop-downs in Part Namer, New Part,
# McMaster to Part and New Project. Changes show up the next time
# you open one of those dialogs.
#
# One word or phrase per line. Lines starting with # are ignored.
# Case doesn't matter. Your words come before the built-in ones.

[NOUNS]
# Nouns for part files, e.g.
# DIFFUSER

[ASSEMBLY NOUNS]
# Nouns for assembly files ("ASSEMBLY" is added after them), e.g.
# PHONE BOOTH

[MODIFIERS]
# Offered for every noun, e.g.
# VISITOR-FACING

# Modifiers for one noun: add a section named after the noun.
[MODIFIERS: PANEL]
# PERFORATED

[REFERENCE VIEWS]
# e.g.
# VIEWED FROM ENTRANCE

[HIDE]
# Built-in words you never want to see, e.g.
# DUROTRAN
"""

_SECTION_RE = re.compile(r"^\[(.+)\]$")


def user_file_path(home=None):
    return os.path.join(home or os.path.expanduser("~"), USER_DIR_NAME, USER_FILE_NAME)


def parse_user_file(text_):
    """Text of My Word Lists.txt -> {'NOUNS': [...], 'MODIFIERS: PANEL': [...], ...}
    Section names and words come back upper case. Unknown sections are kept
    (harmless) so a typo never loses your words."""
    out = {}
    section = None
    for raw in (text_ or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _SECTION_RE.match(line)
        if m:
            section = re.sub(r"\s*:\s*", ": ", m.group(1).strip().upper())
            out.setdefault(section, [])
            continue
        if section:
            word = clean_word(line)
            if word and word not in out[section]:
                out[section].append(word)
    return out


def clean_word(word):
    """' motor  mount ' -> 'MOTOR MOUNT'. Commas are dropped: they separate
    the noun from its modifiers in a name."""
    return re.sub(r"\s+", " ", (word or "").replace(",", " ")).strip().upper()


def load_user_lists(path=None):
    """Read your file. Missing or unreadable -> empty lists (never an error)."""
    try:
        with open(path or user_file_path(), encoding="utf-8") as fh:
            return parse_user_file(fh.read())
    except Exception:
        return {}


def ensure_user_file(path=None):
    """Create your file from the template if it isn't there. Returns its path."""
    path = path or user_file_path()
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(USER_FILE_TEMPLATE)
    return path


# ---------------------------------------------------------------------------
# Merging
# ---------------------------------------------------------------------------

def _merge(*lists, hide=()):
    seen, out = set(hide), []
    for lst in lists:
        for w in lst:
            w = clean_word(w)
            if w and w not in seen:
                seen.add(w)
                out.append(w)
    return out


class WordLists:
    """Built-in lists plus yours, ready for the drop-downs."""

    def __init__(self, user=None):
        self.user = user if user is not None else {}
        self.hide = set(self.user.get("HIDE", []))

    @classmethod
    def load(cls, path=None):
        return cls(load_user_lists(path))

    def nouns(self, assembly=False):
        """Alphabetical, your nouns mixed in. Assembly files get the
        assembly nouns first, then part nouns (a PANEL ASSEMBLY is fine)."""
        if assembly:
            first = sorted(_merge(self.user.get("ASSEMBLY NOUNS", []), ASSEMBLY_NOUNS,
                                  hide=self.hide))
            rest = sorted(set(_merge(self.user.get("NOUNS", []), PART_NOUNS, hide=self.hide))
                          - set(first))
            return first + rest
        return sorted(_merge(self.user.get("NOUNS", []), PART_NOUNS, hide=self.hide))

    def modifiers(self, noun, exclude=()):
        """Modifiers for this noun, most specific first:
        yours for the noun, built-in for the noun, yours general, built-in general.
        Words in exclude (already used in another slot) are left out."""
        key = noun_key(noun)
        hide = self.hide | {clean_word(w) for w in exclude if w}
        return _merge(self.user.get("MODIFIERS: " + key, []) if key else [],
                      MODIFIERS_BY_NOUN.get(key, []),
                      self.user.get("MODIFIERS", []),
                      GENERAL_MODIFIERS,
                      hide=hide)

    def has_own_modifiers(self, noun):
        key = noun_key(noun)
        return bool(key) and (key in MODIFIERS_BY_NOUN
                              or bool(self.user.get("MODIFIERS: " + key)))

    def reference_views(self, current=""):
        """Yours first, then built-in. The project's current view is always
        included so the list never hides what's already set."""
        views = _merge(self.user.get("REFERENCE VIEWS", []), REFERENCE_VIEWS, hide=self.hide)
        cur = clean_word(current)
        if cur and cur not in views:
            views.insert(0, cur)
        return views


def noun_key(noun):
    """'kiosk assembly' -> 'KIOSK';  ' Panel ' -> 'PANEL'"""
    word = clean_word(noun)
    for ending in (" SUBASSEMBLY", " ASSEMBLY", " SUBASSY", " ASSY"):
        if word.endswith(ending):
            return word[:-len(ending)].strip()
    return word
