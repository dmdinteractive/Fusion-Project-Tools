# Fusion Project Tools

An Autodesk Fusion add-in that keeps every project organized the same way. It was written for
exhibit design and fabrication at DMD Interactive, and it works for any Fusion project built
from separate part and assembly files.

| Button | Use it in | What it does |
|---|---|---|
| **New Project** | Anywhere | Creates `CMD-HELLO - Hello Exhibit` with the standard folders and an empty top-level Assembly `CMD-HELLO-000 HELLO EXHIBIT`. Can also bring an existing project up to standard. |
| **New Part** | An assembly | Creates the next numbered linked part (or subassembly) in the right folder, e.g. `CMD-HELLO-015 BRACKET, MOTOR MOUNT, LH` in `02 FABRICATED`. |
| **Project Parameters** | A part file | Shared dimensions (`ply_thickness`, `exhibit_width`...) that every linked part follows. |
| **Part Namer** | A part or assembly file | Sets name, part number, BOM description (and material for parts). Renames and files it to match. |

Requires a current Fusion (January 2026 or later). Tested on Mac.
See [CHANGELOG.md](CHANGELOG.md) for what changed in each version.

## Download

- **Latest release:** the Releases page on the right has a ready-to-install `DMDProjectTools.zip`.
- **Or** click **Code > Download ZIP** and use the `DMDProjectTools` folder inside.

## Project layout

```
CMD-HELLO - Hello Exhibit            <- org code, project code, name
  00 ASSEMBLY        CMD-HELLO-000 HELLO EXHIBIT   (top level; holds the reference view)
                     CMD-HELLO PARAMETERS          (shared dimensions; never in the BOM)
  01 SUBASSEMBLIES   CMD-HELLO-0xx ...
  02 FABRICATED      CMD-HELLO-0xx ...
  03 PURCHASED       CMD-HELLO-0xx ...             (vendor # in the description)
  04 DRAWINGS        (your drawings)
  99 ARCHIVE
```

- Part numbers are `ORG-PROJECT-###`, so they never collide between projects.
- Mirror pairs share a number: `CMD-HELLO-015-LH` and `CMD-HELLO-015-RH`.
- File names start with the part number so folders sort in order. The tool finds the
  next free number by reading file names, so keep that prefix when renaming by hand.
- The project's **reference view** (how LH/RH and locations are judged) is saved in the
  top-level assembly's description in the Data Panel: `[DMD] REF VIEW: ...`.
  You can add your own notes before `[DMD]`. Leave the `[DMD]` part alone.

## Install (Mac)

1. **If you used the old Part Namer, remove it first:** Utilities > ADD-INS > Scripts and Add-Ins (Shift+S),
   select PartNamer, click **Stop**, then remove it from the list. Delete its folder.
2. Unzip. Put the `DMDProjectTools` folder (keep that exact name) somewhere permanent, for example
   `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/`
   (Finder > Cmd+Shift+G and paste the path).
3. In Scripts and Add-Ins: **+** > "Script or add-in from device" > pick the folder,
   then **Run**. Tick **Run on Startup**.
4. Four icons appear on Utilities > ADD-INS: a folder (New Project), a cube (New Part),
   a tag (Part Namer) and a ruler (Project Parameters).

Needs a current Fusion. New Part uses a January 2026 API.

## Everyday workflow

1. **New Project** > "Create a new project". Enter organization (`CMD`), project code
   (`HELLO`), name (`Hello Exhibit`), and the reference view. Click Create.
2. Open `00 ASSEMBLY / CMD-HELLO-000 ...`.
3. **New Part** for each part: pick Fabricated / Purchased / Subassembly, type the name,
   and click Create. The assembly is saved so the new file exists. Then right-click the
   part > **Edit in Place** to model it.
4. Open a part file and run **Part Namer** to set its material, description and vendor
   number. Click Apply. If you switch the part between Fabricated and Purchased, it moves
   folders to match.
5. Open a subassembly file and run **Part Namer** the same way (see Assemblies below).
6. Started a part on its own instead (File > New, Part)? Run **Part Namer** before saving.
   It saves the part into the project's matching folder with the right name and number.

**Existing project?** Open anything in it and run New Project > "Set up the current project".
It adds missing folders, can rename the project to the standard format, and stores the
reference view. It never moves or changes your existing files.

## Assemblies

Part Namer changes to fit an assembly file:

- **Name:** the noun gets ASSEMBLY after it, then the modifiers: `KIOSK ASSEMBLY, PHONE`.
  (Untick "Add ASSEMBLY after the noun" if you don't want it.) New Part names new
  subassemblies the same way.
- **Type:** Subassembly (goes in `01 SUBASSEMBLIES`) or Purchased (`03 PURCHASED`, for
  bought kits you modeled as an assembly).
- **Description:** no material picker. Instead it can include the part count of this level,
  e.g. `8 PARTS, 2 SUBASSEMBLIES`, counting each instance (four of the same bracket = 4
  PARTS). The count is editable before you apply. Overall size, total mass and location are
  also available as tick boxes.
- **Top-level assembly** (the `-000` file, or anything in `00 ASSEMBLY`): the number is
  locked at 000 and it stays in `00 ASSEMBLY`, because the tools find the project's
  reference view through that file. Its name is the exhibit name, without ASSEMBLY added.
  Its `[DMD]` description in the Data Panel is never changed by Part Namer.

## Shared parameters

Project Parameters uses Fusion's own way of sharing dimensions between separate part
files: one master file holds them as *favorites*, and each part *Derives* them.

**Adding or changing one:** open any file in the project, click Project Parameters, type a
name and value, and click Apply. The tool opens `CMD-HELLO PARAMETERS` in the background
(it creates it the first time), saves the change, and closes it again.

- **Names describe the role:** `ply_thickness`, `exhibit_width`, `kerf`. Whatever you type
  is cleaned to that style (`Ply Thickness` becomes `ply_thickness`). A decimal point
  becomes `p` (`.75` becomes `0p75`), because Fusion would read `.75` as a number.
- **Values:** a plain number gets the chosen units (`0.75` with "in" is saved as
  `0.75 in`). Expressions work too: `exhibit_width / 2`. Pick "(no units)" for counts.
- To change one, pick it from the **Parameter** list, edit the value, and Apply.

**Using them in a part: nothing to set up.** Once a project has a parameters file, the
add-in handles parts in the background:

- **Opening a fabricated part** (in `02 FABRICATED`) that isn't linked yet links it.
- **New Part** links each new fabricated part a few seconds after creating it, so the
  parameters are there when you Edit in Place.
- **Every project parameter is starred for you** whenever you open or switch to a part
  and after every Update, including parameters added to the project later. Just type
  `ply_thickness` into any dimension.

Purchased parts (`03 PURCHASED`) aren't linked automatically, since bought parts don't
use your dimensions. You can still link one with the Project Parameters button. Each
automatic step is logged in View > Show Text Commands (`DMD Tools: starred 2 project
parameter(s) in ...`).

**When a value changes:** linked parts show as *out of date*. Open the part and click
Update (the out-of-date icon in the top bar) and its geometry resizes. The tool never
updates part geometry by itself.

**Good to know:**
- Assembly files can't hold features, so link the **parts**, not the assemblies.
- Changing any one parameter marks *every* linked part out of date, even ones that don't
  use it. That's how Fusion's Derive works.
- Every parameter in the master file is kept as a favorite. Un-favoriting one would break
  its link in every part without any warning, so the tool re-favorites anything it finds
  un-favorited.
- The tool doesn't delete parameters, since parts may be using them. To remove one,
  open `CMD-HELLO PARAMETERS` and use Modify > Change Parameters.
- Starring a parameter counts as a change to the part, so Fusion may show the part as
  modified after it's opened. Save as usual.
- Settings for the automatic behavior are at the top of `DMDProjectTools/lib/auto_params.py`:
  `AUTO_LINK` (turn automatic linking off) and `AUTO_LINK_FOLDERS` (which folders
  are linked).
- The list in the dialog is the last one the tool saw. If you edit the parameters file
  by hand, the list catches up after the next Apply, or run the button inside that file.

## Materials

The **Material** list in Part Namer shows, with no search typed:

1. Every material in any library **you** made (anything not named "Fusion ..."), then
2. Fusion materials whose names contain PLYWOOD, ALUMINUM, STEEL or STAINLESS.

Type in **Search** to find any other material. The material is applied to the whole part
(the component and every body), so the BOM's Material column is correct.

For shop materials Fusion doesn't have (Baltic birch, Sintra, Dibond...), make your own
library once: Design workspace > Modify > Manage Materials > create a library such as
"DMD Shop Materials" and add materials to it. Restart Fusion, and they appear at the top of
the list. (The API can read and assign materials but can't create them, so this step is
manual.)

## Speed

Every folder and file the tools look at is a request to Autodesk's cloud, so v2.2 keeps
those to a minimum:

- **The project is read once and shared.** The first dialog you open reads the project's
  file names (skipping `04 DRAWINGS`). Every dialog in the next 5 minutes reuses that
  snapshot. Files the tools create or rename are added to it directly.
- **Materials are cached on disk.** The first time ever, Part Namer reads Fusion's whole
  material library and saves the list in `cache/materials.json` inside the add-in folder.
  Later sessions read that file instead. It's rebuilt automatically when Fusion updates.
  Your own libraries are always read fresh, so new materials show up right away.
- **New Project** reads your hub's project list only once you've typed a full name.

**Measuring it:** View > Show Text Commands. Each dialog writes lines like
`DMD Tools: reading project 'CMD-HELLO - Hello Exhibit' 1.84 s` and
`DMD Tools: Part Namer ready 0.21 s`. If something is still slow, those numbers show where.

**One trade-off:** a part number you type into a file name *by hand* (outside the tools) can
take up to 5 minutes to be noticed by the next-number suggestion. Change
`SNAPSHOT_SECONDS` in `DMDProjectTools/lib/fusion_data.py` to adjust this.

## Changing the conventions

Everything is in `DMDProjectTools/lib/naming_logic.py`:

- `FOLDERS`, `FOLDER_FOR_TYPE`: folder names and which type goes where
- `PART_NUMBER_DIGITS`: 3 gives `-001`, 4 gives `-0001`
- `SHOP_MATERIAL_KEYWORDS`: which Fusion materials show without searching
- `POSITION_WORDS`: words that trigger the "Heads up" warning
- `COMMON_NOUNS`, `VENDORS`: drop-down lists

## Files

- `DMDProjectTools.py`: adds and removes the three buttons
- `commands/new_project.py`, `commands/new_part.py`, `commands/part_namer.py`: one per button
- `DMDProjectTools/lib/naming_logic.py`: the naming rules (no Fusion code, safe to edit)
- `DMDProjectTools/lib/auto_params.py`: links parts and stars project parameters in the background
- `DMDProjectTools/lib/fusion_data.py`: finds projects, folders, files, part numbers and materials in Fusion
- `lib/ui_helpers.py`: shared dialog plumbing. It also runs file work after a dialog closes,
  because Fusion won't save, create or rename files while a dialog is open.

## License

MIT, see [LICENSE](LICENSE). Free to use, change and share; keep the copyright notice.
