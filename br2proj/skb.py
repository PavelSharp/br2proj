# This work is based on
#     BR2 3D FILE FORMATS DOCUMENT
#     by BloodHammer (Mjolnir) (v1.19 - 15.01.2006)
#Available at https://gamebanana.com/tools/18225 (Thanks KillerExe_01 for published it)

from dataclasses import dataclass

#TODO .sern .sern.fixed_types
from .sern import sern_read
from .sern.fixed_types import *
#from sern import jexplore

@sern_read.fixeddata
class SKB_Header:
    verison:c_int32
    numBones:c_int32

@dataclass
class SKB_Bone:
    name:ascii_char * 28
    parentBone:c_int32  #-1 for the root bone 
    symBone:c_int32     #symmetrical bone, -1 for the centric ones    
    matrix: (c_float*3)*3   #/? rotation? (what for?) determinants are 1...
    #умножение на транспонированную к самой себе = единичная матрица - эта матрица вращения

@dataclass
class SKB_Anim:

    @sern_read.fixeddata
    class SKB_Unk3:
        a:c_int32
        b:c_int32

    @sern_read.fixeddata
    class SKB_Unk5:
        a:c_int32
        b:c_float
        c:c_float

    name:ascii_char * 30
    path:ascii_char * 64

    a:c_float             #?? seems 30.0, 32.0, 
    numFrames:c_int32
    c:c_float           #0.1/0.3 -> frame duration, maybe? ??
    d:c_int32           #?? 0, -1, -2... 426?
    e:c_float           #?? less, but very close to numFrames !!! delta = f(d)
    
    i1:c_int32
    i2:c_int32
    i2_data:list[c_uint8] #vs char vs bytearray
    i3:c_int32
    i3_data:list[SKB_Unk3] #(kframe, smthn?)	
    i4:c_int32
    i4_data:list[c_int32]
    i5:c_float #TODO Why list length is float?
    i5_data:list[SKB_Unk5]
    @classmethod
    def sern_read(cls, rdr:sern_read.reader):
        
        dict = rdr.top_fields_read (cls, 'name', 'path', 'a', 'numFrames', 'c','d','e', 'i1')

        def step_read(f1, f1t, f2):
            nonlocal cls,rdr,dict
            val = rdr.auto_read(f1t)
            print(f1, val)
            dict[f1] = val
            dict |= rdr.top_fields_read(cls, (f2, int(val)))
        
        step_read('i2', c_int32, 'i2_data')
        step_read('i3', c_int32, 'i3_data')
        step_read('i4', c_int32, 'i4_data')
        step_read('i5', c_float, 'i5_data')
        #TODO crashed rayne.skl, on combo_up_kkk 
        #jexplore.jprint(dict)
        return cls(**dict)
    
@dataclass
class SKB_File:
    header:SKB_Header
    bones:list[SKB_Bone]
    numFlags:c_int32
    flags:list[ascii_char * 16]
    numAnims:c_int32
    anims:list[SKB_Anim]
    @classmethod
    def sern_read(cls, rdr:sern_read.reader, enable_anims = True):
        dict = rdr.top_fields_read(cls, 
                'header',
                ('bones', sern_read.known_arg('header').numBones),
                'numFlags',
                ('flags', sern_read.known_arg('numFlags')),
                'numAnims',
            )
        if enable_anims:
            dict['anims'] = rdr.auto_read(list[SKB_Anim], dict['numAnims'])
        else:
            dict['anims'] = 'disabled'

        return cls(**dict)

		