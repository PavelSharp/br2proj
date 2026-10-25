#Python 3.12: ReadableBuffer (like hashlib)

#==[TRI CUSTOM HASH FUNCTION]==
# [NEW 20.09.2026] 
# Reverse engineering of the Infernal Engine reveals that Terminal Reality
# used a custom hashing function for all internal string indexing.
# At runtime, the engine discards string buffers by converting
# them into uint32 hashes for fast table lookups across major subsystems.
# It features a case-insensitive, iterative MAD hash design.
# The implementation is based on sub_786230.
def tri_hash(bts: bytes | bytearray | str, init : int = 0) : #init : int32->uint32
    if isinstance(bts, str): bts = bts.encode('ascii', errors='strict')
    signedi32 = ((init + 0x80000000) % 0x100000000) - 0x80000000
    val = signedi32 & 0xFFFFFFFFFFFFFFFF
    for b in bts :
        b = b - 32 if 97 <= b <= 122 else b # type: ignore
        val = (((val + b) * 314159821) & 0xFFFFFFFFFFFFFFFF) % 0xFFFFFFFB # type: ignore
    return val & 0xFFFFFFFF

# ==[Native C implementation]== 
# Precise fixed-width integer types eliminate the need for 
# complex type-wrapping required by Python's infinite ints.
# static inline uint32_t tri_hash(const char* bts, int32_t init = 0) {
#     uint64_t val = (uint64_t)init;
#     for (int i = 0; bts[i]; ++i) {
#         uint8_t b = (uint8_t)bts[i];
#         if (b >= 97 && b <= 122) b -= 32;
#         val = ((val + b) * 314159821) % 0xFFFFFFFBULL;
#     }
#     return (uint32_t)val;
# }

#================================
#         MAIN SECTION
#================================

import math
from typing import NamedTuple, Literal, TypeVar, Generic, Self
from functools import cache as _cache

_Tsc = TypeVar('_Tsc', float, int)

class Vec3(NamedTuple, Generic[_Tsc]):
    x: _Tsc
    y: _Tsc
    z: _Tsc
    def __add__(self, o: Self): return self.__class__(self.x+o.x, self.y+o.y, self.z+o.z)
    def __mul__(self, v: _Tsc): return self.__class__(self.x*v, self.y*v, self.z*v)
    def __floordiv__(self, v: _Tsc): return self.__class__(self.x//v, self.y//v, self.z//v)

class Vec4(NamedTuple, Generic[_Tsc]):
    x: _Tsc
    y: _Tsc
    z: _Tsc
    w: _Tsc
    def __add__(self, o: Self): return self.__class__(self.x+o.x, self.y+o.y, self.z+o.z, self.w+o.w)
    def __mul__(self, v: _Tsc): return self.__class__(self.x*v, self.y*v, self.z*v, self.w*v)
    def __floordiv__(self, v: _Tsc): return self.__class__(self.x//v, self.y//v, self.z//v, self.w//v)


class Vec3i(Vec3[int]): ...
class Vec4i(Vec4[int]): ...
class Vec3f(Vec3[float]): 
    def length(self): return math.sqrt(self.x**2 + self.y**2 + self.z**2)
class Vec4f(Vec4[float]):
    def length(self): return math.sqrt(self.x**2 + self.y**2 + self.z**2 + self.w**2)

EulerAxisOrder = Literal['XYZ', 'XZY', 'YXZ', 'YZX', 'ZXY', 'ZYX']
class Euler(NamedTuple):
    x: float
    y: float
    z: float
    AXIS = 'unknown' #Cannot use EulerAxisOrder or ClassVar[EulerAxisOrder] annotations here
    @classmethod
    def zero(cls): return cls(0.0, 0.0, 0.0)
    @staticmethod
    @_cache
    def _construct_impl(order: EulerAxisOrder): return type(f'PureEuler_{order}', (Euler,), {'AXIS': order})
    @classmethod
    def construct(cls, order: EulerAxisOrder): return cls._construct_impl(order)
    @classmethod
    def __class_getitem__(cls, order: EulerAxisOrder): return cls.construct(order)

# Explicit subclasses ensure type safety.
# a: PureEulerXYZ = PureEulerZXY(0,0,0) triggers a linter error.
# But inline subscripts bypass static analysis, i.e.:
# a: PureEuler['XYZ'] = PureEuler['ZXY'](0,0,0) will NOT trigger a linter error.
class EulerXYZ(Euler['XYZ']): ...
class EulerXZY(Euler['XZY']): ...
class EulerYXZ(Euler['YXZ']): ...
class EulerYZX(Euler['YZX']): ...
class EulerZXY(Euler['ZXY']): ...
class EulerZYX(Euler['ZYX']): ...