import unittest

from ..bfm_imp import *

class TestBFMNameParser(unittest.TestCase):
    def eql(self, lhs:bfm_parsed_name, rhs:bfm_parsed_name):
        self.assertDictEqual(lhs._asdict(), rhs._asdict())
    def parse_eql(self, lhs:str, rhs:bfm_parsed_name):
        return self.eql(bfm_name_parser.parse(lhs), rhs)

    def testSimplest(self):
        eql, cr = self.parse_eql, bfm_parsed_name
        eql('', cr(flags='unsorted'))
        eql('barrel', cr('', 'barrel', flags='unsorted'))
        eql('chunk5', cr('', 'chunk5', flags='unsorted'))

    def testSystemFlags(self):
        eql, cr = self.parse_eql, bfm_parsed_name
        eql('donotdrawme', cr('', 'donotdrawme', flags='system'))
        eql('zzz_bad_caps', cr('', 'zzz_bad_caps', flags='system')) 

    def testFlags(self):
        eql, cr = self.parse_eql, bfm_parsed_name
        #===long/short===
        eql('part_RArm_Long_a', cr('part', 'arm', 'r', mod='long', alpha='a')) 
        eql('part_LShin_Short_b', cr('part', 'shin', 'l', mod='short', alpha='b'))
        #===intact/damage===
        eql('dress_front_damage_03', cr('dress', 'front', mod='damage', num='03')) 
        eql('dress_top_back_damage_02', cr('dress', 'top_back', mod='damage', num='02')) 
        eql('dress_back_intact', cr('dress', 'back', mod='intact')) 

    def testSides(self):
        eql, cr = self.parse_eql, bfm_parsed_name
        eql('eye_left', cr('', 'eye', 'l')) 
        eql('empty_rarm', cr('empty', 'arm', 'r'))
        eql('part_head', cr('part', 'head'))
        eql('acc_mask_a', cr('acc', 'mask', alpha='a')) #Note. Does not exist in the game files
        eql('part_torsoLeft', cr('part', 'torso', 'l'))
        eql('part_rightwing', cr('part', 'wing', 'r'))
        eql('part_rforearm', cr('part', 'forearm', 'r'))
        eql('part_lforearm_a', cr('part', 'forearm', 'l', alpha='a'))
        eql('part_rtorsoTop_shirt_b_02', cr('part', 'torsotop_shirt', 'r', alpha='b', num='02')) #Note. The case is not preserved

    def testSideExceptions(self):
        eql, cr = self.parse_eql, bfm_parsed_name
        eql('part_lashes', cr('part', 'lashes'))
        eql('part_eyelashes', cr('part', 'eyelashes'))
        eql('acc_collar', cr('acc', 'collar'))
        eql('part_tophair', cr('part', 'tophair'))