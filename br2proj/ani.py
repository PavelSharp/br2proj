# This work is based on
#     BR2 3D FILE FORMATS DOCUMENT
#     by BloodHammer (Mjolnir) (v1.19 - 15.01.2006)
#Available at https://gamebanana.com/tools/18225 (Thanks KillerExe_01 for published it)

from dataclasses import dataclass

from .sern import sern_read
from .sern.fixed_types import *
from .sern import jexplore

@sern_read.fixeddata
class ANI_Header:
    version:c_int32
    numFrames:c_int32
    numBonesUsed:c_int32 #// same bones may have multiple transformations applied
    numBonesUsed2:c_int32 #/? number of some more entries more at the end...
    animPoolSize:c_int32 #// size of animdata (+sometimes more, entry2 depending?)

@dataclass
class ANI_BoneEntry:
    name:ascii_char*24
    tt:c_int32 #/? transformation type (0..8)
    numKeyFrames:c_int32

@dataclass
class ANI_BoneEntry2: #?? binding of some sort??
    name:ascii_char*24 #/? of what? sync/wall/rail/pole/gun/spark... ?
    bone:ascii_char*24 #/? tag, offset? OPTIONAL!
    a:c_int32 #??
    b:c_int32 #??
    c:c_int32 #0

@dataclass
class ANI_File:
    header:ANI_Header
    animPool:list[c_uint8]
    used_bones: list[ANI_BoneEntry]
    a:c_int32 #(0/5)
    b:c_int32 #(0)
    unk1: list[ANI_BoneEntry2]
    @classmethod
    def sern_read(cls, rdr:sern_read.reader):
        dict = rdr.top_fields_read(cls, 
                'header',
                ('animPool', sern_read.known_arg('header').animPoolSize),
                ('used_bones', sern_read.known_arg('header').numBonesUsed),
                'a', 'b',
                ('unk1', sern_read.known_arg('header').numBonesUsed2))
        
        c = rdr.file.read(1)
        if c!=b'': raise ValueError(f'END NOT REACHED, pos:{rdr.file.tell()} ')
        return cls(**dict)

#Присутсвует ANI_BoneEntry2
#BITE_BEHIND_GUN_ALT.ANI
#Неужто это отвечает за анимацию присоединенных частей?

#Если у кости только 1 ключевой кадр, то повторяем его для всех 81 кадров?