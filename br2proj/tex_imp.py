from dataclasses import dataclass
from pathlib import Path
import numpy as np

import bpy

from .sern import sern_read
from .tex import TEXMipChoicer, TEX_File

from typing import NamedTuple

class LoadedTexFile(NamedTuple):
    tex:TEX_File
    name:str
    @staticmethod
    def load_mip(tex:TEX_File, name:str, mi: int) -> bpy.types.Image | None:
        pxs = tex.to_rgba(mi)
        if pxs is None: return None
        w, h = tex.header.mipmap_wh(mi)

        bpy_img = bpy.data.images.new(name, width=w, height=h, alpha=True)
        bpy_img.pixels = (pxs.astype(np.float32).reshape(-1) / 255.0).tolist() #type: ignore
        return bpy_img
    
    def mips_generator(self):
        tex, name = self.tex, self.name
        for i in range(tex.header.mipmaps):
            if (mip:=self.load_mip(tex, name, i)) is not None:
                yield mip
                name = f'{self.name}.mip{i}'

    def first_mip(self):
        return next(self.mips_generator()) #May cause exception if no any mips loaded

@dataclass
class tex_importer:
    mif : TEXMipChoicer = 0
    with_ext:bool = False

    def load(self, tex: tuple[TEX_File, str] | TEX_File | Path | str) -> LoadedTexFile:
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
        return LoadedTexFile(tex, name)


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
    def open_img(path:Path) -> bpy.types.Image | None:
        if path.exists():
            if path.suffix.lower()=='.tex': 
                return tex_importer(with_ext=True).load(path).first_mip()                
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