from enum import Enum, IntEnum
from typing import Callable, Any, NamedTuple, Literal, assert_never
from abc import ABC, abstractmethod

import numpy as np
import numpy.typing as npt

from .sern import sern_core
from .sern.sern_core import sernAs, KnownArg, Validators
from .sern.sern_read import sern_dataclass, le_fixed_dataclass as fixed_dataclass
from .sern import sern_read
from .sern.fixed_types import *

from . import swizzle_box
#TODO [Сделано]Пересмотреть политику импорта этого модуля - откзатаься по импорту по *, тогда в простраснтво имен попадают нежелательные типы как formats и pixel_rgba вместо этого - обычный точечный импорт

pixel_bgra = np.dtype([
    ('b', np.uint8),
    ('g', np.uint8),
    ('r', np.uint8),
    ('a', np.uint8)
])

pixel_rgb = np.dtype([
    ('r', np.uint8),
    ('g', np.uint8),
    ('b', np.uint8)
])

pixel_rgba = np.dtype([
    ('r', np.uint8),
    ('g', np.uint8),
    ('b', np.uint8),
    ('a', np.uint8)
])

npByte = np.uint8
npBytes = np.ndarray[tuple[int], np.dtype[npByte]]
np2DBytes = np.ndarray[tuple[int, int], np.dtype[npByte]]

class BrVersion(IntEnum):
    BR1 = 2
    BR2 = 3


class FormatInfo(NamedTuple):
    code:int
    desc:str
    alpha:bool #False обозначает что альфа канал отсутствует либо должен быть проигнорирован
    version:BrVersion | Literal['Any'] = 'Any'

def _bpp4Tobpp8(data:np2DBytes, order:bool) -> np2DBytes:
    nia, nib = (0, 1) if order else (1,0)
    out = np.empty((data.shape[0], data.shape[1]*2), dtype=npByte)
    out[:, nia::2], out[:, nib::2] = data >> 4, data & 15
    return out 


@sern_dataclass
class TEX_Header:
    version:int = sernAs(c_int32) #3 for br2, 2 for br1 
    format: int = sernAs(c_uint32)
    width: int = sernAs(c_int32)
    height: int = sernAs(c_int32)
    unknown1: int = sernAs(c_int32)
    mipmaps_exp2: int = sernAs(c_int32)
    #Return count of mipmaps
    @property
    def mipmaps(self): return self.mipmaps_exp2+1
    def mipmap_wh(self, mi: int): return self.width>>mi, self.height>>mi
    def mipmap_hw(self, mi: int): return self.mipmap_wh(mi)[::-1]
    def mipmap_size(self, mi: int, bpp:int=8): #bpp - bits per pixel
        w,h = self.mipmap_wh(mi)
        return (w*h*bpp+7)//8

@sern_dataclass
class TEXBr2_Header(TEX_Header):
    unknown2: int = sernAs(c_int32)
    unknown3: int = sernAs(c_int32)


@sern_dataclass
class SelectebleTexHeader:
    version:BrVersion = sernAs(c_int32, rvalidator=Validators.try_map(lambda val: BrVersion(val)))
    @classmethod
    def sern_read(cls, rdr:sern_read.reader) -> TEX_Header:
        #TODO разрешить что-то наподобие, для этой задачи ввести похожий тип на SernAs
        #rdr.auto_read(sernAs(c_int32, validator=Validators.try_map(lambda val: BrVersion(val))))
        ver = rdr.fields_read(cls, ['version'])['version']
        rdr.file.seek(-4, 1)
        return rdr.auto_read(TEXBr2_Header if ver==BrVersion.BR2 else TEX_Header)

def generic_mip(pixel_type):
    class genmip:
        @staticmethod
        def sern_read(rdr:sern_read.reader, hdr: TEX_Header, mi:int) -> npt.NDArray:
            return rdr.auto_read(npt.NDArray, (hdr.mipmap_hw(mi), pixel_type))      
    return genmip
        
def mipmaps_reader(pixel_type:type[sern_read.ManualReadable] | np.number):
    if not sern_read.isManualReadable(pixel_type):
        pixel_type = generic_mip(pixel_type) #type:ignore

    class reader:
        @staticmethod
        def sern_read(rdr:sern_read.reader, hdr: TEX_Header) -> Any: #list[npt.NDArray[_T]]
            return [rdr.auto_read(pixel_type, (hdr, mi)) for mi in range(hdr.mipmaps)]
    return reader


class TEX_Base(ABC):
    tex_subclasses = []

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.tex_subclasses.append(cls)

    @abstractmethod
    def to_rgba(self, hdr:TEX_Header, mi:int) -> npt.NDArray: #-> npt.NDArray[np.uint32]:
        raise NotImplementedError()
    
    @classmethod
    @abstractmethod
    def format_info(cls) -> FormatInfo:
        raise NotImplementedError()
    

def _to_rgba_impl(data:npt.NDArray, alpha:npt.NDArray|int|None):
    if alpha is None: alpha = data['a']
    elif isinstance(alpha, int): alpha = np.full_like(data['r'], alpha)
    return np.stack([data['r'], data['g'], data['b'], alpha], axis=-1) 


#................................
#================================
#      PC, MAC, GameCube
#================================
#................................

@sern_dataclass
class TexPC_PalettedRGB(TEX_Base):
    """
    [br1[pc,mac,gc], br2[pc]], rgb palette[256] + mips
    """
    #TODO[Закрыто, оставить NumPy, что бы все типы пикселей описывались единообразно] Нужно ли для палитры, чей размер 768 байт, использовать numpy? С одной стороны, это позволяет привести к единообразнному интерфейсу с другой средства могут быть избыточными
    palette: npt.NDArray = sernAs(rarg=(256, pixel_rgb)) #pixel_rgb * 256
    mipmaps: list[np2DBytes] = sernAs(mipmaps_reader(npByte))
    def to_rgba(self, hdr:TEX_Header, mi:int):
        return _to_rgba_impl(self.palette, 255)[self.mipmaps[mi]]
    
    @classmethod
    def format_info(cls): return FormatInfo(1, 'pc_paletted24', alpha=False)


@sern_dataclass
class TexPC_PalettedRGB_Alpha(TexPC_PalettedRGB):
    """
    [br1[pc,mac,gc], br2[pc]], rgb palette[256] + mips + alpha_mips
    """
    alphas:list[np2DBytes] = sernAs(mipmaps_reader(npByte))
    def to_rgba(self, hdr:TEX_Header, mi:int):
        pxs = super().to_rgba(hdr, mi)
        pxs[...,3] = self.alphas[mi]
        return pxs

    @classmethod
    def sern_read(cls, rdr:sern_read.reader, header: TEX_Header):
        ind8 = rdr.auto_read(TexPC_PalettedRGB, (header,))
        return cls(ind8.palette, ind8.mipmaps, **rdr.top_fields_read(cls, ('alphas', (header,))))
    
    @classmethod
    def format_info(cls): return FormatInfo(2, 'pc_8bit_with_opac', alpha=True)


@sern_dataclass
class TexPC_BGRA(TEX_Base):
    """
    [br1[pc,mac,gc], br2[pc]] bgra mips
    """
    mipmaps: list[npt.NDArray] = sernAs(mipmaps_reader(pixel_bgra))
    def to_rgba(self, hdr:TEX_Header, mi:int):
        return _to_rgba_impl(self.mipmaps[mi], None)
    
    @classmethod
    def format_info(cls): return FormatInfo(3, 'pc_32bit', alpha=True)


#................................
#================================
#           GameCube
#================================
#................................

@sern_dataclass
class TexGC_PalettedRGB_A(TEX_Base):
    """
    [br1[gc]], rgb palette[256] + alpha table[256] + mips
    """    
    palette: npt.NDArray = sernAs(rarg=(256, pixel_rgb))
    alphas: npBytes = sernAs(rarg=256)
    mipmaps: list[np2DBytes] = sernAs(mipmaps_reader(npByte))
    def to_rgba(self, hdr:TEX_Header, mi:int):
        return _to_rgba_impl(self.palette, self.alphas)[self.mipmaps[mi]]
    
    @classmethod
    def format_info(cls): return FormatInfo(8, 'pc_paletted32', alpha=True) #but used on gamecube

@sern_dataclass
class MipGC_Cmp:
    mip:npBytes 

    def unswizz(self, hdr: TEX_Header, mi:int): #-> npt.NDArray[pixel_rgba]:
        w,h = hdr.mipmap_wh(mi)
        rgba = swizzle_box.n64_codec.decode(w,h, self.mip)
        return np.frombuffer(rgba, dtype=pixel_rgba).reshape(h,w)

    @classmethod
    def sern_read(cls, rdr:sern_read.reader, hdr: TEX_Header, mi:int):
        cnt = swizzle_box.n64_codec.bytes_count(*hdr.mipmap_wh(mi))
        return cls(**rdr.top_fields_read(cls, ('mip',cnt)))

@sern_dataclass
class TexGC_Compressed(TEX_Base):
    """
    [br1[gc]], n64 compressed
    """        
    mipmaps: list[MipGC_Cmp] = sernAs(mipmaps_reader(MipGC_Cmp))
    def to_rgba(self, hdr:TEX_Header, mi:int):
        return _to_rgba_impl(self.mipmaps[mi].unswizz(hdr, mi), None)

    @classmethod
    def format_info(cls): return FormatInfo(11, 'gc_compressed', alpha=False)


#................................
#================================
#         PlayStation 2
#================================
#................................

@sern_dataclass
class PalPS2_Sw: #TexPS2Palette_Sw
    unknown: npBytes = sernAs(rarg=32)
    palette: npBytes = sernAs(rarg=1024)
    def unswizz(self): #TODO подумать над ps2_palette которая бы ожидала альфы в 255
       palette = np.frombuffer(swizzle_box.unswizzle_ps2_palette(self.palette), dtype=pixel_rgba)
       palette['a'] = ((palette['a'].astype(np.uint16) * 255) // 128).astype(np.uint8)
       return palette

@sern_dataclass
class MipPS2:
    unknown: npBytes = sernAs(rarg=32)
    mip:np2DBytes 
    @classmethod
    def sern_read(cls, rdr:sern_read.reader, hdr: TEX_Header, mi:int):
        h, w = hdr.mipmap_hw(mi)
        return cls(**rdr.top_fields_read(cls, 'unknown', ('mip',((h,w),))))

@sern_dataclass
class MipPS2_Sw:
    unknown: npBytes = sernAs(rarg=32)
    mip:npBytes
    @classmethod
    def sern_read(cls, rdr:sern_read.reader, hdr: TEX_Header, mi:int):
        return cls(**rdr.top_fields_read(cls, 'unknown', ('mip',hdr.mipmap_size(mi))))
    
    def unswizz(self, hdr: TEX_Header, mi:int):
        w, h = hdr.mipmap_wh(mi)
        data = swizzle_box.mapping_bpp8.unswizzle(w, h, self.mip, swizzle_box.Ps2Swizz)
        return np.frombuffer(data, dtype=np.uint8) #TODO innorrect shape

@sern_dataclass
class TexPS2_SwPalettedRGBA_SwMips(TEX_Base):
    """
    [br1[ps2], br2[ps2]], rgba table(swizzled) + mips(swizzled). Note: opacity eql to 128
    """    
    palette: PalPS2_Sw
    mipmaps: list[MipPS2_Sw] = sernAs(mipmaps_reader(MipPS2_Sw))
    def to_rgba(self, hdr:TEX_Header, mi:int):
       mip = self.mipmaps[mi].unswizz(hdr, mi)
       return _to_rgba_impl(self.palette.unswizz(), None)[mip]

    @classmethod
    def format_info(cls): return FormatInfo(6, 'ps2_paletted24', alpha=True) 


@sern_dataclass
class TexPS2_SwPalettedRGBA(TEX_Base):
    """
    [br1[ps2], br2[ps2]], rgba table(swizzled) + mips. Note: opacity belongs to 0 to 128
    """    
    palette: PalPS2_Sw
    mipmaps: list[MipPS2] = sernAs(mipmaps_reader(MipPS2))
    def to_rgba(self, hdr:TEX_Header, mi:int):
       mip = self.mipmaps[mi].mip
       return _to_rgba_impl(self.palette.unswizz(), None)[mip]

    @classmethod
    def format_info(cls): return FormatInfo(9, 'ps2_paletted32', alpha=True) 


#................................
#================================
#         PlayStation 2[Br1, bpp=4]
#================================
#................................

@sern_dataclass
class PalPS2_4bpp:
    unknown: npBytes = sernAs(rarg=32)
    palette: npt.NDArray = sernAs(rarg=(16, pixel_rgba))
    def unswizz(self):
       #I'm not sure about the correct interpretation of alpha.
       palette = np.copy(self.palette)
       palette['a'] = 255-((palette['a'].astype(np.uint16) * 255) // 128).astype(np.uint8)
       return palette    

@sern_dataclass
class MipPS2_Sw_4bpp_Br1:
    unknown: npBytes = sernAs(rarg=32)
    mip:npBytes
    @classmethod
    def sern_read(cls, rdr:sern_read.reader, hdr: TEX_Header, mi:int):
        return cls(**rdr.top_fields_read(cls, 'unknown', ('mip', hdr.mipmap_size(mi, bpp=4))))
    
    def unswizz(self, hdr: TEX_Header, mi:int):
        h, w = hdr.mipmap_hw(mi)
        mip = self.mip.reshape(h,w//2)
        out = _bpp4Tobpp8(mip, False)
        inds = swizzle_box.mapping_bpp8.unswizzle(w, h, out.reshape(-1), swizzle_box.Ps2Type34BitSwizz)
        return np.frombuffer(inds, dtype=npByte).reshape(h,w)
    
@sern_dataclass
class TexPS2_PalettedRGBA_SwMips_4bpp_Br1(TEX_Base):
    """
    [br1[ps2]], rgba table[16 colors] + mips. Note: The purpose of the opacity is unknown
    """    
    palette: PalPS2_4bpp
    mipmaps: list[MipPS2_Sw_4bpp_Br1] = sernAs(mipmaps_reader(MipPS2_Sw_4bpp_Br1))
    def to_rgba(self, hdr:TEX_Header, mi:int):
       mip = self.mipmaps[mi].unswizz(hdr, mi)
       return _to_rgba_impl(self.palette.unswizz(), None)[mip]

    @classmethod
    def format_info(cls): return FormatInfo(10, version=BrVersion.BR1, desc='ps2_paletted4<Br1>', alpha=True) 




#................................
#================================
#         PlayStation 2[Br2, bpp=4]
#================================
#................................
@sern_dataclass
class MipPS2_4bpp_Br2:
    unknown: npBytes = sernAs(rarg=32)
    mip:np2DBytes
    @classmethod
    def sern_read(cls, rdr:sern_read.reader, hdr: TEX_Header, mi:int):
        w,h=hdr.mipmap_wh(mi)
        return cls(**rdr.top_fields_read(cls, 'unknown', ('mip', ((h,w//2),))))
    
    def unswizz(self, hdr: TEX_Header, mi:int):
        return _bpp4Tobpp8(self.mip, False)


@sern_dataclass
class TexPS2_SwPalettedRGBA_4bpp_Br2(TEX_Base):
    """
    [br2[ps2]], rgba table[16 colors] + mips. Note: The purpose of the opacity is unknown
    For Br2[ps2], only one file exists in the 10 format: LIGHTTEST_LX_0.tex
    """    
    palette: PalPS2_4bpp
    mipmaps: list[MipPS2_4bpp_Br2] = sernAs(mipmaps_reader(MipPS2_4bpp_Br2))
    def to_rgba(self, hdr:TEX_Header, mi:int):
       mip = self.mipmaps[mi].unswizz(hdr, mi)
       return _to_rgba_impl(self.palette.unswizz(), None)[mip]
    @classmethod
    def format_info(cls): return FormatInfo(10, version=BrVersion.BR2, desc='ps2_paletted4<Br2>', alpha=True)

#................................
#================================
#              XBOX
#================================
#................................

@sern_dataclass
class MipXB_Sw:
    mip:npBytes
    def unswizz(self, hdr: TEX_Header, mi:int):
        h, w = hdr.mipmap_hw(mi)
        data = swizzle_box.mapping_bpp8.unswizzle(w, h, self.mip, swizzle_box.MortonSwizz)
        return np.frombuffer(data, dtype=np.uint8).reshape(h,w)
    
    @classmethod
    def sern_read(cls, rdr:sern_read.reader, hdr: TEX_Header, mi:int):
        return cls(**rdr.top_fields_read(cls, ('mip', hdr.mipmap_size(mi))))

@sern_dataclass
class TexXB_PalettedBGRA_SwMips(TEX_Base):
    """
    [br1[xbx], br2[xbx]], bgra table + mips(morton swizzled). Note: opacity belongs to 0 to 255
    """   
    palette: npt.NDArray = sernAs(rarg=(256, pixel_bgra))
    mipmaps: list[MipXB_Sw] = sernAs(mipmaps_reader(MipXB_Sw))
    def to_rgba(self, hdr:TEX_Header, mi:int):
       mip = self.mipmaps[mi].unswizz(hdr, mi)
       return _to_rgba_impl(self.palette, None)[mip]
    
    @classmethod
    def format_info(cls): return FormatInfo(14, 'xbox_paletted32', alpha=True)


@sern_dataclass
class TexXB_PalettedBGRX_SwMips(TexXB_PalettedBGRA_SwMips):
    """
    [br1[xbx], br2[xbx]], bgra table + mips(morton swizzled). Note: opacity eql to 255
    """  
    @classmethod
    def format_info(cls): return FormatInfo(13, 'xbox_paletted24', alpha=False)


from collections.abc import Iterable
def _build_tex_childs_dict(classes:Iterable[type[TEX_Base]]):
    ret:dict[tuple[int, int], type[TEX_Base]] = {}
    for cl in classes:
        format = cl.format_info()
        if format.version == 'Any':
            for ver in BrVersion:
                ret[(format.code, ver.value)] = cl
        else:
            ret[(format.code, format.version.value)] = cl
    return ret

@sern_dataclass
class TEX_File:
    #TEX_MAPPER = {cls.format_info().code: cls for cls in TEX_Base.tex_subclasses}
    TEX_MAPPER = _build_tex_childs_dict(TEX_Base.tex_subclasses)
    header:TEX_Header
    data: TEX_Base

    def to_rgba(self, mi:int): return self.data.to_rgba(self.header, mi)
    #TODO [1,br1,mac]RAYNE_GLOSSMAP.TEX
    @classmethod
    def sern_read(cls, rdr:sern_read.reader):
        header = rdr.auto_read(SelectebleTexHeader)
        print(type(header))
        tex_type = cls.TEX_MAPPER[header.format, header.version]
        return cls(header, rdr.auto_read(tex_type, (header, )))

# 0OVERBRIGHT_LX_0.TEX -- ARGB
# 8FT.TEX -- Indexed8
# KT_CRTMONITOR.TEX  -- Indexed8
# RAYNE_NEW.TEX" -- Indexed8Alpha
# SKYLINETHREE.TEX.001 -- pc_32bit
#BR1 contains textures with the prefix 'e3', which were probably used at the Electronic Entertainment Expo