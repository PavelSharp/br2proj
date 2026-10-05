import ctypes

#Private import, since this module can be imported via *
from typing import Literal as _Literal, Any as _Any
from collections.abc import Iterable as _Iterable
from functools import cache as _cache

c_bool = ctypes.c_bool
c_ubyte = ctypes.c_ubyte
c_byte = ctypes.c_byte
c_uint8 = ctypes.c_uint8
c_int8 = ctypes.c_int8
c_char = ctypes.c_char

c_uint16 = ctypes.c_uint16
c_int16 = ctypes.c_int16

c_int32 = ctypes.c_int32
c_uint32 = ctypes.c_uint32

c_int64 = ctypes.c_int64
c_uint64 = ctypes.c_uint64

c_float = ctypes.c_float
c_double = ctypes.c_double
c_longdouble = ctypes.c_longdouble


Array = ctypes.Array
Structure = ctypes.Structure
LittleEndianStructure = ctypes.LittleEndianStructure
BigEndianStructure = ctypes.BigEndianStructure

c_ushort = ctypes.c_ushort
c_short = ctypes.c_short

c_int = ctypes.c_int
c_uint = ctypes.c_uint

c_long = ctypes.c_long
c_ulong = ctypes.c_ulong

c_longlong = ctypes.c_longlong
c_ulonglong = ctypes.c_ulonglong



#решение наследовать отличное, т.к. point2f*n - работает ожидаемым образом
class point2f(c_float * 2):
    #Удобство в том, что оператор [n] для Си массивов обеспечивает
    #автоматическое преобразование во float (т.е. доступ к .value)
    @property
    def x(self): return self[0]
    @property
    def y(self): return self[1]    

class point3f(c_float * 3):
    @property
    def x(self): return self[0]
    @property
    def y(self): return self[1] 
    @property
    def z(self): return self[2]

class quaternion(c_float*4):
    @property
    def w(self): return self[0]
    @property
    def x(self): return self[1]
    @property
    def y(self): return self[2] 
    @property
    def z(self): return self[3]

class triangle(c_uint16 * 3):
    @property
    def a(self): return self[0]
    @property
    def b(self): return self[1] 
    @property
    def c(self): return self[2]    

class box3d(point3f * 2):
    @property
    def a(self): return self[0]
    @property
    def b(self): return self[1] 


MATRIX_ORDER = _Literal['rm', 'cm']

class Matrix(Array):
    """
    A lightweight, transient data container for binary matrix (de)serialization.

    Designed as a bridge between files and application APIs, 
    this class serves as a standalone "software" implementation.
    While sern supports NumPy arrays, using them for small matrices (up to 4x4) 
    can be redundant.
    
    On the other hand, the ctypes module also offers multidimensional arrays 
    via the (c_type * cols) * rows syntax. However, it fails to abstract 
    the underlying memory layouts (Row-Major vs. Column-Major) at the type level. 
    This class bakes memory layout directly into the type definition, 
    ensuring data transit without cluttering application logic.
    """

    r_count = 0
    c_count = 0
    order = ''
    _length_ = 0 #type: ignore
    _type_ = c_byte #type: ignore

    def _get_ind(self, k: tuple[int, int] | int): 
        if isinstance(k, tuple) and len(k) == 2:
            return k[0] * self.c_count + k[1] if self.order == 'rm' else k[1] * self.r_count + k[0]
        return k
    def __getitem__(self, key: tuple[int, int] | int): return super().__getitem__(self._get_ind(key))
    def __setitem__(self, key: tuple[int, int] | int, val): super().__setitem__(self._get_ind(key), val)

    def _rowscols(self, iscols:bool):
        rows = lambda: tuple(tuple(self[row, col] for col in range(self.c_count)) for row in range(self.r_count))
        cols = lambda: tuple(tuple(self[row, col] for row in range(self.r_count)) for col in range(self.c_count))
        return cols() if iscols else rows()

    @classmethod
    def _from_rowscols(cls, data:_Iterable[_Iterable[_Any]], iscols:bool):
        lst = []
        stride = cls.r_count if iscols else cls.c_count
        for ind, line in enumerate(data):
            for v in line: lst.append(v)
            assert len(lst) == (ind+1) * stride, f'Incorrect line length at the step {ind}'
        assert len(lst) == cls.r_count * cls.c_count, 'Not lines enough'
        return cls.from_flat(lst, 'cm' if iscols else 'rm')
    
    @property
    def rows(self): return self._rowscols(False)
    @property
    def cols(self): return self._rowscols(True)
    @classmethod
    def from_rows(cls, rows: _Iterable[_Iterable[_Any]]): return cls._from_rowscols(rows, False)
    @classmethod
    def from_cols(cls, cols: _Iterable[_Iterable[_Any]]): return cls._from_rowscols(cols, True)
    def transposed(self):
        rows = lambda: [self[row, col] for col in range(self.c_count) for row in range(self.r_count)]
        cols = lambda: [self[row, col] for row in range(self.r_count) for col in range(self.c_count)]
        data = rows() if self.order=='rm' else cols()
        return self.construct(self.c_count, self.r_count)(*data)
    @classmethod
    def from_flat(cls, data: _Iterable[_Any], layout: MATRIX_ORDER):
        return cls(*data) if cls.order == layout else cls.construct(cls.c_count, cls.r_count)(*data).transposed() 
    def to_flat(self, layout:MATRIX_ORDER):
        return list(self if self.order==layout else self.transposed())
    
    @staticmethod
    @_cache
    def _construct_impl(r_count:int, c_count:int, order:MATRIX_ORDER, el_type:type):
        # Inheriting from Matrix instead of cls, as methods valid for an NxM may lose meaning for an MxN
        return type(f'Matrix{r_count}x{c_count}{order}_{el_type.__name__}', (Matrix,), {
            'r_count': r_count, 'c_count':c_count, 'order':order,
            '_length_':r_count*c_count, '_type_': el_type})

    @classmethod
    def construct(cls, r_count:int, c_count:int, order:MATRIX_ORDER|None = None, el_type:type|None = None):
        not_none = lambda dflt, v: dflt if v is None else v
        return cls._construct_impl(
                r_count, c_count,
                not_none(cls.order, order), not_none(cls._type_, el_type))
    @classmethod
    def __class_getitem__(cls, params): return cls.construct(*params)
    def sern_jwrite(self): return self.rows

Matrixf = Matrix[0, 0, None, c_float]
Matrixf2x2RM = Matrixf[2, 2, 'rm']
Matrixf2x2CM = Matrixf[2, 2, 'cm']
Matrixf3x3RM = Matrixf[3, 3, 'rm']
Matrixf3x3CM = Matrixf[3, 3, 'cm']
Matrixf4x4RM = Matrixf[4, 4, 'rm']
Matrixf4x4CM = Matrixf[4, 4, 'cm']
Matrixf3x4RM = Matrixf[3, 4, 'rm']
Matrixf3x4CM = Matrixf[3, 4, 'cm']
Matrixf4x3RM = Matrixf[4, 3, 'rm']
Matrixf4x3CM = Matrixf[4, 3, 'cm']

class _mulmeta(type):
    def __mul__(cls, count):
        assert isinstance(count, int) and count>=0, 'count must be int and non-negative'
        return cls.create_mul_type(count)
    def __call__(cls, *args, **kwargs):
        raise TypeError('Direct call is not allowed. Use * as type level')


class align: 
    pass #for using with isinstance(obj, align)

class align_factory(metaclass=_mulmeta):
    @classmethod
    def create_mul_type(cls, count:int):
        class align_internal(align):
            @staticmethod
            def sern_read(rdr): #: sern_read.reader
                file = rdr.file
                pos = file.tell()
                diff = (pos+count-1)//count*count - pos
                class align_fixed(c_uint8 * diff, align_internal): pass
                return align_fixed.from_buffer_copy(file.read(diff)) #TODO вызвать excacly_read вмето создание align_fixed
                    
        return align_internal


class align16(align_factory * 16): pass

# class _AsciiArrayMeta(type(Array)):
#     def __mul__(cls, _):
#         raise TypeError('Not allowed')

#It's a clever trick. We prefer c_uint8 instead of c_char to avoid reflection, so unmapped_typ no need
class ascii_str(Array): #, metaclass=_AsciiArrayMeta
    _length_ = 0 #type: ignore
    _type_ = c_uint8 #type: ignore
    def __str__(self):
        #self.value вернет строку до первого \0, в случае отсутствия - вся строка
        data = bytes(self)
        pos = data.find(b'\0')
        if pos == -1: raise ValueError("This string is not null terminated")
        return data[:pos].decode('ascii')

    def sern_jwrite(self): return str(self)

    # def sern_jwrite(self):
    #     data = bytes(self)
    #     pos = data.find(b'\0')
    #     if pos==-1: pos = len(data)
    #     head = data[:pos].decode('ascii', errors='replace')
    #     tail = data[pos+1:].decode('ascii', 'backslashreplace')
    #     return head if (len(tail)==0 or all(b == 0 for b in tail)) else [head,tail]

class ascii_char(metaclass=_mulmeta): #We don't inherit from c_char(c_uint8)
    @staticmethod
    def create_mul_type(count: int):
        return type(f'ascii_str_{count}', (ascii_str,), {'_length_': count})


# class ascii_str:
#     """
#     #TODO что-то придумать, что бы разрешить использование этого типа как 
#     fld:Annotated[ascii_str, SernAs(ascii_char*16)]
#     Класс-маркер для идентификации массива ASCII-символов.
#     Применение: вызов isinstance, вызов issubclass
#     """
#     pass

# class ascii_char(metaclass=_mulmeta):
#     """
#     Реализует класс строки фиксированной длины, создаваемые по ascii_char * n
#     Применение. строки, извлекаемые из бинарных файлов, 
#     которые является непрерывной последовательностью ascii символов
#     оканчивающихся 0, после которого могут идти любые байты-заполнители
#     Требоваия. Индентификация этого типа производиться вызывом 
#     isinstance(type_, ascii_str), а также issubclass(ascii_char*5, ascii_str)
#     """
#     @classmethod
#     def create_mul_type(cls, count:int):
#         @sern_read.unmapped_type
#         class ascii_array(c_char * count, ascii_str):
#             def __str__(self):
#                 #Self.value вернет строку до первого \0, в случае отсутствия - вся строка
#                 data = bytes(self)
#                 pos = data.find(b'\0')
#                 if pos == -1: raise ValueError("This string is not null terminated")
#                 return data[:pos].decode('ascii')
#             def sern_jwrite(self): return str(self)
#         return ascii_array