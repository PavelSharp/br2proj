from dataclasses import dataclass, field
from pathlib import Path

import bpy
from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper
from bpy.props import (
    BoolProperty,
    StringProperty,
    CollectionProperty,
)

from . import bpy_utils
from . import ui_decors
from .tex_imp import tex_importer
from .tex import TEX_Header, TEX_File, FormatInfo
#TODO [СДЕЛАНО] Для диалога импорта tex снабдить возможностью предпросмотра
#TODO [будущие] Внутри файловго диалога переключатель для выбора варианта TEX - либо br1 либо br2
#TODO [СДЕЛАНО] Флажок что бы сделать флип
#TODO [СДЕЛАНО] Флажок что бы импортировать каждый мип, но придется по отдельному файлу
#TODO [СДЕЛАНО]После нажатия на priview вывести инофмарцию о файле(ширина, высота, и тип пикселей) 
#TODO подумать над fake_user и pack(включая SMBImporter)
#pack - текстура будет запокована в файл блендера, зависимость от внешнега файла разорвана
#необходимости в pack для ImportTEX нет

#Example of hard bug
#Выделить 009 и 010
#нажать превью
#раскрыть превью поменять на 010
#выделть 008 
#нажать превую

PreviewButton = ui_decors.button_operator(
    doc_str="Load preview image",
    bl_idname="br2proj_utility_op.preview_tex",
    bl_label="Preview TEX",
)

#class PreviewActiveImage(bpy.types.PropertyGroup):
#    image: bpy.props.PointerProperty(type=bpy.types.Image)

from typing import NamedTuple
class MinMax(NamedTuple):
    min:int
    max:int
    def __str__(self):
        a,b = self
        return str(a) if a==b else f'[{a},{b}]'
    def __or__(self, v: int):
        return MinMax(min(v, self.min), max(v, self.max))

class EmptyMinMax(NamedTuple):
    def __or__(self, v: int):
        return MinMax(v,v)

@dataclass
class ImagesInfo:
    width:MinMax | EmptyMinMax = EmptyMinMax()
    height:MinMax | EmptyMinMax = EmptyMinMax() 
    mipmaps:MinMax | EmptyMinMax = EmptyMinMax()

    _fmts:set[str] = field(default_factory=set)

    def fmts(self): return ', '.join(map(lambda v: v, sorted(self._fmts)))

    def __or__(self, tex:TEX_File):
        hdr = tex.header
        self.width |= hdr.width
        self.height |=hdr.height
        self.mipmaps |= hdr.mipmaps
        self._fmts.add(tex.data.format_info().desc)
        return self

@ui_decors.icon_checkbox
class ImportTEX(Operator, ImportHelper):
    """Load a Bloodrayne 2 TEX file"""
    bl_idname = "import_scene.br2tex"
    bl_label = "Import TEX"
    bl_options = {'UNDO', 'PRESET'}
    
    #We prefer capital letters, just like the game files do.
    filename_ext = '.TEX'
    filter_glob : StringProperty(default='*.TEX',options={'HIDDEN'})
    directory: StringProperty()
    files: CollectionProperty(name="File Path", type=bpy.types.OperatorFileListElement) #, options={'HIDDEN', 'SKIP_SAVE'}

    use_flip:BoolProperty(
            name="Flip Image",
            description="""Flip image vertically. 
Note. Disable this option if the image is going to be used as a texture.""",
            default=True,
    )

    use_mipmaps:BoolProperty(
            name="Import all mipmaps",
            description="Import all mipmaps as separate images that the file contains. Just for curiosity",
            default=False,
    )

    use_fake_user:BoolProperty(
            name="Fake User",
            description="Save this data-block even if it has no users",
            default=False,
    )

    @staticmethod
    def find_optimal_mip(hdr:TEX_Header, ind:int):
        optimal_size = 256*256
        return (
            (hdr.mipmaps <= 1) or #есть только один мип
            (hdr.mipmap_size(0)<=optimal_size) or #Наибольший мип меньше оптимальных размеров
            (ind+1 == hdr.mipmaps) or #Добрались до послденего мипа
            (hdr.mipmap_size(ind)>=optimal_size and hdr.mipmap_size(ind+1)<=optimal_size) 
        )

    previews:list[bpy.types.Image] = None
    imgs_info:ImagesInfo = None

    def flip_img(self, img):
        if self.use_flip: bpy_utils.flip_image(img, flip_y=True)
        return img 

    def get_path(self, file):
        path = Path(self.directory) / file.name
        if not (path.exists() and path.is_file()):
            self.report({'WARNING'}, f"File does not exist: {path}")  
            return None
        else:
            return path
        
    @property
    def active_img(self): return lambda ctx: (ctx.scene, 'br2proj_tex_preview')

    @active_img.setter
    def active_img(self, val):
        img, ctx = val
        ctx.scene.br2proj_tex_preview = img

    def clear_preview(self, context):
        self.imgs_info = ImagesInfo()
        if self.previews is None: self.previews = []
        self.active_img = None, context
        for img in self.previews:
            bpy.data.images.remove(img)
        self.previews.clear()


    def on_preview_click(self, context): 
        self.clear_preview(context)
        tex_imp = tex_importer(self.find_optimal_mip, with_ext = True)
        for ind, file in enumerate(self.files):
            if path:=self.get_path(file):
                ltex = tex_imp.load(path)
                self.imgs_info |= ltex.tex
                bpy_img = ltex.first_mip()
                self.previews.append(self.flip_img(bpy_img))   
                if ind==0: self.active_img = (bpy_img, context) #print(f"Preview mip is {img.size[0]}x{img.size[1]}")                

    def draw(self, context):    
        layout = self.layout
        #layout.prop(self, 'use_flip')
        self.draw_icon_checkbox(context, layout, 'use_flip')
        self.draw_icon_checkbox(context, layout, 'use_mipmaps')
        self.draw_icon_checkbox(context, layout, 'use_fake_user', 'FAKE_USER_ON', 'FAKE_USER_OFF')
        prev_btn = layout.operator(PreviewButton.bl_idname, text='Preview')
        PreviewButton.set_click(prev_btn, lambda: self.on_preview_click(context), self.bl_idname)
        #layout.operator(PreviewButton.run_button(lambda: self.on_preview_click(context)), text="Preview")
        box = layout.box()
        if self.previews:
            info = self.imgs_info
            box.label(text=f'Size={info.width}x{info.height}')
            box.label(text=f'Mipmaps={info.mipmaps}')
            box.label(text=f'PixelFormat={info.fmts()}')
            #[На заметку] template_ID_preview изменяет изображение на выбранное в выподающем списке
            layout.template_ID_preview(*self.active_img(context), rows=3, cols=3, hide_buttons = True)
        else:
            box.label(text='No image selected')

    def cancel(self, context):
        self.clear_preview(context)

    def execute(self, context):
        self.clear_preview(context)
        tex = tex_importer(mif = None if self.use_mipmaps else 0, with_ext = True)
        for file in self.files:
            if path:=self.get_path(file):
                for bpy_img in tex.load(path).mips_generator(): 
                    self.flip_img(bpy_img).use_fake_user=self.use_fake_user
        return {'FINISHED'}

def _menu_func_import(self, context):
    self.layout.operator(ImportTEX.bl_idname, text="Bloodrayne 2 TEX (.tex)", icon='IMAGE_DATA')

def register():
    #TODO в свойствах сцены (Scene prop) это свойство все равно видно
    bpy.types.Scene.br2proj_tex_preview = bpy.props.PointerProperty(type=bpy.types.Image, options={'HIDDEN'})
    bpy.utils.register_class(PreviewButton)
    bpy.utils.register_class(ImportTEX)
    bpy.types.TOPBAR_MT_file_import.append(_menu_func_import)

def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(_menu_func_import)
    bpy.utils.unregister_class(ImportTEX)
    bpy.utils.unregister_class(PreviewButton)
    if hasattr(bpy.types.Scene, "br2proj_tex_preview"): del bpy.types.Scene.br2proj_tex_preview



#WW_HANGER_TRIM_2_A_GLOSSMAP.TEX
#ps2/RAYNE_HAIR.TEX