import unittest
import itertools

import bpy
import bpy.types
import bpy_extras

from ..bpy_utils import *

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

