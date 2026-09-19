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
    version:int = sernAs(c_int32) #12
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
class SKB_Signal:
    frame:int = sernAs(c_int16) #[EXPI 19.09.2026]
    type:int = sernAs(c_int16) #[EXPI 19.09.2026]
    sound_id:int = sernAs(c_int32) #[EXPI 19.09.2026] if type=1 then sound index from SKB_Anim.sounds; if type=0 then this global id sound. #TODO Find the places where the engine builds this table

@fixed_dataclass
class SKB_Range:
    flag_ind:int = sernAs(c_int32) #[EXPI 19.09.2026]
    start_frame:float = sernAs(c_float) #[EXPI 19.09.2026]
    end_frame:float = sernAs(c_float) #[EXPI 19.09.2026]

@sern_dataclass
class SKB_Anim:
    name: ascii_str = sernAs(ascii_char * 30)
    ani_file_name: ascii_str = sernAs(ascii_char * 64)
    fps:float = sernAs(c_float)          #[EXPI 19.09.2026] #?? seems 30.0, 32.0,
    numFrames: int = sernAs(c_int32)
    tween_time:float = sernAs(c_float)   #[EXPI 19.09.2026] Transition time to next animation #0.1/0.3 -> frame duration, maybe? ??
    next_anim_ind:int = sernAs(c_int32)  #[EXPI 19.09.2026] Special values: -1 = freeze on last frame, -2 = infinite loop #?? 0, -1, -2... 426?
    play_frames:float = sernAs(c_float)  #[EXPI 19.09.2026] But 0.0 may have a special meaning (Manual/Driven Keyframing). #?? less, but very close to numFrames !!! delta = f(d)
    mask:int = sernAs(c_int32)           #[EXPI 19.09.2026] bitmask: 1 - mirroring, 4 = Allow cache in engine [see sub_722410]. Tested on run_forward, flag 1 mirrors the start from the right foot to the left foot.

    numSounds:int = sernAs(c_int32) #[EXPI 19.09.2026]
    sounds:list[ascii_str] = sernAs(list[ascii_char * 64], rarg=KnownArg('numSounds')) #[EXPI 19.09.2026]

    numSignals:int = sernAs(c_int32) #[EXPI 19.09.2026]
    signals:list[SKB_Signal] = sernAs(rarg=KnownArg('numSignals')) #[EXPI 19.09.2026] #(kframe, smthn?)

    numMarkers:int = sernAs(c_int32) #[EXPI 19.09.2026]
    markers:list[int] = sernAs(list[c_int32], rarg=KnownArg('numMarkers')) #[EXPI 19.09.2026] List of specific frames with timeline markers #TODO Find semantic meaning
    
    numRanges:int = sernAs(c_int32) #[EXPI 19.09.2026] #small inaccuracy in [BR2 3D FILE FORMATS DOCUMENT], should be int
    ranges:list[SKB_Range] = sernAs(rarg=KnownArg('numRanges')) #[EXPI 19.09.2026]

    def sern_jwrite(self):
        from dataclasses import asdict
        di = asdict(self)
        def split_all_by_value(lst, value):
            from itertools import groupby
            return [list(group) for is_split, group in groupby(lst, key=lambda x: x != value) if is_split]
        def dec(n:str):
            di[n] = [bytes(w).decode('ascii', errors='replace') for w in split_all_by_value( [q for q in list(di[n])],0)]
        dec('name')
        dec('ani_file_name')
        return di

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

#================================
#            NOTES
#================================
# ==[About EXPI vs NEW Labels]==
# Fields labeled as NEW are derived from reverse engineering the original binary code
# Fields labeled as EXPI denote that their semantic purpose relies on 
# empirical confirmation. This validation includes several methods such as:
# 1 Verifying the hypothesis by scanning all game assets (even for Br2GOC and Br2Cut)
# 2 Performing target field modifications, and observing the game behavior in response.

# ==[Semantic analysis of SKB_Anim.mask & 4]==
# A global scan across all BR2GOC and BR2Cut files shows that this flag is set 
# only for animations involving multiple entities, including pair 
# fatalities, throw states, and monster feeding tracks.
# However, according to sub_722410, this is implemented as regular caching.

# ==[The ranges of the following fields were confirmed by scanning all files BR2GOC and BR2Cut]==
# SKB_Header.version = 12
# SKB_Anim.next_anim_ind = [-2, -1, ..., SKB_File.numAnims)
# SKB_Anim.play_frames  = [0...SKB_Anim.numFrames]
# SKB_Anim.mask = [0, 1, 4], but not for 5 (1|4)
# SKB_Anim.markers = [0...SKB_Anim.numFrames] (for each)
# SKB_Signal.type = [0, 1]
# SKB_Signal.value = [0...SKB_Anim.numSounds) (for each if signal.type=1)
# SKB_Range.flag_ind = [0...SKB_File.numFlags)

# ==[All possible SKB_File.flags]==
# After scanning all the game files, the following flags were found:
# [acro_trans, allow_recovery, allowharpoon, allowturning, attract_victim, bbladedamage, 
# bite_me, bladedamage1, bladedamage2, bladedamage3, bladedamage4, check_hit_wall, 
# check_pole_turn, check_release, combocontinue, continueevade, create_beam, fire_left_gun, 
# fire_right_gun, fire_roach, firegundamage, gundamage2, gundamage3, head_damage, 
# ignoregravity, jumpTwistLand, lbladedamag2, lbladedamage, lbladedamage1, lbladedamage2, 
# lbladedamage3, lbladedamage4, lclaw2, lclaw3, lfootdamage, lfootdamage1, 
# lfootdamage2, lfootdamage3, lfootdamage4, lhand_damage, lhanddamage1, lhanddamage2, 
# lhanddamage3, lkick3, nogravity,  nosliding, onground, ragecontinue, 
# rbladedamage, rbladedamage1, rbladedamage2, rbladedamage3, rbladedamage4, rclaw1, 
# rclaw2, rclaw3, rfootdamage, rfootdamage1, rfootdamage2, rfootdamage3, 
# rfootdamage4, rhand_damage, rhanddamage1, rhanddamage2, rhanddamage3, staff_blink, 
# vulnerable, weapondamage1, weapondamage2, weapondamage3]

# ==[Resource Compiler & Leftover Strings Discovery]==
# BR2 uses null-terminated, fixed-length strings. Interestingly, inside the 
# SKB binaries, the padding bytes after the null-terminator contain readable 
# text fragments. These uncleaned chunks allowed us to reconstruct the exact 
# semantic names of various fields and structures used here (like <markers>).
#
# This implies that TRI's internal tools originally generated human-readable 
# text configuration files, which a resource compiler then baked into fixed 
# binary streams without clearing the memory buffers. 
#
# Consequently, the game engine might still contain legacy parsers for text-based 
# equivalents. This theory perfectly explains the game's file extension pairings: 
# text-based formats (SKL, DFM, TIFF) vs. compiled binary formats (SKB, BFM, TEX).

#Легкие анимации
#Почти все неизвестные поля по нулям, это должен быть хороший знак для начала исследования этого формата
#rayne.bfm -> 
#   stand_alert.ani - базовая стойка
#   walk_forward_start.ani
#   run_start.ani