from typing import NamedTuple, Literal, assert_never
from enum import IntEnum
from dataclasses import dataclass
import struct
import math

from mathutils import Vector

#TODO use this type in ANI_BoneEntry.tt, after sern will be support it
class TrackType(IntEnum):
    POS         = 0
    SCALE       = 1
    ROT_X       = 2
    ROT_Y       = 3
    ROT_Z       = 4
    ROT_XY      = 5
    ROT_YZ      = 6
    ROT_XZ      = 7
    ROT         = 8

PoolEntityType = Literal['POS', 'SCALE', 'EULER']

class PoolEntity(NamedTuple):
    size: int
    kf: int
    type: PoolEntityType
    vec: Vector

@dataclass(slots=True) 
class PoolCursor:
    pos: int = 0
    def next_track(self): self.pos = (self.pos + 3) & ~3

#According to sub_721820, which parses the ANI file
class PoolParser:
    _ang_rad = math.pi / 32768.0
    _kvec = struct.Struct('ifff') 
    _ka = struct.Struct('hh')
    _kaa = struct.Struct('hhh')
    _kaaa = struct.Struct('hhhh')

    @classmethod
    def extract_value(cls, start:int, pool:bytes, tt:TrackType):
        TT = TrackType
        ang_rad = cls._ang_rad
        kvec = cls._kvec
        ka, kaa, kaaa = cls._ka, cls._kaa, cls._kaaa
        match tt:
            case TT.POS|TT.SCALE:
                kf, x, y, z = kvec.unpack_from(pool, start)
                return PoolEntity(kvec.size, kf, 'POS' if tt==TT.POS else 'SCALE', Vector((x, y, z)))
            case TT.ROT_X|TT.ROT_Y|TT.ROT_Z:
                kf, ang = ka.unpack_from(pool, start)
                ang *= ang_rad
                match tt:
                    case TT.ROT_X: ang=(ang, 0, 0) 
                    case TT.ROT_Y: ang=(0, ang, 0)
                    case TT.ROT_Z: ang=(0, 0, ang)
                return PoolEntity(ka.size, kf, 'EULER', Vector(ang))
            case TT.ROT_XY|TT.ROT_YZ|TT.ROT_XZ:
                kf, ang1, ang2 = kaa.unpack_from(pool, start)
                ang1, ang2 = ang1*ang_rad, ang2*ang_rad
                match tt:
                    case TT.ROT_XY: ang=(ang1, ang2, 0)  
                    case TT.ROT_YZ: ang=(0, ang1, ang2)
                    case TT.ROT_XZ: ang=(ang1, 0, ang2)
                return PoolEntity(kaa.size, kf, 'EULER', Vector(ang))
            case TT.ROT:
                kf, ang1, ang2, ang3 = kaaa.unpack_from(pool, start)
                return PoolEntity(kaaa.size, kf, 'EULER', Vector((ang1*ang_rad, ang2*ang_rad, ang3*ang_rad)))
            case _:
                assert_never(tt)
    @classmethod
    def parse(cls, cursor:PoolCursor, pool:bytes, tt:TrackType):
        ret = cls.extract_value(cursor.pos, pool, tt)
        cursor.pos += ret.size
        return ret