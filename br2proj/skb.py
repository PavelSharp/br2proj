# This work is based on
#     BR2 3D FILE FORMATS DOCUMENT
#     by BloodHammer (Mjolnir) (v1.19 - 15.01.2006)
#Available at https://gamebanana.com/tools/18225 (Thanks KillerExe_01 for published it)

from dataclasses import dataclass

#TODO .sern .sern.fixed_types
from .sern import sern_read
from .sern.fixed_types import *
#from .sern import jexplore

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
    class SKB_Unk2:
        a:c_int16
        flag:c_int16
        b:c_int32
    
    @sern_read.fixeddata
    class SKB_Unk4:
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
    f:c_int32

    i1:c_int32
    i1_data:list[ascii_char * 64]

    i2:c_int32
    i2_data:list[SKB_Unk2] #(kframe, smthn?)

    i3:c_int32
    i3_data:list[c_int32]
    
    i4:c_int32 #small inaccuracy in [BR2 3D FILE FORMATS DOCUMENT], should be int
    i4_data:list[SKB_Unk4]
    @classmethod
    def sern_read(cls, rdr:sern_read.reader):
        dict = rdr.top_fields_read(cls, 'name', 'path', 
                    'a', 'numFrames', 'c','d','e', 'f', 
                    'i1', 
                    ('i1_data', sern_read.known_arg('i1')),
                    'i2',
                    ('i2_data', sern_read.known_arg('i2')),
                    'i3',
                    ('i3_data', sern_read.known_arg('i3')),
                    'i4',
                    ('i4_data', sern_read.known_arg('i4')),  
                    )

        
        #See sub_722410 in Br2GOC for more details
        #for i in range(dict['i2']):
        #    val = dict['i2_data'][i]
        #    if (val.flag==1):
        #        dict['i2_data'][i] = {'a': val.a, 'flag':val.flag, 'b': dict['i1_data'][val.b]}
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
    def sern_read(cls, rdr:sern_read.reader, load_anims = True):
        dict = rdr.top_fields_read(cls, 
                'header',
                ('bones', sern_read.known_arg('header').numBones),
                'numFlags',
                ('flags', sern_read.known_arg('numFlags')),
            )
        if load_anims:
            dict |= rdr.top_fields_read(cls, 
                'numAnims',
                ('anims', sern_read.known_arg('numAnims')))
        else:
            dict |= {'numAnims':0, 'anims':[]}
        #jexplore.jprint(dict, path='test.json')
        return cls(**dict)

#Легкие анимации
#Почти все неизвестные поля по нулям, это должен быть хороший знак для начала исследования этого формата
#rayne.bfm -> 
#   stand_alert.ani - базовая стойка
#   walk_forward_start.ani
#   run_start.ani