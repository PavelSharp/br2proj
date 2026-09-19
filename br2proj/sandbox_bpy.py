import bpy
from bpy.types import Operator
import bpy.types

from bpy_extras.io_utils import ImportHelper
import bpy_extras
import struct

from . import bfm_imp
from . import tex_imp
from mathutils import Vector, Matrix, Quaternion, Euler
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

base_path = Path('D:/Games/Bloodrayne 2_min')
null_tex_prov = tex_imp.null_tex_provider()
tex_prov = tex_imp.tex_provider(base_path / 'ART')
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
    DO_LOGS = False
    DO_TEXTURES = True

    #TODO SLEGION.BFM + COMBO1.ANI где-то происходит нежелательная смена знака в угле

    anis = [
        (
            ['RAYNE.BFM', 'RAYNE_DRESS.BFM', 'RAYNE_SCHOOLGIRL.BFM', 'RAYNE_COWGIRL.BFM'],
            ['WALK_FORWARD.ANI', 'RUN_FORWARD.ANI', 'POLE_JUMP.ANI', 'POLE_OFF.ANI', 'POLE_GRAB.ANI', 'POLE_DOWN_OFF.ANI', 'POLE_DISMOUNT_TO_WJ_LONG.ANI', 'POLE_LONGJUMP.ANI', 'BITE_STAND_KICK.ANI',  'COMBO_CIRCLE_KICK.ANI', 'RECOVERY_ONBACK_DEFAULT.ANI', 'DOUBLE_JUMP.ANI', 'FEED_REPEL.ANI', 'STAND_ALERT.ANI', 'locked_idle.ANI']
        ),
        (
            ['FERRIL.BFM'],
            ['WALK_N.ANI', 'RUN_N.ANI', 'HIGH_JUMP_35.ANI', 'LEAP_ATTACK_KICK.ANI']
        ),
        (
            ['SLEGION.BFM'],
            ['WALKS.ANI', 'RUNN.ANI', 'COMBO1.ANI', 'ATTACK01.ANI', 'ATTACK02.ANI', 'BACKEVADEATTACK.ANI']
        ),
        (
            ['FOREMAN.BFM'],
            ['WALK_N.ANI', 'RUN_N.ANI', 'ATTACK_COMBO.ANI', 'ANGRY_SMASH.ANI', 'FEED.ANI']
        ),
        ]
    ch, bi, ai = 0,0,0
    bfm_path = base_path / 'MODELS' / anis[ch][0][bi]
    ani_path = base_path / 'ANIMATIONS' / Path(anis[ch][0][0]).stem / anis[ch][1][ai]

    skb_prov = bfm_imp.skb_provider(base_path / 'DATA', load_anims=True)
    linker = bfm_imp.bfm_linker(bfm_imp.LinkKinds.Collection, transform=matr)
    loader = bfm_imp.bfm_importer(linker=linker, create_materials = DO_TEXTURES, skb_prov=skb_prov, tex_prov= tex_prov if DO_TEXTURES else null_tex_prov)

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
        return kf, *tuple(arg / 32768.0 * math.pi for arg in args)

    def sym(name:str):
        for bone in skb.bones:
           if ( bone.symBone!=-1 and str(bone.name)==name):
               return str(skb.bones[bone.symBone].name)
        return name

    #[24.04.2025, IMPORTANT] See Nocturne/Editor/doc/Editor.pdf Coordinate System for more details about it

    bone_orient = bfm_imp.bfm_builder.bone_orient.inverted()

    def add_pos(bpy_bone, kf, x, y, z):
        bpy_bone.location = bone_orient @ Vector((z,x,y))
        bpy_bone.keyframe_insert("location", frame=kf+1)

    def add_scale(bpy_bone, kf, x, y, z):
        bpy_bone.scale = Vector((x, y, z))
        bpy_bone.keyframe_insert("scale", frame=kf+1)

    def add_quat(bpy_bone, kf, ang_x=0, ang_y=0, ang_z=0):
        # In accordance with sub_7227A0, Euler angles are used only for
        # compact storage, which are then converted by the engine into quaternion
        quat = Euler((-ang_y,ang_x,-ang_z), 'ZXY').to_quaternion()
        bpy_bone.rotation_quaternion = bone_orient @ quat @ bone_orient.inverted()
        bpy_bone.keyframe_insert("rotation_quaternion", frame=kf+1)
    #According to sub_721820, which parses the ANI file
    for ani_bone in ani.used_bones:
        tt = ani_bone.tt
        bpy_bone = arm.pose.bones[sym(str(ani_bone.name))]

        for k in range(ani_bone.numKeyFrames):
            bpy_bone.rotation_mode = 'QUATERNION'

            if tt in[0,1]:
                ts = 16
                kf, x, y, z = struct.unpack("ifff", bytes(ani.animPool[pool_ind:pool_ind + ts]))
                check_kf(kf)
                if tt == 0:
                    add_pos(bpy_bone, kf, x, y, z)
                elif tt == 1:
                    add_scale(bpy_bone, kf, x, y, z)

            elif tt in [2,3,4]:
                ts = 4
                vl = struct.unpack("hh", bytes(ani.animPool[pool_ind:pool_ind + ts]))
                kf, ang = unp(*vl)
                if tt == 2: add_quat(bpy_bone, kf, ang_x=ang)
                elif tt == 3: add_quat(bpy_bone, kf, ang_y=ang)
                elif tt == 4: add_quat(bpy_bone, kf, ang_z=ang)

            elif tt in [5,6,7]:
                ts = 6
                vl = struct.unpack("hhh", bytes(ani.animPool[pool_ind:pool_ind + ts]))
                kf, ang1, ang2 = unp(*vl)
                if tt == 5:   add_quat(bpy_bone, kf, ang_x=ang1, ang_y=ang2)  # XY
                elif tt == 6: add_quat(bpy_bone, kf, ang_y=ang1, ang_z=ang2)  # YZ
                elif tt == 7: add_quat(bpy_bone, kf, ang_x=ang1, ang_z=ang2)  # XZ
            elif tt == 8:
                ts = 8
                vl = struct.unpack("hhhh", bytes(ani.animPool[pool_ind:pool_ind + ts]))
                kf, ang1, ang2, ang3 = unp(*vl)
                add_quat(bpy_bone, kf, ang_x=ang1, ang_y=ang2, ang_z=ang3)
            pool_ind += ts

        pool_ind = (pool_ind + 3) & ~3

    if pool_ind!=ani.header.animPoolSize: #TODO extra data RUN_FORWARD?
        self.report({'WARNING'}, 'Warring. The pool has not been exhausted. See in console')
        print(f'pool_ind={pool_ind}, header_pool_size={ani.header.animPoolSize}')


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

#For RAYNE.BFM these animations are very useful.
#JUMP.ANI RECOVERY_ONBACK_DEFAULT.ANI, COMBO_CIRCLE_KICK.ANI