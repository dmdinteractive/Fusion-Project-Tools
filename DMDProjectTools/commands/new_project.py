"""
new_project.py - the New Project button.

Two modes:
  Create a new project   - makes "CMD-HELLO - Hello Exhibit" in your hub,
                           adds the standard folders, and saves an empty
                           top-level Assembly "CMD-HELLO-000 HELLO EXHIBIT".
  Set up current project - for a project that already exists: adds any
                           missing folders, can rename it to the standard
                           format, and records the reference view. Existing
                           files are never moved or changed.

The reference view is stored in the top-level assembly's description in
the Data Panel ("[DMD] REF VIEW: ..."), so every tool in the project can
read it without opening anything.
"""

import adsk.core
import adsk.fusion

from ..lib import naming_logic as nl
from ..lib import fusion_data as fd
from ..lib import ui_helpers as uh
from ..lib.ui_helpers import find, val, text

CMD_ID = "dmdNewProject"
CMD_NAME = "New Project"
TOOLTIP = "Create or set up a project with the standard folders, numbering and reference view."

MODE_NEW = "Create a new project"
MODE_SETUP = "Set up the current project"

_state = {}


class CreatedHandler(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        try:
            hub = fd.app().data.activeHub
            current = fd.app().data.activeProject
            _state.clear()
            _state.update({
                "updating": False,
                "hub": hub,
                "current": current,
                "existing": None,      # read only once you've typed a full name
                "top": None,
                "settings": {},
            })

            cmd = args.command
            cmd.okButtonText = "Create"
            inputs = cmd.commandInputs

            inputs.addTextBoxCommandInput(
                "hub", "Hub", hub.name + "   (change hubs in the Data Panel)", 1, True)
            mode = inputs.addRadioButtonGroupCommandInput("mode", "")
            mode.listItems.add(MODE_NEW, True)
            if current:
                mode.listItems.add("{}: {}".format(MODE_SETUP, current.name), False)

            g = inputs.addGroupCommandInput("grpId", "Project").children
            org = g.addStringValueInput("org", "Organization", "")
            org.tooltip = "Who the work is for, e.g. CMD (Children's Museum of Denver) or DMD."
            code = g.addStringValueInput("proj", "Project code", "")
            code.tooltip = "Short code for this exhibit, e.g. HELLO. Letters and numbers only."
            g.addStringValueInput("title", "Project name", "")
            g.addBoolValueInput("rename", "Rename project to the standard format", True, "", True)

            g = inputs.addGroupCommandInput("grpRef", "Reference view").children
            ref = g.addStringValueInput("refView", "Reference view", "")
            ref.tooltip = "The one viewpoint LH/RH and locations are judged from."
            ref.tooltipDescription = "Example: VIEWED FROM VISITOR SIDE, GRAPHIC FACE TOWARD YOU"

            inputs.addBoolValueInput("makeTop", "Create top-level assembly", True, "", True)
            inputs.addTextBoxCommandInput("preview", "Will create", "", 9, True)
            inputs.addTextBoxCommandInput("status", "", "", 2, True)

            uh.connect(cmd, ((ActivateHandler(), cmd.activate),
                             (InputChangedHandler(), cmd.inputChanged),
                             (ValidateHandler(), cmd.validateInputs),
                             (ExecuteHandler(), cmd.execute)))
        except Exception:
            uh.show_error("New Project")


class ActivateHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        _refresh(args.command.commandInputs)


class InputChangedHandler(adsk.core.InputChangedEventHandler):
    def notify(self, args):
        if _state.get("updating"):
            return
        try:
            inputs = uh.all_inputs(args)
            _state["updating"] = True
            if args.input.id == "mode":
                _load_mode(inputs)
            _refresh(inputs)
        except Exception:
            uh.show_error("New Project")
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
                "setup": _is_setup(inputs),
                "hub": _state["hub"],
                "project": _state["current"],
                "top": _state["top"],
                "code": _code(inputs),
                "title": text(inputs, "title"),
                "name": _project_name(inputs),
                "rename": bool(val(inputs, "rename")),
                "refView": text(inputs, "refView").upper(),
                "makeTop": bool(val(inputs, "makeTop")),
            }
            uh.run_later("Setting up the project", lambda: _do(job))
        except Exception:
            uh.show_error("New Project")


# ---------------------------------------------------------------------------
# The actual work (runs after the dialog closes)
# ---------------------------------------------------------------------------

def _do(job):
    done = []
    if job["setup"]:
        project = job["project"]
        if job["rename"] and project.name != job["name"]:
            project.name = job["name"]
            done.append("Renamed project to " + job["name"])
    else:
        project = fd.create_project(job["hub"], job["name"])
        if project is None:
            fd.ui().messageBox("Fusion couldn't create the project.", CMD_NAME)
            return
        done.append("Created project " + job["name"])

    created = fd.ensure_folders(project)
    if created:
        done.append("Added folders: " + ", ".join(created))

    settings = {"REF VIEW": job["refView"]}
    top_file = job["top"] if job["setup"] else None
    if top_file is not None:
        fd.write_project_settings(top_file, settings)
        done.append("Saved reference view on " + top_file.name)
    elif job["makeTop"]:
        name = _create_top_assembly(project, job)
        done.append("Created top-level assembly " + name)

    try:
        fd.app().data.activeProject = project
    except Exception:
        pass
    fd.ui().messageBox("\n".join(done) or "Nothing needed changing.", CMD_NAME)


def _create_top_assembly(project, job):
    pn = nl.format_part_number(job["code"], nl.TOP_ASSEMBLY_NUMBER)
    fname = nl.file_name(pn, job["title"].upper())
    doc = fd.app().documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
    design = adsk.fusion.Design.cast(doc.products.itemByProductType("DesignProductType"))
    try:
        design.designIntent = adsk.fusion.DesignIntentTypes.AssemblyDesignIntentType
    except Exception:
        pass        # older Fusion, or not allowed: the file stays the default type
    root = design.rootComponent
    root.partNumber = pn
    root.description = "TOP-LEVEL ASSEMBLY"
    fd.set_design_setting(design, "code", job["code"])
    fd.set_design_setting(design, "refView", job["refView"])
    folder = fd.top_folder(project, nl.FOLDERS[0])
    doc.saveAs(fname, folder, nl.encode_settings({"REF VIEW": job["refView"]}), "")
    fd.forget_project(project)          # next dialog re-reads it with the new top assembly
    return fname


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_setup(inputs):
    return (val(inputs, "mode") or "").startswith(MODE_SETUP)


def _code(inputs):
    return nl.make_code(text(inputs, "org"), text(inputs, "proj"))


def _project_name(inputs):
    code = _code(inputs)
    return nl.make_project_name(code, text(inputs, "title")) if code else ""


def _load_mode(inputs):
    """Switching to 'set up current' fills in what the project already has."""
    if _is_setup(inputs):
        project = _state["current"]
        code, title = nl.parse_project_name(project.name)
        org, proj = nl.split_code(code)
        find(inputs, "org").value = org
        find(inputs, "proj").value = proj
        find(inputs, "title").value = title
        _state["top"] = fd.find_top_assembly(project, code)
        _state["settings"] = nl.decode_settings(_state["top"].description) if _state["top"] else {}
        find(inputs, "refView").value = _state["settings"].get("REF VIEW", "")
    else:
        for key in ("org", "proj", "title", "refView"):
            find(inputs, key).value = ""
        _state["top"] = None


def _existing_names():
    """Project names in the hub, read the first time they're needed rather
    than when the dialog opens."""
    if _state["existing"] is None:
        _state["existing"] = [n.lower() for n in fd.project_names(_state["hub"])]
    return _state["existing"]


def _problems(inputs):
    issues = []
    if not text(inputs, "org"):
        issues.append("Enter the organization (e.g. CMD).")
    if not text(inputs, "proj"):
        issues.append("Enter a project code (e.g. HELLO).")
    if not text(inputs, "title"):
        issues.append("Enter the project name.")
    name = _project_name(inputs)
    setup = _is_setup(inputs)
    renaming = setup and val(inputs, "rename") and name != _state["current"].name
    if name and text(inputs, "title") and (not setup or renaming) \
            and name.lower() in _existing_names():
        issues.append("A project named '{}' already exists.".format(name))
    return issues


def _refresh(inputs):
    setup = _is_setup(inputs)
    find(inputs, "rename").isVisible = setup
    has_top = setup and _state["top"] is not None
    find(inputs, "makeTop").isVisible = not has_top

    code = _code(inputs) or "ORG-CODE"
    name = _project_name(inputs) or "ORG-CODE - Project name"
    lines = []
    if setup:
        current = _state["current"].name
        lines.append("Project: " + (name if val(inputs, "rename") else current))
    else:
        lines.append("Project: " + name)
    lines.append("Folders: " + ", ".join(nl.FOLDERS) + " (missing ones only)")
    if has_top:
        lines.append("Reference view saved on: " + _state["top"].name)
    elif val(inputs, "makeTop"):
        lines.append("Top assembly: " + nl.file_name(
            nl.format_part_number(code, nl.TOP_ASSEMBLY_NUMBER),
            (text(inputs, "title") or "PROJECT NAME").upper()))
    lines.append("First part number: " + nl.format_part_number(code, 1))
    if not text(inputs, "refView"):
        lines.append("No reference view yet: LH/RH parts can't be named until one is set.")
    find(inputs, "preview").text = "\n".join(lines)
    find(inputs, "status").text = "  ".join(_problems(inputs))
