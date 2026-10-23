"""
name_pickers.py - the Noun / Modifier / Reference view drop-downs, shared
by Part Namer, New Part, McMaster to Part and New Project.

Fusion has no "type or pick" box, so each field is a drop-down sitting
right above its text box: picking a word fills the box, and you can still
type anything in the box yourself. The modifier drop-downs follow the noun:
type or pick PANEL and they offer ACCESS, SIDE, GRAPHIC ...

How a command uses it:
    in CommandCreated:   pickers = name_pickers.add_name_inputs(group, assembly=...)
    in InputChanged:     if name_pickers.handle_change(inputs, changed): ...
    after loading a name into the boxes: name_pickers.refresh_modifiers(inputs)
"""

import os
import subprocess
import sys

import adsk.core

from . import word_lists as wl
from .ui_helpers import find, val

NOUN_PROMPT = "(pick to fill Noun)"
MOD_PROMPT = "(pick to fill Modifier {})"
REF_PROMPT = "(pick to fill Reference view)"
MOD_SLOTS = 3
EDIT_BUTTON_ID = "editWords"

_lists = {"words": None}


def words():
    """Built-in + your lists, read once per dialog (load_words refreshes)."""
    if _lists["words"] is None:
        load_words()
    return _lists["words"]


def load_words():
    _lists["words"] = wl.WordLists.load()
    return _lists["words"]


def _dropdown(group, input_id, label):
    return group.addDropDownCommandInput(input_id, label,
                                         adsk.core.DropDownStyles.TextListDropDownStyle)


def _fill(dd, prompt, items):
    dd.listItems.clear()
    dd.listItems.add(prompt, True)
    for item in items:
        dd.listItems.add(item, False)


def add_name_inputs(group, assembly=False):
    """Noun picker + Noun box, then a picker + box for each modifier."""
    load_words()
    dd = _dropdown(group, "nounPick", "Nouns")
    _fill(dd, NOUN_PROMPT, words().nouns(assembly))
    dd.tooltip = "Pick a noun, or type your own in the box below."
    group.addStringValueInput("noun", "Noun", "")
    for i in range(1, MOD_SLOTS + 1):
        pick = _dropdown(group, "modPick{}".format(i), "Suggestions")
        pick.tooltip = "Words that fit the noun. Pick one, or type in the box below."
        group.addStringValueInput("mod{}".format(i), "Modifier {}".format(i), "")
    refresh_modifiers(group)
    btn = group.addBoolValueInput(EDIT_BUTTON_ID, "Edit my word lists", False, "", False)
    btn.text = "Open file"
    btn.tooltip = "Add your own nouns, modifiers and reference views."
    btn.tooltipDescription = wl.user_file_path()


def add_ref_view_picker(group, current=""):
    """Reference-view picker; add it just before the refView string box."""
    load_words()
    dd = _dropdown(group, "refPick", "Common views")
    _fill(dd, REF_PROMPT, words().reference_views(current))
    return dd


def refresh_modifiers(inputs):
    """Rebuild each modifier drop-down for the current noun, leaving out
    words already used in the other modifier boxes."""
    noun = val(inputs, "noun") or ""
    used = [val(inputs, "mod{}".format(i)) or "" for i in range(1, MOD_SLOTS + 1)]
    key = wl.noun_key(noun)
    for i in range(1, MOD_SLOTS + 1):
        dd = find(inputs, "modPick{}".format(i))
        if dd is None:
            continue
        others = [u for j, u in enumerate(used, start=1) if j != i]
        prompt = MOD_PROMPT.format(i)
        if key and words().has_own_modifiers(noun):
            prompt = "(words for {}: pick to fill Modifier {})".format(key, i)
        _fill(dd, prompt, words().modifiers(noun, exclude=others))


def handle_change(inputs, changed):
    """Deal with the shared inputs. Returns True if it was one of them."""
    cid = changed.id
    if cid == "nounPick" or cid.startswith("modPick") or cid == "refPick":
        item = changed.selectedItem
        if item and changed.listItems.count and item.index != 0:
            target = {"nounPick": "noun", "refPick": "refView"}.get(cid) \
                or "mod" + cid[len("modPick"):]
            find(inputs, target).value = item.name
            changed.listItems.item(0).isSelected = True
        if cid != "refPick":
            refresh_modifiers(inputs)
        return True
    if cid == "noun" or (cid.startswith("mod") and cid[3:].isdigit()):
        refresh_modifiers(inputs)
        return True
    if cid == EDIT_BUTTON_ID:
        open_user_file()
        return True
    return False


def open_user_file():
    """Create your word list if needed and open it in the text editor."""
    path = wl.ensure_user_file()
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-t", path])
        elif os.name == "nt":
            os.startfile(path)            # noqa - Windows only
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        adsk.core.Application.get().userInterface.messageBox(
            "Open this file in a text editor:\n" + path, "My word lists")
