"""
fusion_data.py - small helpers that talk to Fusion's cloud data
(hubs, projects, folders, files) and material libraries.

Every command uses these, so the "how do I find the project / the next
part number / the reference view" logic lives in one place.

Speed notes (v2.2):
- Every folder or file read is a request to Autodesk's cloud, so a project
  is read ONCE into a snapshot (ProjectIndex) and reused by every dialog
  for a few minutes. Files this add-in creates or renames are added to the
  snapshot directly, so it stays correct without re-reading.
- 04 DRAWINGS is skipped; drawings don't carry part numbers.
- The list of Fusion's own materials is saved to cache/materials.json the
  first time, so later Fusion sessions don't re-read hundreds of materials.
- Each slow step is timed and written to the TEXT COMMANDS window
  (View > Show Text Commands) as "DMD Tools: ...".
"""

import json
import os
import time

import adsk.core
import adsk.fusion

from . import naming_logic as nl

ATTR_GROUP = "DMD_ProjectTools"     # name under which settings are stored in a design

# How long a project snapshot is trusted before it is re-read (seconds).
SNAPSHOT_SECONDS = 300

# Folders whose files can't hold part numbers, so they're never read.
SKIP_FOLDERS = {"04 DRAWINGS"}

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache")


def app():
    return adsk.core.Application.get()


def ui():
    return app().userInterface


# ---------------------------------------------------------------------------
# Timing
# ---------------------------------------------------------------------------

class timed:
    """with timed("reading project"): ...   -> logs 'DMD Tools: reading project 0.42 s'"""

    def __init__(self, label):
        self.label = label

    def __enter__(self):
        self.start = time.perf_counter()
        return self

    def __exit__(self, *exc):
        log("{} {:.2f} s".format(self.label, time.perf_counter() - self.start))
        return False


def log(message):
    try:
        app().log("DMD Tools: " + message)
    except Exception:
        pass


def as_list(collection):
    """All items of a Fusion collection, using asArray() (one call) when
    available instead of count + item(i) (one call per item)."""
    if isinstance(collection, (list, tuple)):
        return list(collection)
    try:
        return list(collection.asArray())
    except Exception:
        return [collection.item(i) for i in range(collection.count)]


# ---------------------------------------------------------------------------
# Projects and folders
# ---------------------------------------------------------------------------

def active_project():
    """The project the open file lives in, or the project selected in the
    Data Panel if the file hasn't been saved yet."""
    doc = app().activeDocument
    try:
        if doc and doc.isSaved and doc.dataFile:
            return doc.dataFile.parentProject
    except Exception:
        pass
    return app().data.activeProject


def project_names(hub):
    with timed("listing hub projects"):
        return [p.name for p in as_list(hub.dataProjects)]


def create_project(hub, name):
    """Create a project in the hub. (The API docs list this as add(); some
    pages call it createProject(), so both are tried.)"""
    projects = hub.dataProjects
    creator = getattr(projects, "add", None) or getattr(projects, "createProject")
    return creator(name)


def top_folder(project, name):
    return project.rootFolder.dataFolders.itemByName(name)


def ensure_folders(project):
    """Create any of the standard folders that are missing. Returns the
    names that were created. Existing folders and files are never touched."""
    created = []
    folders = project.rootFolder.dataFolders
    existing = {f.name for f in as_list(folders)}
    for name in nl.FOLDERS:
        if name not in existing:
            folders.add(name)
            created.append(name)
    return created


def iter_files(folder, skip=()):
    """Every file in a folder and its subfolders (except folders named in skip)."""
    for f in as_list(folder.dataFiles):
        yield f
    for sub in as_list(folder.dataFolders):
        if sub.name not in skip:
            for f in iter_files(sub, skip):
                yield f


def project_code(project):
    return nl.parse_project_name(project.name)[0] if project else ""


# ---------------------------------------------------------------------------
# Project snapshot (read once, shared by all dialogs)
# ---------------------------------------------------------------------------

class ProjectIndex:
    """File names in the project plus the 00 ASSEMBLY files, read once."""

    def __init__(self, project):
        self.project_id = project.id
        self.read_at = time.time()
        self.names = []            # (file id, file name) for every numbered-folder file
        self.top_candidates = []   # DataFiles in 00 ASSEMBLY
        with timed("reading project '{}'".format(project.name)):
            root = project.rootFolder
            for f in as_list(root.dataFiles):
                self.names.append((f.id, f.name))
            for folder in as_list(root.dataFolders):
                if folder.name in SKIP_FOLDERS:
                    continue
                for f in iter_files(folder):
                    self.names.append((f.id, f.name))
                    if folder.name == nl.FOLDERS[0]:
                        self.top_candidates.append(f)
        log("  {} files".format(len(self.names)))

    def fresh(self):
        return time.time() - self.read_at < SNAPSHOT_SECONDS

    def file_names(self, exclude_file=None):
        """All file names, leaving out exclude_file (the file being named).
        Files this add-in just created are recorded under a provisional id
        ("new:...") until the cloud gives them a real one, so those are
        matched by name instead."""
        if exclude_file is None:
            return [n for _, n in self.names]
        own_id, own_name = exclude_file.id, exclude_file.name
        return [n for i, n in self.names
                if i != own_id and not (i.startswith(NEW_ID) and n == own_name)]

    def top_assembly(self, code):
        for f in self.top_candidates:
            if code and nl.is_top_level_number(f.name, code):
                return f
        for f in self.top_candidates:
            if nl.SETTINGS_MARKER in (f.description or ""):
                return f
        return None


_indexes = {}


def project_index(project, refresh=False):
    if project is None:
        return None
    idx = _indexes.get(project.id)
    if refresh or idx is None or not idx.fresh():
        idx = ProjectIndex(project)
        _indexes[project.id] = idx
    return idx


NEW_ID = "new:"          # provisional id for files created this session


def note_file(project, file_id, name):
    """Record a file this add-in just created or renamed, so the snapshot
    stays correct without re-reading the project."""
    idx = _indexes.get(project.id) if project else None
    if idx is None:
        return
    idx.names = [(i, n) for i, n in idx.names if i != file_id]
    idx.names.append((file_id, name))


def note_new_file(project, name):
    note_file(project, NEW_ID + name, name)


def forget_project(project):
    if project is not None:
        _indexes.pop(project.id, None)


def find_top_assembly(project, code):
    idx = project_index(project)
    return idx.top_assembly(code) if idx else None


def project_file_names(project):
    idx = project_index(project)
    return idx.file_names() if idx else []


# ---------------------------------------------------------------------------
# Part numbers
# ---------------------------------------------------------------------------

def used_part_numbers(project, design=None, exclude_file=None, exclude_comp=None):
    """Everything that might hold a part number: file names in the project
    plus part numbers of components in the open design (which covers new
    parts that haven't been saved yet)."""
    idx = project_index(project)
    used = idx.file_names(exclude_file) if idx else []
    if design:
        for comp in design.allComponents:
            if exclude_comp is None or comp != exclude_comp:
                used.append(comp.partNumber)
    return used


def next_part_number(project, code, design=None):
    return nl.next_part_number(code, used_part_numbers(project, design))


# ---------------------------------------------------------------------------
# Settings (reference view)
# ---------------------------------------------------------------------------

def get_design_setting(design, key):
    attr = design.attributes.itemByName(ATTR_GROUP, key)
    return attr.value if attr else ""


def set_design_setting(design, key, value):
    if value:
        design.attributes.add(ATTR_GROUP, key, value)


def project_settings(project, code):
    top = find_top_assembly(project, code) if project else None
    return nl.decode_settings(top.description) if top else {}


def write_project_settings(top_file, settings):
    """Store settings in the top-level assembly's description, keeping any
    text you wrote before the [DMD] marker."""
    current = top_file.description or ""
    keep = current.split(nl.SETTINGS_MARKER, 1)[0].strip()
    merged = nl.decode_settings(current)
    merged.update({k: v for k, v in settings.items() if v})
    top_file.description = (keep + " " + nl.encode_settings(merged)).strip()


def reference_view(design, project, code):
    """This design's own setting first (no cloud read needed), then the project's."""
    value = get_design_setting(design, "refView") if design else ""
    if not value and project:
        value = project_settings(project, code).get("REF VIEW", "")
    return value


# ---------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------

def _cache_path():
    return os.path.join(CACHE_DIR, "materials.json")


def _load_material_cache():
    try:
        with open(_cache_path(), encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _save_material_cache(data):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(_cache_path(), "w", encoding="utf-8") as fh:
            json.dump(data, fh)
    except Exception:
        pass


class MaterialIndex:
    """Names of all physical materials, by library. Fusion's own libraries
    are read once and cached on disk per Fusion version (they only change
    when Fusion updates). Your own libraries are always read fresh, so new
    materials you add show up straight away. Material objects are only
    looked up when you actually apply one."""

    def __init__(self):
        self.entries = []          # (library name, material name)
        with timed("loading materials"):
            try:
                version = app().version
            except Exception:
                version = "?"
            cache = _load_material_cache()
            cached_libs = cache.get("libraries", {}) if cache.get("version") == version else {}
            changed = False
            for lib in as_list(app().materialLibraries):
                name = lib.name
                if not nl.is_user_library(name) and name in cached_libs:
                    names = cached_libs[name]
                else:
                    try:
                        names = [m.name for m in as_list(lib.materials)]
                    except Exception:
                        names = []
                    if not nl.is_user_library(name):
                        cached_libs[name] = names
                        changed = True
                for n in names:
                    self.entries.append((name, n))
            if changed:
                _save_material_cache({"version": version, "libraries": cached_libs})
        log("  {} materials".format(len(self.entries)))

    def choices(self, query):
        return nl.filter_materials(self.entries, query)

    @staticmethod
    def label(entry):
        lib, name = entry
        return name if not nl.is_user_library(lib) else "{}  [{}]".format(name, lib)

    def by_label(self, label):
        """Find the real Material object (only when applying)."""
        for lib_name, mat_name in self.entries:
            if self.label((lib_name, mat_name)) != label:
                continue
            lib = app().materialLibraries.itemByName(lib_name)
            if lib is None:
                return None
            try:
                found = lib.materials.itemByName(mat_name)
                if found:
                    return found
            except Exception:
                pass
            for m in as_list(lib.materials):
                if m.name == mat_name:
                    return m
        return None


def apply_material(comp, material):
    """Whole component: the component's material and every body in it."""
    comp.material = material
    for body in as_list(comp.bRepBodies):
        body.material = material


# ---------------------------------------------------------------------------
# Project parameters file
# ---------------------------------------------------------------------------

def find_params_file(project, code):
    """The project's 'CMD-HELLO PARAMETERS' file in 00 ASSEMBLY, or None."""
    idx = project_index(project)
    if idx is None:
        return None
    wanted = nl.params_file_name(code).lower()
    for f in idx.top_candidates:
        if f.name.lower() == wanted:
            return f
    return None


def note_params_file(project, data_file):
    idx = _indexes.get(project.id) if project else None
    if idx is not None and data_file not in idx.top_candidates:
        idx.top_candidates.append(data_file)


def read_parameters(design):
    """[{name, expression, unit, comment}] for every user parameter."""
    out = []
    for p in as_list(design.userParameters):
        try:
            comment = p.comment
        except Exception:
            comment = ""
        out.append({"name": p.name, "expression": p.expression,
                    "unit": p.unit, "comment": comment})
    return out


def _params_cache_path(project):
    safe = "".join(ch if ch.isalnum() else "_" for ch in project.id)
    return os.path.join(CACHE_DIR, "params_{}.json".format(safe))


def load_params_cache(project):
    """The last parameter list this add-in saw for the project (or None)."""
    try:
        with open(_params_cache_path(project), encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def save_params_cache(project, params):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(_params_cache_path(project), "w", encoding="utf-8") as fh:
            json.dump({"saved": time.strftime("%Y-%m-%d %H:%M"), "params": params}, fh)
    except Exception:
        pass


def open_document(data_file, visible=False):
    """An already-open document for this file, or open it (in the background
    by default). Returns (document, opened_here)."""
    docs = app().documents
    for i in range(docs.count):
        d = docs.item(i)
        try:
            if d.isSaved and d.dataFile.id == data_file.id:
                return d, False
        except Exception:
            pass
    with timed("opening " + data_file.name):
        return docs.open(data_file, visible), True
