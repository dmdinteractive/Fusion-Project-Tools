"""
part_namer.py - the Part Namer button.

In a Part or Assembly file it names the open file itself: name, part
number, description (and material, for parts). After you click Apply it
renames the file, e.g. "CMD-HELLO-015 BRACKET, MOTOR MOUNT" or
"CMD-HELLO-020 KIOSK ASSEMBLY, PHONE", and moves it to the matching
project folder (or saves it there if it's new).

The dialog changes with what's open:
  Part file      - Fabricated / Purchased, material picker
  Assembly file  - Subassembly / Purchased, "ASSEMBLY" after the noun,
                   part count instead of material
  Top-level      - the -000 file: number locked, stays in 00 ASSEMBLY

In a Hybrid design it works on a component you select, as before.
Linked parts inside an Assembly have to be named in their own file.
"""

import json

import adsk.core
import adsk.fusion

from ..lib import naming_logic as nl
from ..lib import fusion_data as fd
from ..lib import ui_helpers as uh
from ..lib.ui_helpers import find, val, text, set_choice

CMD_ID = "dmdPartNamer"
CMD_NAME = "Part Namer"
TOOLTIP = "Name this part or assembly noun-first, with a project part number and BOM description."

PICK_PROMPT = "(pick to fill Noun)"
NEW_NUMBER = "(new number)"
KEEP_MATERIAL = "(keep current material)"

_state = {}
_materials = None            # built once per session; libraries are large


def _reset_state():
    _state.clear()
    # kind: "part" or "assembly" when naming the open file, None for Hybrid selection.
    _state.update({"updating": False, "comp": None, "occ": None, "kind": None,
                   "top": False, "project": None, "used": [], "file": None})


def _design():
    return adsk.fusion.Design.cast(fd.app().activeProduct)


def _file_kind(design):
    """'part' or 'assembly' for Fusion's Part/Assembly design types,
    None for Hybrid (or older Fusion without design types)."""
    try:
        intent = design.designIntent
    except Exception:
        return None
    if intent == adsk.fusion.DesignIntentTypes.PartDesignIntentType:
        return "part"
    if intent == adsk.fusion.DesignIntentTypes.AssemblyDesignIntentType:
        return "assembly"
    return None


def _is_top_level(design, code):
    """The project's -000 file, or anything saved in 00 ASSEMBLY."""
    doc = fd.app().activeDocument
    names = [design.rootComponent.partNumber]
    if doc.isSaved:
        names.append(doc.dataFile.name)
        if doc.dataFile.parentFolder.name == nl.FOLDERS[0]:
            return True
    return bool(code) and any(nl.is_top_level_number(n, code) for n in names)


def _material_index():
    global _materials
    if _materials is None:
        _materials = fd.MaterialIndex()
    return _materials


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

class CreatedHandler(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        try:
            design = _design()
            if not design:
                fd.ui().messageBox("Open a design first.")
                args.command.isAutoExecute = True
                return
            _reset_state()
            kind = _file_kind(design)
            _state["kind"] = kind
            project = fd.active_project()
            _state["project"] = project
            code = fd.get_design_setting(design, "code") or fd.project_code(project)
            top = kind == "assembly" and _is_top_level(design, nl.clean_code(code))
            _state["top"] = top

            cmd = args.command
            cmd.okButtonText = "Apply"
            inputs = cmd.commandInputs

            if kind:
                doc = fd.app().activeDocument
                what = "top-level assembly" if top else ("assembly file" if kind == "assembly"
                                                         else "part file")
                inputs.addTextBoxCommandInput("target", "Naming",
                                              "This {}: {}".format(what, doc.name), 1, True)
            else:
                sel = inputs.addSelectionInput("sel", "Component", "Pick a component")
                sel.addSelectionFilter("Occurrences")
                sel.setSelectionLimits(1, 1)

            # --- Reference view ------------------------------------------
            g = inputs.addGroupCommandInput("grpRef", "Reference view (project)").children
            ref = g.addStringValueInput("refView", "Reference view",
                                        fd.reference_view(design, project, code))
            ref.tooltip = "How LH/RH and locations are judged. Set once in New Project."

            # --- Name -----------------------------------------------------
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
            asm = g.addBoolValueInput("asmWord", "Add ASSEMBLY after the noun", True, "",
                                      kind == "assembly" and not top)   # top-level = exhibit name
            asm.isVisible = kind == "assembly"
            hd = g.addDropDownCommandInput("hand", "Hand (mirror parts)",
                                           adsk.core.DropDownStyles.TextListDropDownStyle)
            for i, h in enumerate(nl.HANDS):
                hd.listItems.add(h, i == 0)
            g.addBoolValueInput("upper", "ALL CAPS", True, "", True)
            g.addTextBoxCommandInput("namePreview", "Name preview", "", 1, True)
            warn = g.addTextBoxCommandInput("posWarn", "Heads up", "", 3, True)
            warn.isVisible = False

            # --- Part number ----------------------------------------------
            g = inputs.addGroupCommandInput("grpPN", "Project part number").children
            src = g.addRadioButtonGroupCommandInput("source", "Type")
            if top:
                src.listItems.add(nl.TOP_LEVEL, True)
                src.isEnabled = False
            else:
                choices = nl.ASSEMBLY_TYPES if kind == "assembly" else ["Fabricated", "Purchased"]
                for i, choice in enumerate(choices):
                    src.listItems.add(choice, i == 0)
            g.addBoolValueInput("usePN", "Assign project number", True, "", True)
            g.addStringValueInput("code", "Project code", code)
            g.addStringValueInput("pn", "Base number", "")
            mate = g.addDropDownCommandInput("mate", "Mirror partner",
                                             adsk.core.DropDownStyles.TextListDropDownStyle)
            mate.listItems.add(NEW_NUMBER, True)
            mate.isVisible = False
            g.addTextBoxCommandInput("pnPreview", "Part number preview", "", 1, True)

            # --- Vendor (purchased only) -----------------------------------
            vg = inputs.addGroupCommandInput("grpVendor", "Vendor (purchased parts)")
            v = vg.children
            vdd = v.addDropDownCommandInput("vendor", "Vendor",
                                            adsk.core.DropDownStyles.TextListDropDownStyle)
            for i, (label, _) in enumerate(nl.VENDORS):
                vdd.listItems.add(label, i == 0)
            v.addStringValueInput("vendorName", "Vendor name", "")
            v.addStringValueInput("vendorPn", "Vendor part #", "")
            vg.isVisible = False

            # --- Material (parts only; an assembly's comes from its parts) --
            mg = inputs.addGroupCommandInput("grpMat", "Material (whole part)")
            mg.isVisible = kind != "assembly"
            g = mg.children
            g.addTextBoxCommandInput("matCurrent", "Current", "", 1, True)
            g.addStringValueInput("matFilter", "Search", "")
            g.addDropDownCommandInput("matPick", "Material",
                                      adsk.core.DropDownStyles.TextListDropDownStyle)
            g.addBoolValueInput("incMaterial", "Include in description", True, "", True)

            # --- Info pulled from the part ---------------------------------
            is_asm = kind == "assembly"
            g = inputs.addGroupCommandInput(
                "grpInfo", "From the {} (tick to include)".format(
                    "assembly" if is_asm else "part")).children
            if is_asm:
                g.addBoolValueInput("incCount", "Include part count", True, "", True)
                g.addStringValueInput("count", "Contents", "")
            g.addBoolValueInput("incSize", "Include overall size" if is_asm else "Include size",
                                True, "", False)
            g.addStringValueInput("size", "Size (L x W x H)", "")
            g.addBoolValueInput("incMass", "Include total mass" if is_asm else "Include mass",
                                True, "", False)
            g.addStringValueInput("mass", "Mass", "")
            g.addBoolValueInput("incLocation", "Include location", True, "", False)
            g.addStringValueInput("location", "Location (per ref view)", "")
            g.addStringValueInput("notes", "Extra notes", "")
            g.addTextBoxCommandInput("descPreview", "Description preview", "", 3, True)

            # --- File (part and assembly files) -----------------------------
            if kind:
                g = inputs.addGroupCommandInput("grpFile", "File").children
                saved = fd.app().activeDocument.isSaved
                label = "Rename file and move to matching folder" if saved \
                    else "Save into this project's matching folder"
                g.addBoolValueInput("fileOps", label, True, "", True)
                g.addTextBoxCommandInput("filePreview", "File", "", 2, True)

            inputs.addTextBoxCommandInput("status", "", "", 2, True)

            uh.connect(cmd, ((ActivateHandler(), cmd.activate),
                             (InputChangedHandler(), cmd.inputChanged),
                             (ValidateHandler(), cmd.validateInputs),
                             (ExecuteHandler(), cmd.execute)))
        except Exception:
            uh.show_error("Part Namer")


class ActivateHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        inputs = args.command.commandInputs
        timer = fd.timed("Part Namer ready")
        timer.__enter__()
        try:
            _state["updating"] = True
            _rebuild_materials(inputs)
            if _state["kind"]:
                _load(inputs, _design().rootComponent)
            elif find(inputs, "sel").selectionCount:
                _load_from_selection(inputs)
        except Exception:
            uh.show_error("Part Namer")
        finally:
            _state["updating"] = False
        _refresh(inputs)
        timer.__exit__()


class InputChangedHandler(adsk.core.InputChangedEventHandler):
    def notify(self, args):
        if _state["updating"]:
            return
        try:
            changed = args.input
            inputs = uh.all_inputs(args)
            _state["updating"] = True

            if changed.id == "sel":
                _load_from_selection(inputs)
            elif changed.id == "nounPick":
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
            elif changed.id == "source":
                find(inputs, "grpVendor").isVisible = _is_purchased(inputs)
            elif changed.id == "matFilter":
                _rebuild_materials(inputs)

            _refresh(inputs)
        except Exception:
            uh.show_error("Part Namer")
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
            comp = _state["comp"]
            design = _design()
            file_mode = bool(_state["kind"])

            if not file_mode:
                comp.name = _name(inputs)      # a part/assembly file takes its name from the file
            if val(inputs, "usePN"):
                comp.partNumber = _full_pn(inputs)
            material = _chosen_material(inputs)
            if material:
                fd.apply_material(comp, material)
            comp.description = _description(inputs)

            keep = ["source", "vendor", "vendorName", "vendorPn", "incMaterial", "incSize",
                    "size", "incMass", "mass", "notes", "upper", "hand", "incLocation",
                    "location", "asmWord", "incCount"]
            comp.attributes.add(fd.ATTR_GROUP, "partNamer",
                                json.dumps({k: val(inputs, k) for k in keep
                                            if find(inputs, k) is not None}))
            fd.set_design_setting(design, "refView", text(inputs, "refView").upper())
            fd.set_design_setting(design, "code", nl.clean_code(text(inputs, "code")))

            if file_mode and val(inputs, "fileOps"):
                doc = fd.app().activeDocument
                fname = _file_name(inputs)
                folder = nl.FOLDER_FOR_TYPE[val(inputs, "source")]
                uh.run_later("Saving/renaming the file",
                             lambda: _file_ops(doc, fname, folder))
        except Exception:
            uh.show_error("Could not apply")


# ---------------------------------------------------------------------------
# After Apply: file work (can't happen while the dialog is open)
# ---------------------------------------------------------------------------

def _file_ops(doc, fname, folder_name):
    if doc.isSaved:
        df = doc.dataFile
        notes = []
        if df.name != fname:
            try:
                old_name = df.name
                df.name = fname
                fd.note_file(df.parentProject, df.id, fname)
                _drop_provisional(df.parentProject, old_name)
                notes.append("Renamed to " + fname)
            except Exception:
                notes.append("Couldn't rename the file while it's open. Rename it in the "
                             "Data Panel to:\n" + fname)
        target = fd.top_folder(df.parentProject, folder_name)
        if target is None:
            fd.ensure_folders(df.parentProject)
            target = fd.top_folder(df.parentProject, folder_name)
        if target and df.parentFolder.id != target.id:
            try:
                df.move(target)
                notes.append("Moved to " + folder_name)
            except Exception:
                notes.append("Couldn't move the file while it's open. Drag it to "
                             + folder_name + " in the Data Panel.")
        if notes:
            fd.ui().messageBox("\n".join(notes), "Part Namer")
    else:
        project = fd.active_project()
        fd.ensure_folders(project)
        target = fd.top_folder(project, folder_name)
        doc.saveAs(fname, target, "", "")
        fd.note_new_file(project, fname)
        fd.ui().messageBox("Saved as {}\nin {} / {}".format(fname, project.name, folder_name),
                           "Part Namer")


def _drop_provisional(project, name):
    """A file created this session (provisional id) has now been renamed
    under its real id: forget the provisional entry with its old name."""
    idx = fd._indexes.get(project.id)
    if idx:
        idx.names = [(i, n) for i, n in idx.names
                     if not (i.startswith(fd.NEW_ID) and n == name)]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_purchased(inputs):
    return val(inputs, "source") == "Purchased"


def _code(inputs):
    return nl.clean_code(text(inputs, "code"))


def _name(inputs):
    mods = [val(inputs, "mod1"), val(inputs, "mod2"), val(inputs, "mod3")]
    noun = val(inputs, "noun")
    if _state["kind"] == "assembly" and val(inputs, "asmWord"):
        noun = nl.assembly_noun(noun)
    return nl.compose_name(noun, mods, val(inputs, "upper"), val(inputs, "hand"))


def _full_pn(inputs):
    return nl.full_part_number(val(inputs, "pn"), val(inputs, "hand"))


def _file_name(inputs):
    pn = _full_pn(inputs) if val(inputs, "usePN") else ""
    return nl.file_name(pn, _name(inputs))


def _chosen_material(inputs):
    label = val(inputs, "matPick")
    if not label or label == KEEP_MATERIAL:
        return None
    return _material_index().by_label(label)


def _current_material_name(comp):
    if comp is None:
        return ""
    for i in range(comp.bRepBodies.count):
        m = comp.bRepBodies.item(i).material
        if m:
            return m.name
    return comp.material.name if comp.material else ""


def _description(inputs):
    upper = val(inputs, "upper")
    sections = []
    if _state["kind"] == "assembly":
        if val(inputs, "incCount"):
            sections.append((val(inputs, "count"), False))
    elif val(inputs, "incMaterial"):
        mat = _chosen_material(inputs)
        sections.append((mat.name if mat else _current_material_name(_state["comp"]), False))
    if val(inputs, "incSize"):
        sections.append((val(inputs, "size"), True))
    if val(inputs, "incMass"):
        sections.append((val(inputs, "mass"), True))
    ref_view = val(inputs, "refView")
    sections.append((nl.hand_text(val(inputs, "hand"), ref_view), False))
    if val(inputs, "incLocation"):
        sections.append((nl.location_text(val(inputs, "location"), ref_view), False))
    sections.append((val(inputs, "notes"), False))
    if _is_purchased(inputs):
        sections.append((nl.vendor_text(val(inputs, "vendor"), val(inputs, "vendorName"),
                                        val(inputs, "vendorPn")), True))
    return nl.compose_description(sections, upper)


def _collect_used():
    """Part numbers/file names elsewhere in the project, from the shared
    project snapshot (read from the cloud at most once every few minutes)."""
    own_file = _state["file"]
    _state["used"] = fd.used_part_numbers(_state["project"], _design(),
                                          exclude_file=own_file, exclude_comp=_state["comp"])


def _suggest_pn(inputs):
    code = _code(inputs)
    if not code:
        return ""
    if _state["top"]:
        return nl.format_part_number(code, nl.TOP_ASSEMBLY_NUMBER)
    comp = _state["comp"]
    for existing in (comp.partNumber if comp else "",
                     _state["file"].name if _state["file"] else ""):
        if nl.matches_prefix(existing, code) not in (None, nl.TOP_ASSEMBLY_NUMBER):
            return nl.base_part_number(existing, code)   # keep the number it already has
    return nl.next_part_number(code, _state["used"])


def _taken(code, pn):
    num, hand = nl.parse_part_number(pn, code)
    if num is None:
        return False
    return any(nl.parse_part_number(u, code) == (num, hand) for u in _state["used"])


def _rebuild_mates(inputs):
    mate = find(inputs, "mate")
    options = nl.unpaired_mates(_code(inputs), _state["used"], val(inputs, "hand"))
    mate.listItems.clear()
    mate.listItems.add(NEW_NUMBER, True)
    for base in options:
        mate.listItems.add(base, False)
    mate.isVisible = bool(options)


def _rebuild_materials(inputs):
    index = _material_index()
    dd = find(inputs, "matPick")
    dd.listItems.clear()
    dd.listItems.add(KEEP_MATERIAL, True)
    for entry in index.choices(text(inputs, "matFilter")):
        dd.listItems.add(index.label(entry), False)


def _problems(inputs):
    issues = []
    comp = _state["comp"]
    if comp is None:
        return ["Select a component."]
    occ = _state["occ"]
    if occ is not None and occ.isReferencedComponent:
        return ["This is a linked part. Open its own file (right-click > Open) and run "
                "Part Namer there."]
    if not text(inputs, "noun"):
        issues.append("Enter a noun.")
    if val(inputs, "usePN"):
        code = _code(inputs)
        pn = _full_pn(inputs)
        if not code:
            issues.append("Enter the project code (e.g. CMD-HELLO).")
        elif nl.matches_prefix(pn, code) is None:
            issues.append("Part number should look like {}-001.".format(code))
        elif not _state["top"] and nl.is_top_level_number(pn, code):
            issues.append("{} is reserved for the top-level assembly.".format(pn))
        elif not _state["top"] and _taken(code, pn):
            issues.append("{} is already used in this project.".format(pn))
    if not text(inputs, "refView"):
        if val(inputs, "hand") in nl.OPPOSITE_HAND:
            issues.append("Set a reference view first: LH/RH means nothing without one.")
        if val(inputs, "incLocation") and text(inputs, "location"):
            issues.append("Set a reference view first: the location is measured from it.")
    if _state["kind"] and val(inputs, "fileOps") and not fd.app().activeDocument.isSaved:
        if _state["project"] is None:
            issues.append("Pick a project in the Data Panel to save into.")
    return issues


def _refresh(inputs):
    find(inputs, "namePreview").text = _name(inputs)
    mods = " ".join(val(inputs, k) or "" for k in ("noun", "mod1", "mod2", "mod3"))
    warning = nl.position_warning(mods)
    find(inputs, "posWarn").text = warning
    find(inputs, "posWarn").isVisible = bool(warning)
    use_pn = bool(val(inputs, "usePN"))
    find(inputs, "pnPreview").text = _full_pn(inputs) if use_pn else "(not assigned)"
    find(inputs, "pn").isEnabled = use_pn and not _state["top"]
    find(inputs, "code").isEnabled = use_pn
    find(inputs, "hand").isEnabled = not _state["top"]
    find(inputs, "location").isEnabled = bool(val(inputs, "incLocation"))
    find(inputs, "vendorName").isVisible = (val(inputs, "vendor") or "").startswith("Other")
    find(inputs, "matCurrent").text = _current_material_name(_state["comp"]) or "(none)"
    find(inputs, "descPreview").text = _description(inputs)
    if _state["kind"]:
        folder = nl.FOLDER_FOR_TYPE[val(inputs, "source")]
        find(inputs, "filePreview").text = "{}\nin {}".format(_file_name(inputs), folder)
    find(inputs, "status").text = "  ".join(_problems(inputs))


def _load_from_selection(inputs):
    sel = find(inputs, "sel")
    occ = adsk.fusion.Occurrence.cast(sel.selection(0).entity) if sel.selectionCount else None
    _state["occ"] = occ
    _state["comp"] = occ.component if occ else None
    if occ and not occ.isReferencedComponent:
        _load(inputs, occ.component)


def _load(inputs, comp):
    """Fill the dialog with what we know about this component."""
    _state["comp"] = comp
    doc = fd.app().activeDocument
    _state["file"] = doc.dataFile if (_state["kind"] and doc.isSaved) else None
    _collect_used()
    code = _code(inputs)

    source_name = comp.name
    if _state["kind"] and _state["file"]:
        source_name = _state["file"].name
    noun, mods = nl.parse_name(nl.strip_part_number(source_name, code))
    mods, hand = nl.split_hand(mods)
    if _state["kind"] == "assembly":
        noun, _ = nl.strip_assembly_word(noun)     # the checkbox adds it back
    find(inputs, "noun").value = noun
    for i, m in enumerate(mods, start=1):
        find(inputs, "mod{}".format(i)).value = m

    for existing in (comp.partNumber, source_name):
        _, pn_hand = nl.parse_part_number(existing, code)
        if pn_hand != "None":
            hand = pn_hand
            break
    set_choice(inputs, "hand", hand)

    find(inputs, "size").value = _size_of(comp)
    find(inputs, "mass").value = _mass_of(comp)
    if _state["kind"] == "assembly":
        find(inputs, "count").value = _contents_of(comp)

    attr = comp.attributes.itemByName(fd.ATTR_GROUP, "partNamer")
    if attr:
        try:
            for key, value in json.loads(attr.value).items():
                if key in ("source", "vendor", "hand"):
                    if key == "source" and _state["top"]:
                        continue
                    set_choice(inputs, key, value)
                elif find(inputs, key) is not None and value is not None:
                    find(inputs, key).value = value
        except Exception:
            pass
    find(inputs, "grpVendor").isVisible = _is_purchased(inputs)

    _rebuild_mates(inputs)
    find(inputs, "pn").value = _suggest_pn(inputs)


def _contents_of(comp):
    """What goes together at this level: direct parts and subassemblies,
    counted per instance (4 of the same bracket = 4 PARTS)."""
    parts = subs = 0
    for i in range(comp.occurrences.count):
        occ = comp.occurrences.item(i)
        if occ.component.occurrences.count:
            subs += 1
        else:
            parts += 1
    return nl.contents_text(parts, subs)


def _length_units():
    return _design().fusionUnitsManager.defaultLengthUnits


def _size_of(comp):
    units = _length_units()
    um = _design().fusionUnitsManager
    dims_cm = None
    try:
        obb = comp.orientedMinimumBoundingBox
        if obb:
            dims_cm = [obb.length, obb.width, obb.height]
    except Exception:
        pass
    if not dims_cm:
        bb = comp.boundingBox
        if not bb:
            return ""
        dims_cm = [bb.maxPoint.x - bb.minPoint.x, bb.maxPoint.y - bb.minPoint.y,
                   bb.maxPoint.z - bb.minPoint.z]
    return nl.format_dims([um.convert(d, "cm", units) for d in dims_cm], units)


def _mass_of(comp):
    try:
        kg = comp.physicalProperties.mass
    except Exception:
        return ""
    return nl.format_mass(kg, _length_units() in ("in", "ft"))
