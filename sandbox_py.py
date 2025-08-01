def prepare_module(name:str):
    from types import ModuleType
    from sys import modules
    from pathlib import Path
    mod = ModuleType(name)
    mod.__path__ =  [str(Path(__file__).parent / name)]
    modules[name] = mod
prepare_module('br2proj')

from br2proj import skb, bfm, smb
from br2proj.sern import fixed_types, sern_read, sern_core, jexplore
from dataclasses import dataclass, fields
import typing
from ctypes import *
import ctypes as ct
import numpy as np
import sys

def fixeddata(cls=None, /, **kwargs):
    if cls is None:
        return lambda cls: fixeddata(cls, **kwargs)
    
    cls = type(cls.__name__, (cls, LittleEndianStructure), dict(cls.__dict__))
    cls = dataclass(init=False, **kwargs)(cls)
    cls._pack_ = 1
    cls._fields_ = [(field.name, field.type) for field in fields(cls)]

    return cls

#@sern_read.fixeddata
#@dataclass(init=False)
class SMB_Transform2(LittleEndianStructure):
    pos:c_float*3
    _fields_ = [("pos", c_float *3)]
    _pack_ = 1
    def __len__(self): return 3
    def __getitem__(self, n): return self.pos[n]

@dataclass
class SMB_Transform3:
    pos:c_float*3
    #_pack_ = 2
    def __len__(self): return 3
    def __getitem__(self, n): return self.pos[n]

@fixeddata
class SMB_Transform:
    pos:c_float*3
    def __len__(self): return 3
    def __getitem__(self, n): return self.pos[n]

from typing import Dict, List, Tuple




from dataclasses import field
from typing import Any
from collections.abc import Callable

@dataclass
class TupleFixer:
    @staticmethod
    def _to_fixed(typ):
        def flat_tuple(typ):
            if typing.get_origin(typ) is tuple:
                for arg in typing.get_args(typ): 
                    yield from flat_tuple(arg)
            else:
                yield typ
        fields = []
        for ind, tp in enumerate(flat_tuple(typ)):
            if not sern_read._utils.is_fixed_type(tp): return None
            fields.append((f'sern_field_{ind}', tp))
        from dataclasses import make_dataclass
        return make_dataclass(f'sern_fixed_tuple_{len(fields)}', fields)
    
    @staticmethod
    def _from_fixed(typ, obj):
        def build(typ, gen):
            if typing.get_origin(typ) is not tuple: return next(gen)
            args = typing.get_args(typ)
            return tuple(build(arg, gen) for arg in args)
        return build(typ, (getattr(obj, fld.name) for fld in fields(obj)))

    ORIGINAL_TYP_ATTR = '_sern_original_typ'
    fixeddata: Callable | None = field(default_factory=lambda: sern_read.fixeddata())

    def to_fixed(self, typ):
        if (cls := self._to_fixed(typ)) is None: return None
        if self.fixeddata: cls = self.fixeddata(cls)
        if hasattr(cls, self.ORIGINAL_TYP_ATTR): raise ValueError(f'Name conflict detected, {typ}')
        setattr(cls, self.ORIGINAL_TYP_ATTR, typ) 
        return cls

    def from_fixed(self, obj, typ = None):
        if typ is None: typ = getattr(type(obj), self.ORIGINAL_TYP_ATTR, None)
        if typ is None: raise TypeError('Original tuple annotation not attached to this object')
        return self._from_fixed(typ, obj)

    #def to_fixed(self, typ): return self.fixeddata(tp) if (tp := self._to_fixed(typ)) else None
    #def from_fixed(self, typ, obj): return self._from_fixed(typ, obj)


@dataclass
class DataVec:
    x: c_float
    y: c_float

import numpy as np
import numpy.typing as npt

#from typing import get_type_hints
#print(typing.get_origin(typing.get_args(typing.get_type_hints(foo)['arr5'])[1]) is np.dtype)

#qw:np.ndarray[tuple[int], np.dtype[np.int32]] = np.array([1,2,3], dtype=np.int32)
#qw2:np.ndarray[typing.Any, np.dtype[pixel_rgb]] = np.zeros((3,3), pixel_rgb)

# TODO
# 1)[Частично] Написать тесты
# 1.1)[Сделано] Написать поток (typing.IO[bytes]) который генерирует байты 0,1...256, 0,1...256, ....
# 2)Посмотреть релизацию fixeddata у chatgpt которая добавляет поле pack только если 1
# 2.1)Написать тест для этого кейса с numpy
# 3)[Сделано] Добавить поддержку numpy
# 4)Подумать над TupleFixer, переименовать в FixedOptimization, стоит ли вводить более обшею оптимизацию для NamedTuple, предусмотреть тесты для tuplefixer
# 5)Исправить типизацию в tex.py, перейти на np.ndarray[tuple[int, int], np.float64] вместо npt
#6) Глобально перейти на Annotated[int, SernAs(c_int32)], предусмотреть typereposity[временно отказаться]. Обноваить fixeddata, учесть это обновление для кортежей
# se.int32 se.an_int32 vs se.an_int32 se.c_int32, а массивы анноцировать так
#  Annotated[ct.Array, SernAs(ct.float * 3)]
#6.1)[Сделано] Синтаксис валидаторов(т.е. как функция валидации)
# SernAs(c_int32, validator=SernExpected(4))
# SernAs(c_int32, validator=SernExpectedRange(4,6))
# SernAs(c_int32, validator=user_validator)
# 7)[Сделано] Поддежка завимостей
# @dataclass
# class MyData:
#     length: int
#     data: Annotated[list[int], SernAs(KnownArg('length'))]
#8)Протокол серриализации для sern_jwrite
#9)[Почти сделано, AnnoChecker.compare]AnnoChecker, ManualReadable - проанализировать возвращаемый тип в аннотаци
#10)В SernAs ввести аргумент для отключения валидации?
#11)[Сделано]В модуле sern_read отказаться от библиотеки ctypes, вместо - fixedtypes (as ft)

tp1 = tuple[list[DataVec], list[DataVec]]
#tp2 = tuple[list[NamedVec2], list[NamedVec3]]
tp3 = tuple[list[tuple[c_float,c_float]], list[tuple[c_float,c_float]]]

tp4 = npt.NDArray[np.int32]


from br2proj.sern import sern_tests
from br2proj.sern.sern_core import sernAs
from typing import Annotated
import unittest

unittest.main(module=sern_tests, argv=['ignored'], exit=False, verbosity=2)

@dataclass
class SMB_Header2:
    version: Annotated[int,  sernAs(c_int32, validator=(lambda x: x==4, '', 'warning'))]

# class mant:
#     @classmethod
#     def sern_read(cls, rdr:sern_read.reader, *args) -> 'mant':
#         return mant()

class mant2:
    @classmethod
    def sern_read(cls, rdr:sern_read.reader, *args) -> int:
        return 0

class c_intChild(c_int):
    pass

class intChild(int):
    pass
         
@dataclass
class SMB_Header:

    version: Annotated[int,  sernAs(c_int32, validator=(lambda x: x==4, '', 'warning'))]
    numMeshes: Annotated[int,  sernAs(c_int32, validator=sern_core.Validators.const(4))]
    
    meshes:Annotated[list[int], sernAs(list[c_int32], args=(sern_read.KnownArg('numMeshes'),))]
    meshes2:Annotated[list[list[int]], sernAs(list[list[c_int32]], args=(sern_read.KnownArg('numMeshes'),10))]
    
    numCollisionMeshes: Annotated[int, sernAs(c_int32)]
    #man:mant
    man2:Annotated[int, sernAs(mant2)]

    numEmitters: Annotated[int, sernAs(c_int32)]
    numTexPack: Annotated[int, sernAs(c_int32)]
    numFrames: Annotated[int, sernAs(c_int32)]
    fps: Annotated[int, sernAs(c_float)]

@dataclass
class SMB_Header2:
    ints1:Annotated[list[int], sernAs(c_int*5)]
    ints2:Annotated[list[int], sernAs(list[c_int], read_args=(10,))]
    ints3:c_int32
    pass

# def f1(_):
#     print('q')
#     return False

# def f2(_):
#     print('w')
# sern_core.Validators.check(f1).map(f2)(234, sern_core.ValidationInfo(1,2,'a',int))
#print(sern_read.reader.compare_types(list[int], list[tuple[c_int, c_int]]))

# with open('D:\Games\Bloodrayne 2_min\MODELS\PARK_CHIPPER_ANIM.SMB') as s:
#      np.fromfile(s, dtype=np.int32, count=1)

# rd = sern_read.reader.read_all('D:\Games\Bloodrayne 2_min\MODELS\PARK_CHIPPER_ANIM.SMB', npt.NDArray, (3,'i4'))
# sys.exit()

def decorator(cls = None,*, arg:int=2):
    def wrap(cls):
        return dataclass()(cls)
    return wrap if cls is None else wrap(cls)

class SMB_Vertex:
    pass
    
@dataclass
class SMB_Mesh:
    points: list[SMB_Vertex]

sys.exit()
rd = sern_read.reader.read_all('D:\Games\Bloodrayne 2_min\MODELS\PARK_CHIPPER_ANIM.SMB', SMB_Header2)
sys.exit()

SernAs(validator= sern_read.core.Validators.const(4))
print(isinstance(lambda val: val==4, sern_read.core.Validator))
rd = sern_read.reader.read_all('D:\Games\Bloodrayne 2_min\MODELS\PARK_CHIPPER_ANIM.SMB', SMB_Header) #, 5, 3
#print(isinstance(rd.meshes2[0], list[list[int]]))
#npt.NDArray[typing.Any]
#np.ndarray[something, np.ndarray[typing.Any]]



import ctypes

#print(rd.shape, rd.dtype)

'''
from typing import NamedTuple
class MyVec3(NamedTuple):
    x: float
    y: float
    z: float

fx = TupleFixer(sern_read.fixeddata(endian = sern_read.endian.BIG))

#ft=fx.to_fixed(tuple[c_float,tuple[c_int, c_float]])
ft=fx.to_fixed(MyVec3)
rd = sern_read.reader.read_all('D:\Games\Bloodrayne 2_min\MODELS\PARK_CHIPPER_ANIM.SMB', ft)
obj = fx.from_fixed(rd)
#tuple[list[list[int]], list[int]] 10 10 3
#Tuple[list[dataclass], list[dataclass]] 10 10
w = tuple[list[tuple[c_float,c_float]], list[tuple[c_float,c_float]]]
#w = tuple[list[c_float], list[c_float]]
t = typing.get_args(w)
#rd:smb.SMB_File = sern_read.reader.read_all('D:\Games\Bloodrayne 2_min\MODELS\PARK_CHIPPER_ANIM.SMB', w, 10)
rd = sern_read.reader.read_all('D:\Games\Bloodrayne 2_min\MODELS\PARK_CHIPPER_ANIM.SMB', w, 3,2)
'''

'''
ani = rd.animation
s = SMB_Transform2((0,0,0))
#q=[func for func in rd.__dict__ if callable(func)]
data = np.array([[s,s,s],[s,s,s]], dtype=SMB_Transform2).view(np.float32)#.astype(np.float32)
print(data)
'''
'''
bf = sern_read.reader.read_all(
    "D:\Games\Bloodrayne 2_min\MODELS\RAYNE.BFM", 
    bfm.BFM_File)

jexplore.jprint(bf, path='D:/br2dec/blender/br2proj/bfmdel.json')
'''

'''
import sern.jexplore
import skb
import sern
from sern import sern_read
from sern import jexplore
from sern.fixed_types import *
import bfm
from dataclasses import dataclass

with open("D:\Games\Bloodrayne 2_min\MODELS\RAYNE.BFM", 'rb') as file:
    reader = sern.sern_read.reader(file)

    bf = reader.auto_read(bfm.BFM_File)


    sern.jexplore.jprint(bf, path='D:/br2dec/blender/br2proj/bfmdel.json')
    pass
'''

'''
with open("D:\Games\Bloodrayne 2_min\DATA\RAYNE.SKB", 'rb') as file:
    reader = sern.sern_read.reader(file)
    sk = reader.auto_read(skb.SKB_File, False)
    sern.jexplore.jprint(sk, path='D:/br2dec/blender/br2proj\skbdel.txt')
'''

'''
import struct
import os

import re
import ctypes

import inspect
#debug only
import json

from smb import *
import tex

from ctypes import *
from dataclasses import dataclass
import sern.sern_read as sern_read
import typing
'''



#2TT = c_double

#2@sern_read.fixeddata(pack = 0)
#2class S:
#2    field1: TT
#2    field2: TT*3

#@dataclass
#2class S2(ctypes.Structure):
#2    _fields_ = [("field1", c_int32), ("field2", c_wchar*3)]
   
#2q=S()
#print(type(q.field1), type(q.field2))

#@dataclass
#class C(ctypes.Structure):
#    field1: ctypes.c_int32
#    field2: ctypes.c_uint16
#bts = b';;;'
#q=S(b'0', bytes(b"4"))
#q=S('q', 'qwe')
#print(type(q.field1), type(q.field2))

"""
@dataclass(unsafe_hash=True)
class   q:
    w:int
        
        t = tuple[tuple[c_int32, tuple[tuple[tuple[c_int32]]]], c_int32, c_int32, c_int32, c_int32, c_float]
        qwe = sern.sern_reader()
        #print(qwe.convert_to_fixed(file, t))
        vals = [ct.c_int16(1), ct.c_int32(2), ct.c_int64(3), ct.c_float(4.14),ct.c_bool(True)]
"""


#2with open("D:\Games\Bloodrayne 2_min\MODELS\WEAPONS_RAYNES_GUN.SMB", 'rb') as file:
#2    smb = sern_read.reader(file).auto_read(SMB_File)
#2    sern_read.jprint(smb, path='D:/br2dec/blender/del.txt')
#2    sys.exit()

'''
with open("D:\Games\Bloodrayne 2_min\ART\RAYNE_NEW.TEX", 'rb') as file:
    reader = sern.reader(file)
    tx = reader.auto_read(tex.TEX_File)

    sern.jprint(tx)
    sern.jprint(tx, path='D:/br2dec/blender/del.txt')

    sys.exit()
'''

#"D:\Games\Bloodrayne 2_min\MODELS\CAMERO.SMB"

#2 with open("D:\Games\Bloodrayne 2_min\MODELS\CAMERO.SMB", 'rb') as file:
    
    #qwe = sern.sern_reader()
    #print(qwe.auto_read(file, tuple[c_int32, c_int32, list[c_int32], c_int32, c_int32, c_int32], 10))
    #err = int
    #print(sern._error(err))
    #q = sern.sern.auto_read(file, tuple[c_int32, tuple[c_int32, c_int32], tuple[c_int32, c_int32, str]])
    #2sern_read = sern_read.reader(file)
    #2smb = sern_read.auto_read(SMB_File)

    #sys.exit()
    #2o = {"q1":0, "q2":1, "q3":2}
    #2data1 = {"f0":o, "f1":3, "f2":3, "f3":[o,"qwe",'aaa', o], "f4":[10,20,30,40]}
    #2data2 = {"f1":3, "f2":3}
    #2data3 = [1,2,3,4,5,data1,7,8,9,10,11]

    #2data11 = {None:o, "f1":3, "f2":3, "f3":[o,o,o], "f4":[10,20,30,40]}
    


    #sern.jprint(smb.meshes[0].points[0])
    #2sern_read.jprint(data11)
    #2sern_read.jprint(smb)
    #2sern_read.jprint(smb, path='D:/br2dec/blender/del.txt', list_per_lim = 100, list_total_lim=None)

    #sern.jprint((c_float * 3)(1,2,3))

    #sern.jprint(smb.mesh_header)


    #print(fixed_read(file, c_int32*4))
    #q = sern.sern.auto_read(file, dict[c_int32, c_int32], 10) 
   # print(q)
    
    #print(sern.sern.auto_read(file, dict[c_int32, c_int32],10))
    #print(typing.get_origin(tuple[int, tuple[int, int]] ))
    
    

    #print(sern.sern.auto_read(file, list[list[c_int32]], c_int32(2), c_int32(3)))
    #print(list((c_int32*3)(1,2,3)))
    #print(type(sern.sern.auto_read(file, c_double)))

    #tex_packs = list(filter(None, map(lambda _: SMB_TexPack.read(file), range(smb_header.numTexPack))))
    #print(smb_header.numTexPack)