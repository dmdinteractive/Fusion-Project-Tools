"""
DMDProjectTools.py - what Fusion runs when the add-in starts and stops.

It adds five buttons to Utilities > ADD-INS (promoted to the toolbar):
    New Project  - commands/new_project.py
    New Part     - commands/new_part.py
    Part Namer   - commands/part_namer.py
    Project Parameters - commands/project_params.py
    McMaster to Part   - commands/mcmaster_to_part.py

The naming rules (folders, part number format, flagged words, material
keywords) all live in lib/naming_logic.py.
"""

import os
import traceback

import adsk.core

from .lib import ui_helpers as uh
from .lib import auto_params
from .commands import new_project, new_part, part_namer, project_params, mcmaster_to_part

PANEL_ID = "SolidScriptsAddinsPanel"          # Utilities > ADD-INS
WORKSPACE_ID = "FusionSolidEnvironment"
HERE = os.path.dirname(os.path.abspath(__file__))

COMMANDS = [
    (new_project, os.path.join(HERE, "resources", "new_project")),
    (new_part, os.path.join(HERE, "resources", "new_part")),
    (part_namer, os.path.join(HERE, "resources", "part_namer")),
    (project_params, os.path.join(HERE, "resources", "project_params")),
    (mcmaster_to_part, os.path.join(HERE, "resources", "mcmaster_to_part")),
]


def _panel(ui):
    return ui.workspaces.itemById(WORKSPACE_ID).toolbarPanels.itemById(PANEL_ID)


def run(context):
    ui = None
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface
        uh.start_deferred()
        auto_params.start()         # keeps project parameters starred and linked
        panel = _panel(ui)
        for module, icons in COMMANDS:
            uh.add_button(module.CMD_ID, module.CMD_NAME, module.TOOLTIP, icons,
                          module.CreatedHandler(), panel)
    except Exception:
        if ui:
            ui.messageBox("DMD Project Tools failed to start:\n" + traceback.format_exc())


def stop(context):
    try:
        ui = adsk.core.Application.get().userInterface
        panel = _panel(ui)
        for module, _ in COMMANDS:
            uh.remove_button(module.CMD_ID, panel)
        auto_params.stop()
        uh.stop_deferred()
    except Exception:
        pass
