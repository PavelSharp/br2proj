from pathlib import Path

import bpy
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
from . import smb_imp
from . import tex_imp
from . import ui_decors

#TODO [Сделано, отказано] Сохранять texture_exts как свойтсво сцены.
#Или отказаться от этого (включая texture_path) дабы пользовтатель создавал пресеты?
#TODO [Проблема колекций и пустышек в Blender]
#Импорт с группировкой по Empty скорее всего затрудник реэкспорт(нет не затруднит obj.type == 'EMPTY').


@ui_decors.transform_helper(axis_forward='Z', axis_up='Y')
@ui_decors.texture_helper
@ui_decors.icon_checkbox
@ui_decors.known_option('use_uv_coords', 'use_materials', 'use_custom_normals')
class ImportSMB(Operator, ImportHelper):
    """Load a Bloodrayne 2 SMB file"""

    bl_idname = "import_scene.br2smb"
    bl_label = "Import SMB"
    bl_options = {'UNDO', 'PRESET'}
    
    #We prefer capital letters, just like the game files do.
    filename_ext = ".SMB"
    filter_glob: StringProperty(default="*.SMB", options={'HIDDEN'})

    directory: StringProperty() #subtype='DIR_PATH'
    files: CollectionProperty(name="File Path", type=bpy.types.OperatorFileListElement) #, options={'HIDDEN', 'SKIP_SAVE'}

    #TODO почему при указании иконок, обязательно указывать индекс?
    top_container: EnumProperty(
        name="Top is",
        description="Choose how top-level objects are grouped",
        items=[
            ('NONE', "As it is", "Use the active collection", 'FILE', 0),
            ('COLLECTION', "Collection", "Group objects into a new collection", 'OUTLINER_COLLECTION', 1),
            ('EMPTY', "Empty", "Group objects into a new empty", 'OUTLINER_OB_EMPTY', 2),
        ],
        default='COLLECTION'
    )

    group_container: EnumProperty(
        name="Group is",
        description="Allow grouping of objects by name",
        items=[
            ('NONE', "Not use", "Grouping by name is disabled", 'BLANK1', 0),
            ('COLLECTION', "Collection", "The group will be represented by the collection", 'OUTLINER_COLLECTION', 1),
            ('EMPTY', "Empty", "The group will be represented by a empty", 'OUTLINER_OB_EMPTY', 2),
        ],
        default='COLLECTION'
    )

    use_bound_boxes:BoolProperty(
            name="Bound boxes",
            description="Import bound boxes from file",
            default=False,
    )

    #use_uv_coords:ui_decors.known_option('use_uv_coords')
    #use_materials:ui_decors.known_option('use_materials')
    #use_custom_normals: ui_decors.known_option('use_custom_normals')

    use_collision_meshes:BoolProperty(
            name="Collision meshes",
            description="""Import сollision meshes from file
Note. If imported then the meshes will be hidden for convenience""",
            default=True,
    )

    def validate(self):
        if self.top_container == 'EMPTY' and self.group_container == 'COLLECTION':
            return "Invalid containers choice"
        return None


    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True

        header, body = self.layout.panel("BR2PROJ_import_creatation")
        header.label(text="Creatation")
        if body:
            body.prop(self, "top_container")
            body.prop(self, "group_container")
            if err:=self.validate(): layout.label(text=err, icon='ERROR')

        header, body = self.layout.panel("BR2PROJ_import_include")    
        header.label(text="Include")
        if body:
                #body.use_property_split = False
                self.draw_icon_checkbox(context, body, 'use_bound_boxes', 'MESH_CUBE')
                self.draw_icon_checkbox(context, body, 'use_collision_meshes', 'MOD_PHYSICS')
                self.draw_known_options(context, body)
                #TODO body.prop(self, "use_custom_normals")
                #body.prop(self, "use_uv_coords")
                #body.prop(self, "use_materials")

        self.draw_texture_panel(context, layout, "BR2PROJ_import_textures")
        self.draw_transform_panel(context, layout, "BR2PROJ_import_transform")




    def execute(self, context):
        if err:=self.validate(): 
            self.report({'ERROR'}, err)
            return {'CANCELLED'}
    
        prov = self.get_texture_provider(context)
        if prov is None: return {'CANCELLED'}

        def get_link_flags():
            def set(col, f:smb_imp.LinkKinds, gr=True): return col,f,gr
            activecol = lambda: bpy_utils.get_active_collection()
            none = lambda: None
            colemp, colcol = smb_imp.LinkKinds.CollectionEmpty, smb_imp.LinkKinds.CollectionCollection
            return {
                'NONE':{
                    'NONE':set(activecol, colemp, False), 
                    'COLLECTION':set(activecol, colcol), 
                    'EMPTY':set(activecol, colemp)
                    },
                'COLLECTION':{
                    'NONE':set(none, colemp, False), 
                    'COLLECTION':set(none, colcol),
                    'EMPTY':set(none, colemp)
                    },
                'EMPTY':{
                    'NONE':set(activecol, smb_imp.LinkKinds.EmptyEmpty, False),
                    'EMPTY':set(activecol, smb_imp.LinkKinds.EmptyEmpty)
                    }
                }[self.top_container][self.group_container]

        collection, link_kind, name_groups = get_link_flags()
        smb = smb_imp.smb_importer(
            linker=smb_imp.smb_linker(collection(), link_kind, self.get_transform_matrix()),
            name_groups=name_groups,
            create_materials=self.use_materials,
            tex_prov=prov,
            mesh_flags=smb_imp.MeshFlags.from_bools(self.use_custom_normals, self.use_uv_coords),
            collisions=smb_imp.ObjectLoadState.bool_to_hide(self.use_collision_meshes),
            bound_boxes=smb_imp.ObjectLoadState.bool_to_normal(self.use_bound_boxes)
        )

        for file in self.files:
            path = Path(self.directory) / file.name
            if path.is_file():
                smb.load(path)
            else:
                self.report({'WARNING'}, f"File does not exist: {path}")

        return {'FINISHED'}

def _menu_func_import(self, context):
    self.layout.operator(ImportSMB.bl_idname, text="Bloodrayne 2 SMB (.smb)")

def register():
    bpy.utils.register_class(ImportSMB)
    bpy.types.TOPBAR_MT_file_import.append(_menu_func_import)

def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(_menu_func_import)
    bpy.utils.unregister_class(ImportSMB)