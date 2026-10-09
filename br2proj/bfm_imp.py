import enum
from pathlib import Path
from dataclasses import dataclass, field
import math
from typing import Any
from collections.abc import Callable, Iterable


import bpy
import bpy.types
from mathutils import Vector, Matrix, Quaternion

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
from .bfm_imp_grouper import * #bfm_imp_grouper is part of bfm_imp, so we can allow a star import

#TODO [СДЕЛАНО] подумать над префиксной группировкой. Дело в том, что мэши большинства моделей названы единообразны - начинаются на префикс part_ или acc_
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
        skb = sern_read.reader.read_all(path, SKB_File, self.load_anims, eof=self.load_anims)
        return (skb, path) if ret_path else skb

@dataclass
class bfm_collection_tree:
    name: str
    color: BPY_COLELCTION_COLOR_TAG
    allow_collapse:bool

    collections: list['bfm_collection_tree'] = field(default_factory=list)
    objects: list[bpy.types.Object] = field(default_factory=list)

    def find_or_create_child(self, name: str, color: BPY_COLELCTION_COLOR_TAG, allow_collapse: bool):
        for child in self.collections:
            if child.name == name:
                return child    
        child = bfm_collection_tree(name, color, allow_collapse)
        self.collections.append(child)
        return child
    
    def to_flat(self):
        ret: list[tuple[tuple[str, ...], bfm_collection_tree]] = []
        def traverse(node, path):
            path = path + (node.name,)
            ret.append((path, node))
            for child in node.collections:
                traverse(child, path)
        traverse(self, ())
        return ret
    
    @property
    def is_empty(self): return not self.collections and not self.objects
    @property
    def is_single(self): return not self.collections and len(self.objects) == 1

    def collapse(self):
        # As is well known, Blender's Outliner enforces collections to always appear above objects. 
        # Therefore, collapsing is only executed when it is guaranteed to flatten the collection,
        # which allows the order to be managed
        for child in self.collections:
            child.collapse()
 
        self.collections = [child for child in self.collections if not child.is_empty]
        single_obj_cols = [child for child in self.collections if child.allow_collapse and child.is_single]

        if len(self.collections) == len(single_obj_cols):
            for node in single_obj_cols:
                self.objects.extend(node.objects)
            self.collections.clear()

    def resolve_collisions(self):
        paths = {id(n): (n, p) for p, n in self.to_flat()}
        state = {nid: (1, p[-1:]) for nid, (_, p) in paths.items()}

        def find_collisions():
            colls:dict[str, list[int]] = {}
            for nid, (_, name_parts) in state.items():
                name = '_'.join(name_parts)
                colls.setdefault(name, []).append(nid)
            return colls

        def solve_collisions(colls:dict[str, list[int]]):
            any_solved = False
            for nids in colls.values():
                if len(nids)<=1: continue
                for nid in nids:
                    _, path = paths[nid]
                    depth, _ = state[nid]
                    if depth < len(path):
                        state[nid] = (depth+1, path[-(depth+1):])
                        any_solved = True
            return any_solved

        colls = {}
        while True:
            colls = find_collisions()
            if not solve_collisions(colls): break

        for name, nids in colls.items():
            for nid in nids:
                paths[nid][0].name = name

    def bpy_build(self, bpy_parent_col: bpy.types.Collection, allow_root:bool = True):
        if allow_root:
            bpy_col = bpy.data.collections.new(self.name)
            bpy_utils.link_to_collection(bpy_col, bpy_parent_col)
            if self.color != 'NONE':
                bpy_col.color_tag = self.color
        else:
            bpy_col = bpy_parent_col

        for bpy_obj in sorted(self.objects, key=lambda obj: obj.name):
            bpy_utils.link_to_collection(bpy_obj, bpy_col)

        for node in sorted(self.collections, key=lambda node: node.name):
            node.bpy_build(bpy_col)
        return bpy_col

    def print_tree(self, gr_indent: str = '', indent: str = ''):
        color = f' [{self.color}]' if self.color != 'NONE' else ''
        collaps = ' [+]' if self.allow_collapse else ''
        print(f'{gr_indent}📁 {self.name}{color}{collaps}')
        items = self.collections + self.objects
        for i, item in enumerate(items):
            gr_inc, it_inc = ('└── ', '    ') if i == len(items) - 1 else ('├── ', '│   ')
            if isinstance(item, bfm_collection_tree):
                item.print_tree(indent + gr_inc, indent + it_inc)
            else:
                print(f'{indent + gr_inc}🔹 {item.name}')  

@dataclass
class bfm_linker:
    allow_model_collection: bool = False
    grouper: bfm_grouper = field(default_factory=bfm_null_grouper)
    base_collection:bpy.types.Collection = field(default_factory= lambda: bpy_utils.get_active_collection())
    transform: Matrix = field(default_factory=Matrix)
    _col_tree: bfm_collection_tree = field(init=False)

    def new_container(self, name: str):
        self._col_tree = bfm_collection_tree(name, 'NONE', False)

    def end_container(self):
        self._col_tree.collapse()
        self._col_tree.resolve_collisions()
        return self._col_tree.bpy_build(self.base_collection, self.allow_model_collection)

    def link_root(self, bpy_obj:bpy.types.Object):
        bpy_obj.matrix_world = self.transform
        self._col_tree.objects.append(bpy_obj)

    def link_child(self, bpy_obj:bpy.types.Object, part_name:str):
        root = self._col_tree
        path = self.grouper.get_group_path(part_name)
        for node in path:
            root = root.find_or_create_child(node.name, node.color, node.allow_collapse)
        root.objects.append(bpy_obj) 


_BoneDict = dict[int, dict[float, list[int]]]

@dataclass
class _Armature:
    arm_obj: bpy.types.Object
    bone_names: list[str] = field(init=False, default_factory=list)
    def bone_name(self, ind:int): 
        return self.bone_names[ind]


class bfm_builder:
    bone_orient = Quaternion((1.0, 0.0, 0.0), math.pi / 2.0) #Required by Blender, since a bone can grow only along the Y axis
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
        
        BONE_LENGTH = 0.3

        parents = []
        for i, skb_bone in enumerate(skb_bones):
            parent_ind = skb_bone.parentBone
            if parent_ind>=i: raise ValueError("Bones was not sorted")

            #extra = f't:{bfm_bones.bone_type[i]}, c:{str(skb_bones[bfm_bones.child_ind[i]].name)}'
            bpy_bone = arm.edit_bones.new(str(skb_bone.name))
            #bpy_bone.parent =  arm.edit_bones[parent_ind+1] if parent_ind!=-1 else None
            if parent_ind!=-1:
                bpy_bone.parent = arm.edit_bones[parent_ind]
                parent_head =  bpy_bone.parent.head
            else:
                parents.append(bpy_bone)
                parent_head = Vector((0,0,0))

            rot_mat = Matrix(skb_bone.matrix.rows)
            rot_mat = rot_mat @ bfm_builder.bone_orient.to_matrix()

            pos = Vector(bfm_bones.pos[i])
            #qw = [Vector(bfm_bones.unkown[i].a), Vector(bfm_bones.unkown[i].b)]
            #bpy_utils.create_bound_box(bfm_bones.unkown[i], matryyyyyMatrix.Translation(bpy_bone.head) @ qw)
            bpy_bone.length = BONE_LENGTH
            bpy_bone.matrix = Matrix.LocRotScale(parent_head+pos, rot_mat, None)

            #bpy_bone.use_connect=True
            #bpy_bone.head =  parent_head + Vector(bfm_bones.pos[i])
            #bpy_bone.tail = bpy_bone.head + Vector((0,0.2,0))
            ret_arm.bone_names.append(bpy_bone.name)
        
        #TODO[Done] What if such a bone already exists inside skb_bones?
        #Create a fake bone for Root Motion to keep the Armature Object's transform unoccupied, allowing free manual positioning.
        root_bone = arm.edit_bones.new('root_bone')
        root_bone.length = BONE_LENGTH
        root_bone.matrix = bfm_builder.bone_orient.to_matrix().to_4x4()
        for bone in parents: bone.parent = root_bone

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
            bpy_utils.add_uv_coords(bpy_mesh, [Vector(v.uv) for v in geom.vertices])

        bpy_mesh.update()
        bpy_mesh.shade_smooth()
        return bpy_mesh, bone_dict
    
    @staticmethod
    def apply_armature(bpy_obj:bpy.types.Object, bone_dict:_BoneDict, arm:_Armature):
        bpy_arm_mod = bpy_obj.modifiers.new(name='Armature', type='ARMATURE')
        bpy_arm_mod.object = arm.arm_obj # type: ignore
        #TODO[done] set parent for arm_obj
        bpy_obj.parent = arm.arm_obj 
        bpy_obj.matrix_local = Matrix() 
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
        skb:SKB_File = self.skb_prov.provide(str(bfm.header.skb_name)) #type: ignore
        self.linker.new_container(top_name) #, (str(part.name) for part in bfm.parts)

        arm = bfm_builder.build_armature(top_name, bfm.bones, skb.bones)
        self.linker.link_root(bpy_utils.unlink_from_all(arm.arm_obj))

        bpy_mats = self.build_bpy_mats(bfm.text_packs)

        for i in range(bfm.header.numParts):
            desc = bfm.mesh_descs[i]
            part_name = str(bfm.parts[desc.n1_data[0]].name)
            geom = bfm.geometry[i]
            bpy_mesh, bone_dict = bfm_builder.build_mesh(part_name, geom, self.mesh_flags, arm)
            bpy_obj = bpy.data.objects.new(part_name, bpy_mesh)

            bfm_builder.apply_armature(bpy_obj, bone_dict, arm)
            if self.create_materials:
                tp_ind = desc.tpIndex
                if tp_ind==-842150451 or tp_ind==261674992: tp_ind=0 #adzii.bfm case (gog and 2020)
                bpy_obj.data.materials.append(bpy_mats[tp_ind])
            
            self.linker.link_child(bpy_obj, part_name)
        bpy.context.view_layer.update()

        return self.linker.end_container()

#ZERBAT.BFM - летучая мыши. стоит обратить внимания на анимация, скорее всего они просты и подойдут для старта
#ZGUEST_M.BFM, ZGUEST_F/M, UPANK, ZPUNK, ZPUNKF, LPUNK, FRANK_FEMALE, BOAR, GENERIC_F/M  - группировка по буквам?
#FPUNK_FEMALE
#ZPUNKF

#These models are good for testing bfm_prefix_grouper
#FPUNK_FEMALE RAYNE_DRESS ZPUNKF FERRIL GENERIC_M STREETS_RADIO_TOWER