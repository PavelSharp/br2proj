from . import bfm_imp
from . import tex_imp
from mathutils import Vector, Matrix
import math

def work():
    tex_prov = tex_imp.tex_provider('D:\Games\Bloodrayne 2_min\ART')
    skb_prov = bfm_imp.skb_provider('D:\Games\Bloodrayne 2_min\DATA')
    matr = Matrix.Rotation(math.radians(90.0), 4, 'Y') @ Matrix.Rotation(math.radians(90.0), 4, 'Z')
    linker = bfm_imp.bfm_linker(bfm_imp.LinkKinds.Collection, matr)
    bfm_imp.bfm_importer(linker=linker, create_materials=True, tex_prov=tex_prov, skb_prov=skb_prov).load("D:\Games\Bloodrayne 2_min\MODELS\RAYNE.BFM")
