"""
Skeleton Animation Emulator
=====

NOTE: This file is a standalone sandbox and is not part of the exported extension API.

----------------------------
    Development History
----------------------------
This module began as a research laboratory. To investigate several hypotheses regarding 
skeletal updates in BloodRayne 2, I needed to accurately recreate Blender's animation pipeline. 
I initially suspected that TRI utilized a custom skeletal system that native Blender tools couldn't replicate. 
Halfway through, I confirmed that BR2 relies on a standard pipeline, fully answering my original questions.

----------------------------
ACADEMIC & EDUCATIONAL PURPOSE
----------------------------
Instead of discarding the code, I spent several days refining it with a new motivation: education. 
Skeletal animation is universal, and the data processing logic shown here forms the core of almost any 3D engine. 
The `SkeletonEmulator` class serves as a clean, isolated reference for:
- Graphics programmers studying skeletal math.
- Reverse-engineers analyzing raw 3D animation data in game files.
- Python developers needing a plug-and-play tool to quickly visualize animation data via any 3D graphics library

----------------------------
        VERIFICATION
----------------------------
This emulator achieves mathematical accuracy with Blender. 
Both `SkeletonEmulator` and `BlenderSkeleton` compute global bone matrices for the target frame identically,
which is verified by the included tests.

----------------------------
   BLENDER SLERP PITFALL
----------------------------
It is important to note that Blender evaluates animations via 'FCurves', 
interpolating each channel (X, Y, Z, W) independently (LINEAR, BEZIER, etc.). 
Because of this per-channel decoupling, achieving true SLERP via native Blender curves 
seems impossible, even though SLERP remains the video game industry standard.
"""

import math
import unittest
from typing import NamedTuple, Tuple, Literal, Callable, TypeVar, assert_never, Any
from collections.abc import Iterable, Mapping

import bpy
from mathutils import Vector, Matrix, Quaternion, Euler

from .bpy_utils import restored_playhead

class PosKey(NamedTuple):
    frame: float
    pos: Vector
    @property
    def val(self):return self.pos

class RotKey(NamedTuple):
    frame: float
    rot: Quaternion
    @property
    def val(self):return self.rot    

class ScaleKey(NamedTuple):
    frame: float
    scale: Vector
    @property
    def val(self):return self.scale    

class BoneTracks(NamedTuple):
    pos_track: list[PosKey]
    rot_track: list[RotKey]
    scale_track: list[ScaleKey]

    @classmethod
    def default(cls, pos_track=None, rot_track=None, scale_track=None):
        return cls(
                [] if pos_track is None else pos_track,
                [] if rot_track is None else rot_track,
                [] if scale_track is None else scale_track
        )
    
class AniSample(NamedTuple):
    pos:Vector
    rot:Quaternion
    scale:Vector
    @classmethod
    def default(cls, pos=None, quat=None, scale=None): 
        return cls(
            pos if pos is not None else Vector(), 
            quat if quat is not None else Quaternion(),
            scale if scale is not None else Vector((1, 1, 1)),
        )
    
    def to_matrix(self):
        return Matrix.LocRotScale(self.pos, self.rot, self.scale)

AniFrameBorder = Tuple[PosKey, PosKey | None] | Tuple[RotKey, RotKey | None]

class LocalBone(NamedTuple):
    parent:str | None
    local_matrix:Matrix    

class WorldBone(NamedTuple):
    parent:str | None
    world_matrix:Matrix
    @classmethod
    def from_local(cls, bone: LocalBone, parent_world: Matrix | None):
        local = bone.local_matrix
        return cls(bone.parent, parent_world @ local if parent_world else local.copy())

_TKey = TypeVar('_TKey', PosKey, RotKey, ScaleKey)
Animation = Mapping[str, BoneTracks]
LocalSkeleton = Mapping[str, LocalBone]
WorldSkeleton = Mapping[str, WorldBone]
Skeleton = Mapping[str, WorldBone | LocalBone]
Frame = Mapping[str, Matrix]
RotInterpolation = Literal['slerp', 'nlerp']
# Note: Could not find the place where BeztripleInterpolationModeItems is defined.
FCurvesInterpolation = Literal[
    'CONSTANT', 'LINEAR', 'BEZIER', 
    'SINE', 'QUAD', 'CUBIC', 'QUART', 'QUINT', 'EXPO', 'CIRC', 
    'BACK', 'BOUNCE', 'ELASTIC'
] | None

class AnimationBorder(NamedTuple):
    start_frame:float
    end_frame:float
    def pad(self, v: float):
        return AnimationBorder(self.start_frame - v, self.end_frame + v)
    def extend(self, v:float):
        return AnimationBorder(min(self.start_frame, v), max(self.end_frame, v))
    def round_extend(self):
        return AnimationBorder(math.floor(self.start_frame), math.ceil(self.end_frame))        

class AnimationUtils:
    @staticmethod
    def get_animation_bounds(anim: Animation) -> AnimationBorder | None:
        border:AnimationBorder | None = None
        def extend_track(track):
            nonlocal border
            for k in track:
                border = border.extend(k.frame) if border is not None else AnimationBorder(k.frame, k.frame)
        for tracks in anim.values():
            extend_track(tracks.pos_track)
            extend_track(tracks.rot_track)
            extend_track(tracks.scale_track)
        return border
    

class SkeletonEmulator:
    @staticmethod
    def build_world_rest(rest:Skeleton) -> WorldSkeleton:
        world_rest: dict[str, WorldBone] = {}
        for bone_name, bone in rest.items():
            if isinstance(bone, LocalBone):
                parent_mat = world_rest[bone.parent].world_matrix if bone.parent else None
                world_rest[bone_name] = WorldBone.from_local(bone, parent_mat)
            elif isinstance(bone, WorldBone):
                world_rest[bone_name] = bone
            else:
                raise TypeError(f'Unknown bone type for "{bone_name}", got: "{type(bone).__name__}"')
        return world_rest

    @staticmethod
    def extract_track_border(track: Iterable[_TKey], target_frame: float):
        # NOTE: In practice, software pre-sorts tracks and uses binary search here
        left, right = None, None
        for key in track:
            if key.frame == target_frame:
                return key, None 
            if key.frame <= target_frame:
                if left is None or key.frame > left.frame:
                    left = key
            elif right is None or key.frame < right.frame:
                right = key           
        return left, right
    
    @staticmethod
    def extrapolate(typ, frame: float, dflt, lr:Tuple[_TKey|None, _TKey|None]):
        l,r = lr
        if l is None:
            if r is not None:
                l = typ(frame, r.val)
                r = None
            else:
                l = typ(frame, dflt)
        return l, r

    @classmethod
    def extract_sample(cls, l:_TKey, r:_TKey|None, target_frame: float, interp:Callable[[Any, Any, float], Any]):
        if r is None or l.frame == r.frame:  return l.val
        time = (target_frame - l.frame) / (r.frame - l.frame)
        return interp(l.val, r.val, time)

    @staticmethod
    def get_rot_interpolator(interp:RotInterpolation) -> Callable[[Quaternion, Quaternion, float], Quaternion]:
        def quat_nlerp(q1: Quaternion, q2: Quaternion, t: float):
            return Quaternion(Vector(q1).lerp(Vector(q2), t)).normalized()  #type: ignore
        match interp:
            case 'slerp': return Quaternion.slerp
            case 'nlerp': return quat_nlerp
            case _: assert_never(interp)        

    @classmethod
    def build_sample(cls, tracks:BoneTracks, target_frame: float, interp:RotInterpolation) -> AniSample:
        lp, rp = cls.extrapolate(PosKey, target_frame, Vector(), cls.extract_track_border(tracks.pos_track, target_frame))
        lr, rr = cls.extrapolate(RotKey, target_frame, Quaternion(), cls.extract_track_border(tracks.rot_track, target_frame))
        ls, rs = cls.extrapolate(ScaleKey, target_frame, Vector((1, 1, 1)), cls.extract_track_border(tracks.scale_track, target_frame))
        pos = cls.extract_sample(lp, rp, target_frame, Vector.lerp)
        rot = cls.extract_sample(lr, rr, target_frame, cls.get_rot_interpolator(interp))
        scale = cls.extract_sample(ls, rs, target_frame, Vector.lerp)
        return AniSample(pos, rot, scale)
        
    @classmethod
    def evalute_bone_world_transforms(cls, world_rests:WorldSkeleton, anim_data: Animation, target_frame: float, interp:RotInterpolation) -> Frame:
        world_animated_skeleton:dict[str,Matrix] = {}
        for bone_name, rest_data in world_rests.items():
            parent_name = rest_data.parent
            world_rest = rest_data.world_matrix

            tracks = anim_data.get(bone_name, BoneTracks.default())
            matrix_basis = cls.build_sample(tracks, target_frame, interp).to_matrix()

            if parent_name is None:
                world_animated_skeleton[bone_name] = world_rest @ matrix_basis
            else:
                # NOTE: Inverted matrices can be cached
                local_rest = world_rests[parent_name].world_matrix.inverted() @ world_rest
                local_anim = local_rest @ matrix_basis
                world_animated_skeleton[bone_name] = world_animated_skeleton[parent_name] @ local_anim
        return world_animated_skeleton

    def __init__(self, rest:Skeleton, interp:RotInterpolation):
        self.world_rest = self.build_world_rest(rest)
        self.rot_interp:RotInterpolation = interp

    def get_frame(self, animation_data: Animation, target_frame: float) -> Frame:
        return self.evalute_bone_world_transforms(self.world_rest, animation_data, target_frame, self.rot_interp)
  

class BlenderSkeleton:
    @staticmethod
    def create_armature(obj_name: str, data_name: str, rest: Skeleton, bone_length:float) -> bpy.types.Object:
        rests = SkeletonEmulator.build_world_rest(rest)
        arm_data = bpy.data.armatures.new(data_name)
        arm_obj = bpy.data.objects.new(obj_name, arm_data)
        bpy.context.scene.collection.objects.link(arm_obj)
        bpy.context.view_layer.objects.active = arm_obj
        bpy.ops.object.mode_set(mode='EDIT')
        for bone_name, bone_data in rests.items():
            bpy_bone = arm_data.edit_bones.new(bone_name)
            bpy_bone.length = bone_length
            if bone_data.parent:
                bpy_bone.parent = arm_data.edit_bones[bone_data.parent]
            bpy_bone.matrix = bone_data.world_matrix.copy()
        bpy.ops.object.mode_set(mode='OBJECT')
        return arm_obj
    
    @staticmethod
    def animation_to_action(action_name: str, anim: Animation, fcurves_interp:FCurvesInterpolation = None) -> bpy.types.Action:
        action = bpy.data.actions.new(action_name)
        def add_path(path:str, track:list[_TKey]):
            if not track: return
            channels = len(track[0].val)
            for i in range(channels):
                curve = action.fcurves.new(data_path=path, index=i)
                for key in track:
                    assert channels == len(key.val)
                    kf=curve.keyframe_points.insert(key.frame, key.val[i], options={'FAST'})
                    if fcurves_interp is not None: kf.interpolation = fcurves_interp #IMPORTANT: Bezier curves by default
                curve.keyframe_points.sort()
        for bone_name, bone_tracks in anim.items():
            add_path(f'pose.bones["{bone_name}"].location', bone_tracks.pos_track)
            add_path(f'pose.bones["{bone_name}"].rotation_quaternion', bone_tracks.rot_track)
            add_path(f'pose.bones["{bone_name}"].scale', bone_tracks.scale_track)
        return action

    @classmethod
    def create_action(cls, arm_obj:bpy.types.Object, action_name:str, anim_data:Animation, fcurves_interp:FCurvesInterpolation = None) -> bpy.types.Action:
        bpy.ops.object.mode_set(mode='POSE')
        for bone in arm_obj.pose.bones:
            bone.rotation_mode = 'QUATERNION'
        bpy.ops.object.mode_set(mode='OBJECT')
        action =  cls.animation_to_action(action_name, anim_data, fcurves_interp)
        arm_obj.animation_data_create()
        arm_obj.animation_data.action = action
        return action
    
    def __init__(self, obj_name, data_name, rest:Skeleton, bone_length:float, fcurves_interp:FCurvesInterpolation = None):
        self.arm_obj = self.create_armature(obj_name, data_name, rest, bone_length)
        self.default_fcurves_interp:FCurvesInterpolation = fcurves_interp

    def add_action(self, action_name:str, anim_data:Animation, fcurves_interp:FCurvesInterpolation = None):
        if fcurves_interp is None: fcurves_interp = self.default_fcurves_interp
        return self.create_action(self.arm_obj, action_name, anim_data, fcurves_interp)
    
    def get_frame(self, action:bpy.types.Action, target_frame:float) -> Frame:
        self.arm_obj.animation_data.action = action
        matrices:dict[str, Matrix] = {}
        with restored_playhead(target_frame):
            for bone in self.arm_obj.pose.bones:
                matrices[bone.name] = bone.matrix.copy()
        return matrices

class TestData:
    BONE_LENGTH = 0.2
    _AXIS_X = Vector((1.0, 0.0, 0.0))
    _AXIS_Y = Vector((0.0, 1.0, 0.0))
    _AXIS_Z = Vector((0.0, 0.0, 1.0))
    _ONES = Vector((1.0, 1.0, 1.0))
    _ZERO_ROT =  Quaternion()
    _ZERO_POS = Vector()
    @staticmethod
    def _Vec(x: float, y: float, z: float): return Vector((x, y, z))

    @classmethod
    def create_skel1(cls) -> LocalSkeleton:
        axis_x = cls._AXIS_X
        Vec, Quat = cls._Vec, Quaternion
        ang = math.radians(35)
        return {
            'Snake_Bone_1': LocalBone(None, Matrix.LocRotScale(Vec(0.0, 0.0, 0.0), Quat(axis_x, ang), None)),
            'Snake_Bone_2': LocalBone('Snake_Bone_1', Matrix.LocRotScale(Vec(0.0, cls.BONE_LENGTH, 0.0), Quat(axis_x, -ang), None)),
            'Snake_Bone_3': LocalBone('Snake_Bone_2', Matrix.LocRotScale(Vec(0.0, cls.BONE_LENGTH, 0.0), Quat(axis_x, ang), None))
        }

    @classmethod
    def create_skel1_anim1(cls) -> Animation:
        axis_x, axis_y, axis_z, ones = cls._AXIS_X, cls._AXIS_Y, cls._AXIS_Z, cls._ONES
        zero_pos, zero_rot = cls._ZERO_POS, cls._ZERO_ROT
        pk, rk, sk = PosKey, RotKey, ScaleKey
        Vec, Quat = cls._Vec, Quaternion
        rad = math.radians

        return {
            "Snake_Bone_1": BoneTracks.default(
                pos_track=[
                    pk(0,  zero_pos),
                    pk(10, Vec(0.0, -0.3, 1.0)),
                    pk(20, zero_pos),
                    pk(30, Vec(-0.2, 0.0, 0.2))
                ],
                rot_track=[
                    rk(0,  Quat(axis_x, rad(35))),
                    rk(10, Quat(axis_z, rad(15))),
                    rk(20, zero_rot),
                    rk(30, Quat(axis_y, rad(-45)))
                ],
                scale_track=[
                    sk(0,  ones),
                    sk(10, Vec(1.5, 1.5, 1.5)),
                    sk(20, ones),
                    sk(30, Vec(0.5, 0.5, 0.5))
                ]
            ),
            'Snake_Bone_2': BoneTracks.default(
                pos_track=[
                    pk(0,  Vec(0.1, -0.05, 0.0)),
                    pk(10, zero_pos),
                    pk(14, Vec(0.0, 0.4, 0.0)),
                    pk(30, zero_pos)
                ],
                rot_track=[
                    rk(0,  Quat(axis_y, rad(25))),
                    rk(10, Quat(axis_x, rad(-35))),
                    rk(20, Quat(axis_z, rad(-20))),
                    rk(30, zero_rot)
                ],
                scale_track=[
                    sk(0,  ones),
                    sk(10, Vec(1.0, 2.0, 1.0)),
                    sk(20, ones),
                    sk(30, Vec(1.0, 0.5, 1.0)) 
                ]
            ),
            'Snake_Bone_3': BoneTracks.default(
                pos_track=[
                    # The extrapolation trap is here: frames 0 and 10 are empty
                    pk(20.0, Vec(0.0, 0.0, 0.5)),
                    pk(30.0, Vec(0.3, -0.1, 0.0))
                ],
                rot_track=[
                    rk(20.0, Quat(ones, rad(55))),
                    rk(30.0, Quat(axis_x, rad(-55)))
                ],
                scale_track=[
                    sk(20.0, Vec(1.2, 1.2, 1.2)),
                    sk(30.0, Vec(0.8, 0.8, 0.8))
                ]
            )
        }
    
    @classmethod
    def create_skel1_anim2(cls) -> Animation:
        axis_x, axis_y, axis_z, ones = cls._AXIS_X, cls._AXIS_Y, cls._AXIS_Z, cls._ONES
        zero_pos, zero_rot = cls._ZERO_POS, cls._ZERO_ROT
        pk, rk, sk = PosKey, RotKey, ScaleKey
        Vec, Quat = cls._Vec, Quaternion
        rad = math.radians

        return {
            "Snake_Bone_1": BoneTracks.default(
                # Trap 1: Intensive position track with fractional frames, but rotation and scale are static (0 keys)
                pos_track=[
                    pk(2.5,  zero_pos),
                    pk(7.1,  Vec(0.1, -0.2, 0.5)),
                    pk(11.3, Vec(-0.4, 0.1, 0.0)),
                    pk(17.7, zero_pos)
                ]
            ),
            'Snake_Bone_2': BoneTracks.default(
                # Trap 2: Empty position track. Rotation starts later and cuts off earlier than Bone_1's tracks.
                rot_track=[
                    rk(6.0,  Quat(axis_y, rad(45))),
                    rk(12.0, Quat(axis_x, rad(-15)))
                ],
                # Scale has exactly 1 key (an isolated deadlock to test the l.frame == r.frame condition)
                scale_track=[
                    sk(9.5,  Vec(1.0, 2.5, 1.0))
                ]
            ),
            'Snake_Bone_3': BoneTracks.default(
                # Trap 3: Complete asynchrony. Starts far beyond the timelines of Bone_1 and Bone_2.
                # When the emulator samples frame 10.0, this track will trigger a deep left extrapolation.
                pos_track=[
                    pk(22.0, Vec(0.0, 0.0, -0.5)),
                    pk(38.5, Vec(0.5, 0.0, 0.5))
                ],
                rot_track=[
                    rk(22.0, Quat(axis_z, rad(90))),
                    rk(38.5, zero_rot)
                ],
                scale_track=[
                    sk(22.0, ones),
                    sk(38.5, Vec(0.7, 0.7, 0.7))
                ]
            )
        }


class TestSkeletonComputers(unittest.TestCase):
    FLOAT_EPS = 1e-5
    ANIM_EXTRA_FRAMES = 5
    @staticmethod
    def reset_blender(): 
        #bpy.ops.wm.read_homefile(use_empty=False)
        #bpy.ops.wm.read_factory_settings(use_empty=True)
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.orphans_purge()

    def setUp(self): self.reset_blender()
    @classmethod
    def tearDownClass(cls): cls.reset_blender()

    def _test_frames_equals(self, lhs:Frame, rhs:Frame, frame_ind:int):
        def test_set_equals():
            diff = set(lhs.keys()) ^ set(rhs.keys())
            self.assertFalse(diff, f'The pair of frames at {frame_ind} has different bones: {diff}')

        def test_matrix_equals(m1:Matrix, m2:Matrix, frame_ind:int, bone_name:str):
            details = f'at frame {frame_ind} for bone "{bone_name}"'
            is_4x4 = lambda m: len(m.row)==4 and len(m.col)==4
            self.assertTrue(is_4x4(m1) and is_4x4(m2), f'A matrix of size other than 4 by 4 has been detected {details}.')
            for row1, row2 in zip(m1.row, m2.row): #type: ignore
                for v1, v2 in zip(row1, row2):
                    self.assertAlmostEqual(v1, v2, delta=self.FLOAT_EPS, 
                        msg=f"Matrix desynchronization {details}.\nLHS:{m1}\nRHS:{m2}")
        test_set_equals()
        for bone_name in lhs.keys():
            test_matrix_equals(lhs[bone_name], rhs[bone_name], frame_ind, bone_name)
    
    def _emu_bpy_runner(self, rest:Skeleton, anim:Animation, bone_length:float):
        emu_skel = SkeletonEmulator(rest, 'nlerp')
        bpy_skel = BlenderSkeleton('ArmObj', 'Arm', rest, bone_length, 'LINEAR')
        bpy_act = bpy_skel.add_action('action', anim)
        border = AnimationUtils.get_animation_bounds(anim)
        if border is None: return
        start_frame, end_frame = border.pad(self.ANIM_EXTRA_FRAMES).round_extend()
        for frame_ind in range(int(start_frame), int(end_frame)):
            bpy_frame = bpy_skel.get_frame(bpy_act, frame_ind)
            emu_frame = emu_skel.get_frame(anim, frame_ind)
            self._test_frames_equals(bpy_frame, emu_frame, frame_ind)

    def test_emu_bpy_match_skel1anim1(self):
        self._emu_bpy_runner(TestData.create_skel1(), TestData.create_skel1_anim1(), TestData.BONE_LENGTH)

    def test_emu_bpy_match_skel1anim2(self):
        self._emu_bpy_runner(TestData.create_skel1(), TestData.create_skel1_anim2(), TestData.BONE_LENGTH)

def run_skelanim_tests():
     #unittest.main(argv=['ignored'], exit=False)
    suite = unittest.TestLoader().loadTestsFromTestCase(TestSkeletonComputers)
    unittest.TextTestRunner().run(suite)