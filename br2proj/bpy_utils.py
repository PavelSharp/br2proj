import bpy
import bpy.types
from mathutils import Matrix, Vector
from collections.abc import Iterable
from .sern.fixed_types import box3d
from collections.abc import Sequence
import mathutils
#TODO метод для выравнивания origin

def create_bound_box(box: Sequence[Sequence[float]], name="BoundingBox", mesh_only = False, *, matr = Matrix()):
    ax, ay, az = matr @ Vector(box[0])
    bx, by, bz = matr @ Vector(box[1])
    vertices = [
        (ax, ay, az),
        (bx, ay, az),
        (bx, by, az),
        (ax, by, az),
        (ax, ay, bz),
        (bx, ay, bz),
        (bx, by, bz),
        (ax, by, bz),
    ]

    edges = [
        (0, 1), (1, 2), (2, 3), (3, 0),  # Задняя грань
        (4, 5), (5, 6), (6, 7), (7, 4),  # Передняя грань
        (0, 4), (1, 5), (2, 6), (3, 7)   # Вертикальные рёбра
    ]

    bpy_mesh = bpy.data.meshes.new(name)
    bpy_mesh.from_pydata(vertices, edges, [])
    if mesh_only: return bpy_mesh
    bpy_obj = bpy.data.objects.new(name, bpy_mesh)
    bpy.context.collection.objects.link(bpy_obj)
    return bpy_obj

def flip_image(img: bpy.types.Image, *, flip_x = False, flip_y = False):
    with bpy.context.temp_override(edit_image=img):
        bpy.ops.image.flip(use_flip_x=flip_x, use_flip_y=flip_y)

def origin_to_geometry(obj:bpy.types.Object):
    #with bpy.context.temp_override(object=obj, selected_editable_objects=[obj]):
    #    bpy.ops.object.origin_set(type='ORIGIN_CURSOR', center='MEDIAN')

    #world_matrix = obj.matrix_world.copy()
    #with bpy.context.temp_override(object=obj, selected_editable_objects=[obj]):
    #    bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')
    #obj.matrix_world = world_matrix
    pass

#================================
#		  COLLECTION API
#================================
def get_top_collection() -> bpy.types.Collection: 
    return bpy.context.scene.collection

def get_active_collection() -> bpy.types.Collection: 
    ret = bpy.context.view_layer.active_layer_collection
    return ret.collection if ret else get_top_collection()

def get_collection(allow_active:bool)-> bpy.types.Collection: 
    return get_active_collection() if allow_active else get_top_collection()

def unlink_from_all(bpy_obj:bpy.types.Object):
    for coll in bpy_obj.users_collection:
        coll.objects.unlink(bpy_obj)
    return bpy_obj


def add_uv_coords(bpy_mesh:bpy.types.Mesh, uvs:Sequence[Vector]):
    uv_layer = bpy_mesh.uv_layers.new()
    for loop in bpy_mesh.loops:
        uv_layer.uv[loop.index].vector = uvs[loop.vertex_index]

def add_normals(bpy_mesh:bpy.types.Mesh, normals):
    return bpy_mesh.normals_split_custom_set_from_vertices(normals)

#uv_layer = bpy_mesh.uv_layers.new()
#for poly in bpy_mesh.polygons:
#    for li in poly.loop_indices:
#        vind = bpy_mesh.loops[li].vertex_index
#        uv_layer.data[li].uv = tuple(bfm_geom.vertices[vind].uv)