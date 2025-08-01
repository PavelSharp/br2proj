import bpy
from bpy.types import Operator
import bpy.types

from bpy_extras.io_utils import ImportHelper
import bpy_extras
import struct

from . import bfm_imp
from . import tex_imp
from mathutils import Vector, Matrix, Quaternion
import math
from math import pi

from .sern import jexplore, sern_read
from .ani import *
from .skb import *
from .bfm import *
from . import bpy_utils

from dataclasses import dataclass, field
from pathlib import Path
from typing import Tuple
from . import smb
from . import smb_imp
import bpy.types

null_tex_prov = tex_imp.null_tex_provider() #
tex_prov = tex_imp.tex_provider(r'D:\Games\Bloodrayne 2_min\ART')
matr = bpy_utils.axis_conversion('Z', 'Y', change_orient=True).to_4x4() # Matrix.Identity(4)

def smb_test():
    base_path = Path(r'D:\Games\Bloodrayne 2_min\MODELS')
    anim_prov = smb_imp.smb_action_provider()    
    models = ['VEHICLE_CAMARO.SMB', 'VEHICLE_RYDER_BROKEN.SMB', 'BLOODSTORM.SMB']
    top_collection = bpy_utils.get_top_collection()
    linker = smb_imp.smb_linker(None, smb_imp.LinkKinds.EmptyEmpty, transform=matr)
    s = smb_imp.smb_importer(linker=linker, name_groups=True, tex_prov=tex_prov, create_materials=True, anim_prov=anim_prov, collisions=smb_imp.ObjectLoadState.HIDE)
    for model in models:
        path = base_path / Path(model)
        sm = sern_read.reader.read_all(path, smb.SMB_File)
        #jexplore.jprint(sm, path=path.with_suffix(".json").name)
        for link_kind in smb_imp.LinkKinds:
            linker.collection = top_collection if link_kind.top_is_empty() else None
            s.linker.link_kind = link_kind
            s.load((sm, path.stem))        
        
def fit_timeline_to_scene_keyframes():
    min_frame = float('inf')
    max_frame = float('-inf')

    for obj in bpy.data.objects:
        anim = obj.animation_data
        if anim and anim.action:
            for fcurve in anim.action.fcurves:
                keyframes = [kp.co.x for kp in fcurve.keyframe_points]
                if keyframes:
                    min_frame = min(min_frame, *keyframes)
                    max_frame = max(max_frame, *keyframes)

    if min_frame != float('inf') and max_frame != float('-inf'):
        bpy.data.scenes['Scene'].frame_start = int(min_frame)
        #bpy.context.scene.frame_start = int(min_frame)
        bpy.data.scenes['Scene'].frame_end = int(max_frame)
        print(f"Timeline adjusted: {min_frame} → {max_frame}")
    else:
        print("No keyframes found.")



def _work2():
    smb_test()
    #fit_timeline_to_scene_keyframes()
    return
    #TODO[сделано] учесть анимацию collissions
    #TODO[сделано] это не есть хорошо, вызывать эту функцию если фактической трансформации нет, тогда будет созданы однокадровые кривые
    base_path = Path(r'D:\Games\Bloodrayne 2_min\MODELS')
    linker = smb_imp.smb_linker(bpy_utils.get_top_collection(), smb_imp.LinkKinds.EmptyEmpty, transform=matr)
    anim_prov = smb_imp.smb_action_provider()

    s = smb_imp.smb_importer(linker=linker, name_groups=True, tex_prov=tex_prov, anim_prov=anim_prov, collisions=smb_imp.ObjectLoadState.HIDE)
    for p in pp:
        p = base_path / Path(p)
        sm:smb.SMB_File = sern_read.reader.read_all(p, smb.SMB_File)
        #jexplore.jprint(sm, path=p.with_suffix(".json").name)
        s.load((sm, p.stem))
    return
    '''
    files = list(base_path.iterdir())
    for ind, file in enumerate(files):
            if file.is_file() and file.suffix.lower() == ".smb":
                sm = sern_read.reader.read_all(file, smb.SMB_File)
                print(file.stem, f'({ind}/{len(files)})')
                smb_imp.smb_importer(name_groups=False, collisions=smb_imp.ObjectLoadState.NORMAL).load((sm, file.stem))
    '''

    mods = ['CITY_EXT_RAT_ANIM.SMB', 'MISC_KILL_FAN.SMB', 'weapons_rayne_blade_01.smb', 'WW_BONE_CRUSHER_MAIN.SMB', 
            'VEHICLE_RYDER_ANIM.SMB','PARK_HOT_DOG_CART.SMB', 'BR_CITY_BLUE_MAILBOX.SMB', 'SW_TRAIN_CRASH_ANIMATION.SMB',
              'BLOODSTORM.SMB', 'FOREMAN_HAMMER.SMB', 'PARK_MARLIN_PULL_HALL.SMB', 'MANS_BALLROOM_CHANDELIER_IMPALER.SMB',
               'WETWORKS_DOCK_FORKLIFT_IMPALERS.SMB',
              'PARK_CHIPPER_ANIM.SMB', 'WW_TESLA_GRATE.SMB', 'PARK_SEMI_FALL.SMB', 'WW_TRACKCRANE_ANIMATION1.SMB',
              'PARK_HELICOPTER_ANIMODEL.SMB', 'MISC_COPCAR_BR.SMB', 'ST_HEART_ANI_0.SMB'
              ]
    p = base_path / mods[8]

    class ordered_linker(smb_imp.smb_linker):
        _ordered_objects = list()
        def new_container(self, name: str):
            self._ordered_objects = []
            super().new_container(name)
        def end_container(self):
            return (self._ordered_objects, super().end_container())
        def link(self, bpy_obj:bpy.types.Object):
            self._ordered_objects.append(bpy_obj)
            super().link(bpy_obj)
        def link_to_group(self, group, bpy_obj):
            raise NotImplementedError()
    matr = bpy_utils.axis_conversion('Z', 'Y', change_orient=True).to_4x4()
    linker = ordered_linker(transform=matr)
    sm:smb.SMB_File = sern_read.reader.read_all(p, smb.SMB_File)
    #jexplore.jprint(sm, path=p.with_suffix(".json").name)
    anim_prov = smb_imp.smb_action_provider()
    ord_objs, coll = smb_imp.smb_importer(linker=linker, name_groups=False, create_materials=True, tex_prov=tex_prov, anim_prov=anim_prov, collisions=smb_imp.ObjectLoadState.HIDE).load((sm, p.stem))
    '''
    for emit in sm.emitters:
        emit = str(emit)
        empty = bpy.data.objects.new(emit, None)
        empty.matrix_world = matr
        linker.link(empty)
     
    for bpy_obj in ord_objs:
        new_origin_world = Vector((0, 0, -43))
        offset = bpy_obj.matrix_world.inverted() @ new_origin_world
        bpy_obj.data.transform(Matrix.Translation(-offset))
        bpy_obj.location = new_origin_world
    '''
    from contextlib import redirect_stdout


    return
    with open('del.txt', 'w') as f, redirect_stdout(f):
 

        if sm.header.is_animated:
            colls = [None]*len(sm.animation.indices)
            for i, obj in enumerate(ord_objs):
                
                if sm.animation.indices[i]!=65535 and i<len(sm.mesh_header):
                    coln = str(sm.mesh_header[sm.animation.indices[i]].name)

                    #if coln not in colls:
                    #    colls[coln] = bpy.data.collections.new(coln)
                    #    bpy_utils.get_top_collection().children.link(colls[coln])
                    #    colls[coln].objects.link(ord_objs[sm.animation.indices[i]])
                    #colls[coln].objects.link(ord_objs[i])
                    
                    
                    oi = sm.animation.indices[i]
                    if colls[oi] is None:
                        colls[oi] = bpy.data.collections.new(str(sm.mesh_header[i].name))
                        bpy_utils.get_top_collection().children.link(colls[oi])
                    colls[oi].objects.link(ord_objs[i])
                if i<len(sm.mesh_header):
                    print(sm.mesh_header[i].name,'\t\t', sm.animation.indices[i]) # sm.mesh_header[sm.animation.indices[i]].name
                '''
                    oi = sm.animation.indices[i]
                    if i!=oi and ord_objs[i].parent==None:
                        ord_objs[i].parent = ord_objs[oi]
                    '''
                    #ord_objs[i].name =  ord_objs[i].name+ord_objs[sm.animation.indices[i]].name
                add_smb_animation(ord_objs[i], i, sm.animation, sm.header.fps)

#The simplest is a function that logs to the root (obj, path)
def jlog(*args): 
    for i in range(0, len(args), 2): jexplore.jprint(args[i], path=args[i+1].name+'.json')

def _work(self:Operator):
    #_work2()
    #return
    DO_LOGS = False
    ##matr = Matrix.Rotation(math.radians(90.0), 4, 'Y') @ Matrix.Rotation(math.radians(90.0), 4, 'Z')
    matr = Matrix((
        (1,0,0,0),
        (0,0,1,0),
        (0,1,0,0),
        (0,0,0,1),
    ))
    bfm_imp.bfm_builder.bone_orient = Vector((1,0,0)) #TODO Delete it as soon as I can
    base_path = Path('D:/Games/Bloodrayne 2_min')
    anis = [('RAYNE.BFM', ['RUN_FORWARD.ANI', 'STAND_ALERT.ANI', 'locked_idle.ANI'])]
    bi, ai = 0,0
    bfm_path = base_path / 'MODELS' / anis[bi][0]
    ani_path = base_path / 'ANIMATIONS' / Path(anis[bi][0]).stem / anis[bi][1][ai]

    skb_prov = bfm_imp.skb_provider(base_path / 'DATA', load_anims=True)
    linker = bfm_imp.bfm_linker(bfm_imp.LinkKinds.Collection, transform=matr)
    loader = bfm_imp.bfm_importer(linker=linker, create_materials = True, skb_prov=skb_prov, tex_prov=tex_prov)

    bfm:BFM_File = sern_read.reader.read_all(bfm_path, BFM_File)
    skb, skb_path = skb_prov.provide(str(bfm.header.skb_name), True)
    ani:ANI_File = sern_read.reader.read_all(ani_path, ANI_File)
    if DO_LOGS: jlog(skb, skb_path, ani, ani_path)


    coll = loader.load((bfm, bfm_path.stem))

    arm:bpy.types.Object = None
    for obj in coll.objects:
        if obj.type == 'ARMATURE': arm = obj

    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='POSE')

    action = bpy.data.actions.new(name='ANI_Anim1')
    arm.animation_data_create()
    arm.animation_data.action = action

    fps = 24 
    numFrames = ani.header.numFrames
    pool_ind = 0 

    def check_kf(kf):
        if kf<0 or kf>=ani.header.numFrames:
            raise ValueError(f"Keyframe err, kf was {kf}")
    def unp(kf, *args):
        check_kf(kf)
        return (kf, *tuple((arg / 32768) * math.pi for arg in args))

    def sym(name:str):
        #for bone in rayne_skb.bones:
        #    if ( bone.symBone!=-1 and str(bone.name)==name):
        #        print(1)
        #        return str(rayne_skb.bones[bone.symBone].name)
        return name
    #[24.04.2025, IMPORTANT] See Nocturne/Editor/doc/Editor.pdf Coordinate System for more details about it
    for ani_bone in ani.used_bones:
        tt = ani_bone.tt
        bpy_bone = arm.pose.bones[sym(str(ani_bone.name))]
        #qw = arm.data.bones[str(ani_bone.name)]
        #matr = Matrix.Translation(qw.head)
        bpy_bone.rotation_mode = 'XYZ'

        is_sym = False
        for bone in skb.bones:
            if bone.symBone!=-1 and str(bone.name)==bpy_bone.name:
                is_sym = True
                break
        
        for k in range(ani_bone.numKeyFrames):
            if tt in [0, 1]:
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
                    if is_sym: ang1=-ang1
                    bpy_bone.rotation_euler.y = ang1
                    bpy_bone.keyframe_insert("rotation_euler", index=1, frame=kf)
                elif tt == 4:
                    if is_sym: ang1=-ang1
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
                else: # XZ
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
            
    if pool_ind!=ani.header.animPoolSize: #TODO extra data RUN_FORWARD?
        self.report({'WARNING'}, 'Warring. The pool has not been exhausted. See in console')
        print(f'pool_ind={pool_ind}, header_pool_size={ani.header.animPoolSize}')
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
        _work(self)
        return {'FINISHED'}
    
def register():
    bpy.utils.register_class(SandboxOp)

def unregister():
    bpy.utils.unregister_class(SandboxOp)