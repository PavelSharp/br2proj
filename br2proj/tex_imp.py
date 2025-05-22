from dataclasses import dataclass
from pathlib import Path
import numpy as np

import bpy

from .sern import sern_read
from .tex import (
    TEXMipChoicer,
    TEX_File,
    TexFormats
)

@dataclass
class tex_importer:
    #TODO[сделано] ввестиметод load (TEX_File | Path | str) 
    #TODO[сделано] специальная опция для чтения TEX_File отключающая загрузку митмэпов(должно ускорить чтение)
    mif : TEXMipChoicer = 0
    #width, height, with_alpha, pixels
    #create_func: typing.Callable[[int, int, bool, list[float]], any] = None
    #naming_func: typing.Callable[[Path, int], str] = None
    with_ext:bool = False
    load_hdr:bool = False
    load_mips:bool = False

    def _load(self, tex: tuple[TEX_File, str] | TEX_File | Path | str):
        src_type = type(tex)
        if isinstance(tex, tuple):
            tex, name = tex
        elif isinstance(tex, TEX_File):
            name = 'Br2Texture'
        else:
            if isinstance(tex, str):
                tex = Path(tex)
            if isinstance(tex, Path):
                name = tex.name if self.with_ext else tex.stem
                tex = sern_read.reader.read_all(tex, TEX_File, self.mif)
        if not isinstance(tex, TEX_File) or not isinstance(name, str):
            raise TypeError(f'Unkown type for tex, type was {src_type.__name__}')
        return tex, name


    def _load_mip(self, tex:TEX_File, name:str, mi: int):
        def conv_palette(pal):
            ret = np.empty((len(pal), 4), dtype=np.float32)
            ret[:,0],ret[:,1],ret[:,2],ret[:,3] = pal['r']/255,pal['g']/255,pal['b']/255,1
            return ret
        
        w, h = tex.header.mipmap_wh(mi)
        mip = tex.data.mipmaps[mi]

        if tex.header.format == TexFormats.Indexed8:
            pxs = conv_palette(tex.data.palette)[mip]
        elif tex.header.format == TexFormats.Indexed8Alpha:
            pxs = conv_palette(tex.data.palette)[mip]
            pxs[:,3] = tex.data.alphas[mi]/255
        elif tex.header.format == TexFormats.BGRA:
            pxs = np.empty((mip.shape[0], 4), dtype=np.float32)
            pxs[:,0],pxs[:,1],pxs[:, 2],pxs[:,3] = \
            mip['r']/255,mip['g']/255,mip['b']/255,mip['a']/255

        bpy_img = bpy.data.images.new(name, width=w, height=h, alpha=tex.header.format.with_alpha())
        bpy_img.pixels = pxs.flatten().tolist()
        return bpy_img

    def load(self, tex: tuple[TEX_File, str] | TEX_File | Path | str):
        tex, name = self._load(tex)
        def find_mip_ind(ind):
            for i in range(ind, len(tex.data.mipmaps)):
                if tex.data.mipmaps[i] is not None: return i
            return -1

        mi = find_mip_ind(0)
        def gen_mips():
            nonlocal name, mi
            src_name, ind = name, 1
            while mi!=-1:
                yield self._load_mip(tex, name, mi)
                name, ind = f"{src_name}.mip{ind}", ind+1
                mi = find_mip_ind(mi+1)
                
        mips = gen_mips() if self.load_mips else self._load_mip(tex, name, mi)

        return (mips, tex.header) if self.load_hdr else mips

class null_tex_provider:
    def provide(self, name:str): return None

class tex_provider(null_tex_provider):

    @staticmethod
    def to_path(path:Path | str): 
        return path if isinstance(path, Path) else Path(path)

    def __init__(self, path:Path | str, exts = ['tex', 'tif', 'tiff', 'tga'], enable_cache = True):
        self.path = self.to_path(path)
        self.cache = {} if enable_cache else None
        self.exts = exts
    
    @staticmethod
    def open_img(path:Path) -> bpy.types.Image:
        if path.exists():
            if path.suffix.lower()=='.tex': 
                return tex_importer().load(path)                  
            else:
                return bpy.data.images.load(str(path))
        return None
    
    @staticmethod
    def create_default_img(name: str, w=128, h=128) -> bpy.types.Image:
        img = bpy.data.images.new(name=name, width=w, height=h)
        img.generated_type = 'UV_GRID'
        #img.generated_color = [0.8, 0.0, 0.0, 1.0]
        img.update()
        return img

    
    def open_img_cache(self, path:Path) -> bpy.types.Image:
        has_ch = self.cache is not None
        if has_ch and (img:=self.cache.get(path)): return img
        img = self.open_img(path)
        if img and has_ch: self.cache[path] = img
        return img

    def provide(self, name:str) -> bpy.types.Image:
        checked_exts = []

        def open_img(path):
            checked_exts.append(str(path.suffix))
            return self.open_img_cache(path)

        path = self.path / name
        default_ext = path.suffix

        if img:=open_img(path): return img
        for ext in self.exts:
            ext = '.'+ext
            if ext == default_ext: continue
            path = path.with_suffix(ext)
            if img:=open_img(path): return img
        
        fpath = (self.path / name).with_suffix('')
        exts = '|'.join(checked_exts)
        print(f'Requested image was not found \n{fpath}{exts}')#TODO логирование

        return self.create_default_img(name+'NOTFOUND')
        #raise FileNotFoundError(
        #    'None of these files were found:\n' + 
        #    '\n'.join(str(path) for path in checked_paths))