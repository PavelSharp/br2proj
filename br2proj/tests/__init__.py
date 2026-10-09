import unittest

import bpy
from bpy.types import Operator
import bpy.types

def run_all_tests():
    from . import test_bfm_imp
    from . import test_bpy_utils
    from . import test_utils
    mods = [test_bfm_imp, test_bpy_utils, test_utils]

    suite = unittest.TestSuite()
    loader = unittest.TestLoader()
    for mod in mods: suite.addTests(loader.loadTestsFromModule(mod))
    runner = unittest.TextTestRunner(verbosity=2)
    return runner.run(suite).wasSuccessful()    

class RunTestsOp(Operator):
    'This operator is only for development test execution. It should not be in the built version.'
    bl_idname = 'br2proj.run_all_tests'
    bl_label = 'br2Proj Run all tests'
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        if run_all_tests():
            self.report({'INFO'}, 'All tests passed successfully')
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, 'Tests failed! Open details via: Window->Toggle System Console')
            return {'CANCELLED'}
    
def register():
    bpy.utils.register_class(RunTestsOp)

def unregister():
    bpy.utils.unregister_class(RunTestsOp)



