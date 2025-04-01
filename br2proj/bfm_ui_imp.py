from pathlib import Path

import bpy
import bpy.types
from bpy.types import Operator

from bpy_extras.io_utils import (
    ImportHelper,
    orientation_helper,
    axis_conversion,
    poll_file_object_drop,
)

from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    StringProperty,
    CollectionProperty,
)


from . import bpy_utils
from . import ui_decors
from . import bfm_imp

@ui_decors.transform_helper(axis_forward='Z', axis_up='Y')
@ui_decors.texture_helper
@ui_decors.folder_picker(access_name='skb_path', ui_name='SKB Folder', description=
    """Any BFM file link to the SKB skeleton file.
    Note. Specify path or leave it empty to use the path to the model""")
@ui_decors.icon_checkbox

@ui_decors.known_option('use_uv_coords', 'use_materials', 'use_custom_normals')
class ImportBFM(Operator, ImportHelper):
    """Load a Bloodrayne 2 BFM file"""
    bl_idname = "import_scene.br2bfm"
    bl_label = "Import BFM"
    bl_options = {'UNDO', 'PRESET'}

    #We prefer capital letters, just like the game files do.
    filename_ext = ".BFM"
    filter_glob: StringProperty(default="*.BFM", options={'HIDDEN'})

    directory: StringProperty()
    files: CollectionProperty(name="File Path", type=bpy.types.OperatorFileListElement)

    use_collection:BoolProperty(
            name='Use Collection',
            description='Put object into a collection. Otherwise, the current collection will be used.',
            default=True,
    )

    use_groups:BoolProperty(
            name='Grouping',
            description='Objects with the same prefix will be placed in separate collections.',
            default=True,
    )

    #use_uv_coords:ui_decors.known_option('use_uv_coords')
    #use_materials:ui_decors.known_option('use_materials')
    #use_custom_normals: ui_decors.known_option('use_custom_normals')

    

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = False#TODO

        header, body = self.layout.panel('BR2PROJ_import_creatation')
        header.label(text='Creatation')
        if body:
            body.use_property_split = False
            self.draw_icon_checkbox(context, body, 'use_collection', 'OUTLINER_COLLECTION')
            self.draw_icon_checkbox(context, body, 'use_groups', 'OUTLINER_COLLECTION')
            #row = body.row(align=True)
            #col = row.column()
            #col.prop(self, "use_collection", icon="OUTLINER_COLLECTION")
            #row.prop(self, "use_collection", icon="OUTLINER_COLLECTION")
            #body.prop(self, 'use_collection', icon='OUTLINER_COLLECTION')

        header, body = self.layout.panel("BR2PROJ_import_include")
        header.label(text="Include")
        if body:
            self.draw_known_options(context, body)

            #self.draw_icon_checkbox(context, body, 'use_custom_normals', 'NORMALS_FACE')
            #self.draw_icon_checkbox(context, body, 'use_uv_coords', 'UV')
            #self.draw_icon_checkbox(context, body, 'use_materials', 'MATERIAL')
            #body.prop(self, "use_materials")
            body.label(text='SKB Folder:', icon='OUTLINER_OB_ARMATURE')
            self.draw_folder_picker("skb_path", context, body)
        self.draw_texture_panel(context, layout, "BR2PROJ_import_textures")
        self.draw_transform_panel(context, layout, "BR2PROJ_import_transform")

    def get_skb_provider(self):
        path = self.skb_path
        if path!='':
            path = Path(path)
            if not path.is_dir():
                self.report({'ERROR'}, f"Incorrect skb folder: {path}")
                return None
        else: path =  Path(self.directory)
        return bfm_imp.skb_provider(path, load_anims=True)



    def execute(self, context):
        #TODO[Сделано] если Use Collection true то связывать надо со сценовой коллекцией а не с активной
        if not (tex:=self.get_texture_provider(context)): return {'CANCELLED'}
        if not (skb:=self.get_skb_provider()): return {'CANCELLED'}
        linker = bfm_imp.bfm_linker(
                        bfm_imp.LinkKinds.bool_to_collection(self.use_collection),
                        grouping=self.use_groups, 
                        transform=self.get_transform_matrix(),
                        base_collection=bpy_utils.get_collection(not self.use_collection)
        )

        bfm = bfm_imp.bfm_importer(
            skb_prov=skb,
            linker=linker,
            create_materials=self.use_materials,
            tex_prov=tex,
            mesh_flags=bfm_imp.MeshFlags.from_bools(self.use_custom_normals, self.use_uv_coords)
        )        

        for file in self.files:
            path = Path(self.directory) / file.name
            if path.is_file():
                bfm.load(path)
            else:
                self.report({'WARNING'}, f"File does not exist: {path}")
        return {'FINISHED'}


def _menu_func_import(self, context):
    self.layout.operator(ImportBFM.bl_idname, text="Bloodrayne 2 BFM (.bfm)")


def register():
    bpy.utils.register_class(ImportBFM)
    bpy.types.TOPBAR_MT_file_import.append(_menu_func_import)

def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(_menu_func_import)
    bpy.utils.unregister_class(ImportBFM)