"""
param_sync.py - copies the project parameters into every part.

Why this exists
---------------
Earlier versions linked parts to the parameters file with Fusion's Derive.
Derive only brings in the favorites that exist at the moment you derive;
parameters added to the project later never reach parts that were already
linked, however many times you click Update. So instead of Derive, this
module writes the parameters into each part as ordinary user parameters
and keeps their values matching the parameters file.

When it runs
------------
  - when you open a part (or switch to its tab),
  - right after New Part creates a fabricated part,
  - on the open part, right after you Apply in the Project Parameters dialog.
Parts that stay closed keep their old values until the next time they are
opened (that's the "update when opened" choice).

What it does to a part
----------------------
  1. Adds any project parameter the part doesn't have yet.
  2. Changes a parameter's value when it differs from the parameters file.
     The parameters file always wins; a value typed into the part itself
     is overwritten the next time the part is opened.
  3. Stars every project parameter, so it shows when you type in a
     dimension box.
  4. Parts linked the old way keep their Derive. Parameters that already
     come through it are left to it, and the Derive is moved to the newest
     version of the parameters file. Only parameters it is missing are added.
  5. Saves the part if anything changed, unless you already had unsaved
     changes in it (then it leaves saving to you).

It never deletes a parameter from a part, because features may use it.

Which files
-----------
Part files in SYNC_FOLDERS, and Hybrid designs in any folder except
NEVER_FOLDERS. Assembly files can't hold features, so they're skipped.

How it knows the current values without opening the parameters file
every time: the values are saved to cache/params_<project>.json together
with the parameters file's version number. A part uses the saved values
while the parameters file hasn't moved past that version; otherwise the
file is opened in the background once and the cache refreshed. Fusion's
view of the project is re-read every 5 minutes, so an edit made on
another computer reaches this one within about 5 minutes.
"""

import adsk.core
import adsk.fusion

from . import naming_logic as nl
from . import fusion_data as fd
from . import ui_helpers as uh

# Part files in these folders get the project parameters.
SYNC_FOLDERS = {"02 FABRICATED"}

# Hybrid designs (parts and an assembly in one file) get them in any folder
# except these.
SYNC_HYBRID = True
NEVER_FOLDERS = {"03 PURCHASED", "04 DRAWINGS", "99 ARCHIVE"}

# Save a part after its parameters change (only if it had no unsaved edits).
AUTO_SAVE = True

_busy = {"on": False}       # true while this module opens or saves files itself
_expected = {}              # new part file name -> info, for parts New Part just made


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


def folder_wanted(kind, folder):
    """Should a design of this kind, in this folder, get project parameters?"""
    if kind == "assembly" or folder in NEVER_FOLDERS:
        return False
    if folder in SYNC_FOLDERS:
        return True
    return kind == "hybrid" and SYNC_HYBRID


def derived_names(design):
    """Parameters that come in through an old Derive link."""
    try:
        return {p.name for p in fd.as_list(design.derivedParameters)}
    except Exception:
        pass
    # Older Fusion without derivedParameters: everything that isn't one of
    # this file's own user or model parameters.
    own = {p.name for p in fd.as_list(design.userParameters)} | model_names(design)
    return {p.name for p in fd.as_list(design.allParameters)} - own


def model_names(design):
    names = set()
    for comp in fd.as_list(design.allComponents):
        try:
            names |= {p.name for p in fd.as_list(comp.modelParameters)}
        except Exception:
            pass
    return names


def latest_version(data_file):
    try:
        return int(data_file.latestVersionNumber)
    except Exception:
        return 0


def saved_version(doc, known):
    """Version number of a file we just saved. Fusion may not report the new
    number until the upload finishes, so fall back to one past what we knew."""
    try:
        number = int(doc.dataFile.versionNumber)
    except Exception:
        number = 0
    return max(number, (known or 0) + 1)


# ---------------------------------------------------------------------------
# Reading the parameters file
# ---------------------------------------------------------------------------

def project_values(project, code, force=False):
    """(params, master_file) for the project, from the cache when it's
    current, otherwise by opening the parameters file in the background.
    (None, None) if the project has no parameters file."""
    master = fd.find_params_file(project, code)
    if master is None:
        return None, None
    latest = latest_version(master)
    cache = fd.load_params_cache(project)
    if (not force and cache and latest
            and int(cache.get("version") or 0) >= latest):
        return cache.get("params", []), master
    params = read_master(project, master, latest)
    return params, master


def read_master(project, master, version):
    """Open the parameters file in the background, read it, refresh the cache."""
    was_busy = _busy["on"]
    _busy["on"] = True
    mdoc, opened_here = None, False
    try:
        mdoc, opened_here = fd.open_document(master, False)
        params = fd.read_parameters(design_of(mdoc))
        fd.save_params_cache(project, params, version)
        return params
    finally:
        if mdoc is not None and opened_here:
            try:
                mdoc.close(False)
            except Exception:
                pass
        _busy["on"] = was_busy


# ---------------------------------------------------------------------------
# Writing parameters into a part
# ---------------------------------------------------------------------------

def _add(design, mp, use_value):
    """Add one project parameter to the part. With use_value, add it as a
    plain number (its current value) because its expression needs a
    parameter the part doesn't have yet. Returns the parameter or None."""
    try:
        if use_value:
            if mp.get("value") is None:
                return None
            vin = adsk.core.ValueInput.createByReal(mp["value"])
        else:
            vin = adsk.core.ValueInput.createByString(mp["expression"])
        return design.userParameters.add(mp["name"], vin, mp.get("unit") or "",
                                         mp.get("comment") or "")
    except Exception:
        return None


def sync_design(design, params):
    """Make this design's parameters match the project. Returns a report:
    {"added": [...], "changed": [...], "starred": n, "kept_derived": [...],
     "conflicts": [...], "failed": [...]}"""
    report = {"added": [], "changed": [], "starred": 0, "kept_derived": [],
              "conflicts": [], "failed": []}
    user = {p.name: p for p in fd.as_list(design.userParameters)}
    derived = derived_names(design)
    model = model_names(design)

    mine = []           # project parameters this module manages in this part
    to_add = []
    for mp in params:
        name = mp["name"]
        if name in derived:
            report["kept_derived"].append(name)
        elif name in model:
            report["conflicts"].append(name)
        else:
            mine.append(mp)
            if name not in user:
                to_add.append(mp)

    # 1. Add missing parameters. An expression like exhibit_width / 2 can only
    #    be added once exhibit_width exists, so keep passing over the list
    #    while something gets added. Anything left is added as a plain number
    #    and gets its expression in step 2.
    progress = True
    while to_add and progress:
        progress = False
        for mp in list(to_add):
            p = _add(design, mp, use_value=False)
            if p is not None:
                user[mp["name"]] = p
                report["added"].append(mp["name"])
                to_add.remove(mp)
                progress = True
    for mp in to_add:
        p = _add(design, mp, use_value=True)
        if p is not None:
            user[mp["name"]] = p
            report["added"].append(mp["name"])
        else:
            report["failed"].append(mp["name"])

    # 2. Match expressions (same retry idea, for expressions that refer to
    #    each other).
    pending = [mp for mp in mine if mp["name"] in user
               and user[mp["name"]].expression != mp["expression"]]
    progress = True
    while pending and progress:
        progress = False
        for mp in list(pending):
            try:
                user[mp["name"]].expression = mp["expression"]
                if mp["name"] not in report["added"]:
                    report["changed"].append(mp["name"])
                pending.remove(mp)
                progress = True
            except Exception:
                pass
    report["failed"] += [mp["name"] for mp in pending if mp["name"] not in report["failed"]]

    # 3. Comments (not every Fusion version allows changing them).
    for mp in mine:
        p = user.get(mp["name"])
        if p is None or not mp.get("comment"):
            continue
        try:
            if p.comment != mp["comment"]:
                p.comment = mp["comment"]
        except Exception:
            pass

    # 4. Star project parameters, including old derived ones.
    names = {mp["name"] for mp in params}
    for p in fd.as_list(design.allParameters):
        try:
            if p.name in names and not p.isFavorite:
                p.isFavorite = True
                report["starred"] += 1
        except Exception:
            pass
    return report


def refresh_old_derives(design, master):
    """Move Derive links to the parameters file onto its newest version
    (what the out-of-date Update button does). Returns how many moved."""
    moved = 0
    for comp in fd.as_list(design.allComponents):
        try:
            feats = fd.as_list(comp.features.deriveFeatures)
        except Exception:
            continue
        for feat in feats:
            try:
                ref = feat.documentReference
                if ref.dataFile.name.lower() != master.name.lower():
                    continue
                if ref.isOutOfDate:
                    ref.getLatestVersion()
                    moved += 1
            except Exception:
                pass
    return moved


def summary(report, moved=0):
    parts = []
    if report["added"]:
        parts.append("added " + ", ".join(report["added"]))
    if report["changed"]:
        parts.append("updated " + ", ".join(report["changed"]))
    if moved:
        parts.append("updated the old Derive link")
    if report["starred"]:
        parts.append("starred {}".format(report["starred"]))
    return "; ".join(parts)


def problems_text(report):
    lines = []
    if report["failed"]:
        lines.append("Couldn't add or update: {}. Check their values in the parameters "
                     "file.".format(", ".join(report["failed"])))
    if report["conflicts"]:
        lines.append("Skipped {}: the part already has a feature dimension with that "
                     "name.".format(", ".join(report["conflicts"])))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# The automatic check
# ---------------------------------------------------------------------------

def target(doc):
    """(design, project, code) if this document should get project
    parameters, else None."""
    if doc is None or not doc.isSaved:
        return None
    design = design_of(doc)
    if design is None:
        return None
    df = doc.dataFile
    if not folder_wanted(design_kind(design), df.parentFolder.name):
        return None
    project = df.parentProject
    code = fd.get_design_setting(design, "code") or fd.project_code(project)
    if not code or df.name.lower() == nl.params_file_name(code).lower():
        return None
    return design, project, code


def sync_document(doc, force=False, quiet=True):
    """Bring this document up to date with the project parameters.
    Returns the report, or None if the document isn't one we handle."""
    found = target(doc)
    if found is None:
        return None
    design, project, code = found
    was_modified = bool(getattr(doc, "isModified", False))
    params, master = project_values(project, code, force=force)
    if params is None:
        return None
    try:
        if fd.app().activeDocument != doc and doc.isVisible:
            doc.activate()
    except Exception:
        pass

    report = sync_design(design, params)
    moved = refresh_old_derives(design, master)
    done = summary(report, moved)
    if report["added"] or report["changed"] or moved:
        name = doc.dataFile.name
        if AUTO_SAVE and not was_modified:
            _busy["on"] = True
            try:
                doc.save("Project parameters: " + done)
                fd.log("{}: {} (saved)".format(name, done))
            finally:
                _busy["on"] = False
        else:
            fd.log("{}: {} (not saved; the file had unsaved edits)".format(name, done))
    elif done:
        fd.log("{}: {}".format(doc.dataFile.name, done))
    issues = problems_text(report)
    if issues and not quiet:
        fd.ui().messageBox(issues, "Project Parameters")
    elif issues:
        fd.log(issues.replace("\n", " "))
    return report


def check(doc):
    if _busy["on"] or doc is None:
        return
    try:
        if not doc.isVisible:
            return
        with fd.timed("project parameters check"):
            sync_document(doc)
    except Exception as exc:
        fd.log("project parameter check skipped: {}".format(exc))


# ---------------------------------------------------------------------------
# Parts New Part just created (so Edit in Place has the parameters too)
# ---------------------------------------------------------------------------

def expect_new_part(file_name, project, code, assembly_doc):
    """Called by New Part after saving the assembly. When the new part's file
    finishes uploading, it gets the parameters and the assembly is updated."""
    if fd.find_params_file(project, code) is None:
        return False
    _expected[file_name] = {"project": project, "code": code, "assembly": assembly_doc}
    uh.on_upload(file_name, "Adding project parameters to new part", _fill_new_part)
    return True


def _fill_new_part(data_file):
    info = _expected.pop(data_file.name, None)
    if info is None:
        return
    _busy["on"] = True
    pdoc, opened_here = None, False
    try:
        with fd.timed("project parameters for new part " + data_file.name):
            pdoc, opened_here = fd.open_document(data_file, False)
            if pdoc is None:
                return
            pdesign = design_of(pdoc)
            fd.set_design_setting(pdesign, "code", info["code"])
            params, _ = project_values(info["project"], info["code"])
            if params:
                report = sync_design(pdesign, params)
                pdoc.save("Project parameters: " + (summary(report) or "added"))
    except Exception as exc:
        fd.log("couldn't add project parameters to {} yet ({}); they'll be added "
               "when it's opened".format(data_file.name, exc))
    finally:
        if pdoc is not None and opened_here:
            try:
                pdoc.close(False)
            except Exception:
                pass
        _busy["on"] = False
    try:
        info["assembly"].activate()
        info["assembly"].updateAllReferences()     # pull the new version into the assembly
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Keep the cache right when the parameters file is edited directly
# ---------------------------------------------------------------------------

def note_master_saved(doc):
    try:
        design = design_of(doc)
        if design is None or not doc.isSaved:
            return
        df = doc.dataFile
        if not df.name.upper().endswith(" " + nl.PARAMS_FILE_WORD):
            return
        project = df.parentProject
        cache = fd.load_params_cache(project) or {}
        version = saved_version(doc, int(cache.get("version") or 0))
        fd.save_params_cache(project, fd.read_parameters(design), version)
        fd.log("parameters file saved; values cached (v{})".format(version))
    except Exception as exc:
        fd.log("couldn't cache saved parameters ({})".format(exc))


# ---------------------------------------------------------------------------
# Event wiring
# ---------------------------------------------------------------------------

class _OpenHandler(adsk.core.DocumentEventHandler):
    def notify(self, args):
        doc = args.document
        if not _busy["on"]:
            uh.run_later("Project parameters", lambda: check(doc))


class _SavedHandler(adsk.core.DocumentEventHandler):
    def notify(self, args):
        doc = args.document
        uh.run_later("Project parameters", lambda: note_master_saved(doc))


_wired = []


def start():
    app = fd.app()
    for event, handler in ((app.documentActivated, _OpenHandler()),
                           (app.documentOpened, _OpenHandler()),
                           (app.documentSaved, _SavedHandler())):
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
