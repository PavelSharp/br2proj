import math
import struct
from enum import IntFlag
from dataclasses import dataclass, field
from typing import NamedTuple, Literal, assert_never, Callable, TypeVar, Iterable, Collection

from .utils import Vec3f, EulerZXY
from .sern.fixed_types import ascii_str
from .ani import ANI_File, ANI_Header, ANI_BoneTrack, ANI_TagTrack, AniTrackType

_T = TypeVar('_T')


class RotationFlags(IntFlag):
    EMPTY = 0
    ROT_X = 1 << 0
    ROT_Y = 1 << 1
    ROT_Z = 1 << 2

    ROT_XY = ROT_X | ROT_Y
    ROT_YZ = ROT_Y | ROT_Z
    ROT_XZ = ROT_X | ROT_Z
    ROT_ALL = ROT_X | ROT_Y | ROT_Z

    @classmethod
    def from_track_type(cls, tt:AniTrackType):
        match tt:
            case AniTrackType.ROT_X: return cls.ROT_X
            case AniTrackType.ROT_Y: return cls.ROT_Y
            case AniTrackType.ROT_Z: return cls.ROT_Z
            case AniTrackType.ROT_XY:return cls.ROT_XY
            case AniTrackType.ROT_YZ:return cls.ROT_YZ
            case AniTrackType.ROT_XZ:return cls.ROT_XZ
            case AniTrackType.ROT: return cls.ROT_ALL
            case AniTrackType.POS|AniTrackType.SCALE: raise ValueError(f'Unconvertible track type: {tt.name}')
            case _: assert_never(tt)

    def to_track_type(self):
        match self:
            case RotationFlags.ROT_X:  return AniTrackType.ROT_X
            case RotationFlags.ROT_Y:  return AniTrackType.ROT_Y
            case RotationFlags.ROT_Z:  return AniTrackType.ROT_Z
            case RotationFlags.ROT_XY: return AniTrackType.ROT_XY
            case RotationFlags.ROT_YZ: return AniTrackType.ROT_YZ
            case RotationFlags.ROT_XZ: return AniTrackType.ROT_XZ
            case RotationFlags.ROT_ALL:return AniTrackType.ROT
            case RotationFlags.EMPTY: raise ValueError(f'Unconvertible rotation flag: {self.name}')
            case _: assert_never(self)


PoolEntityType = Literal['POS', 'SCALE', 'EULER']
class PoolEntity(NamedTuple):
    kf: int
    type: PoolEntityType
    vec: Vec3f

class PoolSerializer:
    ANG_RAD = math.pi / 32768.0
    KVEC = struct.Struct('<ifff') 
    KA = struct.Struct('<hh')
    KAA = struct.Struct('<hhh')
    KAAA = struct.Struct('<hhhh')

    @staticmethod
    def align4(pos:int): return (pos + 3) & ~3

    @classmethod
    def read_value(cls, start:int, pool:bytes, tt:AniTrackType):
        TT = AniTrackType
        ang_rad = cls.ANG_RAD
        kvec = cls.KVEC
        ka, kaa, kaaa = cls.KA, cls.KAA, cls.KAAA
        match tt:
            case TT.POS|TT.SCALE:
                kf, x, y, z = kvec.unpack_from(pool, start)
                return kvec.size, PoolEntity(kf, 'POS' if tt==TT.POS else 'SCALE', Vec3f(x, y, z))
            case TT.ROT_X|TT.ROT_Y|TT.ROT_Z:
                kf, ang = ka.unpack_from(pool, start)
                ang *= ang_rad
                match tt:
                    case TT.ROT_X: ang=Vec3f(ang, 0, 0) 
                    case TT.ROT_Y: ang=Vec3f(0, ang, 0)
                    case TT.ROT_Z: ang=Vec3f(0, 0, ang)
                return ka.size, PoolEntity(kf, 'EULER', ang)
            case TT.ROT_XY|TT.ROT_YZ|TT.ROT_XZ:
                kf, ang1, ang2 = kaa.unpack_from(pool, start)
                ang1, ang2 = ang1*ang_rad, ang2*ang_rad
                match tt:
                    case TT.ROT_XY: ang=Vec3f(ang1, ang2, 0)  
                    case TT.ROT_YZ: ang=Vec3f(0, ang1, ang2)
                    case TT.ROT_XZ: ang=Vec3f(ang1, 0, ang2)
                return kaa.size, PoolEntity(kf, 'EULER', ang)
            case TT.ROT:
                kf, ang1, ang2, ang3 = kaaa.unpack_from(pool, start)
                return kaaa.size, PoolEntity(kf, 'EULER', Vec3f(ang1*ang_rad, ang2*ang_rad, ang3*ang_rad))
            case _:
                assert_never(tt)

    @classmethod
    def compress_rotation(cls, vec:Vec3f, eps:float = 0.0) -> RotationFlags:
        is_nzero = lambda v: not math.isclose(v, 0.0, abs_tol=eps)
        has_x, has_y, has_z = is_nzero(vec.x), is_nzero(vec.y), is_nzero(vec.z)
        x_flag = RotationFlags.ROT_X if has_x else RotationFlags.EMPTY
        y_flag = RotationFlags.ROT_Y if has_y else RotationFlags.EMPTY
        z_flag = RotationFlags.ROT_Z if has_z else RotationFlags.EMPTY
        return x_flag|y_flag|z_flag

    @classmethod
    def write_value(cls, tt:AniTrackType, kf:int, vec:Vec3f):
        TT = AniTrackType
        kvec = cls.KVEC
        ka, kaa, kaaa = cls.KA, cls.KAA, cls.KAAA
        x, y, z = vec
        quant = lambda v: round(v / cls.ANG_RAD)
        match tt:
            case TT.POS|TT.SCALE: return kvec.pack(kf,x,y,z)
            case TT.ROT_X: return ka.pack(kf,quant(x))
            case TT.ROT_Y: return ka.pack(kf,quant(y))
            case TT.ROT_Z: return ka.pack(kf,quant(z))
            case TT.ROT_XY: return kaa.pack(kf,quant(x),quant(y))
            case TT.ROT_YZ: return kaa.pack(kf,quant(y),quant(z))
            case TT.ROT_XZ: return kaa.pack(kf,quant(x),quant(z))
            case TT.ROT: return kaaa.pack(kf,quant(x),quant(y),quant(z))
            case _:assert_never(tt)


@dataclass
class PoolReader:
    data:bytes
    pos:int = 0
    def next_track(self): self.pos = PoolSerializer.align4(self.pos)

    def read_value(self, tt:AniTrackType):
        size, entity = PoolSerializer.read_value(self.pos, self.data, tt)
        self.pos += size
        return entity

    def visit_track(self, count:int, tt:AniTrackType, mapper:Callable[[PoolEntity], None]|None=None):
        if mapper is None:
            for _ in range(count): self.read_value(tt)      
        else:
            for _ in range(count): mapper(self.read_value(tt))
        self.next_track()

    def read_track(self, count:int, tt:AniTrackType, mapper:Callable[[PoolEntity], _T]):
        ret:list[_T] = []
        self.visit_track(count, tt, lambda e: ret.append(mapper(e)))
        return ret



@dataclass
class PoolWriter:
    rot_eps:float | None = 0.0
    stream: bytearray = field(default_factory=bytearray)

    def next_track(self):
        pos = len(self.stream)
        diff = PoolSerializer.align4(pos) - pos
        if diff > 0: self.stream.extend(b'\x00' * diff)

    def write_value(self, entity: PoolEntity, track_type:AniTrackType):
        self.stream.extend(PoolSerializer.write_value(track_type, entity.kf, entity.vec))

    def write_track(self, entities: Iterable[PoolEntity], track_type:AniTrackType):
        prev = None
        count = 0
        for ent in entities:
            if prev is not None: assert prev.type==ent.type  
            self.write_value(ent, track_type)
            prev = ent
            count += 1
        self.next_track()
        return count
    
    def write_bone_rotation_track(self, entities: Collection[PoolEntity]) -> tuple[AniTrackType, int] | None:
        if not entities: return None
        if self.rot_eps is None: return AniTrackType.ROT, self.write_track(entities, AniTrackType.ROT)
        rot_typ = RotationFlags.EMPTY
        for ent in entities:
            assert ent.type=='EULER'
            rot_typ |= PoolSerializer.compress_rotation(ent.vec, self.rot_eps)
        if rot_typ==RotationFlags.EMPTY: rot_typ=RotationFlags.ROT_ALL
        rot_typ = rot_typ.to_track_type()
        return rot_typ, self.write_track(entities, rot_typ)
            

# One of the reasons to use custom math types is a more beautiful result during JSON serialization via jexplore.jprint
class VecKey(NamedTuple):
    frame:int
    vec:Vec3f

class RotKey(NamedTuple):
    frame:int
    rot:EulerZXY

class AnimTracks(NamedTuple):
    pos_track: list[VecKey]
    rot_track: list[RotKey]
    scale_track: list[VecKey]

class TaggedBone(NamedTuple):
    tracks: AnimTracks
    tags: dict[str, AnimTracks]

class Animation(NamedTuple):
    frames_count:int
    bones: dict[str, TaggedBone] #'' means root bone
    @staticmethod
    def from_ani(ani:ANI_File): return _Ani2AnimationConverter.convert(ani)
    def to_ani(self): return _Animation2AniConverter.convert(self)


class _Ani2AnimationConverter:
    @staticmethod
    def vec_key(ent:PoolEntity): return VecKey(ent.kf, ent.vec)
    @staticmethod
    def rot_key(ent:PoolEntity): return RotKey(ent.kf, EulerZXY(ent.vec.y, ent.vec.x, ent.vec.z)) #include unswizzling 

    @classmethod
    def build_bone_tracks(cls, ani:ANI_File, reader:PoolReader):
        bones: dict[str, AnimTracks] = {}
        for ani_bone in ani.bone_tracks:
            tracks = bones.setdefault(str(ani_bone.bone_name), AnimTracks([], [], []))
            for k in range(ani_bone.keyframes):
                ent = reader.read_value(ani_bone.track_type)
                match ent.type:
                    case 'POS': tracks.pos_track.append(cls.vec_key(ent))
                    case 'SCALE': tracks.scale_track.append(cls.vec_key(ent)) 
                    case 'EULER': tracks.rot_track.append(cls.rot_key(ent))
                    case _: assert_never(ent.type)
            reader.next_track()

        root_pos_track = reader.read_track(ani.root_pos_keyframes, ANI_File.ROOT_POS_TRACK_TYPE, cls.vec_key)
        root_rot_track = reader.read_track(ani.root_rot_keyframes, ANI_File.ROOT_ROT_TRACK_TYPE, cls.rot_key)
        bones[''] = AnimTracks(root_pos_track, root_rot_track, [])
        return bones

    @classmethod
    def build_tag_tracks(cls, ani: ANI_File, reader:PoolReader):
        bone_tags: dict[str, dict[str, AnimTracks]] = {}
        for entry in ani.tag_tracks:
            pos_track = reader.read_track(entry.pos_keyframes, AniTrackType.POS, cls.vec_key) 
            rot_track = reader.read_track(entry.rot_keyframes, AniTrackType.ROT, cls.rot_key)
            scale_track = reader.read_track(entry.scale_keyframes, AniTrackType.SCALE, cls.vec_key)
            tag_tracks = AnimTracks(pos_track, rot_track, scale_track)
            tag_name = str(entry.tag_name)
            attached_bone = str(entry.bone_name) if entry.is_bone_attached else ''

            tags = bone_tags.setdefault(attached_bone, {})
            assert tag_name not in tags, f'Duplicate tag {tag_name} on bone {attached_bone}'
            tags[tag_name] = tag_tracks
        return bone_tags

    @classmethod
    def convert(cls, ani:ANI_File) -> Animation:
        reader = PoolReader(bytes(ani.anim_pool))
        bone_tracks = cls.build_bone_tracks(ani, reader)
        tag_tracks = cls.build_tag_tracks(ani, reader)
        bones = {}
        for bone_name, tracks in bone_tracks.items():
            tags = tag_tracks.pop(bone_name, {})
            bones[bone_name] = TaggedBone(tracks, tags)
        for bone_name, tags in tag_tracks.items():
            bones[bone_name] = TaggedBone(AnimTracks([], [], []), tags)

        return Animation(ani.header.frames_count, bones)

class _Animation2AniConverter:
    @staticmethod
    def pos_entity(key:VecKey): return PoolEntity(key.frame, 'POS', key.vec)
    @staticmethod
    def rot_entity(key:RotKey): return PoolEntity(key.frame, 'EULER', Vec3f(key.rot.y, key.rot.x, key.rot.z))
    @staticmethod
    def scale_entity(key:VecKey): return PoolEntity(key.frame, 'SCALE', key.vec)

    @classmethod
    def sorted_pos_entries(cls, track:Iterable[VecKey]): return sorted((cls.pos_entity(k) for k in track), key=lambda e: e.kf)
    @classmethod
    def sorted_rot_entries(cls, track:Iterable[RotKey]): return sorted((cls.rot_entity(k) for k in track), key=lambda e: e.kf)
    @classmethod
    def sorted_scale_entries(cls, track:Iterable[VecKey]): return sorted((cls.scale_entity(k) for k in track), key=lambda e: e.kf)

    @classmethod
    def build_bone_tracks(cls, anim:Animation, writer:PoolWriter):
        bone_tracks:list[ANI_BoneTrack] = []
        for bone_name, bone in anim.bones.items():
            if bone_name=='': continue
            pos_cnt = writer.write_track(cls.sorted_pos_entries(bone.tracks.pos_track), AniTrackType.POS)
            rot_info = writer.write_bone_rotation_track(cls.sorted_rot_entries(bone.tracks.rot_track))
            scale_cnt = writer.write_track(cls.sorted_scale_entries(bone.tracks.scale_track), AniTrackType.SCALE)
            ascii_bone_name = lambda: ascii_str.from_str(bone_name, 24)
            if pos_cnt>0: bone_tracks.append(ANI_BoneTrack(ascii_bone_name(), AniTrackType.POS, pos_cnt))
            if rot_info is not None: bone_tracks.append(ANI_BoneTrack(ascii_bone_name(), rot_info[0], rot_info[1]))
            if scale_cnt>0: bone_tracks.append(ANI_BoneTrack(ascii_bone_name(), AniTrackType.SCALE, scale_cnt))

        root_bone = anim.bones.get('', None)
        root_pos_frames, root_rot_frames = 0, 0
        if root_bone is not None:
            assert len(root_bone.tracks.scale_track)==0, 'Scale tracks is not supported by .ANI format'
            root_pos_frames = writer.write_track(cls.sorted_pos_entries(root_bone.tracks.pos_track), AniTrackType.POS)
            root_rot_frames = writer.write_track(cls.sorted_rot_entries(root_bone.tracks.rot_track), AniTrackType.ROT)
        return bone_tracks, root_pos_frames, root_rot_frames
    

    @classmethod
    def build_tag_tracks(cls, anim: Animation, writer: PoolWriter) -> list[ANI_TagTrack]:
        tag_tracks: list[ANI_TagTrack] = []

        def write_tracks(tracks:AnimTracks, bone_name:str, tag_name:str):
            pos_count = writer.write_track(cls.sorted_pos_entries(tracks.pos_track), AniTrackType.POS)
            rot_count = writer.write_track(cls.sorted_rot_entries(tracks.rot_track), AniTrackType.ROT)
            scale_count = writer.write_track(cls.sorted_scale_entries(tracks.scale_track), AniTrackType.SCALE)
            return ANI_TagTrack(
                tag_name=ascii_str.from_str(tag_name, 24),
                bone_name=ascii_str.from_str(bone_name, 24),
                pos_keyframes=pos_count,
                rot_keyframes=rot_count,
                scale_keyframes=scale_count
            )

        root_bone = anim.bones.get('', None)
        if root_bone is not None:
            for tag_name, tracks in root_bone.tags.items():
                tag_tracks.append(write_tracks(tracks, '', tag_name))

        for bone_name, bone in anim.bones.items():
            if bone_name == '': continue
            for tag_name, tracks in bone.tags.items():
                tag_tracks.append(write_tracks(tracks, bone_name, tag_name))
        return tag_tracks

    @classmethod
    def convert(cls, anim:Animation, rot_eps:float = 0.0) -> ANI_File:
        writer = PoolWriter(rot_eps)
        bone_tracks, root_pos_frames, root_rot_frames = cls.build_bone_tracks(anim, writer)
        tag_tracks = cls.build_tag_tracks(anim, writer)
        anim_pool_bytes = list(writer.stream)
        anim_pool_size = len(anim_pool_bytes)

        header = ANI_Header(
            version=3,
            frames_count=anim.frames_count,
            bone_tracks_count=len(bone_tracks),
            tag_tracks_count=len(tag_tracks),
            anim_pool_size=anim_pool_size
        )

        return ANI_File(
            header=header,
            anim_pool=anim_pool_bytes,
            bone_tracks=bone_tracks,
            root_pos_keyframes=root_pos_frames,
            root_rot_keyframes=root_rot_frames,
            tag_tracks=tag_tracks
        )
