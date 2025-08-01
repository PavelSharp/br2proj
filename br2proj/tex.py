from enum import Enum, IntEnum
from typing import Callable, Any

import numpy as np
import numpy.typing as npt

from .sern import sern_core
from .sern.sern_core import sernAs, KnownArg, Validators
from .sern.sern_read import sern_dataclass, le_fixed_dataclass as fixed_dataclass
from .sern import sern_read
from .sern.fixed_types import *

from . import swizzle_box
#TODO [Сделано]Пересмотреть политику импорта этого модуля - откзатаься по импорту по *, тогда в простраснтво имен попадают нежелательные типы как formats и pixel_rgba вместо этого - обычный точечный импорт

class MipLoadState(Enum):
    NOT_LOAD_CONTINUE = 0
    NOT_LOAD_BREAK = 1
    LOAD_CONTINUE = 2
    LOAD_BREAK = 3
    @classmethod
    def bool_to_single(cls, val: bool): return cls.LOAD_BREAK if val else cls.NOT_LOAD_CONTINUE

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

TEXMipChoicer = Callable[['TEX_Header', int], MipLoadState | bool] | int | None

@sern_dataclass
class TEX_Header:
    version:int = sernAs(c_int32) #3 for br2, 2 for br1 
    format: int = sernAs(c_uint32)
    width: int = sernAs(c_int32)
    height: int = sernAs(c_int32)
    unkown1: int = sernAs(c_int32)
    mipmaps_exp2: int = sernAs(c_int32)
    #Return count of mipmaps
    @property
    def mipmaps(self): return self.mipmaps_exp2+1
    #@property
    #def typed_format(self):
    #    return TEX_File.TEX_MAPPER[self.format]
    def mipmap_wh(self, mi: int): return self.width>>mi, self.height>>mi
    def mipmap_hw(self, mi: int): return self.mipmap_wh(mi)[::-1]
    def mipmap_size(self, mi: int): w,h = self.mipmap_wh(mi); return w*h

    @classmethod
    def sern_read(cls, rdr:sern_read.reader):
        hdr = rdr.fields_read(cls,  [f.name for f in sern_read.fields(cls)])
        return rdr.auto_read(br2_TEX_Header, hdr) if hdr['version']==3 else cls(**hdr)


@sern_dataclass
class br2_TEX_Header(TEX_Header):
    unkown2: int = sernAs(c_int32)
    unkown3: int = sernAs(c_int32)
    @classmethod
    def sern_read(cls, rdr:sern_read.reader, hdr_di:dict[str, Any]):
        di = hdr_di | rdr.fields_read(cls, ['unkown2', 'unkown3'])
        return cls(**di)

from os import SEEK_CUR


class SkipedMip:
    pass
SKIPED_MIP = SkipedMip()

def generic_mip(pixel_type):
    class genmip:
        @staticmethod
        def sern_read(rdr:sern_read.reader, hdr: TEX_Header, mi:int, skip:bool) -> npt.NDArray | SkipedMip:
            h, w = hdr.mipmap_hw(mi)
            if skip:
                rdr.file.seek(h*w*np.dtype(pixel_type).itemsize, SEEK_CUR)
                return SKIPED_MIP
            else:
                return rdr.auto_read(npt.NDArray, ((h,w), pixel_type))      
    return genmip

@sern_dataclass
class ps2_mip:
    unknown: bytearray = sernAs(rarg=32)
    mip:npt.NDArray[np.uint8] 
    @classmethod
    def sern_read(cls, rdr:sern_read.reader, hdr: TEX_Header, mi:int, skip:bool) -> 'ps2_mip | SkipedMip':
        h, w = hdr.mipmap_hw(mi)
        if skip:
             rdr.file.seek(32+h*w, SEEK_CUR)
             return SKIPED_MIP
        else:
            mip = cls(**rdr.top_fields_read(cls, 'unknown', ('mip',((h,w),))))
            return mip

def mipmaps_raeder(pixel_type:type[sern_read.ManualReadable] | np.number):
    if not sern_read.isManualReadable(pixel_type):
        pixel_type = generic_mip(pixel_type) #type:ignore

    class raeder:
        @staticmethod
        def sern_read(rdr:sern_read.reader, hdr: TEX_Header, mif:TEXMipChoicer = None) -> Any: #list[npt.NDArray[_T]]
            src_mif = mif
            if isinstance(mif, int):
                mif = lambda hdr, ind: True if ind == src_mif else False
            elif mif is None:
                mif = lambda hdr, ind: MipLoadState.LOAD_CONTINUE
            if not callable(mif):
                raise TypeError(f'Unkown type for mif, type was {type(src_mif).__name__}')
            
            def read(mi:int, skip:bool=False):
                ret = rdr.auto_read(pixel_type, (hdr, mi, skip))
                return None if skip else ret

            mips = [None]*hdr.mipmaps
            break_mode = False #We prefer to emulate a break, which will preserve the correct offset in the file.
            for i in range(hdr.mipmaps):
                if not break_mode:
                    code = mif(hdr, i)
                    if isinstance(code, bool): code = MipLoadState.bool_to_single(code)
                    match code:
                        case MipLoadState.NOT_LOAD_BREAK:read(i, skip=True); break_mode=True
                        case MipLoadState.NOT_LOAD_CONTINUE: read(i, skip=True)
                        case MipLoadState.LOAD_BREAK: mips[i] = read(i); break_mode = True
                        case MipLoadState.LOAD_CONTINUE: mips[i] = read(i)
                        case _: asser_never(code)
                else: read(i, skip=True)
            return mips
    return raeder


from abc import ABC, abstractmethod

from typing import NamedTuple
from collections.abc import Iterator
class FormatInfo(NamedTuple):
    code:int
    desc:str
    alpha:bool

class TEX_Data(ABC):
    tex_subclasses = []

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.tex_subclasses.append(cls)

    @abstractmethod
    def to_rgba(self, hdr:TEX_Header, mi:int) -> npt.NDArray | None: #-> npt.NDArray[np.uint32]:
        raise NotImplementedError()
    
    @classmethod
    @abstractmethod
    def format_info(cls) -> FormatInfo:
        raise NotImplementedError()
    

def _to_rgba_impl(data:npt.NDArray, alpha:npt.NDArray|int|None):
    if alpha is None: alpha = data['a']
    elif isinstance(alpha, int): alpha = np.full_like(data['r'], alpha)
    return np.stack([data['r'], data['g'], data['b'], alpha], axis=-1) 

@sern_dataclass
class TEX_Indexed8(TEX_Data):
    """
    [br1[pc,mac,gc], br2[pc]], rgb palette[256] + mips
    """
    #TODO Нужно ли для палитры, чей размер 768 байт, использовать numpy? С одной стороны, это позволяет привести к единообразнному интерфейсу с другой средства могут быть избыточными
    palette: npt.NDArray = sernAs(rarg=(256, pixel_rgb)) #pixel_rgb * 256
    mipmaps: list[npt.NDArray[np.uint8] | None] = sernAs(mipmaps_raeder(np.uint8))
    def to_rgba(self, hdr:TEX_Header, mi:int):
        if (mip:=self.mipmaps[mi]) is None: return None
        return _to_rgba_impl(self.palette, 255)[mip]
    
    @classmethod
    def format_info(cls): return FormatInfo(1, 'pc_paletted24', alpha=False)






@sern_dataclass
class TEX_Indexed8Alpha(TEX_Indexed8):
    """
    [br1[pc,mac,gc], br2[pc]], rgb palette[256] + mips + alpha_mips
    """
    alphas:list[npt.NDArray[np.uint8] | None] = sernAs(mipmaps_raeder(np.uint8))
    def to_rgba(self, hdr:TEX_Header, mi:int):
        if (pxs := super().to_rgba(hdr, mi)) is None: return None
        assert (alpha_mip:=self.alphas[mi]) is not None
        pxs[...,3] = alpha_mip
        return pxs

    @classmethod
    def sern_read(cls, rdr:sern_read.reader, header: TEX_Header, mif:TEXMipChoicer = None):
        ind8 = rdr.auto_read(TEX_Indexed8, (header, mif))
        nmif = lambda hdr, ind: MipLoadState.LOAD_CONTINUE if ind8.mipmaps[ind] is not None else MipLoadState.NOT_LOAD_CONTINUE
        return cls(ind8.palette, ind8.mipmaps, **rdr.top_fields_read(cls, ('alphas', (header, nmif))))
    
    @classmethod
    def format_info(cls): return FormatInfo(2, 'pc_8bit_with_opac', alpha=True)


@sern_dataclass
class TEX_BGRA(TEX_Data):
    """
    [br1[pc,mac,gc], br2[pc]] bgra mips
    """
    mipmaps: list[npt.NDArray | None] = sernAs(mipmaps_raeder(pixel_bgra))
    def to_rgba(self, hdr:TEX_Header, mi:int):
        if (mip:=self.mipmaps[mi]) is None: return None
        return _to_rgba_impl(mip, None)
    
    @classmethod
    def format_info(cls): return FormatInfo(3, 'pc_32bit', alpha=True)



@sern_dataclass
class TEX_Indexed8RGBAlpha(TEX_Data):
    """
    [br1[gc]], rgb palette[256] + alpha table[256] + mips
    """    
    palette: npt.NDArray = sernAs(rarg=(256, pixel_rgb))
    alphas: npt.NDArray[np.uint8] = sernAs(rarg=256)
    mipmaps: list[npt.NDArray[np.uint8] | None] = sernAs(mipmaps_raeder(np.uint8))
    def to_rgba(self, hdr:TEX_Header, mi:int):
        if (mip:=self.mipmaps[mi]) is None: return None
        return _to_rgba_impl(self.palette, self.alphas)[mip]
    
    @classmethod
    def format_info(cls): return FormatInfo(8, 'pc_paletted32', alpha=True) #but used on gamecube






#TODO ps2_swizzled_palette

@sern_dataclass
class TEX_Indexed8RGBA(TEX_Data):
    """
    [br1[ps2], br2[ps2]], rgba table(swizzled) + mips. Note: opacity belongs to 0 to 128
    """    
    unknown: bytearray = sernAs(rarg=32)
    palette: bytearray = sernAs(rarg=1024)
    mipmaps: list[ps2_mip | None] = sernAs(mipmaps_raeder(ps2_mip))
    def to_rgba(self, hdr:TEX_Header, mi:int):
       if (mip:=self.mipmaps[mi]) is None: return None
       palette = np.frombuffer(swizzle_box.unswizzle_ps2_palette(self.palette), dtype=pixel_rgba)
       palette['a'] = ((palette['a'].astype(np.uint16) * 255) // 128).astype(np.uint8)
       return _to_rgba_impl(palette, None)[mip.mip]
    
    @classmethod
    def format_info(cls): return FormatInfo(9, 'ps2_paletted32', alpha=True) 



@sern_dataclass
class TEX_File:
    TEX_MAPPER = {cls.format_info().code: cls for cls in TEX_Data.tex_subclasses}
    header:TEX_Header
    data: TEX_Data

    def to_rgba(self, mi:int): return self.data.to_rgba(self.header, mi)

    @classmethod
    def sern_read(cls, rdr:sern_read.reader, mif:TEXMipChoicer = None):
        header = rdr.auto_read(TEX_Header)
        tex_type = cls.TEX_MAPPER[header.format]
        return cls(header, rdr.auto_read(tex_type, (header, mif)))

# 0OVERBRIGHT_LX_0.TEX -- ARGB
# 8FT.TEX -- Indexed8
# KT_CRTMONITOR.TEX  -- Indexed8
# RAYNE_NEW.TEX" -- Indexed8Alpha
# SKYLINETHREE.TEX.001 -- pc_32bit