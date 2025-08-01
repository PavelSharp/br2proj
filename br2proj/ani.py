# This work is based on
#     BR2 3D FILE FORMATS DOCUMENT
#     by BloodHammer (Mjolnir) (v1.19 - 15.01.2006)
#Available at https://gamebanana.com/tools/18225 (Thanks KillerExe_01 for published it)

from .sern import sern_core
from .sern.sern_core import sernAs, KnownArg
from .sern.sern_read import sern_dataclass, le_fixed_dataclass as fixed_dataclass
from .sern import sern_read
from .sern.fixed_types import *

@fixed_dataclass
class ANI_Header:
    version:int = sernAs(c_int32)
    numFrames:int = sernAs(c_int32)
    numBonesUsed:int = sernAs(c_int32) #// same bones may have multiple transformations applied
    numBonesUsed2:int = sernAs(c_int32) #/? number of some more entries more at the end...
    animPoolSize:int = sernAs(c_int32) #// size of animdata (+sometimes more, entry2 depending?)

@fixed_dataclass
class ANI_BoneEntry:
    name:ascii_str = sernAs(ascii_char*24)
    tt:int = sernAs(c_int32) #/? transformation type (0..8)
    numKeyFrames:int = sernAs(c_int32)

@fixed_dataclass
class ANI_BoneEntry2: #?? binding of some sort??
    name:ascii_str = sernAs(ascii_char*24) #/? of what? sync/wall/rail/pole/gun/spark... ?
    bone:ascii_str =sernAs(ascii_char*24) #/? tag, offset? OPTIONAL!
    a:int = sernAs(c_int32) #??
    b:int = sernAs(c_int32) #??
    c:int = sernAs(c_int32) #0

@sern_dataclass
class ANI_File:
    header:ANI_Header
    animPool:list[int] = sernAs(list[c_uint8], rarg=KnownArg('header').animPoolSize)
    used_bones: list[ANI_BoneEntry] = sernAs(rarg=KnownArg('header').numBonesUsed)
    a:int = sernAs(c_int32) #(0/5)
    b:int = sernAs(c_int32) #(0)
    unk1: list[ANI_BoneEntry2] = sernAs(rarg=KnownArg('header').numBonesUsed2)

#Присутсвует ANI_BoneEntry2
#BITE_BEHIND_GUN_ALT.ANI
#Неужто это отвечает за анимацию присоединенных частей?

#Если у кости только 1 ключевой кадр, то повторяем его для всех 81 кадров?