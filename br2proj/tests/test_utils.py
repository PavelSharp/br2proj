import unittest

from ..utils import *

class TestUtils(unittest.TestCase):
    def testTriHash(self):
        check = lambda lhs, rhs: self.assertEqual(tri_hash(lhs), rhs, 'Hashes mismatch!')
        #===RAYNE.SKB===
        check('Bip01 Pelvis', 662878852)
        check('Brow_left', 2260275888)
        #===BRUTE.SKB===
        check('Bip01 R Foot', 4043213918)
        check('Bip01 R Finger31', 822135919)
        #===SLEGION.SKB===
        check('cloth3', 1185428701)
        check('dread_leftbottom', 3208519028)