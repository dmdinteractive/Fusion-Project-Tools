"""
new_part.py - the New Part button.

Run it inside an assembly. It takes the next free part number for the
project, builds the file name (CMD-HELLO-015 BRACKET, MOTOR MOUNT, LH),
and creates a new linked part or subassembly in the matching folder:

    Fabricated  -> 02 FABRICATED
    Purchased   -> 03 PURCHASED
    Subassembly -> 01 SUBASSEMBLIES

The new file appears at the assembly origin, ready to Edit in Place.
Fusion only writes the new file when the assembly is saved, so the tool
saves the assembly for you (you can untick that).
"""

import adsk.core
import adsk.fusion

from ..lib import naming_logic as nl
from ..lib import fusion_data as fd
from ..lib import ui_helpers as uh
from ..lib import auto_params
from ..lib.ui_helpers import find, val, text

CMD_ID = "dmdNewPart"
CMD_NAME = "New Part"
TOOLTIP = "Create a numbered, linked part or subassembly in the right project folder."

PICK_PROMPT = "(pick to fill Noun)"
NEW_NUMBER = "(new number)"

_state = {}


def _design():
    return adsk.fusion.Design.cast(fd.app().activeProduct)


def _blocker(design):
    """Reason New Part can't run here, or '' if it can."""
    if not design:
        return "Open an assembly first."
    if not hasattr(design.rootComponent.occurrences, "addNewExternalComponent"):
        return "New Part needs a Fusion update from January 2026 or later."
    try:
        if design.designIntent == adsk.fusion.DesignIntentTypes.PartDesignIntentType:
            return ("This is a Part file. Run New Part from the assembly the new part "
                    "belongs in.")
    except Exception:
        pass
    doc = fd.app().activeDocument
    if not doc.isSaved:
        return "Save this assembly into the project first, then run New Part."
    return ""


class CreatedHandler(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        try:
            design = _design()
            reason = _blocker(design)
            if reason:
                fd.ui().messageBox(reason, CMD_NAME)
                args.command.isAutoExecute = True    # no dialog; nothing to run
                return
            doc = fd.app().activeDocument
            project = doc.dataFile.parentProject
            _state.clear()
            code = fd.get_design_setting(design, "code") or fd.project_code(project)
            # Read the project once now; the dialog reuses these on every keystroke.
            _state.update({"updating": False, "project": project,
                           "used": fd.used_part_numbers(project, design),
                           "refView": fd.reference_view(design, project, code)})

            cmd = args.command
            cmd.okButtonText = "Create"
            inputs = cmd.commandInputs

            inputs.addTextBoxCommandInput("where", "Project", project.name, 1, True)
            src = inputs.addRadioButtonGroupCommandInput("ptype", "Type")
            for i, t in enumerate(nl.PART_TYPES):
                src.listItems.add(t, i == 0)

            g = inputs.addGroupCommandInput("grpName", "Name (noun first)").children
            dd = g.addDropDownCommandInput("nounPick", "Common nouns",
                                           adsk.core.DropDownStyles.TextListDropDownStyle)
            dd.listItems.add(PICK_PROMPT, True)
            for noun in nl.COMMON_NOUNS:
                dd.listItems.add(noun, False)
            g.addStringValueInput("noun", "Noun", "")
            g.addStringValueInput("mod1", "Modifier 1", "")
            g.addStringValueInput("mod2", "Modifier 2", "")
            g.addStringValueInput("mod3", "Modifier 3", "")
            hd = g.addDropDownCommandInput("hand", "Hand (mirror parts)",
                                           adsk.core.DropDownStyles.TextListDropDownStyle)
            for i, h in enumerate(nl.HANDS):
                hd.listItems.add(h, i == 0)
            warn = g.addTextBoxCommandInput("posWarn", "Heads up", "", 3, True)
            warn.isVisible = False

            g = inputs.addGroupCommandInput("grpPN", "Part number").children
            g.addStringValueInput("code", "Project code", code)
            g.addStringValueInput("pn", "Base number", "")
            mate = g.addDropDownCommandInput("mate", "Mirror partner",
                                             adsk.core.DropDownStyles.TextListDropDownStyle)
            mate.listItems.add(NEW_NUMBER, True)
            mate.isVisible = False

            inputs.addTextBoxCommandInput("preview", "Will create", "", 2, True)
            inputs.addBoolValueInput("save", "Save assembly now (writes the new file)",
                                     True, "", True)
            inputs.addTextBoxCommandInput("status", "", "", 2, True)

            uh.connect(cmd, ((ActivateHandler(), cmd.activate),
                             (InputChangedHandler(), cmd.inputChanged),
                             (ValidateHandler(), cmd.validateInputs),
                             (ExecuteHandler(), cmd.execute)))
        except Exception:
            uh.show_error("New Part")


class ActivateHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        inputs = args.command.commandInputs
        _state["updating"] = True
        try:
            find(inputs, "pn").value = _suggest_pn(inputs)
        finally:
            _state["updating"] = False
        _refresh(inputs)


class InputChangedHandler(adsk.core.InputChangedEventHandler):
    def notify(self, args):
        if _state.get("updating"):
            return
        try:
            changed = args.input
            inputs = uh.all_inputs(args)
            _state["updating"] = True
            if changed.id == "nounPick":
                item = changed.selectedItem
                if item and item.name != PICK_PROMPT:
                    find(inputs, "noun").value = item.name
                    changed.listItems.item(0).isSelected = True
            elif changed.id in ("code", "hand"):
                _rebuild_mates(inputs)
                find(inputs, "pn").value = _suggest_pn(inputs)
            elif changed.id == "mate":
                choice = val(inputs, "mate")
                find(inputs, "pn").value = _suggest_pn(inputs) if choice == NEW_NUMBER else choice
            _refresh(inputs)
        except Exception:
            uh.show_error("New Part")
        finally:
            _state["updating"] = False


class ValidateHandler(adsk.core.ValidateInputsEventHandler):
    def notify(self, args):
        try:
            args.areInputsValid = not _problems(uh.all_inputs(args))
        except Exception:
            args.areInputsValid = False


class ExecuteHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        try:
            inputs = args.command.commandInputs
            job = {
                "doc": fd.app().activeDocument,
                "project": _state["project"],
                "folder": nl.FOLDER_FOR_TYPE[val(inputs, "ptype")],
                "fname": _file_name(inputs),
                "pn": _full_pn(inputs),
                "desc": nl.compose_description(
                    [(nl.hand_text(val(inputs, "hand"), _state["refView"]), False)]),
                "save": bool(val(inputs, "save")),
                "code": _code(inputs),
            }
            uh.run_later("Creating the new part", lambda: _create(job))
        except Exception:
            uh.show_error("New Part")


def _create(job):
    doc = job["doc"]
    doc.activate()
    design = adsk.fusion.Design.cast(doc.products.itemByProductType("DesignProductType"))
    fd.ensure_folders(job["project"])
    folder = fd.top_folder(job["project"], job["folder"])

    occ = design.rootComponent.occurrences.addNewExternalComponent(
        job["fname"], folder, adsk.core.Matrix3D.create())
    if occ is None:
        fd.ui().messageBox("Fusion couldn't create the new part.", CMD_NAME)
        return
    comp = occ.component
    try:
        comp.partNumber = job["pn"]
        if job["desc"]:
            comp.description = job["desc"]
        fd.set_design_setting(design, "code", job["code"])
    except Exception:
        pass   # the name already carries the number; Part Namer can fill the rest

    if job["save"]:
        doc.save("Added " + job["fname"])
        fd.note_new_file(job["project"], job["fname"])
        params_note = ""
        if job["folder"] in auto_params.AUTO_LINK_FOLDERS and auto_params.expect_new_part(
                job["fname"], job["project"], job["code"], doc):
            params_note = ("\n\nIt will be linked to the project parameters as soon as Fusion "
                           "finishes uploading it (a few seconds).")
        fd.ui().messageBox(
            "Created {}\nin {}.\n\nRight-click it > Edit in Place to model it, then open it "
            "and run Part Namer to add material and description.{}".format(
                job["fname"], job["folder"], params_note),
            CMD_NAME)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _code(inputs):
    return nl.clean_code(text(inputs, "code"))


def _name(inputs):
    mods = [val(inputs, "mod1"), val(inputs, "mod2"), val(inputs, "mod3")]
    noun = val(inputs, "noun")
    if val(inputs, "ptype") == "Subassembly":
        noun = nl.assembly_noun(noun)          # KIOSK -> KIOSK ASSEMBLY
    return nl.compose_name(noun, mods, True, val(inputs, "hand"))


def _full_pn(inputs):
    return nl.full_part_number(val(inputs, "pn"), val(inputs, "hand"))


def _file_name(inputs):
    return nl.file_name(_full_pn(inputs), _name(inputs))


def _suggest_pn(inputs):
    code = _code(inputs)
    return nl.next_part_number(code, _state["used"]) if code else ""


def _rebuild_mates(inputs):
    mate = find(inputs, "mate")
    options = nl.unpaired_mates(_code(inputs), _state["used"], val(inputs, "hand"))
    mate.listItems.clear()
    mate.listItems.add(NEW_NUMBER, True)
    for base in options:
        mate.listItems.add(base, False)
    mate.isVisible = bool(options)


def _problems(inputs):
    issues = []
    code = _code(inputs)
    pn = _full_pn(inputs)
    if not text(inputs, "noun"):
        issues.append("Enter a noun.")
    if not code:
        issues.append("Enter the project code (e.g. CMD-HELLO).")
    elif nl.matches_prefix(pn, code) is None:
        issues.append("Part number should look like {}-001.".format(code))
    else:
        num, hand = nl.parse_part_number(pn, code)
        if any(nl.parse_part_number(u, code) == (num, hand) for u in _state["used"]):
            issues.append("{} is already used in this project.".format(pn))
    if val(inputs, "hand") in nl.OPPOSITE_HAND and not _state["refView"]:
        issues.append("No reference view set for this project (New Project > Set up "
                      "current project). LH/RH needs one.")
    return issues


def _refresh(inputs):
    mods = " ".join(val(inputs, k) or "" for k in ("noun", "mod1", "mod2", "mod3"))
    warning = nl.position_warning(mods)
    find(inputs, "posWarn").text = warning
    find(inputs, "posWarn").isVisible = bool(warning)
    find(inputs, "preview").text = "{}\nin {}".format(
        _file_name(inputs), nl.FOLDER_FOR_TYPE[val(inputs, "ptype")])
    find(inputs, "status").text = "  ".join(_problems(inputs))
