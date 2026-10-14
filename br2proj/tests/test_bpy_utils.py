import unittest
import itertools

import bpy
import bpy.types
import bpy_extras

from ..bpy_utils import *

def _matr_eql(u:unittest.TestCase, m1:Matrix, m2:Matrix, places:int | None = None):
    msz = (len(m1.row), len(m1.col))
    m2sz = (len(m2.row), len(m2.col))
    u.assertEqual(msz, m2sz, 'The matrix sizes are different')
    for r in range(msz[0]):
        for c in range(msz[1]):
                u.assertAlmostEqual(m1[r][c], m2[r][c], places=places, msg=f'Matrices mismatch at cell [{r}][{c}]')

def _vec_eql(u:unittest.TestCase, v1, v2, places:int | None = None, map = lambda x:x):
    for a, b in zip(v1, v2):
        u.assertAlmostEqual(map(a), map(b), places=places)

class TestOrthoBasis(unittest.TestCase):
    def testToMatrix(self):
        check = lambda s, e: self.assertEqual(OrthoBasis.from_str(s).to_matrix(), Matrix(e))
        #'AB_h', where A is fwd, B is up
        #In the matrix, order is: right, up, fwd
        check('ZY_rh', [
            [ 1,  0,  0],
            [ 0,  1,  0],
            [ 0,  0,  1]
        ])
        check('ZY_lh', [
            [ -1,  0,  0],
            [ 0,  1,  0],
            [ 0,  0,  1]
        ])
        check('-YX_rh', [
            [ 0,  1,  0],
            [ 0,  0, -1],
            [ -1,  0,  0]
        ])
        check('-YX_lh', [
            [ 0,  1,  0],
            [ 0,  0, -1],
            [ 1,  0,  0]
        ])


    def testBasisConversion(self):
        def assertSpaceRaises(s:OrthoBasis): 
            with self.assertRaises(ValueError): s.validate()
        basis_conv = OrthoBasis.basis_conversion
        axes = [UnitAxis.from_str(ax) for ax in ['X', 'Y', 'Z', '-X', '-Y', '-Z']]

        for f_fwd, f_up, t_fwd, t_up in itertools.product(axes, repeat=4):
            from_rh, to_rh = OrthoBasis(f_fwd, f_up, 'rh'), OrthoBasis(t_fwd, t_up, 'rh')
            from_lh, to_lh = OrthoBasis(f_fwd, f_up, 'lh'), OrthoBasis(t_fwd, t_up, 'lh')

            if f_fwd.xyz==f_up.xyz:
                assertSpaceRaises(from_rh)
                assertSpaceRaises(from_lh)
                continue
            if t_fwd.xyz==t_up.xyz:
                assertSpaceRaises(to_rh)
                assertSpaceRaises(to_lh)
                continue

            rh, lh=basis_conv(from_rh, to_rh), basis_conv(from_lh, to_lh)
            rlh, lrh=basis_conv(from_rh, to_lh), basis_conv(from_lh, to_rh)

            self.assertAlmostEqual(rh.determinant(), 1)
            self.assertAlmostEqual(lh.determinant(), 1)
            self.assertAlmostEqual(lrh.determinant(), -1)
            self.assertAlmostEqual(rlh.determinant(), -1)
            bpy_rh = bpy_extras.io_utils.axis_conversion(str(f_fwd), str(f_up), str(t_fwd), str(t_up))
            self.assertEqual(rh, bpy_rh, f'Result does not match blender conversion for {rh}')
            self.assertEqual(lh, rh, f'Transformation matrix must be invariant to handedness. lh: {lh}, rh: {rh}')


class TestSpaceTransformer(unittest.TestCase):
    def testInverted(self):
        rmat = lambda ang, axes: Matrix.Rotation(ang, 3, Vector(axes).normalized())
        vec = lambda x,y,z: Vector((x,y,z))
        quat = lambda w,x,y,z: Quaternion((w,x,y,z)).normalized()

        mats = [rmat(0.74,(1.0, 2.0, 3.0)), rmat(1.35, (5,-1,2)), rmat(0.42, (0,1,0))]
        vecs = [vec(3.14, -2.71, 1.41), vec(-5.5, 12.3, 0.01), vec(1.2, 0.8, 2.5)]
        quats = [quat(0.5, -0.3, 0.8, 0.1), quat(0.7071, 0.0, 0.7071, 0.0), quat(0.25, 0.65, -0.42, 0.58)]
        spaces = ['-YZ_rh', 'ZY_lh', 'XZ_rh', 'XY_rh', '-ZY_lh']
        axes = ['X', 'Y', '-Z']
        prod = itertools.product
        def get_transformers():
            for s1, s2 in prod(spaces, repeat=2):
                for b1, b2 in prod(axes, repeat=2):
                    yield (True, SpaceTransformer.create_app(AppSpace(s1, b1), AppSpace(s2, b2)))
            for space, correction in prod(mats, repeat=2):
                yield (False, SpaceTransformer.create(space, correction))


        for is90, tr in get_transformers():
            tr_inv = tr.inverted()
            for m in mats:
                _matr_eql(self, m, tr_inv.conv_rest_bone_matrix(tr.conv_rest_bone_matrix(m)), places=6)

            for v in vecs:
                _vec_eql(self, v, tr_inv.conv_vec(tr.conv_vec(v)), places=5)
                _vec_eql(self, v, tr_inv.conv_anim_pos(tr.conv_anim_pos(v)), places=5)
                if is90:
                    _vec_eql(self, v, tr_inv.conv_anim_scale(tr.conv_anim_scale(v)), places=5, map=abs)

            for q in quats:
                _vec_eql(self, q, tr_inv.conv_anim_rot(tr.conv_anim_rot(q)), places=5)