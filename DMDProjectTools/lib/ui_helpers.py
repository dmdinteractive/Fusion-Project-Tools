"""
ui_helpers.py - plumbing shared by every command.

Two jobs:
1. Reading and writing dialog inputs by id (including inputs inside groups).
2. "Run this after the dialog closes." Fusion won't create, save or rename
   files while a command dialog is running, so commands queue that work
   here and it runs a moment later.
"""

import traceback

import adsk.core

_app = adsk.core.Application.get()
_ui = _app.userInterface

handlers = []                 # Fusion needs handler objects kept alive

DEFERRED_EVENT_ID = "DMDProjectToolsDeferred"
_queue = []
_event = None


# ---------------------------------------------------------------------------
# Deferred work
# ---------------------------------------------------------------------------

class _DeferredHandler(adsk.core.CustomEventHandler):
    def notify(self, args):
        while _queue:
            label, fn = _queue.pop(0)
            try:
                fn()
            except Exception:
                _ui.messageBox("{} failed:\n{}".format(label, traceback.format_exc()))


def start_deferred():
    global _event
    try:
        _app.unregisterCustomEvent(DEFERRED_EVENT_ID)
    except Exception:
        pass
    _event = _app.registerCustomEvent(DEFERRED_EVENT_ID)
    h = _DeferredHandler()
    _event.add(h)
    handlers.append(h)


def stop_deferred():
    try:
        _app.unregisterCustomEvent(DEFERRED_EVENT_ID)
    except Exception:
        pass


def run_later(label, fn):
    """Queue fn to run once the current dialog has closed."""
    _queue.append((label, fn))
    _app.fireCustomEvent(DEFERRED_EVENT_ID, "")


# ---------------------------------------------------------------------------
# Dialog inputs
# ---------------------------------------------------------------------------

def find(inputs, input_id):
    """Find an input by id, including inputs inside groups."""
    found = inputs.itemById(input_id)
    if found:
        return found
    for i in range(inputs.count):
        group = adsk.core.GroupCommandInput.cast(inputs.item(i))
        if group:
            found = find(group.children, input_id)
            if found:
                return found
    return None


_CHOICE_TYPES = None


def val(inputs, input_id):
    """The current value of an input: text, True/False, or the chosen
    item's name for drop-downs and radio buttons."""
    global _CHOICE_TYPES
    if _CHOICE_TYPES is None:
        _CHOICE_TYPES = (adsk.core.RadioButtonGroupCommandInput.classType(),
                         adsk.core.DropDownCommandInput.classType())
    item = find(inputs, input_id)
    if item is None:
        return None
    if item.objectType in _CHOICE_TYPES:
        return item.selectedItem.name if item.selectedItem else ""
    return item.value


def text(inputs, input_id):
    return (val(inputs, input_id) or "").strip()


def set_choice(inputs, input_id, name):
    item = find(inputs, input_id)
    if item is None:
        return
    for i in range(item.listItems.count):
        li = item.listItems.item(i)
        if li.name == name:
            li.isSelected = True


def all_inputs(args):
    """The whole dialog's inputs from any event. (Event args sometimes only
    carry the group that changed, which caused the v1.1 'pnPreview' error.)"""
    cmd = getattr(args, "command", None)
    if cmd is None:
        changed = getattr(args, "input", None)
        if changed is not None:
            cmd = changed.parentCommand
        else:
            cmd = args.firingEvent.sender
    return cmd.commandInputs


def add_button(cmd_id, name, tooltip, resources, created_handler, panel):
    old = _ui.commandDefinitions.itemById(cmd_id)
    if old:
        old.deleteMe()
    cmd_def = _ui.commandDefinitions.addButtonDefinition(cmd_id, name, tooltip, resources)
    cmd_def.commandCreated.add(created_handler)
    handlers.append(created_handler)
    if not panel.controls.itemById(cmd_id):
        ctrl = panel.controls.addCommand(cmd_def)
        ctrl.isPromoted = True
    return cmd_def


def remove_button(cmd_id, panel):
    ctrl = panel.controls.itemById(cmd_id)
    if ctrl:
        ctrl.deleteMe()
    cmd_def = _ui.commandDefinitions.itemById(cmd_id)
    if cmd_def:
        cmd_def.deleteMe()


def connect(cmd, pairs):
    """Attach (handler, event) pairs and keep the handlers alive."""
    for handler, event in pairs:
        event.add(handler)
        handlers.append(handler)


def show_error(where):
    _ui.messageBox("{}:\n{}".format(where, traceback.format_exc()))
