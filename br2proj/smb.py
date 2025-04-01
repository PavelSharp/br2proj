# This work is based on
#     BR2 3D FILE FORMATS DOCUMENT
#     by BloodHammer (Mjolnir) (v1.19 - 15.01.2006)
#Available at https://gamebanana.com/tools/18225 (Thanks KillerExe_01 for published it)

from dataclasses import dataclass

#TODO .sern .sern.fixed_types
from .sern import sern_read
#TODO такой импорт фиксированных типов приводит к том, что при полном иморте этого модуля(по *) область имен будет испачкана 
from .sern.fixed_types import *

@sern_read.fixeddata
class SMB_Header:
    version: c_int32
    numMeshes: c_int32
    numCollisionMeshes: c_int32
    numEmitters: c_int32 #/?
    numTexPack: c_int32
    a: c_int32 #?? length of additional data per mesh/cmesh/emmiter
    fps: c_float #30.0 NTSC fps?    

@dataclass
class SMB_TexPack:
    version: c_int32  # 7
    transparency: c_int32 # 0-opaque, 1-?, 8-w/alpha
    
    a: c_int32 # ?? 0
    texCode: c_int32 # /? 0 [BFM] unique ID: maybe texes are precached somewhere
    texture: ascii_char * 64
    
    b: c_int32 # ?? 0
    bumpCode: c_int32 # /? 0 [BFM] bumps not cached?
    bumpmap: ascii_char * 64
      
    c: c_int32 # ?? 0
    glossCode: c_int32 # /? 0 [BFM] unique ID: maybe glosses are precached somewhere
    glossmap: ascii_char * 64
    #see sub_5CD040
    indxs: c_float * 32   # ?? 0's and 1's, mostly the same pattern
        
    i: c_int32  # ?? 1
    j: c_int32  # 1?
    

@dataclass
class SMB_CollisionMesh:
    name: ascii_char * 32
    b: c_int32 #?? 2?
    numVertices: c_int32
    numTriangles: c_int32
    
    points: list[point3f]
    triangles: list[triangle]
    unkown: bytearray
    
    @classmethod
    def sern_read(cls, rdr:sern_read.reader):
        return  cls(**rdr.top_fields_read(cls, 
                    'name', 'b', 'numVertices', 'numTriangles',
                    ('points', sern_read.known_arg('numVertices')),
                    ('triangles', sern_read.known_arg('numTriangles')),
                    ('unkown', sern_read.known_arg('numTriangles'))
                ))

@dataclass
class SMB_MeshHeader:
    name: ascii_char * 32
    tpIndex: c_int16 #2 byte int texpack index
    b: c_int32
    box: box3d #[Verified. It's bound box]
    version2: c_int32 #2 [NEW 25.03.2025] This is the same version as in bfm
    datasize: c_int32 # size of the vertex+triangle data for the mesh
    vertex_type: c_int32 #4 [NEW 25.03.2025] (according to sub_6BEFE0, but smb only use type 6)
    numVertices: c_int32
    numTriangles: c_int32
    e: c_float #?? 0?		
  
@sern_read.fixeddata
class SMB_Vertex:
    position: point3f
    normal: point3f
    uv: point2f
    
    norm1: point3f #?? binormal/tangent
    norm2: point3f #?? binormal/tangent (not sure of the order/orientation yet)
    #[2025.02.14] looks like norm2 == cross(norm1, normal)
    zeros: c_float * 5 #?? 0 0 0 0 0
    term: c_float #?? -1?
    
@dataclass
class SMB_Mesh:
    points: list[SMB_Vertex]
    triangles: list[triangle]
    
    @classmethod
    def sern_read(cls, rdr:sern_read.reader, info: SMB_MeshHeader):
        return cls(**rdr.top_fields_read(cls, 
                        ("points", info.numVertices), 
                        ("triangles", info.numTriangles)))

@sern_read.fixeddata
class SMB_Emitter:
    unkown: c_uint8 * 32

@dataclass
class SMB_UnkownData:
    for_mesh:list[c_uint16]
    for_cmesh:list[c_uint16]
    for_emmit:list[c_uint16]

    for_mesh2:list[list[c_float * 7]]
    for_cmesh2:list[list[c_float * 7]]
    for_emmit2:list[list[c_float * 7]]
    #[17.02.2025] header.a - количесвто кадров, c_float * 7 - описатель кадра(трансформация) ???
    @classmethod
    def sern_read(cls, rdr:sern_read.reader, hdr:SMB_Header):
        if hdr.a>1 or hdr.numEmitters>1 or (hdr.numEmitters == hdr.a == 1):
            return cls(**rdr.top_fields_read(cls, 
                    ('for_mesh', hdr.numMeshes),
                    ('for_cmesh', hdr.numCollisionMeshes),
                    ('for_emmit', hdr.numEmitters),
                    ('for_mesh2', hdr.numMeshes, hdr.a),
                    ('for_cmesh2', hdr.numCollisionMeshes, hdr.a),
                    ('for_emmit2', hdr.numEmitters, hdr.a)))
        else:
            return cls([],[],[],[],[],[])

@dataclass
class SMB_File:    
    header: SMB_Header
    text_packs: list[SMB_TexPack]
    collisions: list[SMB_CollisionMesh]
    emitters: list[SMB_Emitter]
    box: box3d #[Verified. It's bound box for whole model]
    mesh_header: list[SMB_MeshHeader]
    unkown: SMB_UnkownData
    align: align16
    meshes: list[SMB_Mesh]
    #[17.02.2025] Проверено. Недочитанных данных не остается 
    @classmethod
    def sern_read(cls, rdr:sern_read.reader):
        dict =  rdr.fields_read(cls, ['header'])
        hdr = dict['header']
        dict |= rdr.top_fields_read (cls, 
                ('text_packs', hdr.numTexPack),
                ('collisions', hdr.numCollisionMeshes),
                ('emitters', hdr.numEmitters),
                'box',
                ('mesh_header', hdr.numMeshes),
                ('unkown', hdr),
                'align',
                )

        mesh_hdrs = dict['mesh_header']
        read_mesh = lambda i: rdr.auto_read(SMB_Mesh, mesh_hdrs[i])
        dict['meshes'] = [read_mesh(i) for i in range(hdr.numMeshes)]

        return cls(**dict)