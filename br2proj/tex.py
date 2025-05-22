from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import Callable

import numpy as np
import numpy.typing as npt

from .sern import sern_read
from .sern.fixed_types import *
#TODO [Сделано]Пересмотреть политику импорта этого модуля - откзатаься по импорту по *, тогда в простраснтво имен попадают нежелательные типы как formats и pixel_rgba вместо этого - обычный точечный импорт

class TexFormats(IntEnum):
    Indexed8 = 1
    Indexed8Alpha = 2
    BGRA = 3
    @classmethod
    def sern_read(cls, rdr:sern_read.reader): return cls(rdr.auto_read(c_uint32))
    def sern_jwrite(self): return self.name
    def with_alpha(self): return self!=self.Indexed8

class MipLoadState(Enum):
    NOT_LOAD_CONTINUE = 0
    NOT_LOAD_BREAK = 1
    LOAD_CONTINUE = 2
    LOAD_BREAK = 3
    @classmethod
    def bool_to_single(cls, val: bool): return cls.LOAD_BREAK if val else cls.NOT_LOAD_CONTINUE

pixel_bgra = np.dtype([
    ("b", np.uint8),
    ("g", np.uint8),
    ("r", np.uint8),
    ("a", np.uint8)
])

pixel_rgb = np.dtype([
    ("r", np.uint8),
    ("g", np.uint8),
    ("b", np.uint8)
])


TEXMipChoicer = Callable[['TEX_Header', int], MipLoadState | bool] | int | None

@dataclass
class TEX_Header:
    version: c_int32 #3 for br2 
    format: TexFormats
    width: c_int32
    height: c_int32

    unkown1: c_int32
    mipmaps_exp2: c_int32
    unkown2: c_int32
    unkown3: c_int32
    #Return count of mipmaps
    @property
    def mipmaps(self): return self.mipmaps_exp2+1
    def mipmap_wh(self, mi: int): return self.width>>mi, self.height>>mi
    def mipmap_size(self, mi: int): w,h = self.mipmap_wh(mi); return w*h

    def _read_mips(self, rdr:sern_read.reader, pixel_type, mif:TEXMipChoicer = None):
        src_mif = mif
        if isinstance(mif, int):
            mif = lambda hdr, ind: True if ind == src_mif else False
        elif mif is None:
            mif = lambda hdr, ind: MipLoadState.LOAD_CONTINUE
        if not callable(mif):
            raise TypeError(f'Unkown type for mif, type was {type(src_mif).__name__}')
        
        #mip = lambda i: rdr.auto_read(list[pixel_type], self.mipmap_size(i))
        def mip(i):
            #rdr.auto_read(list[pixel_type], self.mipmap_size(i))
            return np.fromfile(rdr.file, dtype = pixel_type, count = self.mipmap_size(i))

        def skip(i): 
            from os import SEEK_CUR
            rdr.file.seek(self.mipmap_size(i)*np.dtype(pixel_type).itemsize, SEEK_CUR)
            return None

        
        mips = [None]*self.mipmaps
        break_mode = False #We prefer to emulate a break, which will preserve the correct offset in the file.
        for i in range(self.mipmaps):
            if not break_mode:
                code = mif(self, i)
                if isinstance(code, bool): code = MipLoadState.bool_to_single(code)
                match code:
                    case MipLoadState.NOT_LOAD_BREAK: break_mode=True
                    case MipLoadState.NOT_LOAD_CONTINUE: mips[i] = skip(i)
                    case MipLoadState.LOAD_BREAK: mips[i] = mip(i); break_mode = True
                    case MipLoadState.LOAD_CONTINUE: mips[i] = mip(i)
                    case _: raise ValueError(f"Unknown state: {code}")
            else: skip(i)
        return mips

@dataclass
class TEX_Indexed8:
    #TODO Нужно ли для палитры, чей размер 768 байт, использовать numpy? С одной стороны, это позволяет привести к единообразнному интерфейсу с другой средства могут быть избыточными
    palette: npt.NDArray[pixel_rgb] #pixel_rgb * 256
    mipmaps: list[npt.NDArray[np.uint8]]
    @classmethod
    def sern_read(cls, rdr:sern_read.reader, header: TEX_Header, mif:TEXMipChoicer = None):
        #palette = rdr.auto_read(pixel_rgb * 256)
        palette = np.fromfile(rdr.file, dtype = pixel_rgb, count = 256)
        return cls(palette, header._read_mips(rdr, np.uint8, mif))

@dataclass
class TEX_Indexed8Alpha(TEX_Indexed8):
    #alphas: list[list[c_uint8]]
    alphas:list[npt.NDArray[np.uint8]]
    @classmethod
    def sern_read(cls, rdr:sern_read.reader, header: TEX_Header, mif:TEXMipChoicer = None):
        ind8 = TEX_Indexed8.sern_read(rdr, header, mif)
        mif = lambda hdr, ind: MipLoadState.LOAD_CONTINUE if ind8.mipmaps[ind] is not None else MipLoadState.NOT_LOAD_CONTINUE
        return cls(ind8.palette, ind8.mipmaps, header._read_mips(rdr, np.uint8, mif))

@dataclass
class TEX_BGRA:
    #mipmaps: list[list[pixel_bgra]]
    mipmaps: list[npt.NDArray[pixel_bgra]]
    @classmethod
    def sern_read(cls, rdr:sern_read.reader, header: TEX_Header, mif:TEXMipChoicer = None):
        return cls(header._read_mips(rdr, pixel_bgra, mif))

@dataclass
class TEX_File:
    header:TEX_Header
    data: TEX_Indexed8 | TEX_Indexed8Alpha | TEX_BGRA

    @classmethod
    def sern_read(cls, rdr:sern_read.reader, mif:TEXMipChoicer = None):
        header = rdr.auto_read(TEX_Header)
        tex_typ = {
            TexFormats.Indexed8: TEX_Indexed8,
            TexFormats.Indexed8Alpha: TEX_Indexed8Alpha,
            TexFormats.BGRA: TEX_BGRA,
        }[header.format]
        return cls(header, rdr.auto_read(tex_typ, (header, mif)))

# 0OVERBRIGHT_LX_0.TEX -- ARGB
# 8FT.TEX -- Indexed8
# KT_CRTMONITOR.TEX  -- Indexed8
# RAYNE_NEW.TEX" -- Indexed8Alpha
