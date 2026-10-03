"""
auto_params.py - keeps project parameters ready to use in every part,
without you starring anything.

It runs in the background whenever:
  - you open or switch to a part file,
  - you run Fusion's Update (or any command with Update/Reference/Derive
    in its name),
  - New Part has just created a new fabricated part.

What it does to a part file:
  1. If the part is in a project that has a "CMD-HELLO PARAMETERS" file and
     the part isn't linked yet, it links it (one Derive of the favorite
     parameters). Only parts in AUTO_LINK_FOLDERS are linked automatically.
  2. It marks every project parameter in the part as a favorite, so they
     show up when you type in a dimension. This is repeated after every
     Update, because parameters added to the project later arrive
     un-starred.

Settings are the two constants just below.
"""

import adsk.core
import adsk.fusion

from . import naming_logic as nl
from . import fusion_data as fd
from . import ui_helpers as uh

# Link parts automatically when they're opened (False = only star parts you
# linked yourself with the Project Parameters button).
AUTO_LINK = True

# Only parts in these folders are linked automatically. Purchased parts are
# left out because bought parts don't use your project's dimensions.
AUTO_LINK_FOLDERS = {"02 FABRICATED"}

# Commands after which favorites are re-checked (matched inside the command id).
UPDATE_WORDS = ("update", "reference", "derive")

_busy = {"on": False}       # true while this module is opening/saving files itself
_expected = {}              # new file name -> info, for parts New Part just created


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def design_of(doc):
    try:
        return adsk.fusion.Design.cast(doc.products.itemByProductType("DesignProductType"))
    except Exception:
        return None


def design_kind(design):
    try:
        intent = design.designIntent
    except Exception:
        return "hybrid"
    if intent == adsk.fusion.DesignIntentTypes.PartDesignIntentType:
        return "part"
    if intent == adsk.fusion.DesignIntentTypes.AssemblyDesignIntentType:
        return "assembly"
    return "hybrid"


def derived_parameter_names(design):
    """Parameters that came in through Derive: everything that is neither one
    of this file's own user parameters nor a model (feature) parameter."""
    own = {p.name for p in fd.as_list(design.userParameters)}
    for comp in fd.as_list(design.allComponents):
        try:
            own |= {p.name for p in fd.as_list(comp.modelParameters)}
        except Exception:
            pass
    return {p.name for p in fd.as_list(design.allParameters)} - own


def star(design, names):
    """Mark these parameters as favorites. Returns how many changed."""
    changed = 0
    for p in fd.as_list(design.allParameters):
        if p.name in names and not p.isFavorite:
            p.isFavorite = True
            changed += 1
    return changed


def project_parameter_names(project):
    cache = fd.load_params_cache(project) or {}
    return {p["name"] for p in cache.get("params", [])}


def link_design(design, master_design, master_file):
    """Derive the master's favorite parameters into design and star them.
    Returns True if the link was made."""
    feats = design.rootComponent.features.deriveFeatures
    inp = feats.createInput(master_design)
    inp.isIncludeFavoriteParameters = True
    inp.isIncludeComponentParameters = False
    if feats.add(inp) is None:
        return False
    names = {p.name for p in fd.as_list(master_design.userParameters)}
    star(design, names | derived_parameter_names(design))
    fd.set_design_setting(design, "paramsLinked", master_file.id if master_file else "yes")
    return True


# ---------------------------------------------------------------------------
# The automatic check
# ---------------------------------------------------------------------------

def ensure_ready(doc, allow_link=True):
    """Make project parameters usable in this document, if it's a project part."""
    if _busy["on"] or doc is None:
        return
    try:
        if not doc.isVisible or not doc.isSaved:
            return
        design = design_of(doc)
        if design is None or design_kind(design) == "assembly":
            return
        df = doc.dataFile
        project = df.parentProject
        code = fd.get_design_setting(design, "code") or fd.project_code(project)
        if not code or df.name.lower() == nl.params_file_name(code).lower():
            return

        if fd.get_design_setting(design, "paramsLinked"):
            names = project_parameter_names(project) | derived_parameter_names(design)
            n = star(design, names)
            if n:
                fd.log("starred {} project parameter(s) in {}".format(n, df.name))
            return

        if not (AUTO_LINK and allow_link) or design_kind(design) != "part":
            return
        if df.parentFolder.name not in AUTO_LINK_FOLDERS:
            return
        master = fd.find_params_file(project, code)
        if master is None:
            return
        with fd.timed("auto-linking {} to project parameters".format(df.name)):
            _link_with_master(doc, master, project)
    except Exception as exc:
        fd.log("project parameter check skipped: {}".format(exc))


def _link_with_master(doc, master_file, project):
    _busy["on"] = True
    mdoc, opened_here = None, False
    try:
        mdoc, opened_here = fd.open_document(master_file, False)
        if mdoc is None:
            return False
        mdesign = design_of(mdoc)
        fd.save_params_cache(project, fd.read_parameters(mdesign))
        doc.activate()
        return link_design(design_of(doc), mdesign, master_file)
    finally:
        if mdoc is not None and opened_here:
            mdoc.close(False)
        try:
            doc.activate()
        except Exception:
            pass
        _busy["on"] = False


# ---------------------------------------------------------------------------
# Parts New Part just created (so Edit in Place has the parameters too)
# ---------------------------------------------------------------------------

def expect_new_part(file_name, project, code, assembly_doc):
    """Called by New Part after saving the assembly. When the new part's file
    finishes uploading, it is linked and the assembly is updated."""
    if not AUTO_LINK or fd.find_params_file(project, code) is None:
        return False
    _expected[file_name] = {"project": project, "code": code, "assembly": assembly_doc}
    return True


def _link_new_part(data_file):
    info = _expected.pop(data_file.name, None)
    if info is None:
        return
    master = fd.find_params_file(info["project"], info["code"])
    if master is None:
        return
    _busy["on"] = True
    pdoc = mdoc = None
    opened_part = opened_master = False
    try:
        with fd.timed("linking new part " + data_file.name):
            pdoc, opened_part = fd.open_document(data_file, False)
            mdoc, opened_master = fd.open_document(master, False)
            if pdoc is None or mdoc is None:
                return
            pdesign = design_of(pdoc)
            fd.set_design_setting(pdesign, "code", info["code"])
            if link_design(pdesign, design_of(mdoc), master):
                pdoc.save("Linked to project parameters")
    except Exception as exc:
        fd.log("couldn't link new part {} yet ({}); it will link when opened"
               .format(data_file.name, exc))
    finally:
        for d, mine in ((mdoc, opened_master), (pdoc, opened_part)):
            if d is not None and mine:
                try:
                    d.close(False)
                except Exception:
                    pass
        _busy["on"] = False
    asm = info["assembly"]
    try:
        asm.activate()
        asm.updateAllReferences()        # pull the linked version into the assembly
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Event wiring
# ---------------------------------------------------------------------------

class _DocHandler(adsk.core.DocumentEventHandler):
    def notify(self, args):
        doc = args.document
        if not _busy["on"]:
            uh.run_later("Project parameters", lambda: ensure_ready(doc))


class _CommandDoneHandler(adsk.core.ApplicationCommandEventHandler):
    def notify(self, args):
        try:
            cid = (args.commandId or "").lower()
        except Exception:
            return
        if not _busy["on"] and any(w in cid for w in UPDATE_WORDS):
            uh.run_later("Project parameters",
                         lambda: ensure_ready(fd.app().activeDocument, allow_link=False))


class _UploadHandler(adsk.core.DataEventHandler):
    def notify(self, args):
        try:
            f = args.file
        except Exception:
            return
        if f is not None and f.name in _expected:
            uh.run_later("Linking new part", lambda: _link_new_part(f))


_wired = []


def start():
    app = fd.app()
    for event, handler in ((app.documentActivated, _DocHandler()),
                           (app.documentOpened, _DocHandler()),
                           (app.userInterface.commandTerminated, _CommandDoneHandler()),
                           (app.dataFileComplete, _UploadHandler())):
        event.add(handler)
        _wired.append((event, handler))
        uh.handlers.append(handler)


def stop():
    for event, handler in _wired:
        try:
            event.remove(handler)
        except Exception:
            pass
    _wired.clear()
