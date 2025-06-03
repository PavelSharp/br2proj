import enum
from pathlib import Path
from dataclasses import dataclass, field
import math
from typing import Any
from collections.abc import Callable, Iterable


import bpy
import bpy.types
from mathutils import Vector, Matrix

from .sern import sern_read
from .sern import jexplore
from .bfm import (
    BFM_File,
    BFM_Bones,
    BFM_TexPack,
    BFM_MeshDesc,
    BFM_MeshGeometry,
)
from .skb import (
    SKB_File,
    SKB_Bone
)

from .smb_imp import (
    smb_builder,
    MeshFlags,
    ObjectLoadState
)
from . import tex_imp
from . import bpy_utils
from .tex_imp import null_tex_provider

#TODO подумать над префиксной группировкой. Дело в том, что мэши большинства моделей названы единообразны - начинаются на префикс part_ или acc_
#Поэтому стоит рассмотреть введение группировки по известным прификсам: part_, acc_, rayne_ и т.д.
#acc - accessories
#TODO [СДЕЛАНО] исправить симметрию, ошибки который подтверждаются https://web.archive.org/web/20090411063619/http://www.bloodrayne2.ru/ru/bloodrayne2/gallery/3d-models.html
#Видно, что аксессуар относится к правой ноге. Аналогично для модели RayneCOWGIRL
#TODO FERRIL.BFM проблема с прозрачностью материалов

class skb_provider:    
    def __init__(self, path:Path | str, load_anims = False):
        self.path = path if isinstance(path, Path) else Path(path)
        self.load_anims  = load_anims 

    def provide(self, name:str, ret_path = False) -> SKB_File | tuple[SKB_File, Path]:
        path = self.path / name
        if path.suffix.upper() == '.SKL': path = path.with_suffix('.SKB')
        skb = sern_read.reader.read_all(path, SKB_File, self.load_anims, must_eof=self.load_anims)
        return (skb, path) if ret_path else skb

class LinkKinds(enum.Enum):
    AsIs = 0
    Collection = 1
    Empty = 2
    @classmethod
    def bool_to_collection(cls, collection:bool):
        return cls.Collection if collection else cls.AsIs
    def apply(self, on_asis, on_collection, on_empty):
        call = lambda func: func() if func is not None else None
        match self:
            case LinkKinds.AsIs: return call(on_asis)            
            case LinkKinds.Collection: return call(on_collection)
            case LinkKinds.Empty: return call(on_empty)
            case _: raise ValueError(f'Unkown link, link was:{self.name}')

@dataclass
class bfm_linker:
    link_kind:LinkKinds = LinkKinds.Collection
    grouping: bool = False
    transform: Matrix = field(default_factory=Matrix)
    base_collection:bpy.types.Collection = field(default_factory= lambda: bpy_utils.get_active_collection())

    _collection:bpy.types.Collection = field(init=False)
    _empty:bpy.types.Object = field(init=False)
    _groups:dict[str, bpy.types.Collection] = field(init=False, default_factory=dict)
    _top_name:str = None

    def _base_link(self, bpy_obj:bpy.types.Object | bpy.types.Collection, coll=None):
        if coll is None: coll = self.base_collection
        if isinstance(bpy_obj, bpy.types.Object):
            coll.objects.link(bpy_obj)
        elif isinstance(bpy_obj, bpy.types.Collection):
            coll.children.link(bpy_obj)
        else:
            raise TypeError(f'Unkown type, type was {type(bpy_obj).__name__}')

    def new_container(self, name: str): #, all_names:Iterable[str]
        self._groups = dict()
        #if self.grouping: 
        #    self._groups = dict([(pref,bpy.data.collections.new(pref)) for nm in all_names if (pref:=self.get_prefix(nm))])
        def on_collection():
            self._collection = bpy.data.collections.new(name)
            self._top_name = self._collection.name
            self._base_link(self._collection)
        def on_empty():
            self._empty = bpy.data.objects.new(name, None)
            self._empty.matrix_world = self.transform 
            self._top_name = self._empty.name
            self._base_link(self._empty)
        self.link_kind.apply(None, on_collection, on_empty)
    

    def end_container(self):
        return self.link_kind.apply(lambda: self.base_collection, lambda: self._collection, lambda: self._empty)

    def _get_group_name(self, name:str):
        parts = name.split('_')
        for i, part in enumerate(parts):
            if len(part) == 1 and i >= 2:
                if parts[1][0] in ['L','R', 'l','r']: 
                    parts[1] = parts[1][1:]
                return parts[0]+'_'+parts[1], 1
        return (parts[0], 0) if len(parts) > 1 and parts[1] and parts[0]!='zzz' else None

    def link(self, bpy_obj:bpy.types.Object, allow_group:bool = True):
        coll = self.base_collection
        if self.link_kind==LinkKinds.Collection: coll = self._collection

        if self.grouping and allow_group: #self._top_name+'_'+
            if gr := self._get_group_name(bpy_obj.name):
                gr_name, gr_kind = gr
                if (group := self._groups.get(gr_name)) is None:
                    self._groups[gr_name] = group = bpy.data.collections.new(gr_name)
                    if gr_kind==1: group.color_tag= 'COLOR_04'
                    self._base_link(group, coll)
                coll = group


        self._base_link(bpy_obj, coll)
        #bpy_utils.origin_to_geometry(bpy_obj)

        def on_asis(): bpy_obj.matrix_world = self.transform
        def on_collection(): bpy_obj.matrix_world = self.transform
        def on_empty(): bpy_obj.parent = self._empty

        self.link_kind.apply(on_asis, on_collection, on_empty)



_BoneDict = dict[int, dict[float, list[int]]]

@dataclass
class _Armature:
    arm_obj: bpy.types.Object
    bone_names: list[str] = field(init=False, default_factory=list)
    def bone_name(self, ind:int): 
        return self.bone_names[ind]


class bfm_builder:
    bone_orient = Vector((0, 0, 1)) #TODO only for tests in sandbox
    @staticmethod
    def build_material(pack:BFM_TexPack, tex_prov:null_tex_provider, name: str | None = None) -> bpy.types.Material: 
        return smb_builder.build_material(pack, tex_prov, name)
    
    @staticmethod
    def load_textures_only(pack:BFM_TexPack, tex_prov:null_tex_provider):
        return smb_builder.load_textures_only(pack, tex_prov)

    @staticmethod
    def build_armature(name:str, bfm_bones:BFM_Bones, skb_bones:list[SKB_Bone]) -> _Armature:
        #TODO сравнить количесвто костей
        arm = bpy.data.armatures.new("Armature")    
        ret_arm = _Armature(bpy.data.objects.new(name, arm))    
        
        bpy.context.scene.collection.objects.link(ret_arm.arm_obj)
        bpy.context.view_layer.objects.active = ret_arm.arm_obj
        bpy.ops.object.mode_set(mode='EDIT')
        
        for i, skb_bone in enumerate(skb_bones):
            parent_ind = skb_bone.parentBone
            if parent_ind>=i: raise ValueError("Bones was not sorted")

            #extra = f't:{bfm_bones.bone_type[i]}, c:{str(skb_bones[bfm_bones.child_ind[i]].name)}'
            bpy_bone = arm.edit_bones.new(str(skb_bone.name))
            parent_head = Vector((0,0,0))
            if parent_ind!=-1:
                bpy_bone.parent = arm.edit_bones[parent_ind]
                parent_head =  bpy_bone.parent.head

            rot_mat = Matrix(skb_bone.matrix)
            pos = Vector(bfm_bones.pos[i])

            bpy_bone.head = parent_head+pos
            #qw = [Vector(bfm_bones.unkown[i].a), Vector(bfm_bones.unkown[i].b)]
            #bpy_utils.create_bound_box(bfm_bones.unkown[i], matryyyyyMatrix.Translation(bpy_bone.head) @ qw)
            bpy_bone.tail = bpy_bone.head + (rot_mat @ bfm_builder.bone_orient * 0.3)
            #bpy_bone.use_connect=True
            #bpy_bone.head =  parent_head + Vector(bfm_bones.pos[i])
            #bpy_bone.tail = bpy_bone.head + Vector((0,0.2,0))
            ret_arm.bone_names.append(bpy_bone.name)
        
        bpy.ops.object.mode_set(mode='OBJECT')
        return ret_arm

    @staticmethod  
    def build_mesh(name:str, geom:BFM_MeshGeometry, flags:MeshFlags, arm: _Armature) -> tuple[bpy.types.Mesh, _BoneDict]:
        vertices = []
        bone_dict = {}
        for vi, bfm_vert in enumerate(geom.vertices):
            bpy_pos = Vector((0,0,0))
            for n in range(bfm_vert.numWeights):
                pos = Vector(bfm_vert.weight_pos[n])
                bias = bfm_vert.biases[n]
                bone_ind = bfm_vert.bone_indices[n]
                bone = arm.arm_obj.data.bones.get(arm.bone_name(bone_ind))
                matr = Matrix.Translation(bone.head_local)
                #matr = bone.matrix_local
                #matr = qwe[bone_ind]
                bpy_pos+= (matr * bias) @ pos
                bone_dict.setdefault(bone_ind, {}).setdefault(bias, []).append(vi)
            vertices.append(bpy_pos)

        bpy_mesh = bpy.data.meshes.new(name)
        bpy_mesh.from_pydata(vertices, [], geom.triangles) #TODO it's normal?  [(a,b,c) for a,b,c in geom.triangles]

        if MeshFlags.NORMALS in flags:
            bpy_utils.add_normals(bpy_mesh, [v.normal for v in geom.vertices])
        if MeshFlags.UVs in flags:
            bpy_utils.add_uv_coords(bpy_mesh, [v.uv for v in geom.vertices])

        bpy_mesh.update()
        bpy_mesh.shade_smooth()
        return bpy_mesh, bone_dict
    
    @staticmethod
    def apply_armature(bpy_obj:bpy.types.Object, bone_dict:_BoneDict, arm:_Armature):
        bpy_arm_mod = bpy_obj.modifiers.new(name='Armature', type='ARMATURE')
        bpy_arm_mod.object = arm.arm_obj
        for bone_ind, wi_dict in bone_dict.items():
            bpy_vg = bpy_obj.vertex_groups.new(name=arm.bone_name(bone_ind))
            for wight, inds in wi_dict.items():
                bpy_vg.add(inds, weight=wight, type='REPLACE')        
        return bpy_obj

@dataclass
class bfm_importer:
    skb_prov: skb_provider
    linker: bfm_linker = field(default_factory=bfm_linker)
    create_materials:bool = False
    tex_prov: null_tex_provider = field(default_factory=null_tex_provider)
    mesh_flags:MeshFlags = MeshFlags.ALL
    part_bound_boxes:ObjectLoadState = ObjectLoadState.NOT_LOAD

    def build_bpy_mats(self, mats: Iterable[BFM_TexPack]):
        if self.create_materials:
            return [bfm_builder.build_material(mat,  self.tex_prov) for mat in mats]
        else:
            return [bfm_builder.load_textures_only(mat, self.tex_prov) for mat in mats]

    def load(self, bfm: tuple[BFM_File, str] | BFM_File | Path | str):
        bfm, top_name =  smb_builder._generic_load(BFM_File, bfm)
        #jexplore.jprint(bfm, path=f'{top_name}.json')
        skb = self.skb_prov.provide(str(bfm.header.skb_name))
        self.linker.new_container(top_name) #, (str(part.name) for part in bfm.parts)

        arm = bfm_builder.build_armature('arm'+top_name, bfm.bones, skb.bones)
        self.linker.link(bpy_utils.unlink_from_all(arm.arm_obj), allow_group=False)

        bpy_mats = self.build_bpy_mats(bfm.text_packs)

        for i in range(bfm.header.numParts):
            desc = bfm.mesh_descs[i]
            part_name = str(bfm.parts[desc.n1_data[0]].name)
            #print(part_name)
            geom = bfm.geometry[i]
            bpy_mesh, bone_dict = bfm_builder.build_mesh(part_name, geom, self.mesh_flags, arm)
            bpy_obj = bpy.data.objects.new(part_name, bpy_mesh)

            bfm_builder.apply_armature(bpy_obj, bone_dict, arm)
            if self.create_materials:
                tp_ind = desc.tpIndex
                if tp_ind==-842150451 or tp_ind==261674992: tp_ind=0 #adzii.bfm case (gog and 2020)
                bpy_obj.data.materials.append(bpy_mats[tp_ind])
            
            self.linker.link(bpy_obj)
        bpy.context.view_layer.update()

        return self.linker.end_container()

#ZERBAT.BFM - летучая мыши. стоит обратить внимания на анимация, скорее всего они просты и подойдут для старта
#ZGUEST_M.BFM, ZGUEST_F/M, UPANK, ZPUNK, ZPUNKF, LPUNK, FRANK_FEMALE, BOAR, GENERIC_F/M  - группировка по буквам?
#FPUNK_FEMALE
#ZPUNKF