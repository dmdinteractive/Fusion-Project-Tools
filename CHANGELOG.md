# Changelog

Versions match `"version"` in `DMDProjectTools/DMDProjectTools.manifest`.

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
