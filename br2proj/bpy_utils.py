import bpy
import bpy.types
from bpy_extras import io_utils
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

#Keep in mind that when we change_orient, the scale becomes negative. In blenderui, some scale values will be negative.
def axis_conversion(from_forward='Y', from_up='Z', to_forward='Y', to_up='Z', change_orient = False) -> Matrix:
    def parse(val): 
        axes = {'X':0, 'Y':1, 'Z':2}
        def throw(): raise ValueError(f'Unkown Axis {val}')
        if not (1<=len(val)<=2) or val[-1] not in axes: throw()
        sig=1 
        if len(val)==2:
            if val[0]!='-': throw()
            sig = -1
        return sig, axes[val[-1]]

    def find_basis(fwd, up): #Tuple[bool, int]
        mul_dict = {
            (0,1):(+1,2),  (1,2):(+1,0),  (2,0):(+1,1),
            (1,0):(-1,2),  (2,1):(-1,0),  (0,2):(-1,1),
        }
        sig1, i1 = fwd
        sig2, i2 = up  
        sig, res  = mul_dict[(i1,i2)]
        return sig1*sig2*sig, res
    
    ret = Matrix(((0,0,0), (0,0,0), (0,0,0)))
    def add(v1, v2):
        sig1, i1 = parse(v1)
        sig2, i2 = parse(v2)
        ret[i2][i1]=sig1*sig2
        return (sig1, i1), (sig2, i2)

    from_forward, to_forward = add(from_forward,to_forward)
    from_up, to_up = add(from_up,to_up)
    
    if from_forward[1] == from_up[1] or to_forward[1] == to_up[1]:
        raise ValueError('Axis conflict detected')

    sig1, i1 = find_basis(from_forward, from_up)
    sig2, i2 = find_basis(to_forward, to_up)
    ret[i2][i1] = (-1 if change_orient else 1)*sig1*sig2
    return ret
        
    

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


'''
#TODO Think about where to place tests of axis_conversion
    axes = ['X','Y','Z', '-X','-Y','-Z']
    for f_fwd in axes:
        for f_up in axes:
            for t_fwd in axes:
                for t_up in axes:

                    if f_fwd[-1]==f_up[-1] or t_fwd[-1]==t_up[-1]:
                        err = None
                        try:
                            axis_conversion(f_fwd, f_up, t_fwd, t_up)
                        except ValueError as e:
                            err = str(e)

                        if err!='Axis conflict detected':
                             raise ValueError(f'Exception test failed')
                        continue

                    cor = bpy_extras.io_utils.axis_conversion(f_fwd, f_up, t_fwd, t_up)
                    my = axis_conversion(f_fwd, f_up, t_fwd, t_up)

                    my2 = axis_conversion(f_fwd, f_up, t_fwd, t_up, True)

                    if my==my2: raise ValueError('Self checking error')
                    if my2.determinant()!=-1: raise ValueError('Determinant error')

                    if cor!=my: raise ValueError('Equality test failed')
'''