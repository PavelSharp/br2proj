# This work is based on
#     BR2 3D FILE FORMATS DOCUMENT
#     by BloodHammer (Mjolnir) (v1.19 - 15.01.2006)
#Available at https://gamebanana.com/tools/18225 (Thanks KillerExe_01 for published it)

#TODO .sern .sern.fixed_types
from .sern import sern_core
from .sern.sern_core import sernAs, KnownArg
from .sern.sern_read import sern_dataclass, le_fixed_dataclass as fixed_dataclass
from .sern import sern_read
from .sern.fixed_types import *
#from .sern import jexplore

@fixed_dataclass
class SKB_Header:
    verison:int = sernAs(c_int32)
    numBones:int = sernAs(c_int32)

@sern_dataclass
class SKB_Bone:
    name:ascii_str = sernAs(ascii_char * 24)
    name_hash: int =sernAs(c_uint32) #[NEW 27.03.2025] (according to sub_722EF0)
    parentBone:int = sernAs(c_int32)  #-1 for the root bone 
    symBone:int = sernAs(c_int32)     #symmetrical bone, -1 for the centric ones    
    matrix: Array[Array[c_float]] = sernAs((c_float*3)*3)   #/? rotation? (what for?) determinants are 1...
    #умножение на транспонированную к самой себе = единичная матрица - эта матрица вращения


@fixed_dataclass
class SKB_Unk2:
    a:int = sernAs(c_int16)
    flag:int = sernAs(c_int16)
    b:int = sernAs(c_int32)

@fixed_dataclass    
class SKB_Unk4:
    a:int = sernAs(c_int32)
    b:float = sernAs(c_float)
    c:float = sernAs(c_float)

@sern_dataclass
class SKB_Anim:
    name: ascii_str = sernAs(ascii_char * 30)
    ani_file_name: ascii_str = sernAs(ascii_char * 64)
    a:float = sernAs(c_float)             #?? seems 30.0, 32.0, 
    numFrames: int = sernAs(c_int32)
    c:float = sernAs(c_float)           #0.1/0.3 -> frame duration, maybe? ??
    d:int = sernAs(c_int32)           #?? 0, -1, -2... 426?
    e:float = sernAs(c_float)           #?? less, but very close to numFrames !!! delta = f(d)
    f:int = sernAs(c_int32)

    i1:int = sernAs(c_int32)
    i1_data:list[ascii_str] = sernAs(list[ascii_char * 64], rarg=KnownArg('i1'))

    i2:int = sernAs(c_int32)
    i2_data:list[SKB_Unk2] = sernAs(rarg=KnownArg('i2')) #(kframe, smthn?)

    i3:int = sernAs(c_int32)
    i3_data:list[int] = sernAs(list[c_int32], rarg=KnownArg('i3'))
    
    i4:int = sernAs(c_int32) #small inaccuracy in [BR2 3D FILE FORMATS DOCUMENT], should be int
    i4_data:list[SKB_Unk4] = sernAs(rarg=KnownArg('i4'))

    def sern_jwrite(self):
        from dataclasses import asdict
        di = asdict(self)
        def split_all_by_value(lst, value):
            from itertools import groupby
            return [list(group) for is_split, group in groupby(lst, key=lambda x: x != value) if is_split]
        def dec(n:str):
            di[n] = [bytes(w).decode('ascii', errors='replace') for w in split_all_by_value( [q[0] for q in list(di[n])],0)]
        dec('name')
        dec('ani_file_name')
        return di

    #See sub_722410 in Br2GOC for more details
    #for i in range(dict['i2']):
    #    val = dict['i2_data'][i]
    #    if (val.flag==1):
    #        dict['i2_data'][i] = {'a': val.a, 'flag':val.flag, 'b': dict['i1_data'][val.b]}

@sern_dataclass
class SKB_File:
    header:SKB_Header
    bones:list[SKB_Bone]
    numFlags:int = sernAs(c_int32)
    flags:list[ascii_str] = sernAs(list[ascii_char * 16])
    numAnims:int = sernAs(c_int32)
    anims:list[SKB_Anim]
    @classmethod
    def sern_read(cls, rdr:sern_read.reader, load_anims = True):
        dict = rdr.top_fields_read(cls, 
                'header',
                ('bones', KnownArg('header').numBones),
                'numFlags',
                ('flags', KnownArg('numFlags')),
            )
        if load_anims:
            dict |= rdr.top_fields_read(cls, 
                'numAnims',
                ('anims', KnownArg('numAnims')))
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