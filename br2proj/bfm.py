#This work is based on the following documents
#1.   BR2 3D FILE FORMATS DOCUMENT
#     by BloodHammer (Mjolnir) (v1.19 - 15.01.2006)
#Available at https://gamebanana.com/tools/18225 (Thanks KillerExe_01 for published it)
#2.   https://suzerayne.weebly.com/
#     which was published in January 2014.

from dataclasses import dataclass

from .sern import sern_read
from .sern.fixed_types import *
from .smb import SMB_TexPack

@dataclass
class BFM_Header:
    version:c_int32
    a:c_int32 #/? 1 always
    numParts:c_int32
    numBones:c_int32
    numTexPacks:c_int32
    numAttachedMeshes: c_int32 #// like blades&guns
    c:c_int32 #/? 1 always
    d:c_int32 #/? 0 always
    skb_name: ascii_char * 80 #// SKB identifier

#Переименовано в BMF_Part(имена этих объектов в моделях начинаются на part_ )
@dataclass
class BFM_Part:
    name:ascii_char*30
    bone:c_int32 #// tip is the sub-bounding box's coord. sys. reference point
    box:box3d #// sub-bounding box
    #[10.03.2025] Проверено. bone - индекс кости, относительно который заданы вершины box


@dataclass
class BFM_AttachedMesh:
    name:ascii_char*24 #smb_name
    bone:c_int32 #// tip is the sub-bounding box's coord. sys. reference point
    a:c_float*12 #?? this should be attaching info AND BBOX!
    #[10.03.2025] Не удалось подтвердить, что в .a содержится bound box


@dataclass
class BFM_MeshDesc:
    a:c_int32 #/? 3
    tpIndex:c_int32 #// texpack index
    #[14.03.2025] BR2 GOC, только ADZII.BFM имеет странный индекс материала -842150451
    n1:c_int32 #//
    n1_data:list[c_int16] #// n1 * short: parts indices
    n2:c_int32
    n2_data:list[c_int16] #// n2 * short: indices of adjacent parts
    #[10.03.2025] Есть гипотеза, что n1=1 и n2=0 для обычных мэшей. Как только начинаются gap-мэши, эти значения могут указывать на "стыкове" сведения, между обычными мэшами
    c:c_int32 #/? 2
    datasize:c_int32 #// size of the vertex+triangle data for the mesh
    d:c_int32 #/? 4
    numVertices:c_int32
    numTriangles:c_int32
    numBones:c_int32 #// why here?
    @classmethod
    def sern_read(cls, rdr:sern_read.reader):
        return  cls(**rdr.top_fields_read(cls, 
                    'a', 'tpIndex', 
                    'n1', ('n1_data', sern_read.known_arg('n1')),
                    'n2', ('n2_data', sern_read.known_arg('n2')),
                    'c',  'datasize', 'd',
                    'numVertices', 'numTriangles', 'numBones')
                )

BFM_TexPack = SMB_TexPack

@sern_read.fixeddata
class BFM_Vertex:
    numWeights:c_int32 #// max 4
    weight_pos:point3f * 4 #weight vectors/vertex-bone offsets
    biases:c_float * 4 #// weights, sum ~ 1.0
    normal:point3f
    bone_indices:c_int32 * 4 #// bone indices
    uv:point2f
    norm1:point3f #?? binormal/tangent
    norm2:point3f #?? binormal/tangent (not sure of the order/orientation yet)

@dataclass 
class BFM_Bones:
    pos:list[point3f] #(baseframe bone positions/offsets)
    box:list[box3d] #[13.03.2025] Проверено, это bonund box, задан в пространстве кости
    #[13.03.2025] Br2 использует физику мягких тел, есть вероятность, что тип кости говорит об этой информации.
    bone_type:list[c_int32] #(bone indices, what for?, maybe something with the line above...),
    child_ind:list[c_int32]

    @classmethod
    def sern_read(cls, rdr:sern_read.reader, count:int):
        return cls(**rdr.top_fields_read(cls, 
                        ('pos', count), 
                        ('box', count),
                        ('bone_type', count),
                        ('child_ind', count)
                    ))

@dataclass
class BFM_MeshGeometry:
    vertices: list[BFM_Vertex] #TODO переименовать в points как в smb
    triangles: list[triangle]
    @classmethod
    def sern_read(cls, rdr:sern_read.reader, verts:int, trins:int):
        return cls(**rdr.top_fields_read(cls, ('vertices', verts),  ('triangles', trins)))

#GapMesh - это мэши расположенные на месте сочлинения конечностей, невидимые.
#Текстурирование не правильное. Вероятно, выполняют служебную роль
#Очень вероятно, GapMesh - предназначен для маскирование отверстия при расчленении.
#Хотя это не всё объясняет

@dataclass
class BFM_File:
    header:BFM_Header
    parts:list[BFM_Part]
    attached_meshes:list[BFM_AttachedMesh]
    text_packs: list[BFM_TexPack]
    bones:BFM_Bones
    total_meshes: c_int32 #BFM_Header.numParts + numGapMeshes,
    mesh_descs: list[BFM_MeshDesc]
    align:align16
    geometry: list[BFM_MeshGeometry]
    @classmethod
    def sern_read(cls, rdr:sern_read.reader):
        dict =  rdr.fields_read(cls, ['header'])
        hdr = dict['header']

        dict |= rdr.top_fields_read(cls, 
                ('parts', hdr.numParts),
                ('attached_meshes', hdr.numAttachedMeshes),
                ('text_packs', hdr.numTexPacks),
                ('bones', hdr.numBones),
                'total_meshes',
                ('mesh_descs', sern_read.known_arg('total_meshes')),
                'align',
            )
        geom = lambda dc: rdr.auto_read(BFM_MeshGeometry, (dc.numVertices, dc.numTriangles))
        dict['geometry'] = [geom(desc) for desc in dict['mesh_descs']]
        return cls(**dict)