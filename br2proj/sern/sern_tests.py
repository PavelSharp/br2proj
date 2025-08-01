import io
import unittest
import typing
from typing import Any, Annotated
import dataclasses
from dataclasses import dataclass, field
#import ctypes

from . import sern_core as core
from .sern_core import sernAs
from . import sern_read
from . import fixed_types as ft
from .fixed_types import *
from .sern_read import reader, fixeddata

#np, npt = sern_core.try_import_lib('numpy', 'numpy.typing')
np, npt = sern_read.np, sern_read.npt
def HAS_NUMPY(): return np is not None and npt is not None

class TestByteStream(io.RawIOBase):
    def __init__(self, size:int | None =None):
        self._pos = 0
        self._size = size 

    def read(self, size: int = -1) -> bytes:
        if size == -1:
            if self._size is None:
                raise ValueError('Unbounded read not supported on infinite stream')
            else:
                size = self._size - self._pos
        elif self._size is not None:
            size = min(size, self._size - self._pos)
        if size<0: size = 0
        data = bytes((self._pos + i) % 256 for i in range(size))
        self._pos += size
        return data

    def readinto(self, b: bytearray | memoryview) -> int:
        mv = memoryview(b).cast('B')
        data = self.read(len(mv))
        mv[:len(data)] = data
        return len(data)

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        if whence == io.SEEK_SET:
            self._pos = offset
        elif whence == io.SEEK_CUR:
            self._pos += offset
        elif whence == io.SEEK_END:
            if self._size is not None:
                self._pos = self._size - offset 
            else:
                raise OSError('Cannot seek from end on infinite stream')
        
        if self._pos < 0: raise ValueError('Seek resulted in negative position')
        if self._size is not None and self._pos > self._size: raise ValueError('Seek position is beyond end of stream')
        return self._pos
    
    def readable(self): return True
    def seekable(self): return True
    def tell(self): return self._pos

_read_all = reader.read_all
#_data = TestByteStream


class testSernReader(unittest.TestCase):
    def testNumpy(self):
        if np is None: return
        NDArray, ndarray, dtype = npt.NDArray, np.ndarray, np.dtype #type: ignore
        pixel = np.dtype([('r', np.uint8),('g', np.uint8),('b', np.uint8)])
        def read12(typ, *args):
            stream = lambda: TestByteStream(12)
            ret = reader.read_all(stream(), typ, *args, eof='error')
            self.assertEqual(ret.tobytes(), stream().read())
            if len(args)>0 and isinstance(args[0], tuple) and len(args[0])==2:
                shape, dtype = args[0]
                if isinstance(shape, int): shape = (shape, )
                self.assertEqual(ret.shape, shape)
                self.assertEqual(ret.dtype, dtype)
            return ret

        read12(NDArray, (3, np.int32))
        read12(NDArray[Any], ((3,1),np.int32))
        read12(NDArray[Any], (4,pixel))
        read12(NDArray[np.int32], (3,))
        read12(NDArray[np.int8], ((3,2,2),np.int8))
        read12(NDArray[np.int32], (3,np.int32))
        with self.assertRaisesRegex(ValueError, '^Argument was not passed'):
            read12(ndarray[tuple[int,...], np.dtype[np.int32]])
        with self.assertRaisesRegex(TypeError, '^Dtype mismatch'):
            read12(NDArray[np.int32], (3,np.int64))
        with self.assertRaisesRegex(TypeError, '^Shape mismatch'):
            read12(ndarray[tuple[int,int,int], np.dtype[np.int32]], ((3,1),np.int32))
        with self.assertRaisesRegex(TypeError, '^Shape is missing'):
            read12(ndarray[tuple[int], np.dtype[np.int32]], ())
        with self.assertRaisesRegex(TypeError, '^Invalid shape: expected a tuple of integers'):
            read12(ndarray[tuple[int,...], np.dtype[np.int32]], 'not shape')

        read12(ndarray[tuple[int,int], dtype[np.int32]], ((3,1), np.int32))
        read12(ndarray[tuple[int,int], dtype[Any]], ((4,1), pixel))
        read12(ndarray[tuple[int,...], dtype[Any]], ((3,2,1), np.int16))
        read12(ndarray[tuple[int,...], dtype[Any]], ((4,1,1), pixel))

    def testNumpyScalars(self):
        if np is None: return
        def read_scalar(typ):
            sz = np.dtype(typ).itemsize
            stream = lambda: TestByteStream(sz)
            ret = reader.read_all(stream(), typ, eof='error')
            self.assertEqual(type(ret), typ)
            self.assertEqual(ret.tobytes(), stream().read())
            return ret   
        for sca in [np.int16, np.uint32, np.float64, np.bool_]:
            read_scalar(sca)
        with self.assertRaisesRegex(ValueError, '^Unable to find a suitable deserializer for bool'):
            read_scalar(bool)
        
        with self.assertRaises(Exception):
            reader.read_all(TestByteStream(1), 'absf')

    def testNamedTuple(self):
        from typing import NamedTuple
        from collections import namedtuple
        Named1 = namedtuple('Named1', ['x', 'y'])
        Named2 = NamedTuple('Named2', [('x',int), ('y',float)])
        class Named3(NamedTuple):
            x: int
            y: float
        is_tuple = core.is_typed_namedtuple
        self.assertFalse(is_tuple(int))
        self.assertFalse(is_tuple(Named1))
        self.assertTrue(is_tuple(Named2))
        self.assertTrue(is_tuple(Named3))

    def testMethodReturnType(self):
        class bar:
            pass
        class foo:
            @classmethod
            def work1(cls, b:'bar') -> 'foo':
                return foo()
            @classmethod
            def work2(cls, b:'bar') -> list['foo']:
                return [foo(), foo()]
            @classmethod
            def work3(cls, b:'bar') -> bar:
                return bar()
            @classmethod
            def work4(cls, b:'bar') -> tuple['foo', 'foo']:
                return foo(), foo()
            @staticmethod
            def no_ret(b:'bar'):
                return bar()
        self.assertEqual(core.methodReturnType(foo, 'work1'), foo)
        self.assertEqual(core.methodReturnType(foo, 'work2'), list[foo])
        self.assertEqual(core.methodReturnType(foo, 'work3'), bar)
        self.assertEqual(core.methodReturnType(foo, 'no_ret'), core.NO_RETURN)
    
    def fixed_read(self, typ, *args):
        stream = lambda: TestByteStream(core.FixedUtils.sizeof(typ))
        ret = reader.read_all(stream(), typ, *args, eof='error')
        self.assertEqual(core.FixedUtils.tobytes(ret), stream().read())
        return ret

    def testFixedDataDecorator(self):
        class Basic:
            a: Annotated[ft.Array, sernAs(ft.c_int16*2)]
            def foo(self, arg): return arg

        @sern_read.fixed_dataclass(checker='error')
        class FixClass1:
            not_annotated = (42,43)
            a: Annotated[int, sernAs(ft.c_int32)] 
            b: Annotated[float, sernAs(ft.c_float)]
            def foo(self): pass
            def __len__(self): return 0
        self.assertTrue(core.FixedUtils.sizeof(FixClass1)==8)
        
        with self.assertRaisesRegex(TypeError, 'arleady have fields: _fields_ or _pack_'):
            @sern_read.fixed_dataclass(checker='error')
            class FixClass2(FixClass1):
                pass

        with self.assertRaises(sern_read.CheckerError):
            class int_child(int):
                pass
            @sern_read.fixed_dataclass(checker='error')
            class FixClass3:
                a: Annotated[int_child, sernAs(ft.c_int32)] 

        def check_interface(val, a, b):
            val.foo()
            val.__len__()
            self.assertTrue(val.not_annotated==(42,43))
            self.assertTrue(type(val.a)==int and type(val.b)==float)
            self.assertTrue(val.a==a and val.b==b)
            a,b = 32,128
            val.a, val.b = a, b
            self.assertTrue(val.a==a and val.b==b)
            self.assertTrue(dataclasses.is_dataclass(val))
            fields_names = [fld.name for fld in dataclasses.fields(val)]
            self.assertFalse(['_fields_', '_pack_'] in fields_names)
            self.assertTrue(fields_names == ['a', 'b'])
        
        frombytes = core.FixedUtils.frombytes

        check_interface(FixClass1(42, 64), 42, 64)
        
        check_interface(self.fixed_read(FixClass1), 
                        frombytes(ft.c_int32, b'\x00\x01\x02\x03', True), 
                        frombytes(ft.c_float, b'\x04\x05\x06\x07', True))

        # has_callable = lambda o, name: callable(getattr(o, name,None))
        # self.assertTrue(has_callable(c1, 'foo'))
        # self.assertTrue(has_callable(c1, 'bar'))
        # print(q)
        # #Проверить что fields не возвращает _fields_, _pack_
        # #Проверить наследование
        # #Проверить статический член
        # ret = reader.read_all(TestByteStream(8), FixClass1, eof='error')        


        pass

    def testFixedDataDecoratorTypeChecker(self):
        @sern_read.fixed_dataclass(checker='error')
        class FixClass1:
            a: Annotated[ft.ascii_str, sernAs(ft.ascii_char * 8)]
            b: Annotated[ft.Array[ft.c_uint16], sernAs(ft.c_uint16*8)]
            c: Annotated[ft.Array[ft.Array[ft.c_ubyte]], sernAs(ft.c_ubyte*2*3)]
        self.assertTrue(isinstance(self.fixed_read(FixClass1).a,ft.ascii_str))
        self.assertTrue(core.FixedUtils.sizeof(FixClass1)==30)

        def must_ok(anno):
            t = type('tmp_struct', (),  {'__annotations__': {'a': anno}})
            return sern_read.fixed_dataclass(t, checker='error')
        def must_raise(anno):
            with self.assertRaises(sern_read.CheckerError):
                must_ok(anno)

        must_raise(Annotated[ft.Array[ft.c_ubyte], sernAs(ft.c_ubyte*2*3)])
        must_raise(Annotated[ft.Array[ft.Array[ft.c_ubyte]], sernAs(ft.c_int32*2*3)])  
        must_ok(Annotated[ft.Array, sernAs(ft.c_int32*2*3)])
        must_ok(Annotated[Any, sernAs(ft.c_int32)])

    @staticmethod    
    def getChecker(func=sern_read.reader.type_mapper):
        ch = sern_read.AnnoChecker('error')
        ch.configure(func)
        return ch

    def testAnnoChecker(self):
        class c_intChild(c_int):
            pass
        ch = self.getChecker()
        def eql(expected, current, correct=None):
            self.assertTrue(ch.compare(expected, current))
            if correct is None: 
                correct = expected
            else:
                 self.assertTrue(ch.compare(expected, correct)) #Not sure
            self.assertTrue(ch.build_anno(current)==correct)
        def dif(expected, current, correct):
            self.assertFalse(ch.compare(expected, current))
            if correct is not None:
                self.assertTrue(ch.build_anno(current)==correct)

        eql(Array[c_int], c_int * 5)
        dif(Array[c_int16], c_int * 5, Array[c_int])
        eql(Array[Array[c_int]], (c_int*5)*4)
        dif(Array[Array[c_byte]], (c_int*5)*4, Array[Array[c_int]])
        dif(Array[Array[c_intChild]], (c_int*5)*4, Array[Array[c_int]])
        eql(Array[Array[c_int]], (c_intChild*5)*4, Array[Array[c_intChild]])
        eql(bytes, c_char*4)
        eql(Array[Array[c_char]], (c_char*5)*4)
        dif(Array[int], c_int*5, Array[c_int])
        dif(c_int*5, Array[c_int], None) #!!!

        dif(c_int, c_int, None)
        eql(int, c_int, None)
        eql(int, int)
        dif(list[int], list[tuple[c_int, c_int]], list[tuple[int, int]])
        eql(list[Any], list[tuple[c_int, c_int]], list[tuple[int, int]])

        dif(c_int * 5, Array, Array)
        #eql(list[Array], list[c_int32*5], list[Array[c_int32]])
        #eql(Array, c_int * 5, Array[c_int])
        eql(list[Annotated[tuple[int,int], ...]], list[tuple[c_int, c_int]], list[tuple[int, int]])
        eql(Annotated[int,...], c_int, int)
        eql(Annotated[Annotated[int,...],...], c_int, int)
        dif(c_intChild, c_int, int)
        eql(c_int, c_intChild, c_intChild)
        
        from typing import TypeVar, Generic
        T = TypeVar('T') 
        class list2(list[T]):
            pass

        class mangen(Generic[T]):
            @classmethod
            def sern_read(cls, rdr:sern_read.reader, *args) -> int:
                return 0

        class mant:
            @classmethod
            def sern_read(cls, rdr:sern_read.reader, *args) -> 'mant':
                return mant()

        class mant_child(mant):
            @classmethod
            def sern_read(cls, rdr:sern_read.reader, *args) -> int:
                return 0
            
        class mant_hard:
            @classmethod
            def sern_read(cls, rdr:sern_read.reader, *args) -> list['mant_hard']:
                return [mant_hard(), mant_hard()]  
        
        eql(list[int], list2[c_int], list2[int])
        dif(list2[int], list[c_int], list[int])
        dif(int, mant, mant)
        eql(mant, mant)
        dif(mant, int, None)
        eql(list[mant], list[mant])
        eql(list[int], list[mant_child])
        dif(list[mant_child], list[mant], list[mant])
        eql(list[list[mant_hard]], list[mant_hard])
        self.assertFalse(isinstance(list[mangen[int]], sern_read.ManualReadable))    

    def testAnnoCheckerBuilderOnly(self):
        class fixman(c_int*5):
            @classmethod
            def sern_read(cls, rdr:sern_read.reader, *args) -> int:
                return 0
        class mant_hard:
            @classmethod
            def sern_read(cls, rdr:sern_read.reader, *args) -> list['mant_hard']:
                return [mant_hard(), mant_hard()]  
        ch = self.getChecker()
        def check(lhs, rhs):
            self.assertTrue(ch.build_anno(lhs)==rhs)
        check(list[c_int*5], list[Array[c_int]])
        check(list[tuple[Array[ascii_char*5] ,c_int]], list[tuple[Array[ascii_str] ,int]])
        check(list[c_int*5],list[Array[c_int]])
        check(list[tuple[Array[ascii_char*5] ,c_int]], list[tuple[Array[ascii_str] ,int]])
        check(ascii_char*5, ascii_str)
        check(list[c_char*5], list[bytes])
        check(list[fixman], list[int])
        check(list[tuple[c_int*5, c_int, tuple[c_long, c_bool], dict[int, str]]], list[tuple[Array[c_int], int, tuple[int, bool], dict[int, str]]])
        check(list[mant_hard], list[list[mant_hard]])

    def testDataClass(self):
        pass

# class foo:
#     arr1:npt.NDArray[np.int32] = np.zeros((3,3), np.int32)
#     arr2:npt.NDArray[typing.Any] = np.array([1,2,3], dtype=np.int32)
#     arr3:npt.NDArray = np.zeros((3,3), np.int32)
#     arr4:npt.NDArray = np.zeros((3,3), pixel_rgb)
#     arr5:np.ndarray[tuple[int,int,int], np.dtype[np.int32]] = np.zeros((1,2,3), np.int32)
#     arr6:np.ndarray[tuple[int,...], np.dtype[np.int32]] = np.array([1,2,3], dtype=np.int32)
#     arr7:np.ndarray[tuple[int,...], np.dtype[typing.Any]] =  np.zeros((3,3), pixel_rgb)
#     arr8:np.ndarray[tuple[int,int], np.dtype[typing.Any]] =  np.zeros((3,3), pixel_rgb)