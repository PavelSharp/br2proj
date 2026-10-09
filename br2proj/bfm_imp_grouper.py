from typing import Literal, ClassVar, NamedTuple, assert_never
from abc import ABC, abstractmethod

BPY_COLELCTION_COLOR_TAG  = Literal['NONE', 'COLOR_01', 'COLOR_02', 'COLOR_03', 'COLOR_04', 'COLOR_05', 'COLOR_06', 'COLOR_07', 'COLOR_08']

class bfm_name_parser:
    Side = Literal['l', 'r'] | None
    Flags = Literal['system', 'unsorted'] | None
    Modifier = Literal['damage', 'intact', 'long', 'short'] | None
    _NAME_MISTAKES = {
        'part_RHead_Bottom_a': 'part_RHeadBottom_a', # [GENERIC_M.BFM]
        'par_larm': 'part_larm', # [RAYNE_ARMOR.BFM]
    }
    _SIDE_EXCEPTIONS = {'rack', 'lashes', 'lash', 'laces', 'lace', 'collar', 'hair'} #NOTE: lowercase [after normalization]
    @classmethod
    def normalize_part_name(cls, text:str):
        text = cls._NAME_MISTAKES.get(text, text)
        text = text.lower()
        while '__' in text:
            text = text.replace('__', '_')
        return text
    @staticmethod
    def extrbeg(text:str, s:str): return text[len(s):] if text.startswith(s) else None
    @staticmethod
    def extrend(text:str, s:str): return text[:-len(s)] if text.endswith(s) else None

    @classmethod
    def extract_flags(cls, text:str) -> tuple[Flags, str, bool]:
        if any(n in text for n in ('donotdrawme', 'zzz_bad_caps')):
            return 'system', text, True
        parts = text.split('_', 1)
        if len(parts)<=1:
            return 'unsorted', text, True
        return None, text, False

    @classmethod
    def extract_alphanum(cls, text:str) -> tuple[str, str, str]:
        i = len(text) - 1
        while i >= 0 and text[i].isdigit(): i -= 1
        alpha, num = '', text[i+1:]
        if i>0 and text[i]=='_': i-=1
        if i >= 2 and text[i].isalpha() and text[i-1]=='_': 
            alpha=text[i]
            i-=2
        return alpha, num, text[:i+1]

    @classmethod
    def extract_modifier(cls, text:str) -> tuple[Modifier, str]:
        end = cls.extrend
        if s:=end(text, '_long'):   return 'long',   s
        if s:=end(text, '_short'):  return 'short',  s
        if s:=end(text, '_damage'): return 'damage', s
        if s:=end(text, '_intact'): return 'intact', s
        return None, text

    @classmethod
    def extract_side_end(cls, text:str) -> tuple[Side, str]:
        if any(text.endswith(exc) for exc in cls._SIDE_EXCEPTIONS): return None, text
        end = lambda s: cls.extrend(text, s)
        if s:=end('_left')  or end('left')  or end('_l'): return 'l', s
        if s:=end('_right') or end('right') or end('_r'): return 'r', s
        if text in cls._SIDE_EXCEPTIONS: return None, text
        if s:=end('l'): return 'l', s
        if s:=end('r'): return 'r', s
        return None, text
    
    @classmethod
    def extract_side_beg(cls, text:str) -> tuple[Side, str]:
        if any(text.startswith(exc) for exc in cls._SIDE_EXCEPTIONS): return None, text
        beg = lambda s: cls.extrbeg(text, s)
        if s:=beg('left_')  or beg('left')  or beg('l_'): return 'l', s
        if s:=beg('right_') or beg('right') or beg('r_'): return 'r', s
        if s:=beg('l'): return 'l', s
        if s:=beg('r'): return 'r', s
        return None, text   
        
    @classmethod
    def extract_group(cls, text):
        parts = text.split('_', 1)
        if len(parts)==1:
            return '', parts[0]
        return parts[0], parts[1]

    @classmethod
    def parse(cls, text:str):
        text = cls.normalize_part_name(text)
        flags, text, is_short = cls.extract_flags(text)
        if is_short: return bfm_parsed_name(object_name=text, flags=flags)
        alpha, num, text = cls.extract_alphanum(text)
        mod, text = cls.extract_modifier(text)
        side, text = cls.extract_side_end(text)
        group, text = cls.extract_group(text)
        if side is None: side, text = cls.extract_side_beg(text)
        return bfm_parsed_name(group, text, side, flags, mod, alpha, num)

class bfm_parsed_name(NamedTuple):
    group_name: str = ''
    object_name: str = ''
    side:bfm_name_parser.Side = None
    flags:bfm_name_parser.Flags = None
    mod: bfm_name_parser.Modifier = None
    alpha:str = ''
    num:str =''


class bfm_group_node(NamedTuple):
    name:str
    color:BPY_COLELCTION_COLOR_TAG = 'NONE'
    allow_collapse:bool = True

bfm_group_path = list[bfm_group_node]

# Implemented as a regular class so subclasses can accept constructor arguments
# and to maintain a consistent style across the codebase.

class bfm_grouper(ABC):
    @abstractmethod
    def get_group_path(self, part_name: str) -> bfm_group_path: ...

class bfm_null_grouper(bfm_grouper):
    def get_group_path(self, part_name: str) -> bfm_group_path:
        return []

class bfm_prefix_grouper(bfm_grouper):
    _GROUP_COLORS: ClassVar[dict[str, BPY_COLELCTION_COLOR_TAG]] = {
        'acc': 'COLOR_05',
        'dress': 'COLOR_06',
        'part': 'COLOR_02',
    }

    def get_group_path(self, part_name: str) -> bfm_group_path:
        node = bfm_group_node
        name = bfm_name_parser.parse(part_name)
        group_name, object_name = name.group_name, name.object_name

        match name.flags:
            case 'system': return [node('system', 'COLOR_01', False)]
            case 'unsorted': return [node('unsorted', 'COLOR_02', False)]
            case None: ...
            case _: assert_never(name.flags)

        path: bfm_group_path = []
        if group_name.startswith('cage'):
            path.append(node('cage', 'COLOR_03'))            
        
        path.append(node(group_name, self._GROUP_COLORS.get(group_name, 'NONE'), False))         

        match name.side:
            case 'l': object_name = f'{object_name} L'
            case 'r': object_name = f'{object_name} R'
            case None: ...
            case _: assert_never(name.side)

        path.append(node(object_name, 'NONE'))
        match name.mod:
            case 'damage': path.append(node('damage', 'COLOR_01'))
            case 'intact': path.append(node('intact'))
            case 'long':   path.append(node('long', 'COLOR_04'))
            case 'short':  path.append(node('short', 'COLOR_04'))
            case None: ...
            case _: assert_never(name.mod)

        return path