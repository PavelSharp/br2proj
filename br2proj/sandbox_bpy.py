import bpy
from bpy.types import Operator
import bpy.types

from bpy_extras.io_utils import ImportHelper
import bpy_extras
import struct

from . import bfm_imp
from . import tex_imp
from mathutils import Vector, Matrix
import math
from math import pi

from .sern import jexplore
from .sern import sern_read
from .ani import *
from .skb import *

from typing import Tuple






def _work():
    bfm_imp.bfm_builder.bone_orient = Vector((1,0,0))
    tex_prov = tex_imp.tex_provider('D:\Games\Bloodrayne 2_min\ART')
    #phonemes, RUN_FORWARD STAND_ALERT locked_idle
    with open('D:/Games/Bloodrayne 2_min/ANIMATIONS/RAYNE/RUN_FORWARD.ani', 'rb') as file:
        ani:ANI_File = sern_read.reader(file).auto_read(ANI_File)
        #jexplore.jprint(dict, path = "D:/br2dec/blender/br2proj/alert.json")

    skb_prov = bfm_imp.skb_provider('D:\Games\Bloodrayne 2_min\DATA')
    
    matr = Matrix((
        (1,  0,  0,0),
        (0,  0,  1,0),
        (0, 1,  0,0),
        (0, 0, 0, 1),
    ))
    #matr = Matrix.Rotation(math.radians(90.0), 4, 'Y') @ Matrix.Rotation(math.radians(90.0), 4, 'Z')
    linker = bfm_imp.bfm_linker(bfm_imp.LinkKinds.Collection, transform=matr)
    coll = bfm_imp.bfm_importer(linker=linker, create_materials = True, skb_prov=skb_prov, tex_prov=tex_prov).load("D:\Games\Bloodrayne 2_min\MODELS\RAYNE.BFM")
    
    arm:bpy.types.Object = None
    for obj in coll.objects:
        if obj.type == 'ARMATURE': arm = obj

    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="POSE")

    action = bpy.data.actions.new(name="ANI_Anim1")
    arm.animation_data_create()
    arm.animation_data.action = action

    fps = 24 
    numFrames = ani.header.numFrames
    pool_ind = 0 

    def check_kf(kf):
        if kf<0 or kf>=ani.header.numFrames:
            raise ValueError(f"Keyfram err, kf was {kf}")
    def unp(kf, *args):
        check_kf(kf)
        return (kf, *tuple((arg / 32768) * math.pi for arg in args))

    with open('D:/Games/Bloodrayne 2_min/DATA/RAYNE.SKB', 'rb') as file:
        rayne_skb:SKB_File = sern_read.reader(file).auto_read(SKB_File)

    def sym(name:str):
        #for bone in rayne_skb.bones:
        #    if ( bone.symBone!=-1 and str(bone.name)==name):
        #        print(1)
        #        return str(rayne_skb.bones[bone.symBone].name)
        return name


    for ani_bone in ani.used_bones:
        tt = ani_bone.tt
        bpy_bone = arm.pose.bones[sym(str(ani_bone.name))]
        #qw = arm.data.bones[str(ani_bone.name)]
        #matr = Matrix.Translation(qw.head)
        bpy_bone.rotation_mode = 'XYZ'

        is_sym = False
        for bone in rayne_skb.bones:
            if bone.symBone!=-1 and str(bone.name)==bpy_bone.name:
                is_sym = True
                break
        
        for k in range(ani_bone.numKeyFrames):
            if tt in [0, 1]:  # Позиция
                kf,x,y,z = struct.unpack("ifff", bytes(ani.animPool[pool_ind:pool_ind + 16]))
                check_kf(kf)
                pool_ind+=16

                if tt == 0:
                    bpy_bone.location =Vector((x,y,z))
                    bpy_bone.keyframe_insert("location", frame=kf)
                elif tt == 1:
                    bpy_bone.scale = (x, y, z) 
                    bpy_bone.keyframe_insert("scale", frame=kf)

            elif tt in [2,3,4]:
                vl = struct.unpack("hh", bytes(ani.animPool[pool_ind:pool_ind + 4]))
                pool_ind+=4
                kf, ang1 = unp(*vl)

                if tt == 2:
                    if is_sym: ang1=-ang1
                    bpy_bone.rotation_euler.x = ang1
                    bpy_bone.keyframe_insert("rotation_euler", index=0, frame=kf)
                elif tt == 3:
                    #if is_sym: ang1=-ang1
                    bpy_bone.rotation_euler.y = ang1
                    bpy_bone.keyframe_insert("rotation_euler", index=1, frame=kf)
                elif tt == 4:
                    #if is_sym: ang1=-ang1
                    bpy_bone.rotation_euler.z = ang1
                    bpy_bone.keyframe_insert("rotation_euler", index=2, frame=kf)

            elif tt in [5,6,7]:
                vl = struct.unpack("hhh", bytes(ani.animPool[pool_ind:pool_ind + 6]))
                pool_ind+=6
                pool_ind = (pool_ind+4-1)//4*4

                kf, ang1, ang2 = unp(*vl)

                if tt == 5:  # XY
                    bpy_bone.rotation_euler.x = ang1
                    bpy_bone.rotation_euler.y = ang2
                    bpy_bone.keyframe_insert("rotation_euler", index=0, frame=kf)
                    bpy_bone.keyframe_insert("rotation_euler", index=1, frame=kf)
                elif tt == 6:  # YZ
                    bpy_bone.rotation_euler.y = ang1
                    bpy_bone.rotation_euler.z = ang2
                    bpy_bone.keyframe_insert("rotation_euler", index=1, frame=kf)
                    bpy_bone.keyframe_insert("rotation_euler", index=2, frame=kf)
                else:
                    bpy_bone.rotation_euler.z = ang2
                    bpy_bone.rotation_euler.x = ang1
                    bpy_bone.keyframe_insert("rotation_euler", index=2, frame=kf)
                    bpy_bone.keyframe_insert("rotation_euler", index=0, frame=kf)
                

            elif tt==8:
                vl = struct.unpack("hhhh", bytes(ani.animPool[pool_ind:pool_ind + 8]))
                pool_ind+=8
                kf, ang1, ang2, ang3 = unp(*vl)
                if is_sym: ang1=-ang1
                bpy_bone.rotation_euler = (ang1, ang2, ang3)
                bpy_bone.keyframe_insert("rotation_euler", frame=kf)
                #print(vl[0])
            else:
                raise ValueError('TT ERROR')
            
    #if pool_ind!=ani.header.animPoolSize: TODO extra data RUN_FORWARD?
        #raise ValueError(f'The end has not been reached, ind:{pool_ind}, size:{ani.header.animPoolSize}')
    print(pool_ind)
    print(ani.header.animPoolSize)
            #    anim_pool_index += 4
                
            #    bone.location.x = value  # Например, изменяем X
            #    bone.keyframe_insert("location", index=0, frame=frame+1)

            #elif tt == 8:  # Вращение (кватернион)
            #    quat_x = struct.unpack("f", bytes(ani_data["animPool"][anim_pool_index:anim_pool_index + 4]))[0]
            #    anim_pool_index += 4
            #    bone.rotation_quaternion = (1, quat_x, 0, 0)  # Заглушка (полный кватернион нужно читать!)
            #    bone.keyframe_insert("rotation_quaternion", frame=frame+1)        

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