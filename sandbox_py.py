import sys
sys.path.append("D:/br2dec/blender/br2proj/sern")

import sern.jexplore
import skb
import sern
from sern import sern_read
from sern import jexplore
from sern.fixed_types import *
import skb
import bfm
from dataclasses import dataclass

with open("D:\Games\Bloodrayne 2_min\MODELS\RAYNE.BFM", 'rb') as file:
    reader = sern.sern_read.reader(file)

    bf = reader.auto_read(bfm.BFM_File)


    sern.jexplore.jprint(bf, path='D:/br2dec/blender/br2proj/bfmdel.json')
    pass

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