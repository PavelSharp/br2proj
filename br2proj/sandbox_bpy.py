import bpy
from bpy.types import Operator

from bpy_extras.io_utils import ImportHelper

from . import bfm_imp
from . import tex_imp
from mathutils import Vector, Matrix
import math

def _work():
    tex_prov = tex_imp.tex_provider('D:\Games\Bloodrayne 2_min\ART')
    skb_prov = bfm_imp.skb_provider('D:\Games\Bloodrayne 2_min\DATA')
    matr = Matrix.Rotation(math.radians(90.0), 4, 'Y') @ Matrix.Rotation(math.radians(90.0), 4, 'Z')
    linker = bfm_imp.bfm_linker(bfm_imp.LinkKinds.Collection, matr)
    bfm_imp.bfm_importer(linker=linker, create_materials=True, tex_prov=tex_prov, skb_prov=skb_prov).load("D:\Games\Bloodrayne 2_min\MODELS\RAYNE.BFM")

#Usage: press F3 in blender, type br2proj
class SandboxOp(Operator):
    "This operator is only for development. It should not be in the built version."
    bl_idname = "br2proj.sandbox_op"
    bl_label = "Br2Proj Sandbox Test Operator"
    bl_options = {'UNDO', 'PRESET'}
    def execute(self, context):
        _work()
        return {'FINISHED'}
    
def register():
    bpy.utils.register_class(SandboxOp)

def unregister():
    bpy.utils.unregister_class(SandboxOp)