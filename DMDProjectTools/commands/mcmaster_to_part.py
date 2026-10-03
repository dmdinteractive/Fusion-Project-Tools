"""
mcmaster_to_part.py - the McMaster to Part button.

Fusion only allows "Insert McMaster-Carr Component" in Hybrid (and Assembly)
files, and it puts the part INSIDE that file. This button turns it into its
own Part file, like every other purchased part:

  1. Select the McMaster part you just inserted.
  2. Type its noun-first name (SCREW, SOCKET HEAD CAP, 1/4-20 x 1).
  3. Click Convert. The tool saves it as
        CMD-HELLO-008 SCREW, SOCKET HEAD CAP, 1/4-20 x 1   in 03 PURCHASED
     with "DIST PN (McMaster-Carr): 91251A540" as its description, then
     replaces every copy in this assembly with the linked file, in the
     same positions.

If that McMaster number already has a file in the project, that file is
reused instead of making a duplicate.

Run it right after inserting: joints attached to the embedded copy can't be
carried over to the linked file (a Fusion limitation).
"""

import adsk.core
import adsk.fusion

from ..lib import naming_logic as nl
from ..lib import fusion_data as fd
from ..lib import ui_helpers as uh
from ..lib.ui_helpers import find, val, text

CMD_ID = "dmdMcMasterToPart"
CMD_NAME = "McMaster to Part"
TOOLTIP = "Turn an inserted McMaster-Carr part into its own numbered part file in 03 PURCHASED."

PICK_PROMPT = "(pick to fill Noun)"
PURCHASED = "Purchased"

_state = {}


def _design():
    return adsk.fusion.Design.cast(fd.app().activeProduct)


class CreatedHandler(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        try:
            design = _design()
            doc = fd.app().activeDocument
            if not design or not doc.isSaved:
                fd.ui().messageBox("Save this assembly into its project first.", CMD_NAME)
                args.command.isAutoExecute = True
                return
            project = doc.dataFile.parentProject
            code = fd.get_design_setting(design, "code") or fd.project_code(project)
            _state.clear()
            _state.update({"updating": False, "project": project, "doc": doc,
                           "occ": None, "occs": [], "existing": None, "joints": 0,
                           "used": fd.used_part_numbers(project, design),
                           "purchased": None})

            cmd = args.command
            cmd.okButtonText = "Convert"
            inputs = cmd.commandInputs

            sel = inputs.addSelectionInput("sel", "McMaster part", "Pick the inserted McMaster part")
            sel.addSelectionFilter("Occurrences")
            sel.setSelectionLimits(1, 1)
            inputs.addStringValueInput("mcPn", "McMaster number", "")
            inputs.addTextBoxCommandInput("found", "", "", 2, True)

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

            g = inputs.addGroupCommandInput("grpPN", "Part number").children
            g.addStringValueInput("code", "Project code", code)
            g.addStringValueInput("pn", "Number", "")

            inputs.addTextBoxCommandInput("preview", "Will create", "", 3, True)
            inputs.addTextBoxCommandInput("status", "", "", 3, True)

            uh.connect(cmd, ((ActivateHandler(), cmd.activate),
                             (InputChangedHandler(), cmd.inputChanged),
                             (ValidateHandler(), cmd.validateInputs),
                             (ExecuteHandler(), cmd.execute)))
        except Exception:
            uh.show_error(CMD_NAME)


class ActivateHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        inputs = args.command.commandInputs
        try:
            _state["updating"] = True
            find(inputs, "pn").value = _suggest_pn(inputs)
            if find(inputs, "sel").selectionCount:
                _load_selection(inputs)
        except Exception:
            uh.show_error(CMD_NAME)
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
            if changed.id == "sel":
                _load_selection(inputs)
            elif changed.id == "mcPn":
                _find_existing(inputs)
            elif changed.id == "code":
                find(inputs, "pn").value = _suggest_pn(inputs)
            elif changed.id == "nounPick":
                item = changed.selectedItem
                if item and item.name != PICK_PROMPT:
                    find(inputs, "noun").value = item.name
                    changed.listItems.item(0).isSelected = True
            _refresh(inputs)
        except Exception:
            uh.show_error(CMD_NAME)
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
            mc = nl.find_mcmaster_number(text(inputs, "mcPn"))
            occ = _state["occ"]
            comp = occ.component
            # Remember where every copy is now; the swap happens after saving.
            copies = [(_parent_component(o), _local_transform(o)) for o in _state["occs"]]
            job = {"doc": _state["doc"], "project": _state["project"], "comp": comp,
                   "copies": copies, "occs": list(_state["occs"]), "mc": mc,
                   "existing": _state["existing"]}
            if job["existing"] is None:
                name = _name(inputs)
                pn = nl.full_part_number(text(inputs, "pn"), "None")
                job["fname"] = nl.file_name(pn, name)
                # These travel with the component into its new file.
                comp.partNumber = pn
                comp.description = nl.compose_description([(nl.mcmaster_tag(mc), True)])
            uh.run_later("Saving the McMaster part", lambda: _save(job))
        except Exception:
            uh.show_error(CMD_NAME)


# ---------------------------------------------------------------------------
# The work (after the dialog closes)
# ---------------------------------------------------------------------------

def _save(job):
    if job["existing"] is not None:
        _swap(job, job["existing"])
        return
    project = job["project"]
    fd.ensure_folders(project)
    folder = fd.top_folder(project, nl.FOLDER_FOR_TYPE[PURCHASED])
    future = job["comp"].saveCopyAs(job["fname"], folder, nl.mcmaster_tag(job["mc"]), "")
    if future is None:
        fd.ui().messageBox("Fusion couldn't save the part as its own file.", CMD_NAME)
        return
    fd.note_new_file(project, job["fname"])
    ready = None
    try:
        ready = future.dataFile          # sometimes available straight away
    except Exception:
        pass
    if ready is not None:
        _swap(job, ready)
    else:
        uh.on_upload(job["fname"], "Swapping in " + job["fname"], lambda f: _swap(job, f))
        fd.log("waiting for {} to finish uploading".format(job["fname"]))


def _swap(job, data_file):
    """Replace every embedded copy with the linked file, same positions."""
    doc = job["doc"]
    doc.activate()
    done, skipped = 0, 0
    for (parent, transform), occ in zip(job["copies"], job["occs"]):
        try:
            new = parent.occurrences.addByInsert(data_file, transform, True)
            if new is None:
                skipped += 1
                continue
            occ.deleteMe()
            done += 1
        except Exception:
            skipped += 1
    lines = ["{}\nis in {}.".format(data_file.name, nl.FOLDER_FOR_TYPE[PURCHASED]),
             "Replaced {} cop{} in this assembly.".format(done, "y" if done == 1 else "ies")]
    if skipped:
        lines.append("{} cop{} couldn't be replaced (inside a linked subassembly?). Replace "
                     "them by hand: right-click > Replace Component.".format(
                         skipped, "y" if skipped == 1 else "ies"))
    lines.append("Save the assembly to keep the change.")
    fd.ui().messageBox("\n\n".join(lines), CMD_NAME)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _code(inputs):
    return nl.clean_code(text(inputs, "code"))


def _name(inputs):
    mods = [val(inputs, "mod1"), val(inputs, "mod2"), val(inputs, "mod3")]
    return nl.compose_name(val(inputs, "noun"), mods, True)


def _suggest_pn(inputs):
    code = _code(inputs)
    return nl.next_part_number(code, _state["used"]) if code else ""


def _parent_component(occ):
    ctx = occ.assemblyContext
    return ctx.component if ctx else _design().rootComponent


def _local_transform(occ):
    native = occ.nativeObject or occ
    return native.transform2


def _load_selection(inputs):
    sel = find(inputs, "sel")
    occ = adsk.fusion.Occurrence.cast(sel.selection(0).entity) if sel.selectionCount else None
    _state["occ"] = occ
    _state["occs"] = []
    _state["joints"] = 0
    if occ is None or occ.isReferencedComponent:
        return
    comp = occ.component
    root = _design().rootComponent
    _state["occs"] = list(fd.as_list(root.allOccurrencesByComponent(comp)))
    occ_set = _state["occs"]
    for j in fd.as_list(root.allJoints) + fd.as_list(root.allAsBuiltJoints):
        try:
            if j.occurrenceOne in occ_set or j.occurrenceTwo in occ_set:
                _state["joints"] += 1
        except Exception:
            pass
    find(inputs, "mcPn").value = nl.find_mcmaster_number(comp.name)
    _find_existing(inputs)


def _purchased_files():
    """Files in 03 PURCHASED with their descriptions, read once per dialog."""
    if _state["purchased"] is None:
        folder = fd.top_folder(_state["project"], nl.FOLDER_FOR_TYPE[PURCHASED])
        with fd.timed("reading 03 PURCHASED descriptions"):
            _state["purchased"] = [(f, f.description or "")
                                   for f in (fd.iter_files(folder) if folder else [])]
    return _state["purchased"]


def _find_existing(inputs):
    mc = nl.find_mcmaster_number(text(inputs, "mcPn"))
    _state["existing"] = None
    if not mc:
        return
    tag = nl.mcmaster_tag(mc)
    for f, desc in _purchased_files():
        if tag in desc:
            _state["existing"] = f
            return


def _problems(inputs):
    occ = _state["occ"]
    if occ is None:
        return ["Select the McMaster part you inserted."]
    if occ.isReferencedComponent:
        return ["That part is already its own file."]
    issues = []
    if not nl.find_mcmaster_number(text(inputs, "mcPn")):
        issues.append("Enter the McMaster number (e.g. 91251A540).")
    if _state["existing"] is None:
        code = _code(inputs)
        pn = text(inputs, "pn").upper()
        if not text(inputs, "noun"):
            issues.append("Enter a noun.")
        if not code:
            issues.append("Enter the project code (e.g. CMD-HELLO).")
        elif nl.matches_prefix(pn, code) in (None, nl.TOP_ASSEMBLY_NUMBER):
            issues.append("Number should look like {}-001.".format(code))
        elif any(nl.parse_part_number(u, code) == nl.parse_part_number(pn, code)
                 for u in _state["used"]):
            issues.append("{} is already used in this project.".format(pn))
    return issues


def _refresh(inputs):
    existing = _state["existing"]
    for key in ("grpName", "grpPN"):
        find(inputs, key).isVisible = existing is None
    n = len(_state["occs"])
    copies = "Replaces {} cop{} in this assembly.".format(n, "y" if n == 1 else "ies") if n else ""
    if existing is not None:
        find(inputs, "found").text = "Already in this project, so it will be reused."
        preview = "{}\n{}".format(existing.name, copies)
    else:
        find(inputs, "found").text = ""
        fname = nl.file_name(text(inputs, "pn").upper(), _name(inputs))
        preview = "{}\nin {}  ({})\n{}".format(
            fname, nl.FOLDER_FOR_TYPE[PURCHASED],
            nl.mcmaster_tag(nl.find_mcmaster_number(text(inputs, "mcPn"))), copies)
    find(inputs, "preview").text = preview
    issues = _problems(inputs)
    if _state["joints"] and not issues:
        issues = ["Heads up: {} joint(s) attached to this part will be removed; "
                  "re-add them after converting.".format(_state["joints"])]
    find(inputs, "status").text = "  ".join(issues)
