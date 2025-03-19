from . import ui_decors
from . import tex_ui_imp
from . import smb_ui_imp
from . import bfm_ui_imp

from pathlib import Path
if (Path(__file__).parent / 'sandbox_bpy.py').exists():
    from . import sandbox_bpy
else:
    sandbox_bpy = None

#TODO [частично сделано, но предупреждение остаётся]File-> new empty scene break hotkey addon

def register():
    ui_decors.register()
    tex_ui_imp.register()
    smb_ui_imp.register()
    bfm_ui_imp.register()
    if sandbox_bpy: sandbox_bpy.register()


def unregister():
    if sandbox_bpy: sandbox_bpy.unregister()
    smb_ui_imp.unregister()
    tex_ui_imp.unregister()
    ui_decors.unregister()
    bfm_ui_imp.unregister()

if __name__ == "__main__":
    register()