import enum
from pathlib import Path
from dataclasses import dataclass, field
from collections.abc import Iterable
from typing import Any, Literal
from functools import cache

import numpy as np
import bpy
import bpy.types
import mathutils
from mathutils import Vector, Matrix, Quaternion

from .sern.fixed_types import box3d
from .sern import sern_read
from . import bpy_utils
from .smb import (
    SMB_MeshHeader,
    SMB_Mesh,
    SMB_CollisionMesh,
    SMB_TexPack,
    SMB_Animation, SMB_Transform,
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
#TODO [СДЕЛАНО] Какая ориентация предполагалось для SMB? Нужен ли flip orient? Скорее всего да, но некоторые объекты всё равно не будут выглядить корректно, причина - начальная позиция анимированных объектов задаётся в секции анимации 
#TODO что происходит с нормалями при отрицацельной мировой матрицы объекта(т.е. при смене базиса)

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


def _smb_ani_float_eql(x,y):return abs(x-y)<1e-6 #[Note]This is convenient, but some of the original data will be lost during re-export.

def _optimize_smb_action(action:bpy.types.Action, matr:Matrix, allow_output_matrix:bool = False) -> tuple[bpy.types.Action | None, Matrix]:
    fcurve_rot = [curve for curve in action.fcurves if curve.data_path == 'rotation_quaternion']
    fcurve_loc = [curve for curve in action.fcurves if curve.data_path == 'location']
    if any((len(curve.keyframe_points)==0 for curve in fcurve_rot+fcurve_loc)):
        raise ValueError('Empty keyframes are prohibited') #Because we won't be able to build the output matrix
    
    if allow_output_matrix:
        quat = Quaternion((curve.keyframe_points[0].co.y for curve in fcurve_rot))
        pos = Vector((curve.keyframe_points[0].co.y for curve in fcurve_loc))
        out_matr =  Matrix.LocRotScale(pos, quat, matr.to_scale()).to_4x4()
    else:
        out_matr = matr.copy()

    def optimize_action(action:bpy.types.Action, curves:list[bpy.types.FCurve], comps):
        for i, curve in enumerate(curves):
            keyframes = curve.keyframe_points
            if len(keyframes)==1 and (allow_output_matrix or _smb_ani_float_eql(keyframes[0].co.y, comps[i])):
                action.fcurves.remove(curve)

    optimize_action(action, fcurve_loc, matr.to_translation())
    optimize_action(action, fcurve_rot, matr.to_quaternion())

    if len(action.fcurves)==0: 
        bpy.data.actions.remove(action)
        action = None
    return action, out_matr


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
                file = sern_read.reader.read_all(file, typ)
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
       
    _action_optimizes = Literal['off', 'action', 'action+matr']
    #Note. Практика показала, что подход с оптимизацией SMB_Animation (optimize:_action_optimizes)
    #(удаление вереницы неиспользуемых кадров вплоть до интеграции единственного кадра в матрицу), 
    #скорее даже не столь опциия а необходимость, поскольку значения всех неанимируемых свойств берется из matrix_basis 
    #объекта, а это позволяет пользователю задавать вручуню, например, позици, тогда при старте произведения
    #она не будет сброшена. То есть, модель чья анимация только вращения, будет вопроизведена ожидаемым образом    
    @staticmethod
    def build_animation(name:str, obj_ind:int, ani:SMB_Animation, fps:float, *, 
                            matr:Matrix=Matrix(),
                            optimize:_action_optimizes = 'off'):
        if len(ani.frames)==0: return None, matr
        action = bpy.data.actions.new(name)
        fcurve_rot = [action.fcurves.new(data_path='rotation_quaternion', index=i) for i in range(4)]
        fcurve_loc = [action.fcurves.new(data_path='location', index=i) for i in range(3)]
        
        def add_component(curves:list[bpy.types.FCurve], fdx:float, comps):
            for curve, val in zip(curves, comps):
                keyframes = curve.keyframe_points
                if not keyframes or not _smb_ani_float_eql(keyframes[-1].co.y, val):        
                    keyframes.insert(fdx, val, options={'FAST'})
        
        world_quat = matr.to_quaternion().normalized() #TODO проблема с поворотом у PARK_CHIPPER_ANIM.SMB и WW_TRACKCRANE_ANIMATION1.SMB
        for frame_ind, frame in enumerate(ani.frames):
            transform = frame[obj_ind]
            quat = (world_quat @ Quaternion(transform.quat)).normalized()
            pos = matr @ Vector(transform.pos)
            frame_fdx = frame_ind * bpy.context.scene.render.fps / fps + 1
            add_component(fcurve_rot, frame_fdx, quat)
            add_component(fcurve_loc, frame_fdx, pos)
        
        match optimize:
            case 'off': return action, matr.copy() #We return the untouched matrix to harmonize the return type
            case 'action': return _optimize_smb_action(action, matr, False)
            case 'action+matr': return _optimize_smb_action(action, matr, True)
            case _: assert_never(optimize)

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

#TODO переписать линковщик и встроить в него функионал по группировки, сделать похожим на bfm_linker. 
#Может быть даже унаследовать от bfm_linker переопределив функию _get_group_name
#TODO По множеству причин отказаться от поддержка группировки по empty.
#Говоря предворительно, но задача по преобразованию коллекции в пустышку, что даёт несомненное удобство,
#должна быть частью встронного функционала блендера а не этого плагина
#TODO провести исследование всех названий всех мэший и (collisions) всех smb файлов. 
#Делать группировку на основе этого, например, модели с одинаковым damage1 - одна коллекция
#А также группировать одноименные мэши, которые допустимы этим форматом
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
        else:
            self._empty = None


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
class smb_action_provider:
    enable_cache: bool = True
    optimize: smb_builder._action_optimizes = 'action+matr'

    _ani: SMB_Animation | None = field(default=None, init=False)
    _fps: float | None = field(default=None, init=False)
    _inv_inds: np.ndarray | None = field(default=None, init=False)
    _cached_build_animation: Any = field(default=None, init=False)

    def _build_animation(self, obj_ind:int, matr:Matrix):
        return smb_builder.build_animation('_unnamed_', obj_ind, self._ani, self._fps, matr=matr, optimize=self.optimize)

    def provide(self, obj_ind:int, matr:Matrix = Matrix()):
        if self._ani is None or self._fps is None:
            raise ValueError('The configuration step was skipped or None were set.')
        if self._inv_inds is not None:
            first_meet = self._inv_inds[obj_ind] == obj_ind
            obj_ind = self._inv_inds[obj_ind]
        else:
            first_meet = True
        action, matr = self._cached_build_animation(obj_ind, matr.copy().freeze())
        return action, matr, first_meet
    
    def configure(self, ani:SMB_Animation, fps:float):
        self._ani, self._fps, self._inv_inds = ani, fps, None
        self._cached_build_animation = self._build_animation
        if self.enable_cache:
            self._cached_build_animation = cache(self._build_animation)
            if len(ani.frames)>0:
                data = np.array(ani.frames, dtype=np.float32)
                _, uni, inv = np.unique(data, axis=1, return_index=True, return_inverse=True)
                self._inv_inds = uni[inv]
            
         
@dataclass
class smb_importer:
    linker: smb_linker = field(default_factory=smb_linker)
    name_groups: bool = True
    create_materials:bool = False
    tex_prov: null_tex_provider = field(default_factory=null_tex_provider)
    anim_prov: smb_action_provider | None = field(default_factory=smb_action_provider) #By default, animation loading is enabled, since in smb the initial transformation is set by the first frame (if available)
    mesh_flags:MeshFlags = MeshFlags.ALL
    collisions:ObjectLoadState = ObjectLoadState.NOT_LOAD
    bound_boxes:ObjectLoadState = ObjectLoadState.NOT_LOAD
    emitters:ObjectLoadState = ObjectLoadState.NORMAL

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
    
    def build_bpy_obj(self, bpy_mesh:bpy.types.Mesh|None, name:str, group_name:str|None):
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

    def build_animation(self, bpy_obj:bpy.types.Object, obj_ind:int, name:str):
        assert self.anim_prov is not None
        #don't forget to call bpy.context.view_layer.update() to update the object world matrix
        bpy.context.view_layer.update()
        action, matr, first_meet = self.anim_prov.provide(obj_ind, bpy_obj.matrix_local)
        if action is not None:
            action.name = (name if first_meet else 'Shared')+'_SMBAction'
            bpy_obj.rotation_mode = 'QUATERNION'
            bpy_obj.animation_data_create()
            bpy_obj.animation_data.action = action
        bpy_obj.matrix_local = matr
  
    def build_emitter(self, name:str, obj_ind:int, ani:SMB_Animation):
        bpy_obj = self.build_bpy_obj(bpy_mesh=None, name=name, group_name=None)
        assert len(ani.frames)>0
        create_anims = self.anim_prov is not None
        if not create_anims:
            trans = ani.frames[0][obj_ind]
            bpy.context.view_layer.update()
            matr = bpy_obj.matrix_local
            bpy_obj.matrix_local = matr @ Matrix.LocRotScale(trans.pos, Quaternion(trans.quat), matr.to_scale())
        return bpy_obj

    def load(self, smb: tuple[SMB_File, str] | SMB_File | Path | str):
        bpy.context.view_layer.update()
        smb, top_name = smb_builder._generic_load(SMB_File, smb)
        self.linker.new_container(top_name)
        self.configure_groups(smb)
        create_anims = self.anim_prov is not None
        if create_anims: self.anim_prov.configure(smb.animation, smb.header.fps)

        self.build_bound_box(smb.box, top_name, None)
        bpy_mats = self.build_bpy_mats(smb.text_packs)
        
        obj_ind = 0
        for hdr, mesh in zip(smb.mesh_header, smb.meshes):
            bpy_obj = self.build_mesh(hdr, mesh)
            if create_anims:
                self.build_animation(bpy_obj, obj_ind, str(hdr.name))
            if self.create_materials:
                bpy_obj.data.materials.append(bpy_mats[hdr.tpIndex])
            obj_ind+=1

        if self.collisions:
            for col in smb.collisions:
                bpy_obj = self.build_collision_mesh(col)
                if create_anims:
                    self.build_animation(bpy_obj, obj_ind, str(col.name))
                self.collisions.apply(bpy_obj)
                obj_ind+=1
        else:
            obj_ind+=len(smb.collisions)

        if self.emitters:
            for emit in smb.emitters:
                bpy_obj=self.build_emitter(str(emit), obj_ind, smb.animation)
                if create_anims:
                    self.build_animation(bpy_obj, obj_ind, str(emit))                
                self.emitters.apply(bpy_obj)
                obj_ind+=1
        else:
            obj_ind+=len(smb.emitters)

        bpy.context.view_layer.update()
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
#MISC_COPCAR_BR.SMB - есть анимация
#SW_GATE_ANI.SMB, STATION_CLOCK_GEARS.SMB - пример красивой анимации
#STATION_CLOCK_WEIGHTS - самая длинная анимация

#PARK_HELICOPTER_ANIMODEL.SMB - анимировання модель вертолета. Примечательно, что существует ещё файл PARK_HELICOPTER _ANIMODEL.SMB
#CITY_EXT_RAT_ANIM.SMB - присутствие в секции unkown только for_mesh2 данных делает этот файл удобным для изучение анимации 
#weapons_rayne_blade_01.smd - содержит анимацию и не содержит эммитеров, неплохой вариант для изучения анимации
#WW_BONE_CRUSHER_MAIN - 
    #особенно интересен с точки зрения анимации(ANI2BREAK.LVL).
    #Стоит добавить, что это лучший пример по анимации. 
    #Первые 4 float всегда 1,0,0,0, что намекает на кватерлионы, но особенно хороша их одинаковость для всех кадров. 
    #Таким образом сквозь кадры анимации меняется только позиция   
#VEHICLE_RYDER_ANIM - тоже анимации
#!PARK_SEMI_FALL.SMB - очень интереная анимация - падающий с неба тягач
#DHAMPIR_SCIMITAR.SMB - только один эмиттер 'blade', что навевает на мысль, эмиттер - точка в пространсве, но чья
#позиция задаётся в секции анимации 
#SUN_BALL.SMB - имеет эмиттер 'paticle01', хм, не опечатка ли этом?
#PARK_IMPALER_ELEPHANT_LEFT.SMB, PARK_IMPALER_ELEPHANT_RT.SMB - так же. Эмиттер 'taget'

#BR_CITY_BLUE_MAILBOX.SMB - [emitters=0] frames = 0, но в других моделях отсуствующая анимации выражалось frames=1
#!!sub_40FD70!! - именно эта функция заявляет, что в smb используется соглашение об именовании, что бы извлекать разные разновидности модели при разном урове повреждений(damage)
#broken, chunk, pivot, intact, Damaged[1-7](Chunk[1-7]) - обязательно присутствующие имена, в противном случае деталь будет исключена из рендера
#Повреждения и анимация?
#PARK_CHIPPER_ANIM.SMB
# ~PARTYMALEASIAN - не используемый персонаж?

#Группировка(одноименные модели):
#SUBWAY_CAR_NEW
#SUBWAY_CAR_SUCCESSION.SMB
#SW_TRAIN_CRASH_ANIMATION.SMB (пример группировки с collision)

#Какие разновидности smb бывают (version 13)?
#CBoxActor CAniModel CBreakable CMeleeWeapon CAnimatedMeleeWeapon CGun CDoor CImpaler CVampireDoor 
#[Предположительно] CMultigun всегда загружает WEAPONS_RAYNES_GUN.SMF(WEAPONS_DARK_RAYNES_GUN.SMF)
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
