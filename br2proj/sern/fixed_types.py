import ctypes
from . import sern_read

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

'''
c_ushort = ctypes.c_ushort
c_short = ctypes.c_ushort

c_int = ctypes.c_int
c_uint = ctypes.c_uint

c_long = ctypes.c_long
c_ulong = ctypes.c_ulong


c_longlong = ctypes.c_longlong
c_ulonglong = ctypes.c_ulonglong
'''


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



class _mulmeta(type):
    def __mul__(cls, count):
        assert isinstance(count, int) and count>=0, "count must be int and non-negative" 
        return cls.create_mul_type(count)
    def __call__(cls, *args, **kwargs):
        raise TypeError("Direct call is not allowed. Use * as type level")

class align: pass #for using with isinstance(obj, align)

class align_factory(metaclass=_mulmeta):
    @classmethod
    def create_mul_type(cls, count:int):
        class align_internal(align):
            @staticmethod
            def sern_read(rdr: sern_read.reader):
                file = rdr.file
                pos = file.tell()
                diff = (pos+count-1)//count*count - pos
                class align_fixed(c_uint8 * diff, align_internal): pass
                return align_fixed.from_buffer_copy(file.read(diff))
                    
        return align_internal


class align16(align_factory * 16): pass

class ascii_str:
    """
    Класс-маркер для идентификации массива ASCII-символов.
    Применение: вызов isinstance
    """
    pass

class ascii_char(metaclass=_mulmeta):
    """
    Реализует класс строки фиксированной длины, создаваемые по ascii_char * n
    Применение. строки, извлекаемые из бинарных файлов, 
    которые является непрерывной последовательностью ascii символов
    оканчивающихся 0, после которого могут идти любые байты-заполнители
    Требоваия. Индентификация этого типа производиться вызывом 
    isinstance(type_, ascii_str)
    """
    @classmethod
    def create_mul_type(cls, count:int):
        @sern_read.unmapped_type
        class ascii_array(c_char * count, ascii_str):
            def __str__(self):
                #Self.value вернет строку до первого \0, в случае отсутствия - вся строка
                data = bytes(self)
                pos = data.find(b'\0')
                if pos == -1: raise ValueError("This string is not null terminated")
                return data[:pos].decode('ascii')
            def sern_jwrite(self): return str(self)
        return ascii_array