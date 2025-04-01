import enum
from pathlib import Path
from dataclasses import dataclass, field
from collections.abc import Iterable
from typing import Any

import bpy
import bpy.types
import mathutils
from mathutils import Vector

from .sern.fixed_types import box3d
from .sern import sern_read
from . import bpy_utils
from .smb import (
    SMB_MeshHeader,
    SMB_Mesh,
    SMB_CollisionMesh,
    SMB_TexPack,
    SMB_File
)
from .tex_imp import null_tex_provider

#TODO. Разбить на два класса. smb_builder - полностью статический класс
#smb_importer.load(датакласс?) - поля этого класса будут задавать настройки 
#построения сцены, например стоит ли включть bound_box или collision_mesh

#TODO [СДЕЛАНО] Для класса buld_smb предусматреть отдельную архитектурныю возможность по связыванию с занузчиком текстур. Скорее всего, это будет функция, которая принимает один строковой аргумент - имя текстуры, а на выходе - blender material
#TODO. Обратить внимания bpy_mesh.calc_tangents и сравнить с smb_vertex.norm1
#TODO. Основы логирования для скрипта Blender
#TODO. Логировать SMB_Header SMB_TexPack SMB_MeshHeader в одну строку (доделать jprint)
#TODO [СДЕЛАНО] При название материала найти наибольший общий префикс среди трех текстур, если пустота - Br2Material 
#TODO [СДЕЛАНО] Этот скрипт в палитру поддерживаемых форматов также должен добавлять TEX, что бы художник мог поэксперементировать с разными текстурами
#TODO [СДЕЛАНО] Учеть что blender api предоставляет встроенные возможности по диалоговому интерфесу выбора базисных осей orientation_helper, axis_conversion из bpy_extras.io_utils
#TODO Должен ли импорт SMB производится только в объектном режиме?
#TODO FERRIL_TAT_TEST.SMB/FERRIL.BFM прозрачность верхних мэшей с татуировками отрабатывает неправильно
#TODO Какая ориентация предполагалось для SMB? Нужен ли flip orient?

class MeshFlags(enum.Flag):
    NONE = 0
    NORMALS = 1
    UVs = 2
    ALL = NORMALS | UVs
    @classmethod
    def from_bools(cls, normals:bool, uvs:bool):
        ret = cls.NONE
        if normals: ret |= cls.NORMALS
        if uvs: ret |= cls.UVs
        return ret

class ObjectLoadState(enum.IntEnum):
    NOT_LOAD = 0
    HIDE = 1
    NORMAL = 2
    @classmethod
    def bool_to_hide(cls, val: bool): return cls.HIDE if val else cls.NOT_LOAD
    @classmethod
    def bool_to_normal(cls, val: bool): return cls.NORMAL if val else cls.NOT_LOAD      
    def apply(self, bpy_obj):
        match self:
            case ObjectLoadState.NOT_LOAD: raise RuntimeError("The object should not have been loaded.")
            case ObjectLoadState.HIDE: bpy_obj.hide_set(True)
            case ObjectLoadState.NORMAL: pass
            case _: raise ValueError(f"Unknown state: {self}")
        return bpy_obj


class smb_builder:
    @staticmethod
    def _generic_load(typ:type, file: tuple[Any, str] | Any | Path | str):
        src_type = type(file)
        if isinstance(file, tuple):
            file, name = file
        elif isinstance(file, typ):
            name = 'Br2Model'
        else:
            if isinstance(file, str):
                file = Path(file)
            if isinstance(file, Path):
                name = file.stem
                with open(file, 'rb') as input:
                    file = sern_read.reader(input).auto_read(typ)
                    #if input.read(1) != '': print('ERR')
        if not isinstance(file, typ) or not isinstance(name, str):
            raise TypeError(f'Unkown type for {typ}, type was {src_type.__name__}')
        return file, name

    @staticmethod
    def build_collission_mesh(mesh: SMB_CollisionMesh) -> bpy.types.Mesh:
        name = str(mesh.name)
        vertices = [(x,y,z) for x,y,z in mesh.points]
        faces = [(a,b,c) for a,b,c in mesh.triangles]

        bpy_mesh = bpy.data.meshes.new(name)
        bpy_mesh.from_pydata(vertices, [], faces)
        bpy_mesh.update() #TODO it is necessary?

        return bpy_mesh

    @staticmethod
    def build_mesh(hdr:SMB_MeshHeader, mesh:SMB_Mesh, flags:MeshFlags) -> bpy.types.Mesh:
        vertices = [tuple(v.position) for v in mesh.points]
        faces = [(a,b,c) for a,b,c in mesh.triangles] #TODO it is necessary?

        bpy_mesh = bpy.data.meshes.new(str(hdr.name))
        bpy_mesh.from_pydata(vertices, [], faces)

        if MeshFlags.NORMALS in flags:
            bpy_utils.add_normals(bpy_mesh, [pt.normal for pt in mesh.points])

        if MeshFlags.UVs in flags:
            bpy_utils.add_uv_coords(bpy_mesh, [pt.uv for pt in mesh.points])

        bpy_mesh.update()
        #bpy_mesh.validate()
        bpy_mesh.shade_smooth()
        return bpy_mesh
    
    @staticmethod
    def load_textures_only(pack:SMB_TexPack, tex_prov:null_tex_provider):
        def load_img(name) -> bpy.types.Image | None:
            if not name: return None
            bpy_img = tex_prov.provide(name)
            if bpy_img is not None:
                bpy_img.pack()
            return bpy_img
    
        return [load_img(str(name)) for name in [pack.texture, pack.glossmap, pack.bumpmap]]


    @staticmethod
    def build_material(pack:SMB_TexPack, tex_prov:null_tex_provider, name: str | None = None) -> bpy.types.Material:
        DEFAULT_NAME = 'Br2Material'
        def get_material_name(maps):
            if not maps: return DEFAULT_NAME
            ind = 0
            for chars in zip(*maps):
                if len(set(chars)) != 1: break
                ind+=1
            name, sep, tail = maps[0][0:ind].rpartition('.')
            if not sep: name = tail
            #TODO если имя окначивается на _ то удалить его
            return name if len(name)>2 else DEFAULT_NAME


        bpy_mat = bpy.data.materials.new(DEFAULT_NAME)
        bpy_mat.use_nodes = True

        nodes = bpy_mat.node_tree.nodes
        links = bpy_mat.node_tree.links

        nodes.clear()

        out_node = nodes.new(type='ShaderNodeOutputMaterial')
        bsdf_node = nodes.new(type='ShaderNodeBsdfPrincipled')
        links.new(bsdf_node.outputs['BSDF'], out_node.inputs['Surface'])

        maps = []
        def create_teximg_node(name, colorspace = None):
            nonlocal maps
            maps.append(name)#maps.append(diffuse_nm)
            node = nodes.new(type='ShaderNodeTexImage')
            bpy_img = tex_prov.provide(name)
            if bpy_img is not None:
                bpy_img.pack()
                if colorspace is not None:  bpy_img.colorspace_settings.name = colorspace 
                node.image = bpy_img
            return node
        
        nosz = 270

        if diffuse_nm := str(pack.texture):
            tex_node = create_teximg_node(diffuse_nm)
            tex_node.location = Vector((-nosz, 0))
            links.new(tex_node.outputs['Color'], bsdf_node.inputs['Base Color'])
            links.new(tex_node.outputs['Alpha'], bsdf_node.inputs['Alpha'])

        
        if gloss_nm := str(pack.glossmap): 
            tex_node = create_teximg_node(gloss_nm, 'Non-Color')
            tex_node.location = Vector((-nosz, -nosz))
            inv_node = nodes.new(type='ShaderNodeInvert')
            inv_node.location = Vector((0, -nosz))
            links.new(tex_node.outputs['Color'], inv_node.inputs['Color'])
            links.new(inv_node.outputs['Color'], bsdf_node.inputs['Roughness'])


        if bump_nm := str(pack.bumpmap):
            tex_node = create_teximg_node(bump_nm, 'Non-Color')
            tex_node.location = Vector((-nosz, -2*nosz))
            norm_node = nodes.new(type='ShaderNodeNormalMap')
            norm_node.location = Vector((0, -2*nosz))
            links.new(tex_node.outputs['Color'], norm_node.inputs['Color'])
            links.new(norm_node.outputs['Normal'], bsdf_node.inputs['Normal'])

        bpy_mat.name = get_material_name(maps) if name is None else name
        bsdf_node.location = Vector((nosz*0.8, -nosz))
        out_node.location = Vector((2*nosz, -nosz))
        return bpy_mat





class LinkKinds(enum.Enum):
    CollectionCollection = 0
    CollectionEmpty = 1
    EmptyEmpty = 2
    def top_is_empty(self):
        return self ==  LinkKinds.EmptyEmpty
    def group_is_empty(self):
        return self in [LinkKinds.CollectionEmpty, LinkKinds.EmptyEmpty]


@dataclass
class smb_linker:
    collection: bpy.types.Collection = None
    link_kind:LinkKinds = LinkKinds.CollectionEmpty
    transform: mathutils.Matrix = field(default_factory=mathutils.Matrix) 


    _collection:bpy.types.Collection = field(init=False)
    _empty:bpy.types.Object = field(init=False)


    def _base_link(self, bpy_obj:bpy.types.Object | bpy.types.Collection):
        if isinstance(bpy_obj, bpy.types.Object):
            self._collection.objects.link(bpy_obj)
        elif isinstance(bpy_obj, bpy.types.Collection):
            self._collection.children.link(bpy_obj)
        else:
            raise TypeError(f'Unkown type, type was {type(bpy_obj).__name__}')


    def link(self, bpy_obj:bpy.types.Object):
        self._base_link(bpy_obj)

        if self.link_kind.top_is_empty():
            bpy_obj.parent = self._empty
        else:
            bpy_obj.matrix_world = self.transform


    def new_container(self, name: str):
        if self.collection is None:
            self._collection = bpy.data.collections.new(name)
            bpy_utils.get_active_collection().children.link(self._collection)
        else:
            self._collection = self.collection

        if self.link_kind.top_is_empty():
            self._empty = bpy.data.objects.new(name, None)
            self._empty.matrix_world = self.transform
            self._base_link(self._empty)            


    def end_container(self):
        if self.link_kind.top_is_empty():
            return self._empty
        else: 
            return self._collection


    def new_group(self, name:str):
        if self.link_kind.group_is_empty():
            ret = bpy.data.objects.new(name, None)
            self.link(ret)
        else:
            ret = bpy.data.collections.new(name)
            self._base_link(ret)
        return ret
    
       
    def link_to_group(self, group, bpy_obj): #:bpy.types.Object | bpy.types.Collection
        if self.link_kind.group_is_empty():
            #TODO [вероятно, отказаться]отцентрировать empty, добавить флаг отвечающий за это
            #Вероятно, отказаться, так как вершины в файле задаются относително позиции (0,0,0)
            #Вероятно, согласится. Но это потребует настройки видовой матрицы
            bpy_obj.parent = group
            self._base_link(bpy_obj)
        else:
            group.objects.link(bpy_obj)
            bpy_obj.matrix_world = self.transform





@dataclass
class smb_importer:
    linker: smb_linker = field(default_factory=smb_linker)
    name_groups: bool = True
    create_materials:bool = False
    tex_prov: null_tex_provider = field(default_factory=null_tex_provider)
    mesh_flags:MeshFlags = MeshFlags.ALL
    collisions:ObjectLoadState = ObjectLoadState.NOT_LOAD
    bound_boxes:ObjectLoadState = ObjectLoadState.NOT_LOAD

    _group_dict:dict[str, bpy.types.Object] = field(init=False, default_factory=dict)

    def configure_groups(self, smb:SMB_File):
        self._group_dict = {}

        if not self.name_groups: return
        seen = set()

        def walk(names):
            for name in names:
                if (name in seen) and (name not in self._group_dict):
                    self._group_dict[name] = self.linker.new_group(name)
                seen.add(name)

        walk((str(nm.name) for nm in smb.mesh_header))
        if self.bound_boxes:
            walk((str(nm.name) for nm in smb.mesh_header))
        if self.collisions:
            walk((str(nm.name) for nm in smb.collisions))


    def build_bpy_mats(self, mats: Iterable[SMB_TexPack]):
        if self.create_materials:
            return [smb_builder.build_material(mat,  self.tex_prov) for mat in mats]
        else:
            return [smb_builder.load_textures_only(mat, self.tex_prov) for mat in mats]
        #return [smb_builder.build_material(mat,  self.tex_prov) for mat in mats]
    
    def build_bpy_obj(self, bpy_mesh:bpy.types.Mesh, name:str, group_name:str|None):
        bpy_obj = bpy.data.objects.new(name, bpy_mesh)
        
        #bpy_obj.data.update()#TODO it is necessary?
        if (group_name is not None) and (group := self._group_dict.get(group_name)):
            self.linker.link_to_group(group, bpy_obj)
        else:
            self.linker.link(bpy_obj)

        return bpy_obj

    def build_bound_box(self, box:box3d, name, group_name):
        if not self.bound_boxes: return
        bpy_obj = self.build_bpy_obj(bpy_utils.create_bound_box(box, name, mesh_only=True), name+".box", group_name)
        self.bound_boxes.apply(bpy_obj)
        return bpy_obj

    def build_mesh(self, hdr:SMB_MeshHeader, mesh:SMB_Mesh):
        name = str(hdr.name)
        bpy_obj = self.build_bpy_obj(smb_builder.build_mesh(hdr, mesh, self.mesh_flags),name, name)
        self.build_bound_box(hdr.box, name, name)
        
        return bpy_obj

    def build_collision_mesh(self, mesh:SMB_CollisionMesh):
        name = str(mesh.name)
        return self.build_bpy_obj(smb_builder.build_collission_mesh(mesh), name, name)


    def load(self, smb: tuple[SMB_File, str] | SMB_File | Path | str):
        smb, top_name = smb_builder._generic_load(SMB_File, smb)
        self.linker.new_container(top_name)
        self.configure_groups(smb)

        self.build_bound_box(smb.box, top_name, None)

        bpy_mats = self.build_bpy_mats(smb.text_packs)

        for hdr, mesh in zip(smb.mesh_header, smb.meshes):
            bpy_obj = self.build_mesh(hdr, mesh)
            if self.create_materials:
                bpy_obj.data.materials.append(bpy_mats[hdr.tpIndex])

        if self.collisions:
            for col in smb.collisions:
                self.collisions.apply(self.build_collision_mesh(col))

        bpy.context.view_layer.update() #TODO[скорее да, чем нет] it is necessary?
        return self.linker.end_container()

#"D:\Games\BloodRayne 2 Terminal Cut_min\MODELS\RAYNE.SMB"
#=========
#BR2 GOC
#=========
#~RAYNE.SMB
#~RAYNE_DRESS_POSE1.SMB
#EPHEMERA.SMB
#~EPHEMERA.SMB
#~BRUTE.SMB
#VEHICLE_CAMARO.SMB
#BR_CITY_CAR_CAMARO.SMB
#GREMLIN.SMB COLLISIONS MESH=1
#BRIDGE_MASSING_MODEL.SMB
#SMB_CollisionMesh is used
#CAMERO.SMB COLLISIONS MESH=1

#CRANE_BALL.SMB
#FERRIL_TAT_TEST.SMB
#podtools crash
#WW_TESLA_GRATE.SMB
#~FOREMAN01.SMB

#WEAPONS_RAYNES_GUN.SMB UNKOWN DATA
#BR_CITY_BLUE_MAILBOX.SMB UNKOWN DATA
#ANIMODEL_HARPOON_BLANK.SMB UNKOWN DATA
#DETPACK.SMB" UNKOWN DATA
#WEAPONS_RAYNE_KATANA.SMB MATERIALS NOT FOUND

#=========
#BR2 2020
#=========
#SUBWAY_CAR_SUCCESSION.SMB ПОЕЗД(есть одноименные детали)
#TEST.SMB - МОДЕЛЬ РЕЙЕН
#~KIMSUI.SMB - Жуткая модель (ещё одна причина отключить загрузку нормали по умолчанию или дело не в нормалях?)
#KAGAN.SMB - НЕ ПРАВИЛЬНОЕ ТЕКСТУРИРОВАНИЕ
#KIMSUI.SMB - Хм, имена похожи на название костей
#ROACHES.SMB - жуки
#TOMAHAWK.SMB - МОТОЦИКЛ
#MISC_KILL_FAN(все позиции - MISC_054.TEX), PARK_HOT_DOG_CART, STREETS_GT_ACTOR, ST_HEART_ANI_BROKEN, SW_TRAIN_CRASH_ANIMATION - Какая-то интересная модель, есть damage, что насчет анимаций?
#STREETS_RADIO_TOWER_A(and B) - КОСТИ?! и damage

#weapons_rayne_blade_01.smd - содержит анимацию и не содержит эммитеров, неплохой вариант для изучения анимации
#WW_BONE_CRUSHER_MAIN - особенно интересен с точки зрения анимации(ANI2BREAK.LVL)
#VEHICLE_RYDER_ANIM - тоже анимации

#Повреждения и анимация?
#PARK_CHIPPER_ANIM.SMB

#Группировка(одноименные модели):
#SUBWAY_CAR_NEW
#SUBWAY_CAR_SUCCESSION.SMB
#SW_TRAIN_CRASH_ANIMATION.SMB (пример группировки с collision)

#Какие разновидности smb бывают (version 13)?
#CBoxActor CAniModel CBreakable CMeleeWeapon CAnimatedMeleeWeapon CGun CDoor CImpaler CVampireDoor 

'''
with open("D:/Games\Bloodrayne 2_min/ART/RAYNE_NEW.TEX", 'rb') as file:
    reader = sern.reader(file)
    tex = reader.auto_read(TEX_File)
    import_tex_file(tex)
'''

'''
prov = tex_provider(Path('D:\Games\Bloodrayne 2_min\ART'))
prov.provide('BR2_LOAD_14.TEX')
#"D:\Games\Bloodrayne 2_min\MODELS\BR_CITY_BLUE_MAILBOX.SMB"
'''

'''
with open("D:\Games\Bloodrayne 2_min\MODELS\VEHICLE_CAMARO.SMB", 'rb') as file:
    smb = sern.reader(file).auto_read(SMB_File)
    tex_prov = tex_provider('D:\Games\Bloodrayne 2_min\ART')
    smb_importer.build2((smb, 2), tex_prov=tex_prov, box=True)
'''

'''
matr = mathutils.Matrix.Rotation(math.radians(90), 4, 'X') @ \
        mathutils.Matrix.Rotation(math.radians(-90), 4, 'Y')

tex_prov = tex_provider('D:\Games\Bloodrayne 2_min\ART')
smb_importer.build("D:\Games\Bloodrayne 2_min\MODELS\~RAYNE.SMB", tex_prov = tex_prov, transform = matr)
'''

'''
smbs = sorted(Path('D:/Games/Bloodrayne 2_min/MODELS').glob('*.SMB'))
tex_prov = tex_provider('D:/Games/Bloodrayne 2_min/ART')

for ind, smb_path in enumerate(smbs):
    with open(smb_path, 'rb') as file:
        print(ind, smb_path.name)
        smb = sern.reader(file).auto_read(SMB_File)        
        smb_importer.build(smb, tex_prov, smb_path.stem, box = False)
'''
'''
              smb: tuple[SMB_File, str] | SMB_File | Path | str,
              create_materials = False,
              #tex_prov = null_tex_provider(),
              collection: bpy.types.Collection | None = None,
              #transform: mathutils.Matrix = mathutils.Matrix(),
              #mesh_flags = MeshFlags.ALL,
              #collisions = ObjectLoadState.NOT_LOAD,
              box = ObjectLoadState.NOT_LOAD
'''   
#if self.create_materials:
#    bpy_mats = self.build_bpy_mats(smb.text_packs)
#else:
#    bpy_mats = None
#    for mat in smb.text_packs: smb_builder.load_textures_only(mat, self.tex_prov)
