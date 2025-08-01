# This work is based on
#     BR2 3D FILE FORMATS DOCUMENT
#     by BloodHammer (Mjolnir) (v1.19 - 15.01.2006)
#Available at https://gamebanana.com/tools/18225 (Thanks KillerExe_01 for published it)

#TODO .sern .sern.fixed_types
from .sern import sern_core
from .sern.sern_core import sernAs, KnownArg
from .sern.sern_read import sern_dataclass, le_fixed_dataclass as fixed_dataclass
from .sern import sern_read
#TODO такой импорт фиксированных типов приводит к том, что при полном иморте этого модуля(по *) область имен будет испачкана 
from .sern.fixed_types import *

@fixed_dataclass
class SMB_Header:
    version: int = sernAs(c_int32)
    numMeshes: int = sernAs(c_int32)
    numCollisionMeshes: int = sernAs(c_int32)
    numEmitters: int = sernAs(c_int32) #/?
    numTexPack: int = sernAs(c_int32)
    numFrames: int = sernAs(c_int32) #[NEW 30.05.2025] (it's just a number of frames)
    fps: float = sernAs(c_float) #30.0 NTSC fps?
    @property
    def is_animated(self): return self.numFrames>1 or self.numEmitters>0

# @dataclass
# @sern_read.allow_sernAs
# class QW:
#     version: int = sernAs(c_int32) | 5.7

# import dataclasses
# @dataclass
# class QW2:
#     version: int = dataclasses.field(default=4)

# QW2()
# q = QW()
# import typing
# print(typing.get_type_hints(SMB_Header, include_extras=True))
# assert q.version==8

@fixed_dataclass
class SMB_TexPack:
    version: int = sernAs(c_int32)  # 7
    transparency: int = sernAs(c_int32) # 0-opaque, 1-?, 8-w/alpha
    
    a:int = sernAs(c_int32) # ?? 0
    texCode:int = sernAs(c_int32) # /? 0 [BFM] unique ID: maybe texes are precached somewhere
    texture: ascii_str = sernAs(ascii_char * 64)
    
    b: int = sernAs(c_int32) # ?? 0
    bumpCode: int = sernAs(c_int32) # /? 0 [BFM] bumps not cached?
    bumpmap:ascii_str = sernAs(ascii_char * 64)
      
    c: int = sernAs(c_int32) # ?? 0
    glossCode: int = sernAs(c_int32) # /? 0 [BFM] unique ID: maybe glosses are precached somewhere
    glossmap: ascii_str = sernAs(ascii_char * 64)
    #see sub_5CD040
    indxs: Array[c_float] = sernAs(c_float * 32)   # ?? 0's and 1's, mostly the same pattern
        
    i:int = sernAs(c_int32)  # ?? 1
    j:int = sernAs(c_int32)  # 1?
    

@sern_dataclass
class SMB_CollisionMesh:
    name: ascii_str = sernAs(ascii_char * 32)
    version:int = sernAs(c_int32) #3 [NEW 29.05.2025] (according to sub_60E820) (small inaccuracy in [BR2 3D FILE FORMATS DOCUMENT], should be 3, not 2)
    numVertices:int = sernAs(c_int32)
    numTriangles:int = sernAs(c_int32)
    
    points: list[point3f] = sernAs(rarg=KnownArg('numVertices'))
    triangles: list[triangle] = sernAs(rarg=KnownArg('numTriangles'))
    unknown: bytearray = sernAs(rarg=KnownArg('numTriangles')) # Per-triangle material or collision flag


@fixed_dataclass
class SMB_MeshHeader:
    name: ascii_str = sernAs(ascii_char * 32)
    tpIndex: int = sernAs(c_int16) #2 byte int texpack index
    version: int = sernAs(c_int32) #2 [NEW 28.05.2025] (according to sub_60FB20, it's part of CMesh::loadHeader)
    box: box3d #[Verified. It's bound box]
    version2: int = sernAs(c_int32) #2 [NEW 25.03.2025] Just like in bfm (according to sub_6BEEF0, it's called RenderPacket)
    datasize: int = sernAs(c_int32) # size of the vertex+triangle data for the mesh
    vertex_type: int = sernAs(c_int32) #4 [NEW 25.03.2025] (according to sub_6BEFE0, but smb only use type 6)
    numVertices: int = sernAs(c_int32)
    numTriangles: int = sernAs(c_int32)
    e: float = sernAs(c_float) #?? 0?		

@fixed_dataclass
class SMB_Vertex:
    position: point3f
    normal: point3f
    uv: point2f
    
    norm1: point3f #?? binormal/tangent
    norm2: point3f #?? binormal/tangent (not sure of the order/orientation yet)
    #[2025.02.14] looks like norm2 == cross(norm1, normal)
    zeros: Array[c_float] = sernAs(c_float * 5) #?? 0 0 0 0 0
    term: float = sernAs(c_float) #?? -1?
    
@sern_dataclass
class SMB_Mesh:
    points: list[SMB_Vertex]
    triangles: list[triangle]
    
    @classmethod
    def sern_read(cls, rdr:sern_read.reader, info: SMB_MeshHeader):
        return cls(**rdr.top_fields_read(cls, 
                        ('points', info.numVertices), 
                        ('triangles', info.numTriangles)))


#TODO[IMPORTANT] Must be @sern_read.fixeddata (check the correctness with smb_action_provider)
@sern_dataclass
class SMB_Transform:
    quat:quaternion
    pos:point3f
    def sern_jwrite(self): return [list(self.quat), list(self.pos)]
    def __len__(self): return 7
    def __getitem__(self, n): return self.quat[n] if n<4 else self.pos[n-4]

@sern_dataclass
class SMB_Animation:
    #[31.05.2025] Может быть, мндексы связаны с уровнем повреждения
    unk: list[int] = sernAs(list[c_uint16]) 
    frames:list[list[SMB_Transform]] #According to sub_60FB20, engine reads it as 16+12
    #[17.02.2025] header.a - количесвто кадров, c_float * 7 - описатель кадра(трансформация) [28.05.2025, Подтверждено]
    @classmethod
    def sern_read(cls, rdr:sern_read.reader, hdr:SMB_Header):
        if not hdr.is_animated: return cls([],[])
        cnt = hdr.numMeshes+hdr.numCollisionMeshes+hdr.numEmitters
        return cls(**rdr.top_fields_read(cls, ('unk', cnt), ('frames', hdr.numFrames, cnt)))

#a = SMB_Animation([3],[[SMB_Transform()]])

@sern_dataclass
class SMB_File:    
    header: SMB_Header
    text_packs: list[SMB_TexPack]
    collisions: list[SMB_CollisionMesh]
    emitters:  list[ascii_str] = sernAs(list[ascii_char*32])
    box: box3d #[Verified. It's bound box for whole model]
    mesh_header: list[SMB_MeshHeader]
    animation: SMB_Animation
    align: align16
    meshes: list[SMB_Mesh]
    #[17.02.2025] Проверено. Недочитанных данных не остается 
    @classmethod
    def sern_read(cls, rdr:sern_read.reader):
        dict =  rdr.fields_read(cls, ['header'])
        hdr: SMB_Header = dict['header']
        dict |= rdr.top_fields_read (cls, 
                ('text_packs', hdr.numTexPack),
                ('collisions', hdr.numCollisionMeshes),
                ('emitters', hdr.numEmitters),
                'box',
                ('mesh_header', hdr.numMeshes),
                ('animation', hdr),
                #*([('animation', hdr)] if hdr.is_animated else []),
                'align',
                )
        dict['meshes'] = [rdr.auto_read(SMB_Mesh, m) for m in dict['mesh_header']]
        return cls(**dict)
    
#All knowm emitters (founded by scanning all games files[GOG])
#Base base Tip tip Handle 
#blade effect gunR lasersight lightpos male female
#Target taget target target01
#muzzle1 muzzle2
#particle particle01 particle02 particle03 particle04 particle05
#particle06 particle07 particle08 particle09 particle10 paticle01
#sparks sword 

#Практическое подтверждение
#Прим. ллюбой регистор написания эмитерров
#1)Если smb модель используется как CAniModel, то очень вероятно эмитторы игнорируются
#2)Если smb модель используется как CImpaler(в файле .LVL) и секция эмиттеров
#не содержит пару: 'tip' и 'base' -> критическая ошибки:
#'Model %s doesn't have a 'tip' part.', 'Model %s doesn't have a 'base' part.'