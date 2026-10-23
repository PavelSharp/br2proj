# This work is based on
#     BR2 3D FILE FORMATS DOCUMENT
#     by BloodHammer (Mjolnir) (v1.19 - 15.01.2006)
#Available at https://gamebanana.com/tools/18225 (Thanks KillerExe_01 for published it)
from enum import IntEnum

from .sern import sern_core
from .sern.sern_core import sernAs, KnownArg
from .sern.sern_read import sern_dataclass, le_fixed_dataclass as fixed_dataclass
from .sern import sern_read
from .sern.fixed_types import *

class AniTrackType(IntEnum):
    POS         = 0
    SCALE       = 1
    ROT_X       = 2
    ROT_Y       = 3
    ROT_Z       = 4
    ROT_XY      = 5
    ROT_YZ      = 6
    ROT_XZ      = 7
    ROT         = 8

@fixed_dataclass
class ANI_Header:
    version:int = sernAs(c_int32) #3
    frames_count:int = sernAs(c_int32) #[EXPI 18.10.2026] Duration in frames (seconds=frames/SKB_Anim.fps). Engine uses constant extrapolation if necessary.
    bone_tracks_count:int = sernAs(c_int32) #Multiple tracks of different types may target the same bone
    tag_tracks_count:int = sernAs(c_int32) 
    anim_pool_size:int = sernAs(c_int32) #Total size of the anim_pool in bytes.

@fixed_dataclass
class ANI_BoneTrack:
    bone_name:ascii_str = sernAs(ascii_char*24)
    track_type_raw:int = sernAs(c_int32)
    keyframes:int = sernAs(c_int32)
    @property
    def track_type(self): return AniTrackType(self.track_type_raw)

@fixed_dataclass
class ANI_TagTrack:
    tag_name:ascii_str = sernAs(ascii_char*24)
    bone_name:ascii_str = sernAs(ascii_char*24) #May empty #TODO Does an empty string denote binding to the root bone?
    pos_keyframes:int = sernAs(c_int32) #[EXPI 22.09.2026]
    rot_keyframes:int = sernAs(c_int32) #[EXPI 22.09.2026]
    scale_keyframes:int = sernAs(c_int32) #[EXPI 22.09.2026]
    @property
    def is_bone_attached(self): return len(str(self.bone_name))>0

@sern_dataclass
class ANI_File:
    ROOT_POS_TRACK_TYPE = AniTrackType.POS
    ROOT_ROT_TRACK_TYPE = AniTrackType.ROT
    
    header:ANI_Header
    anim_pool:list[int] = sernAs(list[c_uint8], rarg=KnownArg('header').anim_pool_size)
    bone_tracks: list[ANI_BoneTrack] = sernAs(rarg=KnownArg('header').bone_tracks_count)
    root_pos_keyframes:int = sernAs(c_int32) #[EXPI 21.09.2026] #(0/5)
    root_rot_keyframes:int = sernAs(c_int32) #[EXPI 21.09.2026] #(0)
    tag_tracks: list[ANI_TagTrack] = sernAs(rarg=KnownArg('header').tag_tracks_count) #[EXPI 22.09.2026]

    #NOTE: Temporary hot-fix method, sern doesn't support binary writing yet
    def dbg_to_bytes(self):
        import struct
        hdr = self.header

        assert hdr.version == 3
        assert hdr.anim_pool_size == len(self.anim_pool)
        assert hdr.bone_tracks_count == len(self.bone_tracks)
        assert hdr.tag_tracks_count == len(self.tag_tracks)

        bts = bytearray()
        bts.extend(struct.pack('<iiiii', hdr.version, hdr.frames_count, hdr.bone_tracks_count, hdr.tag_tracks_count, hdr.anim_pool_size))
        
        bts.extend(bytes(self.anim_pool))
        for tr in self.bone_tracks:
            bts.extend(struct.pack('<24sii', bytes(tr.bone_name), tr.track_type_raw, tr.keyframes))

        bts.extend(struct.pack('<ii', self.root_pos_keyframes, self.root_rot_keyframes))
        for tag in self.tag_tracks:
            bts.extend(struct.pack('<24s24siii', bytes(tag.tag_name), bytes(tag.bone_name), tag.pos_keyframes, tag.rot_keyframes, tag.scale_keyframes))
        return bytes(bts)

#================================
#            NOTES
#================================

# ==[The ranges of the following fields were confirmed by scanning all files BR2GOC and BR2Cut]==
# ANI_Header.version = 3
# ANI_Header.frames_count >= max keyframe+1 calculated from pool
# ANI_BoneTrack.track_type_raw = [0...8]

#================================
#     .SKB .ANI AND BONES
#================================
#1. SHARED ANIMATIONS
# Some .SKB models reuse animations from other characters.
# For example, KESTRAL.SKB uses some Rayne animations, and DHAMPIR_F.SKB has no unique animations, referencing Rayne entirely.
# As a result, missing .SKB bones targeted by the .ANI file are safely ignored during parsing.

#2. UNUSED BONES IN NATIVE ANIMATIONS
# Even within a character's native animations (excluding shared ones), 
# ANI_BoneTracks can contain bone tracks that are completely missing from the .SKB.
#2.1   Some native animations for GENERIC_M, KAGEN_ELITE, NINJAM, SEVERIN, SLEGION, UPUNK, and ZPUNKF 
#      contain the extra 'Bip01 Footsteps' and 'eyetargetnub' tracks.
#2.2   Also, some models lack bones for tracks present in their native animations:
#      - EPHEMERA.SKB : h_back_center01, h_back_center02, h_back_center04
#      - UPUNK.SKB    : Bip01 R Forearm, Bip01 L Forearm, Eye_Right, Eye_Left
#      - ZPUNKF.SKB   : bone_right_breast, bone_left_breast, eye_rightnub, eye_leftnub, eye_lookat_nub, Eye_Target_nub
# Probably remaining from earlier development stages.
# Most importantly, IDA string analysis shows the engine has no hardcoded references to them
# with a few exceptions like 'Bip01 R/L Forearm' and 'Eye_Right/Left'.

#3. TAG ATTACHMENT BONES
# Unlike skeletal animation tracks, bone names in ANI_TagTracks are universal across all characters.
# Every model has these base bones used for tag bindings.


#================================
#         TAG ANALYSIS
#================================
# A scan of all game files yields the following results 
# Note: ANI list is filtered to include only tags with an attached bone.
# ====[Set of all tags collected from .ANI files]====
# base, bat, belly, bladeL, bladeR, chest, gun_tip, gunL, gunR, hammer, knife, left, lgun_tip, Lspark, mouth, noseL, noseR, right, Rspark, staff, sunbeam, sword, tip
# ====[Set of all tags collected from .BFM files]====
# base, belly, blade_L, blade_R, bladeL, bladeR, cannon, chest, gunL, gunR, hammer, lbreast, left, lshoulder, lthigh, mouth, noseL, noseR, rbreast, right, rshoulder, rthigh, sunbeam, sword, tip
# ====[.BFM unique (never animated)]====
# blade_L, blade_R, cannon, lbreast, lshoulder, lthigh, rbreast, rshoulder, rthigh
# ====[.ANI unique (not all tags are attached parts)]====
# bat, gun_tip, knife, lgun_tip, Lspark, Rspark, staff
# Conclusion: There is a distinct group of bone-bound tags that do not serve as anchor points for attachment meshes.

#================================
#        ANIMATION POOL
#================================
# The anim_pool is a continuous byte stream partitioned into three sequential
# logical sections processed in the following order:
# [ SECTION A: Bone Tracks ] -> [ SECTION B: Root Motion Tracks] -> [ SECTION C: Tag Tracks ]
# Each section consists of tracks, WITH A 4-BYTE ALIGNMENT enforced after each one.

# * SECTION A (Skeletal Bone Tracks):
#  - Layout: Track1, Track2... TrackN, where N equals the `ANI_BoneTrack` array size.
#  - Keyframe Count: The exact number of keyframes for each track `[i]` is defined by `ANI_BoneTrack[i].keyframes`.
#  - Keyframe Type: The keyframe layout and parsing rule for track `[i]` are indicated by `ANI_BoneTrack[i].track_type`.

# * SECTION B (Root Motion Tracks):
#  - Layout: PositionTrack, RotationTrack
#  - Keyframe Count: Defined by `root_pos_keyframes` and `root_rot_keyframes`.
#  - Keyframe Type: Position track uses Type 0 (POS); Rotation track uses Type 8 (ROT).

# * SECTION C (Tag Tracks):
#  - Layout: Triplet1, Triplet2... TripletN, where N is the `ANI_TagTrack` array size.
#  - Keyframe Count: Defined per-entry by `pos_keyframes`, `rot_keyframes`, and `scale_keyframes`.
#  - Keyframe Type: Each triplet follows the pattern: Type 0 (POS) -> Type 8 (ROT) -> Type 1 (SCALE).
# --------------------------------
#    KEYFRAME SPECIFICATION
# --------------------------------
#------------------------------------------------------------------------------
# ID | Type    | Layout | Size | Equivalent tuple | Features                  |
# ---+---------+--------+------+------------------+---------------------------+
#  0 | POS     | 'ifff' |  16B | (kf, x, y, z)    | -                         | 
#  1 | SCALE   | 'ifff' |  16B | (kf, x, y, z)    | Non-uniform for leaf bones| 
#  2 | ROT_X   | 'hh'   |   4B | (kf, x, 0, 0)    | Quantized, Swizzled       |
#  3 | ROT_Y   | 'hh'   |   4B | (kf, 0, y, 0)    | Quantized, Swizzled       | 
#  4 | ROT_Z   | 'hh'   |   4B | (kf, 0, 0, z)    | Quantized, Swizzled       |
#  5 | ROT_XY  | 'hhh'  |   6B | (kf, x, y, 0)    | Quantized, Swizzled       |
#  6 | ROT_YZ  | 'hhh'  |   6B | (kf, 0, y, z)    | Quantized, Swizzled       |
#  7 | ROT_XZ  | 'hhh'  |   6B | (kf, x, 0, z)    | Quantized, Swizzled       |
#  8 | ROT     | 'hhhh' |   8B | (kf, x, y, z)    | Quantized, Swizzled       |

#===About features===
#1. Rotations in .ANI files are quantized to integers. The original [-pi, +pi] range is mapped to [-32768, 32767]. [BloodHammer was right in 2006]
#2. Swizzled refers to axis permutation. The read tuple of xyz angles must be transformed into yxz order.
#3. Rotations are stored as Euler angles using the ZXY axis multiplication order.

#===About space===
#Unlike modern software that expects bone-space data, this distinct choice is driven by optimization.
#1. Position is given in Character Orientation space, where the origin is the bone's rest position (the sum of BFM_Bones.pos).
#2. Scale is given in Character Space.
#3. All rotation channels relative to SKB_Bone.Matrix.


#================================
#         IDA References
#================================
# sub_721820 - Validates version 3, reads track counts, and shows the anim_pool layout.
#              Proves byte sizes for track types 0-8 and enforces 4-byte pointer alignment after tracks.
# sub_720790 - Decodes quantized rotation tracks (types 2-8) into quaternions via binary search and angular Wrap.
#              Proves the 'ZXY' Euler rotation order during angle unpacking conversion via Math_SinCos.
# sub_7227A0 - Samples frames using vector linear interpolation (Lerp) for track types 0 and 1, 
#              and converts rotation track types 2-8 into quaternions.


#================================
#       ALL POSSIBLE TAGS
#================================
# Here is the complete list of tags obtained by scanning all game files. 
# They are split into two groups: where the bone name is empty and where it is assigned.
# And finally, group 3 shows the tags collected from .BFM files.
# NOTE 1. Results for BR2GOC and BR2Cut versions are identical.
# NOTE 2. Left of ':' are .SKB filenames without extension to save space.

#==[ANI_TagTrack.bone_name is empty]==
# BOAR, BRUTE, KAGEN_ELITE, LPUNK, UPUNK, ZPUNK: sync
# DHAMPIR_F, RAYNE, RAYNE_ARMOR, RAYNE_COWGIRL, RAYNE_DARK, RAYNE_DRESS, RAYNE_SCHOOLGIRL: aim, blood_blade, feed, next, pole, previous, rail, sync, vert, victim, wall
# DHAMPIR_M: feed, rail, sync
# FERRIL: Lspark, Lspark01, Rspark, rail
# FOREMAN: sparks, sync
# KAGAN: sword, sync
# KESTRAL: aim, next, pole, previous, rail, wall
# LOCKDOWN_TURNED, ZERENZKI_TURNED: barrel, sync
# NINJAF: sword
# UNRAVELER: belly, pole, sync

#==[ANI_TagTrack.bone_name is NOT empty]==
# BOAR: bat(Bip01 R Hand), chest(Bip01 Spine2), gunR(Bip01 R Hand), knife(Bip01 L Hand)
# BRUTE: mouth(Bip01 Jaw), noseL(Bip01 Head), noseR(Bip01 Head)
# DHAMPIR_F, RAYNE_ARMOR, RAYNE_COWGIRL, RAYNE_DARK, RAYNE_DRESS, RAYNE_SCHOOLGIRL: Lspark(Bip01 L Foot), Rspark(Bip01 R Foot), bladeL(Bip01 L Forearm), bladeR(Bip01 R Forearm), 
# gunL(Bip01 L Forearm), gunL(Bip01 L Hand), gunR(Bip01 R Forearm), gunR(Bip01 R Hand), gun_tip(Bip01 R Forearm), lgun_tip(Bip01 L Forearm)
# DHAMPIR_M: Lspark(Bip01 L Foot), Rspark(Bip01 R Foot), bladeL(Bip01 L Hand), bladeR(Bip01 R Hand)
# FOREMAN: hammer(Bip01 R Hand)
# FPUNK_FEMALE: bat(Bip01 R Hand), gunR(Bip01 R Hand), knife(Bip01 L Hand)
# KAGAN: sunbeam(Bip01 L Hand)
# KAGEN_ELITE: gunL(Bip01 L Hand), gunR(Bip01 R Hand)
# KESTRAL: gunL(Bip01 L Forearm), gunR(Bip01 R Forearm)
# LPUNK, UPUNK, ZPUNK: chest(Bip01 Spine2), gunR(Bip01 R Hand), knife(Bip01 L Hand)
# NINJAF: gunR(Bip01 R Hand), sword(Bip01 R Hand)
# POLICEMAN: gunR(Bip01 R Hand)
# SLEGION: left(Bip01 L Hand), right(Bip01 R Hand)
# TURRET_BIOGUN: tip(pivot)
# TURRET_MACHINEGUN, TURRET_SUNGUN: base(pivot), tip(pivot)
# UNRAVELER: belly(Bip01 Prop3)
# ZERENZKI: staff(Bip01 Prop1)
# ZPUNKF: gunR(Bip01 R Hand), knife(Bip01 L Hand)


#==[All discovered tags (sockets) from .BFM files]==
# BIO_ARMOR.BFM: cannon, lshoulder, lthigh, rshoulder, rthigh
# BOAR.BFM: chest, gunR
# BRUTE.BFM: mouth, noseL, noseR
# DHAMPIR.BFM, KESTRAL.BFM: bladeL, bladeR
# DHAMPIR_F.BFM, RAYNE.BFM, RAYNE_ARMOR.BFM, RAYNE_COWGIRL.BFM, RAYNE_DARK.BFM, RAYNE_DRESS.BFM, RAYNE_DRESS_BLUE.BFM, RAYNE_DRESS_DRAGON.BFM, RAYNE_DRESS_GREEN.BFM, RAYNE_DRESS_RED.BFM, RAYNE_SCHOOLGIRL.BFM: bladeL, bladeR, gunL, gunR
# EPHEMERA.BFM: blade_L, blade_R
# FOREMAN.BFM: hammer
# FPUNK_FEMALE.BFM, LPUNK.BFM, POLICEMAN.BFM, UPUNK.BFM, ZPUNK.BFM, ZPUNKF.BFM: gunR
# KAGAN.BFM: gunR, sunbeam, sword
# KAGEN_ELITE.BFM: gunL, gunR
# NINJAF.BFM, NINJAM.BFM: sword
# SLEGION.BFM: left, right
# SLEZZ.BFM: lbreast, rbreast
# TURRET_BIOGUN.BFM: tip
# TURRET_MACHINEGUN.BFM, TURRET_SUNGUN.BFM: base, tip
# UNRAVELER.BFM: belly, mouth


#================================
#    TAG KEYFRAME EXAMPLES
#================================
# This section provides examples of .ANI files containing tag tracks, 
# sorted in descending order of their total keyframe count.
# Keyframe counts are displayed in the format: position/rotation/scale.

# FOREMAN\FEED.ANI                sparks: 152/155/1, sync: 110/1/0, hammer: 1/1/0
# KAGAN\GRABATTACK.ANI            sword: 126/127/0, sync: 97/10/0
# KAGAN\COMBO4.ANI                sword: 130/124/0, sunbeam: 7/19/0
# KAGAN\COMBO6.ANI                sword: 134/134/0
# KAGAN\COMBO5.ANI                sword: 127/127/0
# KAGAN\SHOCKWAVE.ANI             sword: 117/118/0, sunbeam: 1/1/0
# KAGAN\COMBO3.ANI                sword: 115/116/0
# FOREMAN\ANGRY_SMASH.ANI         sparks: 109/109/1, hammer: 1/1/0
# KAGAN\COMBO1.ANI                sword: 99/101/0, sunbeam: 6/13/0
# FOREMAN\FIDGET_TWIRL.ANI        sparks: 76/76/1, hammer: 8/27/0
# KAGAN\COMBO2.ANI                sword: 81/81/0
# RAYNE\BITE_STAND_LOOP.ANI       blood_blade: 60/24/0, feed: 72/1/0, sync: 0/1/0
# BRUTE\BRUTE_FEED.ANI            sync: 150/0/0, noseL: 1/1/0, noseR: 1/1/0, mouth: 1/1/1
# KAGAN\FIRERAY.ANI               sword: 57/61/0, sunbeam: 5/27/0
# RAYNE\BITE_STAND_BLADE.ANI      blood_blade: 67/1/0, feed: 69/1/0, sync: 5/1/0
# FOREMAN\ATTACK_SLIP.ANI         sparks: 48/48/1, hammer: 7/33/0
# FOREMAN\ATTACK_COMBO.ANI        sparks: 62/62/1, hammer: 6/1/0
# FERRIL\RAIL_TO_RAIL_LEFT.ANI    Lspark: 31/1/0, Lspark01: 31/1/0, rail: 31/1/0, Rspark: 31/1/0
# FOREMAN\ATTACK_OVERHEAD.ANI     sparks: 60/60/1, hammer: 6/1/0
# FOREMAN\FIDGET_SWAY_TWO.ANI     sparks: 60/59/1, hammer: 1/1/0