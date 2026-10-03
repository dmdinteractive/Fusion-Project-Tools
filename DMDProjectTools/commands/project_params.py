"""
project_params.py - the Project Parameters button.

Shares dimensions across all the part files in a project, using Fusion's
own method: one master file holds the parameters as favorites, and each
part Derives them. Change a value here, and every linked part shows as out
of date; click Fusion's Update button in a part and it resizes.

    CMD-HELLO - Hello Exhibit
      00 ASSEMBLY
        CMD-HELLO PARAMETERS      <- created by this tool, holds ply_thickness etc.

What the dialog does:
  - Shows the project's parameters.
  - Adds or changes one parameter (name cleaned to ply_thickness style).
    The master file is opened in the background, edited, saved, and closed.
    Every parameter in it is kept marked as a favorite, because un-favoriting
    one silently breaks the link in every part.
  - Links the open part to the project parameters (one Derive, favorites only).
"""

import adsk.core
import adsk.fusion

from ..lib import naming_logic as nl
from ..lib import fusion_data as fd
from ..lib import ui_helpers as uh
from ..lib import auto_params
from ..lib.ui_helpers import find, val, text

CMD_ID = "dmdProjectParams"
CMD_NAME = "Project Parameters"
TOOLTIP = "Create and share dimensions across every part in the project."

NEW_PARAM = "(new parameter)"
NO_UNITS = "(no units)"

_state = {}


def _design():
    return adsk.fusion.Design.cast(fd.app().activeProduct)


def _kind(design):
    try:
        intent = design.designIntent
    except Exception:
        return "hybrid"
    if intent == adsk.fusion.DesignIntentTypes.PartDesignIntentType:
        return "part"
    if intent == adsk.fusion.DesignIntentTypes.AssemblyDesignIntentType:
        return "assembly"
    return "hybrid"


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

class CreatedHandler(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        try:
            design = _design()
            project = fd.active_project()
            if not design or project is None:
                fd.ui().messageBox("Open a file in a project (or pick a project in the "
                                   "Data Panel) first.", CMD_NAME)
                args.command.isAutoExecute = True
                return
            doc = fd.app().activeDocument
            code = fd.get_design_setting(design, "code") or fd.project_code(project)
            master = fd.find_params_file(project, code) if code else None
            is_master = bool(master and doc.isSaved and doc.dataFile.id == master.id)
            _state.clear()
            _state.update({
                "updating": False, "project": project, "code": code, "doc": doc,
                "kind": _kind(design), "master": master, "is_master": is_master,
                "linked": bool(fd.get_design_setting(design, "paramsLinked")),
                "params": [],
            })

            cmd = args.command
            cmd.okButtonText = "Apply"
            inputs = cmd.commandInputs

            inputs.addTextBoxCommandInput("info", "Project", "", 2, True)
            if not code:
                inputs.addStringValueInput("code", "Project code", "")
            inputs.addTextBoxCommandInput("list", "Parameters", "", 7, True)

            g = inputs.addGroupCommandInput("grpEdit", "Add or change a parameter").children
            pick = g.addDropDownCommandInput("pick", "Parameter",
                                             adsk.core.DropDownStyles.TextListDropDownStyle)
            pick.listItems.add(NEW_PARAM, True)
            name = g.addStringValueInput("name", "Name", "")
            name.tooltip = "What it is, not its size: ply_thickness, exhibit_width, kerf"
            g.addTextBoxCommandInput("namePreview", "Will be saved as", "", 1, True)
            value = g.addStringValueInput("value", "Value", "")
            value.tooltip = "A number (0.75) or an expression (exhibit_width / 2)"
            units = g.addDropDownCommandInput("units", "Units",
                                              adsk.core.DropDownStyles.TextListDropDownStyle)
            default_unit = design.fusionUnitsManager.defaultLengthUnits
            for u in nl.PARAM_UNITS:
                units.listItems.add(u or NO_UNITS, u == default_unit)
            g.addStringValueInput("comment", "Comment", "")

            g = inputs.addGroupCommandInput("grpLink", "This file").children
            g.addTextBoxCommandInput("linkInfo", "", "", 3, True)
            link = g.addBoolValueInput("link", "Link this file to project parameters",
                                       True, "", True)
            link.isVisible = _can_link()

            inputs.addTextBoxCommandInput("status", "", "", 2, True)

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
            _load_params()
            pick = find(inputs, "pick")
            for p in _state["params"]:
                pick.listItems.add(p["name"], False)
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
            if changed.id == "pick":
                _fill_from_pick(inputs)
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
            job = {
                "doc": _state["doc"], "project": _state["project"],
                "code": _code(inputs), "master": _state["master"],
                "is_master": _state["is_master"],
                "edit": _edit_wanted(inputs),
                "name": nl.clean_param_name(text(inputs, "name")),
                "expression": _expression(inputs),
                "unit": _unit(inputs),
                "comment": text(inputs, "comment"),
                "link": _link_wanted(inputs),
            }
            uh.run_later("Updating project parameters", lambda: _apply(job))
        except Exception:
            uh.show_error(CMD_NAME)


# ---------------------------------------------------------------------------
# The work (after the dialog closes)
# ---------------------------------------------------------------------------

def _apply(job):
    origin = job["doc"]
    project = job["project"]
    notes = []
    created = opened_here = False

    # 1. Get the master parameters file (open in the background, or create it).
    if job["is_master"]:
        mdoc = origin
    elif job["master"] is None:
        mdoc = _create_master(project, job["code"])
        created = opened_here = True
        notes.append("Created {} in {}".format(mdoc.dataFile.name if mdoc.isSaved
                                                else nl.params_file_name(job["code"]),
                                                nl.FOLDERS[0]))
    else:
        mdoc, opened_here = fd.open_document(job["master"], False)
        if mdoc is None:
            fd.ui().messageBox("Couldn't open {}.".format(job["master"].name), CMD_NAME)
            return
    mdesign = adsk.fusion.Design.cast(mdoc.products.itemByProductType("DesignProductType"))

    changed = False
    try:
        # 2. Add or change the parameter; keep every parameter a favorite.
        if job["edit"]:
            notes.append(_set_parameter(mdesign, job))
            changed = True
        for p in fd.as_list(mdesign.userParameters):
            if not p.isFavorite:
                p.isFavorite = True
                changed = True
        if changed:
            mdoc.save("Project parameters: " + (job["name"] or "favorites"))
        params = fd.read_parameters(mdesign)
        fd.save_params_cache(project, params)

        # 3. Link the file the user is in.
        if job["link"]:
            origin.activate()
            notes.append(_link(origin, mdesign, mdoc, params))
    finally:
        # never leave the parameters file open in the background
        if opened_here:
            mdoc.close(False)
        try:
            origin.activate()
        except Exception:
            pass
    if changed and not created:
        notes.append("Linked parts now show as out of date. Open one and click Update "
                     "(or the out-of-date icon) to pull in the new values; they're "
                     "starred for you automatically.")
    fd.ui().messageBox("\n\n".join(n for n in notes if n), CMD_NAME)


def _create_master(project, code):
    doc = fd.app().documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
    design = adsk.fusion.Design.cast(doc.products.itemByProductType("DesignProductType"))
    try:
        design.designIntent = adsk.fusion.DesignIntentTypes.PartDesignIntentType
    except Exception:
        pass
    fd.set_design_setting(design, "code", code)
    fd.ensure_folders(project)
    folder = fd.top_folder(project, nl.FOLDERS[0])
    doc.saveAs(nl.params_file_name(code), folder, nl.PARAMS_FILE_DESCRIPTION, "")
    fd.note_params_file(project, doc.dataFile)
    return doc


def _set_parameter(design, job):
    params = design.userParameters
    existing = params.itemByName(job["name"])
    try:
        if existing:
            existing.expression = job["expression"]
            if job["comment"]:
                try:
                    existing.comment = job["comment"]
                except Exception:
                    pass            # some Fusion versions only allow comments on create
            return "Changed {} to {}".format(job["name"], job["expression"])
        added = params.add(job["name"], adsk.core.ValueInput.createByString(job["expression"]),
                           job["unit"], job["comment"])
        if added is None:
            raise RuntimeError("Fusion returned nothing")
        added.isFavorite = True
        return "Added {} = {}".format(job["name"], job["expression"])
    except Exception as exc:
        raise RuntimeError("Fusion didn't accept '{}' = '{}'. Check the name and value.\n({})"
                           .format(job["name"], job["expression"], exc))


def _link(origin, mdesign, mdoc, params):
    design = adsk.fusion.Design.cast(origin.products.itemByProductType("DesignProductType"))
    if not auto_params.link_design(design, mdesign, mdoc.dataFile if mdoc.isSaved else None):
        return "Fusion couldn't link this file. Use Insert > Derive and pick the parameters file."
    names = sorted(p["name"] for p in params)
    return ("Linked this file to the project parameters. Type a name like {} into any "
            "dimension.".format(names[0] if names else "ply_thickness"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _code(inputs):
    return _state["code"] or nl.clean_code(text(inputs, "code"))


def _load_params():
    """Live from the master if it's the open file, otherwise the list this
    add-in saved last time; only if neither exists is the master opened."""
    project = _state["project"]
    if _state["is_master"]:
        _state["params"] = fd.read_parameters(_design())
        fd.save_params_cache(project, _state["params"])
        return
    cache = fd.load_params_cache(project)
    if cache is not None:
        _state["params"] = cache.get("params", [])
        _state["cache_time"] = cache.get("saved", "")
        return
    if _state["master"] is not None:
        mdoc, opened_here = fd.open_document(_state["master"], False)
        if mdoc:
            mdesign = adsk.fusion.Design.cast(mdoc.products.itemByProductType("DesignProductType"))
            _state["params"] = fd.read_parameters(mdesign)
            fd.save_params_cache(project, _state["params"])
            if opened_here:
                mdoc.close(False)
            _state["doc"].activate()


def _fill_from_pick(inputs):
    choice = val(inputs, "pick")
    for p in _state["params"]:
        if p["name"] == choice:
            find(inputs, "name").value = p["name"]
            find(inputs, "value").value = p["expression"]
            find(inputs, "comment").value = p.get("comment", "")
            uh.set_choice(inputs, "units", p.get("unit") or NO_UNITS)
            return
    for key in ("name", "value", "comment"):
        find(inputs, key).value = ""


def _unit(inputs):
    u = val(inputs, "units")
    return "" if u == NO_UNITS else u


def _expression(inputs):
    """A bare number gets its units attached ('0.75' -> '0.75 in');
    expressions and values with units are left as typed."""
    raw = text(inputs, "value")
    unit = _unit(inputs)
    try:
        float(raw)
        return "{} {}".format(raw, unit).strip()
    except ValueError:
        return raw


def _edit_wanted(inputs):
    return bool(text(inputs, "name") or text(inputs, "value"))


def _can_link():
    return (not _state["is_master"] and not _state["linked"]
            and _state["kind"] in ("part", "hybrid"))


def _link_wanted(inputs):
    link = find(inputs, "link")
    return bool(link.isVisible and link.value)


def _problems(inputs):
    issues = []
    if not _code(inputs):
        issues.append("Enter the project code (e.g. CMD-HELLO).")
    if _edit_wanted(inputs):
        problem = nl.param_name_problem(nl.clean_param_name(text(inputs, "name")))
        if problem:
            issues.append(problem)
        if not text(inputs, "value"):
            issues.append("Enter a value.")
    elif not _link_wanted(inputs):
        issues.append("Enter a parameter to add or change.")
    return issues


def _refresh(inputs):
    code = _code(inputs)
    master = _state["master"]
    fname = nl.params_file_name(code) if code else "(project code needed)"
    count = len(_state["params"])
    if master is not None:
        where = "{}  ({} parameter{})".format(fname, count, "" if count == 1 else "s")
    else:
        where = "{}  (will be created in {} on Apply)".format(fname, nl.FOLDERS[0])
    find(inputs, "info").text = "{}\n{}".format(_state["project"].name, where)

    lines = [nl.param_line(p["name"], p["expression"], p.get("comment", ""))
             for p in _state["params"]]
    if not lines:
        lines = ["No project parameters yet."]
    elif _state.get("cache_time") and not _state["is_master"]:
        lines.append("(as of {}; edits made directly in the parameters file "
                     "show here after the next Apply)".format(_state["cache_time"]))
    find(inputs, "list").text = "\n".join(lines)

    cleaned = nl.clean_param_name(text(inputs, "name"))
    preview = cleaned
    if cleaned and cleaned in [p["name"] for p in _state["params"]]:
        preview += "   (changes the existing value)"
    find(inputs, "namePreview").text = preview

    if _state["is_master"]:
        link_text = "This is the project parameters file."
    elif _state["linked"]:
        link_text = ("Linked. After parameters change, click Update (the out-of-date icon) "
                     "in this file; new parameters are starred automatically.")
    elif _state["kind"] == "assembly":
        link_text = ("Assembly files can't hold features, so they can't be linked. "
                     "Link the parts instead.")
    else:
        link_text = "Not linked yet."
    find(inputs, "linkInfo").text = link_text
    find(inputs, "status").text = "  ".join(_problems(inputs))
