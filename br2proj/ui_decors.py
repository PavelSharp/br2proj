from pathlib import Path

import bpy
from bpy.types import Operator, UILayout
import mathutils

from bpy_extras.io_utils import (
    orientation_helper,
)
from bpy.props import (
    BoolProperty,
    FloatProperty,
    StringProperty,
)

from . import tex_imp
from .bpy_utils import axis_conversion


def button_operator(*, doc_str:str, bl_idname: str, bl_label: str):
    def execute(self, _ctx):
        if action:=self.click_dict.get(self.click_name):
            action()
        else:
            raise ValueError("on_click cannot be None")
        return {'FINISHED'}

    @classmethod
    def set_click(cls, btn, action, unique_id:str):
        cls.click_dict[unique_id] = action
        btn.click_name = unique_id

    attrs = {
        '__doc__': doc_str,
        'bl_idname': bl_idname,
        'bl_label': bl_label,
        'bl_options': {'REGISTER', 'INTERNAL'}, 
        'execute': execute,
        'set_click': set_click,
        'click_dict': {},
        '__annotations__': {
            'click_name': bpy.props.StringProperty()
        }
    }
    return type(bl_idname+"Class", (Operator,), attrs)


def transform_helper(cls=None, /, **kwargs):
    if cls is None: return lambda cls: transform_helper(cls, **kwargs)
    
    def unpack_checkbox(val, dflt:bool):
        if isinstance(val, bool):
            return val, dflt
        
        if not isinstance(val, tuple) or not all(isinstance(v, bool) for v in val):
            raise ValueError(f'Unkown type for unpack, type was {type(val)}')
        return val
    
    orient_checkbox, orient_default = unpack_checkbox(kwargs.pop('orient_checkbox', True), True)

    apply_checkbox = kwargs.pop("apply_checkbox", False)
    transform_panel_id = kwargs.pop("transform_panel_id", None)

    cls = orientation_helper(**kwargs)(cls)
    anno = cls.__annotations__

    anno["use_manual_orientation"] = BoolProperty(
        name="Manual Orientation",
        description="Specify the manual orientation, instead of using native one",
        default=True,
    )

    if orient_checkbox:
        anno['use_flip_orient'] = BoolProperty(
            name='Flip Orientation',
            description='Switch between left-handed and right-handed coordinate systems',
            default=orient_default,
        )

    if apply_checkbox:
        anno["use_apply_matrix"] = BoolProperty(
            name="Apply Matrix",
            description="Use matrix to transform the objects",
            default=True,
        )

    anno["global_scale"] = FloatProperty(
        name="Scale",
        description="Scale factor for all objects",
        min=0.01, max=1000.0,
        default=1.0,
    )

    def draw_orientation_panel(self, context, layout):
        if transform_panel_id is not None: 
            header, body = layout.panel(transform_panel_id)
        else:
            header, body = layout.row(), layout.box()

        header.use_property_split = False
        header.prop(self, "use_manual_orientation")

        if body:
            body.enabled = self.use_manual_orientation
            body.prop(self, "axis_forward")
            body.prop(self, "axis_up")
            body.prop(self, "use_flip_orient")


    def draw_transform_panel(self, context, layout:UILayout, id:str, text = "Transform"):
        header, body = layout.panel(id)
        header.label(text=text)
        if body:
            body.use_property_split = True
            draw_orientation_panel(self, context, body)
            body.prop(self, "global_scale")
            if apply_checkbox:
                body.prop(self, "use_apply_matrix")

    def get_transform_matrix(self):
        rot = mathutils.Matrix()
        if self.use_manual_orientation:
            flip = self.use_flip_orient if orient_checkbox else orient_default 
            rot = axis_conversion(from_forward=self.axis_forward, from_up=self.axis_up, change_orient=flip).to_4x4()
        matr = rot @ mathutils.Matrix.Scale(self.global_scale, 4)
        return (self.use_apply_matrix, matr) if apply_checkbox else matr
        
    cls.draw_transform_panel = draw_transform_panel
    cls.get_transform_matrix = get_transform_matrix
    return cls



#TODO[Вороятно, исправлено] Применения этого оператора может быть отменено через ctrl-z
FolderPickerOp = button_operator(
    doc_str = "After clicking, open path will be inserted",
    bl_idname= "br2proj_utility_op.folder_picker",
    bl_label = "Pick Folder",
)


def folder_picker(cls = None,*, access_name, ui_name, default="", description="", source_provider="directory"):
    if cls is None: return lambda cls: folder_picker(cls, 
            access_name=access_name,
            ui_name=ui_name,
            default=default,
            description=description,
            source_provider=source_provider
    )

    if "__annotations__" not in cls.__dict__:
        setattr(cls, "__annotations__", {})

    anno = cls.__annotations__
    anno[access_name]= StringProperty(
        name=ui_name,
        default=default,
        description=description
    )

    def _draw_this_picker(self, context, layout):
        row = layout.row(align=True)
        row.use_property_split = False

        row.prop(self, access_name, text='')
        pick_click = lambda:setattr(self, access_name, getattr(self, source_provider))
        #row.operator(FolderPickerOp.run_button(pick_click), icon='FILE_FOLDER', text='')
        picker = row.operator(FolderPickerOp.bl_idname, icon='FILE_FOLDER', text='')
        FolderPickerOp.set_click(picker, pick_click, cls.__name__ + access_name)

    old_draw = getattr(cls, "draw_folder_picker", None)
    def _draw_folder_picker(self, acc_name:str, context, layout):
        if acc_name==access_name: _draw_this_picker(self, context, layout)
        elif old_draw: old_draw(self, acc_name, context, layout)

    cls.draw_folder_picker = _draw_folder_picker
    return cls






def texture_helper(cls=None):
    if cls is None: return lambda cls: texture_helper(cls)

    cls = folder_picker(
        access_name="texture_path",
        ui_name="Texture folder",
        description="""Path to the folder containing textures
Note. Paste path or leave it empty to use the path to the model"""
    )(cls)
    anno = cls.__annotations__


    anno["use_textures"] = BoolProperty(
        name="Load textures",
        description="Enable texture loading",
        default=False,
    )

    def norm_exts(exts:str):
        exts = exts.split(';')
        exts = (st.lstrip('.').lower() for ext in exts if (st:=ext.strip()))
        return ';'.join(exts)

    anno["texture_extensions"] = StringProperty(
        name="Texture exts",
        description="""Allowed texture formats (semicolon-separated)
Note. The order of extensions determines the priority of the corresponding files.
In any case, the name given in the materials section of the imported file has the highest priority
""",
        set = lambda s, v: s.__setitem__("texture_extensions", norm_exts(v)), 
        get = lambda s: s.get("texture_extensions", "tex;tif;tga;png"), #107671
    )


    def _draw_texture_panel(self, context, layout:UILayout, id:str):
        header, body = layout.panel(id)
        header.use_property_split = False
        header.prop(self, "use_textures")
        if body:
            body.use_property_split = True
            body.enabled = self.use_textures
            self.draw_folder_picker("texture_path", context, body)
            body.prop(self, "texture_extensions")


    def _get_texture_provider(self, context):
        if not self.use_textures: return tex_imp.null_tex_provider()

        path = self.texture_path
        if path!='':
            path = Path(path)
            if not (path.is_dir() and path.exists()):
                self.report({'ERROR'}, f"Incorrect texture folder: {path}")
                return None
        else: path =  Path(self.directory)

        exts = self.texture_extensions.split(';')
        ret_exts = []
        for ext in exts:
            if not ext: continue
            if not ext.isalnum():
                self.report({'ERROR'}, f"Invalid extension: {ext}")
                return None
            ret_exts.append(ext)

        return tex_imp.tex_provider(path, ret_exts)

    cls.draw_texture_panel = _draw_texture_panel
    cls.get_texture_provider = _get_texture_provider

    return cls


def icon_checkbox(cls = None):
    if cls is None: return lambda cls: icon_checkbox(cls)
    def draw_icon_checkbox(self, context, layout: UILayout, id:str, on_icon = None, off_icon = None):
        row = layout.row()
        row.use_property_split = False
        row.prop(self, id)
        ico = on_icon if getattr(self, id) else off_icon
        if ico is not None: row.label(icon=ico)
    cls.draw_icon_checkbox = draw_icon_checkbox
    return cls


def known_option(*opts):

    def cb_draw(on_icon = None, off_icon = None):
        return lambda self, ctx, layout, id: self.draw_icon_checkbox(ctx, layout, id, on_icon, off_icon)

    opt_dict = {
            'use_uv_coords': (BoolProperty(
                name='UV Coords',
                description='Import UV coords from file',
                default=True,
            ), cb_draw('UV')),
            'use_materials': (BoolProperty(
                name='Materials',
                description='If checked then the materials will be created in the shader editor and applied to the model',
                default=True,
            ), cb_draw('MATERIAL')),
            'use_custom_normals': (BoolProperty(
                name='Custom Normals',
                description='Import normals from a file instead of recalculating them automatically',
                default=True,
            ), cb_draw('NORMALS_FACE'))
        }

    def wrapper(cls):
        cls = icon_checkbox(cls)
        anno = cls.__annotations__
        anno.update({opt: opt_dict[opt][0] for opt in opts})
        
        def draw_known_option(self, ctx, layout: UILayout, id:str):
            opt_dict[id][1](self, ctx, layout, id)

        def draw_known_options(self, ctx, layout: UILayout):
            for opt in opts: self.draw_known_option(ctx, layout, opt)

        cls.draw_known_option = draw_known_option
        cls.draw_known_options = draw_known_options
        return cls
    
    return wrapper


def register():
    bpy.utils.register_class(FolderPickerOp)

def unregister():
    bpy.utils.unregister_class(FolderPickerOp)