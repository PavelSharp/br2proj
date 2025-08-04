from typing import Union, Callable, Any
from functools import wraps

BytesLike = bytes | bytearray | memoryview | Any
#Python 3.14: memory_view[byte]
import typing

def _as_memoryview(val):
    def check_memview(val:memoryview):
        if not val.contiguous:
            raise ValueError('memoryview must be contiguous')
        if val.format != 'B' or val.itemsize!=1:
            raise ValueError("memoryview must be of format 'B'")
        if val.ndim != 1:
            raise ValueError('ndim of memoryview must be eql to 1')
        return val
    
    if not isinstance(val, memoryview):
        try:
            val = memoryview(val)
        except Exception as e:
            raise ExceptionGroup("Can't construct memoryview", [e])
    return check_memview(val)


# def accepts_buffer(func):

#     annotations = typing.get_type_hints(func, include_extras=True)
#     buffer_args = {name for name, hint in annotations.items() if hint == BytesLike}

#     @wraps(func)
#     def wrapper(*args, **kwargs):
#         pass
#         # if isinstance(bts, (bytes, bytearray)):
#         #     buf = memoryview(bts)
#         # elif isinstance(bts, memoryview):
#         #     if not bts.contiguous:
#         #         raise ValueError("Memoryview must be contiguous (C-style)")
#         #     if bts.format != 'B':
#         #         raise ValueError("Memoryview must be of format 'B' (unsigned bytes)")
#         #     buf = bts
#         # else:
#         #     raise TypeError("Expected bytes, bytearray, or memoryview")
        
#         return func(*args, **kwargs)
#     return wrapper



#Based on https://github.com/bartlomiejduda/ReverseBox/blob/f95e768749c4b8301bfa02507916db23b0230f17/reversebox/image/swizzling/swizzle_ps2.py#L21
def unswizzle_ps2_palette(palette: BytesLike) -> bytearray:
    palette = _as_memoryview(palette)
    converted = bytearray()
    bpp = 4
    stripes = 2
    colors = 8
    blocks = 2
    total = bpp*blocks*stripes*colors
    assert len(palette) % total==0
    parts = len(palette) // total
    for part in range(parts):
        for block in range(blocks):
            for stripe in range(stripes):
                for color in range(colors):
                    off = (
                        part * colors * stripes * blocks
                        + block * colors
                        + stripe * stripes * colors
                        + color)*bpp
                    converted+=palette[off:off+bpp]

    assert len(converted)==len(palette)
    return converted

from typing import NamedTuple

class Point(NamedTuple):
    x:int
    y:int


class MortonSwizz:
    IS_SWIZZ = False
    @staticmethod
    def map(x:int, y:int, width:int, height:int) -> Point:
        ind = y * width + x
        shift_x = shift_y = 1
        xx = yy = 0
        while width > 1 or height > 1:
            if width > 1:
                xx += shift_x * (ind & 1)
                ind >>= 1
                shift_x *= 2
                width >>= 1
            if height > 1:
                yy += shift_y * (ind & 1)
                ind >>= 1
                shift_y *= 2
                height >>= 1
        return Point(xx,yy)

class Ps2Swizz:
    IS_SWIZZ = True
    @staticmethod
    def map(x:int, y:int, width:int, height:int) -> Point:
        block_location = (y & (~0xF)) * width + (x & (~0xF)) * 2
        swap_selector = (((y + 2) >> 2) & 0x1) * 4
        pos_y = (((y & (~3)) >> 1) + (y & 1)) & 0x7
        column_location = pos_y * width * 2 + ((x + swap_selector) & 0x7) * 4
        byte_num = ((y >> 1) & 1) + ((x >> 2) & 2)
        swizzle_id = block_location + column_location + byte_num
        return Point(swizzle_id % width, swizzle_id // width)

#Based on https://reshax.com/topic/17924-ps2-how-does-ea%E2%80%99s-type-3-4-bit-swizzle-actually-work/
class Ps2Type34BitSwizz:
    IS_SWIZZ = True
    @staticmethod
    def map(x:int, y:int, width:int, height:int) -> Point:
        pageX = x  &  (~127)
        pageY = y  &  (~127)
        
        pages_horz = (width + 127)  //  128
        pages_vert = (height + 127)  //  128
        
        page_number = (pageY  //  128) * pages_horz + (pageX  //  128)
        page32Y = (page_number  //  pages_vert) * 32
        page32X = (page_number  %  pages_vert) * 64
        
        page_location = page32Y * height * 2 + page32X * 4

        locX = x  &  127
        locY = y  &  127
        block_location = ((locX  &  (~31))  >>  1) * height + (locY  &  (~15)) * 2
        swap_selector = (((y + 2)  >>  2)  &  1) * 4
        posY = (((y  &  (~ 3))  >>  1) + (y  &  1))  &  7
        column_location = posY * height * 2 + ((x + swap_selector)  & 7) * 4
        byte_num = (x  >>  3)  &  3        
        bits_set = (y  >>  1)  &  1
        
        ind = (page_location + block_location + column_location + byte_num)*2+bits_set
        return Point(ind % width, ind // width)
   
class mapping_bpp8:
    @staticmethod
    def map(width:int, height:int, data:BytesLike, direct:bool, func) -> bytearray:
        data = _as_memoryview(data)
        ret = bytearray(len(data))
        assert len(data)==width*height
        for j in range(height):
            for i in range(width):
                pt1 = Point(i,j)
                pt2 = func(i,j, width, height)
                if direct: pt1, pt2 = pt2, pt1
                p1 = pt1.y * width + pt1.x
                p2 = pt2.y * width + pt2.x
                ret[p1] = data[p2]
        return ret
    
    @classmethod
    def swizzle(cls, width:int, height:int, data:BytesLike, func):
        return cls.map(width, height, data, func.IS_SWIZZ, func.map)
    @classmethod
    def unswizzle(cls, width:int, height:int, data:BytesLike, func):
        return cls.map(width, height, data, not func.IS_SWIZZ, func.map)
    
class Vec4(NamedTuple):
    x:int
    y:int 
    z:int
    w:int
    def __add__(self, o: 'Vec4'):
        return Vec4(self.x+o.x, self.y+o.y, self.z+o.z, self.w+o.w)
    def __mul__(self, v: int):
        return Vec4(self.x*v, self.y*v, self.z*v, self.w*v)
    def __floordiv__(self, v: int):
        return Vec4(self.x//v, self.y//v, self.z//v, self.w//v)

#Based on https://github.com/bartlomiejduda/ReverseBox/blob/main/reversebox/image/decoders/n64_decoder.py#L43
class n64_codec:
    BLOCK_SIZE = (8,8)    
    @staticmethod
    def decode_rgb565(pixel_int: int) -> Vec4:
        r = ((pixel_int >> 11) & 0x1F) * 0xFF // 0x1F
        g = ((pixel_int >> 5) & 0x3F) * 0xFF // 0x3F
        b = ((pixel_int >> 0) & 0x1F) * 0xFF // 0x1F
        a = 0xFF
        return Vec4(r,g,b,a)

    @classmethod
    def decode(cls, width:int, height:int, data:BytesLike) -> bytearray:
        data = _as_memoryview(data)
        block_w, block_h = cls.BLOCK_SIZE
        assert width % block_w==0 and height % block_h==0
        ret = bytearray(width*height*4) #Image data in row-major RGBA format
    
        i = 0
        for y in range(0, height, block_h):
            for x in range(0, width, block_w):
                for y2 in range(0, block_h, 4):
                    for x2 in range(0, block_w, 4):
                        c0 = (data[i+0]<<8) | data[i+1]
                        c1 = (data[i+2]<<8) | data[i+3]
                        i+=4
                        v0, v1 = cls.decode_rgb565(c0), cls.decode_rgb565(c1)
                        vecs = [v0,v1, None, None]
                        
                        if c0>c1:
                            vecs[2] = (v0 * 2 + v1) // 3
                            vecs[3] = (v1 * 2 + v0) // 3
                        else:
                            vecs[2] = (v0 + v1) // 2
                            vecs[3] = Vec4(0,0,0,0)

                        for y3 in range(4):
                            b = data[i]; i+=1
                            for x3 in range(4):
                                px = x + x2 + x3
                                py = y + y2 + y3
                                col = vecs[(b >> (6 - (x3 * 2))) & 0b11]
                                index = (py * width + px) * 4 
                                ret[index:index+4] = col
        return ret

    @classmethod
    def bytes_count(cls, width:int, height:int)->int:
        bw, bh = cls.BLOCK_SIZE
        for_iters = lambda start, end, step: max((end-start)//step+1,0)
        i1 = for_iters(0,height-1,bh)
        i2 = for_iters(0,width-1, bw)
        i3 = for_iters(0, bh-1, 4)
        i4 = for_iters(0, bw-1, 4)
        return i1*i2*i3*i4*8
    