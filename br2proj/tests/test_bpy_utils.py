import unittest
import itertools

import bpy
import bpy.types
import bpy_extras

from ..bpy_utils import *

class TestBPYUtils(unittest.TestCase):
    def testAxisConversion(self):
        axes = ['X', 'Y', 'Z', '-X', '-Y', '-Z']
        for f_fwd, f_up, t_fwd, t_up in itertools.product(axes, repeat=4):
            if f_fwd[-1]==f_up[-1] or t_fwd[-1]==t_up[-1]:
                with self.assertRaises(ValueError):
                    axis_conversion(f_fwd, f_up, t_fwd, t_up)
                continue
            rh = axis_conversion(f_fwd, f_up, t_fwd, t_up, False)
            lh = axis_conversion(f_fwd, f_up, t_fwd, t_up, True)
            self.assertAlmostEqual(rh.determinant(), 1)
            self.assertAlmostEqual(lh.determinant(), -1)
            bpy_rh = bpy_extras.io_utils.axis_conversion(f_fwd, f_up, t_fwd, t_up)
            self.assertEqual(rh, bpy_rh, f'Result does not match blender conversion for {f_fwd}, {f_up} -> {t_fwd}, {t_up}')