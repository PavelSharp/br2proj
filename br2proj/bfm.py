#This work is based on the following documents
#1.   BR2 3D FILE FORMATS DOCUMENT
#     by BloodHammer (Mjolnir) (v1.19 - 15.01.2006)
#Available at https://gamebanana.com/tools/18225 (Thanks KillerExe_01 for published it)
#2.   https://suzerayne.weebly.com/
#     which was published in January 2014.

from .sern.sern_core import sernAs, KnownArg
from .sern.sern_read import sern_dataclass, le_fixed_dataclass as fixed_dataclass
from .sern import sern_read
from .sern.fixed_types import *
from .smb import SMB_TexPack

@fixed_dataclass
class BFM_Header:
    version:int = sernAs(c_int32) #6
    lods:int = sernAs(c_int32) #1 [NEW 25.03.2025] (according to sub_724100, but only 1 is supported.)
    numParts:int = sernAs(c_int32)
    numBones:int = sernAs(c_int32)
    numTexPacks:int = sernAs(c_int32)
    numAttachedMeshes:int = sernAs(c_int32) #// like blades&guns
    a:int = sernAs(c_int32) #/? 1 always
    b:int = sernAs(c_int32) #/? 0 always
    skb_name: ascii_str = sernAs(ascii_char * 80) #// SKB identifier

#Переименовано в BMF_Part(имена этих объектов в моделях начинаются на part_ )
@fixed_dataclass
class BFM_Part:
    name:ascii_str = sernAs(ascii_char*30)
    bone:int = sernAs(c_int32) #// tip is the sub-bounding box's coord. sys. reference point
    box:box3d #// sub-bounding box
    #[10.03.2025] Проверено. bone - индекс кости, относительно который заданы вершины box


@fixed_dataclass
class BFM_AttachedMesh:
    name:ascii_str = sernAs(ascii_char*24) #smb_name
    bone:int = sernAs(c_int32) #// tip is the sub-bounding box's coord. sys. reference point
    a:Array[c_float] = sernAs(c_float*12) #?? this should be attaching info AND BBOX!
    #[10.03.2025] Не удалось подтвердить, что в .a содержится bound box


@sern_dataclass
class BFM_MeshDesc:
    version:int = sernAs(c_int32) #3 [NEW 23.03.2025] (according to sub_723D90, it's called BonePacket)
    tpIndex:int = sernAs(c_int32) #// texpack index
    #[14.03.2025] BR2 GOG, только ADZII.BFM имеет странный индекс материала -842150451
    n1:int = sernAs(c_int32)
    n1_data:list[int] = sernAs(list[c_int16], rarg=KnownArg('n1')) #// n1 * short: parts indices
    n2:int = sernAs(c_int32)
    n2_data: list[int] = sernAs(list[c_int16], rarg=KnownArg('n2')) #// n2 * short: indices of adjacent parts
    #[10.03.2025] Есть гипотеза, что n1=1 и n2=0 для обычных мэшей. Как только начинаются gap-мэши, эти значения могут указывать на "стыковые" сведения, между обычными мэшами
    version2:int = sernAs(c_int32) #2 [NEW 23.03.2025] (according to sub_6BEEF0, it's called RenderPacket)
    datasize:int = sernAs(c_int32) #// size of the vertex+triangle data for the mesh
    vertex_type:int = sernAs(c_int32) #4 [NEW 25.03.2025] (according to sub_6BEFE0, but bfm only use type 4)
    numVertices:int = sernAs(c_int32)
    numTriangles:int = sernAs(c_int32)
    numBones:int = sernAs(c_int32) #// why here?

BFM_TexPack = SMB_TexPack

@fixed_dataclass
class BFM_Vertex:
    numWeights:int = sernAs(c_int32) #// max 4
    weight_pos:Array[point3f] = sernAs(point3f * 4) #weight vectors/vertex-bone offsets
    biases:Array[c_float] = sernAs(c_float * 4) #// weights, sum ~ 1.0
    normal:point3f
    bone_indices: Array[c_int32] = sernAs(c_int32 * 4) #// bone indices
    uv:point2f
    norm1:point3f #?? binormal/tangent
    norm2:point3f #?? binormal/tangent (not sure of the order/orientation yet)


@sern_dataclass
class BFM_Bones:
    pos:list[point3f] #(baseframe bone positions/offsets)
    box:list[box3d] #[13.03.2025] Проверено, это bonund box, задан в пространстве кости
    #[13.03.2025] Br2 использует физику мягких тел, есть вероятность, что тип кости говорит об этой информации.
    bone_type:list[int] = sernAs(list[c_int32]) #(bone indices, what for?, maybe something with the line above...),
    child_ind:list[int] = sernAs(list[c_int32])

    @classmethod
    def sern_read(cls, rdr:sern_read.reader, count:int):
        return cls(**rdr.top_fields_read(cls, 
                        ('pos', count), 
                        ('box', count),
                        ('bone_type', count),
                        ('child_ind', count)
                    ))

@sern_dataclass
class BFM_MeshGeometry:
    vertices: list[BFM_Vertex] #TODO[Отказано, здесь имеет место общепринятое понятие как вершины и вершинные аттрибуты] переименовать в points как в smb
    triangles: list[triangle]
    align: bytes #Special member for xbox
    @classmethod
    def sern_read(cls, rdr:sern_read.reader, verts:int, trins:int, datasize:int):
        pos = rdr.file.tell()
        #TODO перекрывание стандартной функции dict одноименной переменной, пересмотреть во всех методах sern_read 
        dict = rdr.top_fields_read(cls, ('vertices', verts),  ('triangles', trins))
        dict['align'] = rdr.file.read(datasize-(rdr.file.tell()-pos))
        return cls(**dict)

#GapMesh - это мэши расположенные на месте сочлинения конечностей, невидимые.
#Текстурирование не правильное. Вероятно, выполняют служебную роль
#Очень вероятно, GapMesh - предназначен для маскирование отверстия при расчленении.
#Хотя это не всё объясняет

@sern_dataclass
class BFM_File:
    header:BFM_Header
    parts:list[BFM_Part]
    attached_meshes:list[BFM_AttachedMesh]
    text_packs: list[BFM_TexPack]
    bones:BFM_Bones
    total_meshes: int = sernAs(c_int32) #BFM_Header.numParts + numGapMeshes,
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
                ('mesh_descs', KnownArg('total_meshes')),
                'align',
            )
        #ps2 crash here. Geometry can use compression, in which real numbers are encoded as uint16. But the size of the vertices is variable
        geom = lambda dc: rdr.auto_read(BFM_MeshGeometry, (dc.numVertices, dc.numTriangles, dc.datasize))
        dict['geometry'] = [geom(desc) for desc in dict['mesh_descs']]
        #jexplore.jprint(dict, path = 'xbx_rayne.json')
        return cls(**dict)