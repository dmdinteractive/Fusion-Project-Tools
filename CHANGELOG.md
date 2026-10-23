# Changelog

Versions match `"version"` in `DMDProjectTools/DMDProjectTools.manifest`.

## 2.6.0
- **Smarter drop-downs** in Part Namer, New Part and McMaster to Part:
  - Each Modifier box has a **Suggestions** drop-down above it that follows the noun
    (PANEL offers SIDE, ACCESS, GRAPHIC ...; SCREW offers SOCKET HEAD, 1/4-20, M4 ...).
    Words already used in another modifier box are left out. You can still type anything.
  - Bigger noun list (about 90 part nouns). Assembly files get assembly nouns first
    (KIOSK, CABINET, PEDESTAL ...).
  - **Reference view** drop-down in Part Namer and New Project.
- **Your own word lists:** the "Edit my word lists" button opens `My Word Lists.txt`
  (in a `DMD Project Tools` folder in your home folder, so add-in updates never touch it).
  Add nouns, modifiers for any noun, reference views, or hide built-in words.
- Descriptions with both a hand and a location show the reference view once:
  `LH, LOC: NEAR PHONE (PER REF VIEW: VIEWED FROM VISITOR SIDE)`.

## 2.5.0
- New **McMaster to Part** button: turns a McMaster-Carr part inserted into a Hybrid
  assembly into its own numbered part file in `03 PURCHASED` (McMaster number in the
  description) and replaces every copy with the linked file in the same position.
  Reuses the existing file when the same McMaster number is already in the project.
- Internal: one shared "when this upload finishes" helper, used by New Part's automatic
  parameter linking and by McMaster to Part.

## 2.4.1
- Windows: install steps added to the README (the same download runs on Mac and Windows).
- Cache files are always read and written as UTF-8, so material names with accents or
  symbols behave the same on Windows as on Mac.

## 2.4.0
- Project parameters are linked and starred in every part automatically: on opening a
  fabricated part, after every Update, and for new parts made with New Part.
- Settings for this in `lib/auto_params.py` (`AUTO_LINK`, `AUTO_LINK_FOLDERS`).

## 2.3.0
- New **Project Parameters** button: shared dimensions (`ply_thickness`, `exhibit_width`)
  kept in a per-project `CODE PARAMETERS` file and derived into parts.

## 2.2.0
- Dialogs open faster: the project is read once and shared for 5 minutes, `04 DRAWINGS`
  is skipped, and the material list is cached on disk.
- Timing lines in View > Show Text Commands (`DMD Tools: ...`).
- Fixed: a part New Part had just created could flag its own number as already used.

## 2.1.0
- Part Namer names assembly files: `KIOSK ASSEMBLY, PHONE`, Subassembly/Purchased types,
  part count in the description.
- Top-level assembly locked at `-000` and kept in `00 ASSEMBLY`.

## 2.0.0
- Became **DMD Project Tools**, replacing the single Part Namer add-in.
- New **New Project** (standard folders, top-level assembly, reference view) and
  **New Part** (next numbered linked part in the right folder).
- Part numbers `ORG-PROJECT-###`; file names start with the part number.
- Part Namer works on Fusion's Part design type and assigns materials.

## 1.1.x (Part Namer)
- 1.1.1: fixed a crash when changing fields in different dialog sections.
- 1.1.0: position-word warnings, LH/RH tied to a reference view, location notes.

## 1.0.0 (Part Namer)
- Noun-first names, per-project part numbers, opt-in BOM descriptions, vendor part numbers.
