from pathlib import Path
import dataclasses
from dataclasses import dataclass, fields
from functools import lru_cache
import typing
from typing import Any, Annotated, Literal, assert_never, Protocol, runtime_checkable, Callable
from warnings import warn

from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator

from . import sern_core as core
from .sern_core import FixedUtils, type_name, type_repr, type_str, is_typed_namedtuple, KnownArg, exactly_read
from .import fixed_types as ft

np, npt = core.try_import_lib('numpy', 'numpy.typing')
#import numpy as np
#import numpy.typing as npt


#TODO JSONDebugger. При невозможности преобразования вызвать sern_jwrite
#TODO Ввести поддержку enum, на уровне reader и JSONDebugger. Enum->Json использовать строковое представление?
#TODO Исключитть некоторые assert в пользу исключений, т.к. assert в release удалаются
#TODO [СДЕЛАНО] вместо none использовать какой-то обощенный тип
#как например Error<T>, где T - тип который не удалось десериализовать 
#Это улучшит сообщение об ошибке

#Note. При написание writer учесть, что список может содержать разные типы
#Примечательно, что при чтение списка такая ситуация невозможна
#TODO [СДЕЛАНО] Все функцию принимающие type_ или typ должны отказаться от типизации как
#Type[any], поскольку Tuple[T,...] - не аявляется типом а является аннотацией
#TODO [СДЕЛАНО] Снабдить библиотеку sern типом ansi_str, с оператором ansi_str * n
#Цель - внутри ansi_str должно быть поле value - обеспечивающие преобразование 
#bytes в строку python (взять значения до первого \0)

#TODO [СДЕЛАНО] auto_read to static class sern.read (or use module?)
#Note. Поля структур должны иметь именно аннотацию в стиле c-типов.
#Не переходить к python типам так как они могут не предстовлять все множесвто допустимых значений
#Напр. строка - для си это массив байт где после нуля может идте всё что угодно
#но строка python такое содержимое представить не сможет
#TODO [СДЕЛАНО] SMB_Vertex should use point3f and point2f insted of c_float*3
#

#суть алгоритма auto_read
#1. Если поле с Annotated то обновить переменную format
#2. Если поле без Annotated то:
#2.1 если format не пуст то выполнить чтение из файла и заполнить словарь, сбросить format
#2.2 если это список то прочитать список(read_list)
#2.3 иначе вызвать статик. функцию read которую должна предоставить вызывающая сторона 
#3. По завершению алгоритма выполнить 2.1



#1. fixed type (or c types): abc: c_int,   abc: c_int32 * 12
#2. dynamic type with user read method: abc:foo or abc:annotated[foo, ""]

#3 #For some standard types we can automatically generated the read method:
#3.1 read method with request an extra argument for represent the length: 
#i.e list[c_int], dict[c_int, c_int] 
#3.2 fixed types with automatically generated read method:
#i.e. tuple[c_int, c_int]
#TODO [СДЕЛАНО] не забыть про тип bytearray

#!Метод fields_read возвращает словарь а не констирует тип, т.к. нет гарантий что переданы все поля


#суть алгоритма auto_read(Новый подход)
#1. Если тип имеет статический метод sern_read то вызвать его
#2. Если это один из типов для которых надо генерировать специальный sern_read то сделать это
#3. Иначе мы имеем структуру.
#3.1 Рекурссивно обходить поля и накапливать форматтер до тех 
# пока тип текущего поля имеем фиксированный тип
#ПРИМЕЧАНИЕ. Необходима поддержка типов как массив массивов(список списков) tex
#args is a tuple(E1, E2, ...), where E is 
#step by step reduced when calling sern_read or standrad_read

ByteStream = typing.IO[bytes]
PathLike = Path | str
PathLikeTypes = (Path, str)

#This is a special type that occurs if a suitable sterilizer is not found, is not exception
#A user method sern_read can create an instance of this type to receive a standard error.
class UnsupportedType:
    def __init__(self, typ): self.typ = typ
    def __str__(self): return type_repr(self.typ)
    def __repr__(self): return f"<{type_name(self)}: {type_repr(self.typ)}>"

@runtime_checkable
class ManualReadable(Protocol):
    @classmethod
    def sern_read(cls, rdr:'reader', *args) -> Any:
        raise NotImplementedError()

def _error(obj): return isinstance(obj, UnsupportedType)
def _pack_tuple(val): return val if isinstance(val, tuple) else (val, )
def isManualReadable(obj_or_typ: Any) -> bool:
    if isinstance(obj_or_typ, type):
        return issubclass(obj_or_typ, ManualReadable)
    else:
        return isinstance(obj_or_typ, ManualReadable)

def retTypeManualReadable(obj_or_typ: Any):
    if isManualReadable(obj_or_typ):
        owner = obj_or_typ if isinstance(obj_or_typ, type) else type(obj_or_typ)
        ret = core.methodReturnType(owner, 'sern_read')
        return owner if ret is core.NO_RETURN else ret
    return core.NO_RETURN


class Checker(ABC):
    @abstractmethod
    def configure(self, mapper:Callable[[Any], Any]):
        raise NotImplementedError()
    
    @abstractmethod
    def check(self, field: str, owner:type[Any], expected, current) -> bool:
         raise NotImplementedError()

class CheckerError(core.SernException):
    @staticmethod
    def create(obj, field: str, owner:type[Any], expected, current):
        obj.field, obj.owner = field, owner
        obj.expected, obj.current = expected, current
        return f'Incorrect annotation: {type_str(current)} found in {type_name(owner)}.{field}, expected: {type_str(expected)}'
    def __init__(self, field: str, owner:type[Any], expected, current):
        super().__init__(CheckerError.create(self, field, owner, expected, current))

class CheckerWarning(core.SernWarning):
    def __init__(self, field: str, owner:type[Any], expected, current):
        super().__init__(CheckerError.create(self, field, owner, expected, current))



@dataclass
class AnnoChecker(Checker):
    def _get_origin(self, typ):
        org = typing.get_origin(typ)
        if (org is Annotated) and len(args:=typing.get_args(typ))>0:
            return args[0], typing.get_origin(args[0])
        return typ, org

    def build_anno(self, typ, allow_map:bool = True):
        def map_type(typ):
            from .fixed_types import ascii_str
            if (mantyp:=retTypeManualReadable(typ)) is not core.NO_RETURN: return mantyp, ...
            if allow_map:
                typ = self._mapper(typ)
            if issubclass(typ, ascii_str): return ascii_str, False
            if issubclass(typ, ft.Array) and hasattr(typ, '_type_'): return ft.Array[typ._type_], True
            return typ, False
        typ, is_array = map_type(typ)
        if is_array==...: return typ
        typ, orgigin = self._get_origin(typ)
        if orgigin is None: return typ
        args = typing.get_args(typ)
        return orgigin[tuple(self.build_anno(arg, not is_array) for arg in args)]

    def compare(self, expected, current, allow_map:bool = True) -> bool:
        def compare_single(a,b, inv=False):
            if a is Any: return True ^ inv          
            if isinstance(a, type) and isinstance(b, type):
                return issubclass(b, a) ^ inv 
            return a!=b if inv else a==b
            
        def exclude_manual(exp, cur):
            #it's also work for generics, i.e 
            #assert isinstance(manual_type[T], ManualReadable) == True
            #assert isinstance(list[manual_type[T]], ManualReadable) == False
            #exp_man, cur_man = isinstance(exp, ManualReadable), isinstance(cur, ManualReadable)
            exp_mantyp, cur_mantyp = retTypeManualReadable(exp), retTypeManualReadable(cur)
            is_exp_man = exp_mantyp is not core.NO_RETURN
            is_cur_man = cur_mantyp is not core.NO_RETURN
            
            if not is_exp_man: exp_mantyp = exp
            if not is_cur_man: cur_mantyp = cur

            if is_exp_man or is_cur_man: return compare_single(exp_mantyp, cur_mantyp)
            return ...
        
        def exclude_array(typ):
            if isinstance(typ, type) and  issubclass(typ, ft.Array) and hasattr(typ, '_type_'):
                return ft.Array[typ._type_], True
            return typ, False

        if (ret:=exclude_manual(expected, current))!=...:return ret
        #Такая проверка запрещает мэппинг многомерных массивов (больше одного измерения)
        if allow_map: current = self._mapper(current)
        if compare_single(expected,current): return True
        (expected, _), (current, cur_is_array) = exclude_array(expected), exclude_array(current)
        (expected, exp_org), (current, cur_org) = self._get_origin(expected), self._get_origin(current)
        if compare_single(exp_org, cur_org, inv=True): return False
        if exp_org is None and cur_org is None: return compare_single(expected,current)
        exp_args, cur_args  = typing.get_args(expected), typing.get_args(current)
        if len(exp_args) != len(cur_args): return False
        return all(self.compare(exp, cur, not cur_is_array) for exp, cur in zip(exp_args, cur_args)) 

    policy:Literal['error', 'warning'] = 'warning'
    cache_size:int = 128
    _cached_comparer: Any = dataclasses.field(default=None, init=False)
    _mapper:Callable[[Any], Any] = dataclasses.field(init=False)

    def __setattr__(self, prop, val):
        if prop == 'cache_size':
            self._cached_comparer = lru_cache(self.cache_size, typed=True)(self.compare)
        super().__setattr__(prop, val)

    def configure(self, mapper:Callable[[Any], Any]):
        assert self._cached_comparer is not None
        self._mapper = mapper

    def check(self, field: str, owner:type[Any], expected, current) -> bool:
        if not (ret:=self._cached_comparer(expected, current)):
            current, expected = expected, self.build_anno(current)
            match self.policy:
                case 'warning': warn(CheckerWarning(field, owner, expected, current))
                case 'error': raise CheckerError(field, owner, expected, current)
                case _: assert_never(self.policy)
        return ret


class reader:
    CheckEOFPolicy = Literal['error', 'warning', 'silent']
    @staticmethod
    def check_eof(stream:ByteStream, eof:CheckEOFPolicy, path:PathLike | None = None) -> bool:
        pos, readed = stream.tell(), stream.read(1)
        stream.seek(pos)
        if readed != b'':
            err = f'EOF has not been reached. Pos: {pos}' + ('' if path is None else f', file: {path}') 
            match eof:
                case 'error': raise IOError(err)
                case 'warning': warn(err, BytesWarning)
                case 'silent': pass
                case _: assert_never(eof)
            return False
        return True

    @classmethod #TODO подумать над тем, что бы объявить эту функцию на уровне библиотеки
    def read_all(cls, file:ByteStream | PathLike, typ, *args, eof:CheckEOFPolicy | bool = 'warning'):
        if isinstance(eof, bool): eof = 'warning' if eof else 'silent'
        def impl(stream:ByteStream, path):
            res = cls(stream).auto_read(typ, *args)
            cls.check_eof(stream, eof, path)
            return res
        if isinstance(file, PathLikeTypes):
            with open(file, 'rb') as stream:
                return impl(stream, file)   
        else:
            return impl(file, None)

    @staticmethod
    def type_mapper(obj_or_typ):
        def impl(typ:type, mapfunc:bool):
            if not isManualReadable(typ) and not _unmapped_type_support.is_marked(typ) and FixedUtils.is_fixed_type(typ):
                return FixedUtils.fixed_to_py(typ, mapfunc)
            return (typ, lambda x:x) if mapfunc else typ
        if isinstance(obj_or_typ, type):
            return impl(obj_or_typ, False)
        else:
            return impl(type(obj_or_typ), True)[1](obj_or_typ)

    def __init__(self, file:ByteStream, checker:Checker | None = AnnoChecker()):
        self.file = file
        if checker is not None: checker.configure(self.type_mapper)
        self.checker = checker

    def _anno_read(self, hint, *args, owner:type[Any],field_name:str,readed_fields:dict[str, Any] | None = None): # hints:dict[str, Any], 
        def _auto_read(typ, *args):
            if (readed_fields is not None) and len(args)>0 and isinstance(args[0], core.KnownArg):
                args = (args[0]._access_from_fields(readed_fields), *args[1:])
            return self._auto_read(typ, *args)
        
        def check(expected, current):
            if self.checker is not None:
                self.checker.check(field_name, owner, expected, current)

        main_hint, sernas = core.AnnoUtils.handle_field_hint(hint)
        match sernas.status:
            case 'OK':
                sernas = sernas.value
                typ, nargs = core.not_none(sernas.typ, main_hint), core.not_none(sernas.read_args, args)
                offset = self.file.tell()
                ret_obj, ret_args = _auto_read(typ, *nargs)
                if sernas.read_args:
                    if ret_args: raise ValueError(f'Unnecessary arguments detected in anno, type: {typ}, unused args: {ret_args}.')
                    ret_args = args 
                map_obj = sernas.read_validator(ret_obj, core.ValidationInfo(offset, self.file.tell()-offset, field_name, owner))
                if map_obj is ret_obj:
                    check(main_hint, typ)
                return map_obj, ret_args
            case 'NotFound': return (_auto_read(main_hint, *args), check(main_hint, main_hint))[0]
            case 'Duplication': raise core.DuplicateSernAsError(field_name, owner)
            case _: assert_never(sernas.status)

        # if typing.get_origin(hint) is Annotated:
        #     hint_args = typing.get_args(hint)
        #     sernas = self.find_SernAs(hint_args[1:], owner, field_name)
        #     if sernas is None: return _auto_read(hint_args[0], *args)
        # else:
        #     return (_auto_read(hint, *args), check(hint, hint))[0]

    #fields is tuple(E1, E2, ...),
    #where E is tuple(str, args) or tuple(str,) or just str
    #args is tuple(arg1, arg2, ...) or just arg1
    def _top_fields_read(self, owner, *fields_):
        dict = {}
        args = []

        def prepare_args(args):
            map = lambda arg: arg._access(dict[arg.name]) if isinstance(arg, core.KnownArg) else arg
            return tuple(map(arg) for arg in _pack_tuple(args))

        hints = typing.get_type_hints(owner, include_extras=True)

        for field in fields_:
            field = _pack_tuple(field)
            field_name = field[0]
            cur_obj, cur_args = self._anno_read(hints[field_name], *prepare_args(field[1:]), owner=owner, field_name=field_name, readed_fields=dict)
            if cur_args: args.append(cur_args)
            if _error(cur_obj): return cur_obj, args
            dict[field_name] = cur_obj  
            # cur_dict, cur_args = self._fields_read(owner, [field_name], *prepare_args(field[1:]))
            # if cur_args: args.append(cur_args)
            # if _error(cur_dict): return cur_dict, args
            # dict[field_name] = cur_dict[field_name]   
        return dict, args

    def _fields_read(self, owner, fields_:Iterable[str], *args):
        dict = {}
        
        hints = typing.get_type_hints(owner, include_extras=True)
        
        for field_name in fields_:
            #field_type = _utils.extract_anno(hints[field_name])[0]
            #obj, args = self._auto_read(field_type, *args)
            obj, args = self._anno_read(hints[field_name], *args, owner=owner, field_name=field_name, readed_fields=dict)
            if _error(obj): return obj, args
            dict[field_name] = obj
            
        return dict, args

    def _manual_read(self, typ, *args):
        if isManualReadable(typ):
            #TODO[Закрыто] перед вызовом sern_read сверить число аргументов, и учесть что этот метод может быть classmethod
            #Note. Отказаться от идеи, что если sern_read не принимает достаточное кол-во аргументов то не вызовать его, это небезопасно, так как пользователь мог их просто забыть указать
            obj = typ.sern_read(self, *(_pack_tuple(args[0]) if args else ()))
            assert obj is not None, 'Not supported, sern_read must return not a None'
            return obj, args[1:] if not _error(obj) else args
        return None, args
 
    def _fixed_read(self, typ, *args, size: int | None = None):
        if FixedUtils.is_fixed_type(typ): 
            return self.type_mapper(FixedUtils.read_fixed(self.file, typ, size, False)), args
        else:
            return None, args

    #Поддерживаемые типы: bytes, bytearray, list[T], tuple[T,...], dict[k,v]
    def _standard_read(self, typ, *args):
        def size_args():
          assert len(args)>0 and isinstance(args[0], int), f'Size was not provided or its not int, typ was: {typ}, args was: {args}'
          return args[0], args[1:]
        
        def steps_read(ret_obj, elem_typ, size:int, args:tuple[Any, ...], assign):
            ret_args = None
            for _ in range(size): 
                cur_obj, cur_args = self._auto_read(elem_typ, *args)
                if ret_args is not None and ret_args!=cur_args:
                    raise ValueError(f'Multiple readings of the same type led to different arguments, type was {elem_typ}')
                ret_args = cur_args
                if _error(cur_obj): ret_obj = cur_obj; break
                assign(ret_obj, cur_obj)
            return ret_obj, ret_args

        if typ is bytes:
            size, args = size_args()
            return exactly_read(self.file, size), args
        if typ is bytearray:
            size, args = size_args()
            return bytearray(exactly_read(self.file, size)), args
        
        origin = typing.get_origin(typ)
        if origin is list:
            elt = typing.get_args(typ)[0]
            size, args = size_args()
            obj, args = self._fixed_read(elt, *args, size = size)
            if obj is not None: return list(obj), args
            def assign(r, v): r.append(v)
            return steps_read([], elt, size, args, assign)
        
        if origin is dict:
            kv = tuple[*typing.get_args(typ)]
            def assign(r, v): r[v[0]] = v[1]
            return steps_read({}, kv, *size_args(), assign)
        
        if origin is tuple:
            ret = []
            for field_type in typing.get_args(typ):
                obj, args = self._auto_read(field_type, *args)
                if _error(obj): return obj, args
                ret.append(obj)
            return tuple(ret), args
        
        return None, args
       
    #Поддерживаемые типы: @dataclass, typing.NamedTuple
    def _struct_read(self, typ, *args):
        def fields(typ):
            if dataclasses.is_dataclass(typ): return (fld.name for fld in dataclasses.fields(typ))
            if is_typed_namedtuple(typ): return typ._fields
            return None
        if (flds := fields(typ)) is not None:
            dict, args = self._fields_read(typ, flds, *args)
            ret = dict if _error(dict) else typ(**dict)
            return ret, args
        return None, args
    
    def _numpy_read(self, typ, *args):
        """
        Читает массив NumPy из файла, интерпретируя `typ` как аннотацию:
        `np.ndarray[ShapeType, np.dtype[Dtype]]`, где:
        - `ShapeType` - это либо **конкретная** форма (напр., `tuple[int, int]`), либо **неконкретная** (`tuple[int, ...]`).
        - `Dtype` - это либо **конкретный** тип (напр., `np.int32`), либо **неконкретный** (`Any` или `npt.NDArray` без уточнения `dtype`).
        
        Прим. `npt.NDArray` синони на `numpy.ndarray[tuple[typing.Any, ...], numpy.dtype[~_ScalarT]]`, допускающий не более одого параметра для установки `dtype`
        
        Типизация аргумента `args[0]` зависит от комбинации 'конкретности' `ShapeType` и `Dtype`
        и должен быть одного из следующих типов(показано далее с помощью аннотаций):
        1. **`int`** eсли `ShapeType` **неконкретен** или является Tuple[int], а `Dtype` **конкретен**. Пример: `9`
        2. **`tuple[tuple[int, ...]]`** eсли `ShapeType` **неконкретен** или **в точности соответствуют**, а `Dtype` **конкретен**. Пример: `((4,5),)`
        3. **`tuple[int, Dtype]`** eсли `ShapeType` **неконкретен** или является Tuple[int], а `Dtype` **неконкретен** или **в точности соответствует**. Пример: `(9, np.int32)`
        4. `tuple[tuple[int, ...], Dtype]` eсли `ShapeType` **неконкретен** или количество элементов в точности соответствуют, а `Dtype` **неконкретен** или **в точности соответствует**. Пример: `((4,5), np.int32)`
        """
        if np is None: return None, args
        #Если shape конкретный(tuple[int,]) то первый аргмент должен быть такой же формы
        #Если shape неконкретный(tuple[int,...]) то shape выводится по  первому аргументу
        def validate_shape(np_shape, arg:int | Iterator[Any]):
            shape = next(arg, None) if isinstance(arg, Iterator) else arg 
            if isinstance(shape, int):
                shape = (shape, )
            elif shape is None:
                raise TypeError('Shape is missing')
            elif not (isinstance(shape, tuple) and all(isinstance(sh, int) for sh in shape)):
                raise TypeError(f'Invalid shape: expected a tuple of integers, got {type(shape)}')
            UNCONCRETE_SHAPE = [tuple[int, ...], typing.Tuple[int, ...], typing.Any]
            assert typing.get_args(npt.NDArray)[0] in UNCONCRETE_SHAPE # type: ignore
            if np_shape not in UNCONCRETE_SHAPE:
                shorigin, shargs = typing.get_origin(np_shape), typing.get_args(np_shape)
                assert (shorigin is tuple) and all(sh is int for sh in shargs)
                if len(shape)!=len(shargs):
                    raise TypeError(f'Shape mismatch: expected {len(shargs)}, got {len(shape)}')
            return shape, arg if isinstance(arg, Iterator) else None
        
        #Если dtype неконкретный(typing.Any) то dtype выводится по второму аргументу, обязан присутствовать
        #Если dtype конкретный(np.dtype[np.int32]) то второй аргмунет должен быть таким же или отсутсовать
        def validate_dtype(np_dtype, arg: Iterator[Any] | None):
            UNCONCRETE_DTYPE = [typing.get_args(npt.NDArray)[1], np.dtype[typing.Any]] # type: ignore
            if np_dtype in UNCONCRETE_DTYPE:
                dtype = next(arg, None) if isinstance(arg, Iterator) else arg 
                if dtype is None: raise TypeError('dtype is missing')
            else:
                dtorigin, dtargs = typing.get_origin(np_dtype), typing.get_args(np_dtype)
                assert dtorigin is np.dtype and len(dtargs)==1 # type: ignore
                dtype = next(arg, None) if isinstance(arg, Iterator) else arg
                if dtype is None: 
                    dtype=dtargs[0]
                elif dtype!=dtargs[0]:
                    raise TypeError(f'Dtype mismatch: annotation requires {dtargs[0]}, but got {dtype}')
            #
            return dtype, arg if isinstance(arg, Iterator) else None
         
        def np_fromgeneric(stream, dtype, count):
            def fileno_test():
                try:
                    return callable(getattr(stream, 'fileno', None)) and (stream.fileno() or True)
                except OSError:
                    return False
            if fileno_test():
                #TODO явно проверить что было прочитано запрошенное число байт
                return np.fromfile(stream, dtype=dtype, count=count) # type: ignore
            else:
                return np.frombuffer(exactly_read(stream, count*np.dtype(dtype).itemsize), dtype=dtype, count=count) # type: ignore
            
        if typ is np.ndarray: typ = npt.NDArray # type: ignore

        if typing.get_origin(typ) is np.ndarray:
            if len(args)==0: raise ValueError('Argument was not passed for reading numpy array')
            arg, args = args[0], args[1:]
            np_shape, np_dtype = typing.get_args(typ)
            if isinstance(arg, Iterable): arg = iter(arg)
            shape, arg=validate_shape(np_shape, arg)
            dtype, arg=validate_dtype(np_dtype, arg)
            if isinstance(arg, Iterator) and (extra:=next(arg, None)) is not None:
                raise ValueError(f'Unexpected extra argument: {extra}')
            from math import prod
            return np_fromgeneric(self.file, dtype, count=prod(shape)).reshape(shape), args
        def safe_issubdtype(typ, num):
            try:
                return np.issubdtype(typ, num)
            except:
                return False
        
        if safe_issubdtype(typ, np.number) or typ == np.bool_: typ = np.dtype(typ)
        if isinstance(typ, np.dtype): return np_fromgeneric(self.file, typ, 1)[0], args
        return None, args

    def _auto_read(self, typ, *args):
        FUNCS = [self._manual_read, self._fixed_read, self._standard_read, self._struct_read, self._numpy_read]
        for func in FUNCS:
            obj, nargs = func(typ, *args)
            if obj is not None:
                return obj, nargs
        return UnsupportedType(typ), args    

    #User-end method group
    @staticmethod
    def _readcheck(typ, obj, args):
        if _error(obj): raise ValueError(f"Unable to find a suitable deserializer for {type_repr(obj.typ)}, owner is {type_repr(typ)}")
        if args: raise ValueError(f"""Unnecessary arguments detected, type: {typ}, args: {args}.
Use tuple if you need to call sern_read with multiple arguments.""")
        return obj

    def fields_read(self, owner, fields_:Iterable[str], *args):
        return self._readcheck(owner, *self._fields_read(owner, fields_, *args))

    def top_fields_read(self, owner, *fields_):
        return self._readcheck(owner, *self._top_fields_read(owner, *fields_))
    
    def auto_read(self, typ, *args):
        return self._readcheck(typ, *self._auto_read(typ, *args) )  







#TODO fields_iterator
#TODO добавить метод  в AnnoUtils - генерировать исключение при дублирование
#TOOD оператор | для SernAs
def get_fields(cls, include_extras=False):
    hints = typing.get_type_hints(cls, include_extras=include_extras)
    for name, hint in hints.items():
        if not callable(attr:=getattr(cls, name, None)) and not isinstance(attr, property):
            yield name, hint
    
#Примечение.
#Наследование от структуры и добавление полей   _fields_ = [("x", c_int), ("y", c_int)]
#1 Обеспечат констуркторы Point(x,y), и Point() 
#2 Доступ по pnt.x
#3 Не обеспечит str()
from typing import dataclass_transform
from dataclasses import field
from typing import TypeVar
_T = TypeVar('_T', bound=type)

#Note. Добавлен field, так как предпологается вариант использования - sernAs(...) | field(...)
@dataclass_transform(field_specifiers=(core.sernAs, field, core.SernAsWithDefault))
def sern_dataclass(cls:_T | None = None, **kwargs) -> Callable[[_T], _T] | _T:
    def wrap(cls:_T) -> _T:
        for name, hint in get_fields(cls, include_extras=False):
            core.AnnoUtils.sernAs_to_annotated(name, hint, cls)
        return dataclasses.dataclass(**kwargs)(cls)
    return wrap if cls is None else wrap(cls) 

@dataclass_transform(field_specifiers=(core.sernAs,))
def fixed_dataclass(cls:_T | None = None,*,
                pack:int=1, 
                endian:Literal['little','big','native'] = 'native', 
                checker:Literal['error','warning','disabled'] | bool = 'warning', 
                dataclass:bool = True, **kwargs) -> Callable[[_T], _T] | _T:
    def get_structure():
        match endian:
            case 'little': return ft.LittleEndianStructure
            case 'big': return ft.BigEndianStructure
            case 'native': return ft.Structure
            case _: assert_never(endian)

    def get_field_hint(name:str, hint, owner):
        # main_hint, sernas = core.AnnoUtils.handle_field_hint(hint)
        # match sernas.status:
        #     case 'OK': 
        #         if not (sernas := sernas.value).is_trivial: raise core.SernAsNotTrivialError()
        #         user_hint = main_hint if sernas.typ is None else sernas.typ
        #     case 'NotFound': user_hint = main_hint
        #     case 'Duplication': raise core.DuplicateSernAsError(name, owner)
        #     case _:assert_never(sernas.status)

        main_hint, sernas = core.AnnoUtils.clever_find_sernas(name, hint, owner)
        if sernas is not None:
            if not sernas.is_trivial: raise core.SernAsNotTrivialError()
            user_hint = core.not_none(sernas.typ, main_hint)
        else:
            user_hint = main_hint


        if _unmapped_type_support.is_marked(user_hint):
            raise TypeError(f'The type of {type_name(owner)}.{name} has an unmapped marked type')
        if isManualReadable(user_hint):
            raise TypeError(f'The type of {type_name(owner)}.{name} is ManualReadable and cannot be fixed')
        if (di:=getattr(owner, '__dict__', None)) and name in di:
            raise TypeError(f'{type_name(owner)}.{name} contained default value: {di[name]}')
        return main_hint, user_hint       
    
    def validate(cls):
        if isManualReadable(cls): 
            raise TypeError(f'Type {type_name(cls)} is ManualReadable and cannot be fixed')
        if any(hasattr(cls, at) for at in ['_fields_', '_pack_']):
            raise TypeError(f'Type {type_name(cls)} arleady have fields: _fields_ or _pack_')
        if not dataclass and kwargs: 
            raise TypeError('The creation of the dataclass was canceled, although the arguments were passed')
        if kwargs.get('init', False) or kwargs.get('frozen', False): 
            raise TypeError('It is not possible to create a fixed dataclass with redefined init or frozen')
    
    def get_checker():
        nonlocal checker
        if isinstance(checker, bool): checker = 'warning' if checker else 'disabled'
        match checker:
            case 'disabled': return None
            case 'error': return AnnoChecker('error')
            case 'warning':return AnnoChecker('warning')
            case _: assert_never(checker)

    def handle_fields(cls):
        field_hints = [(name, get_field_hint(name, hint, cls)) for name, hint in get_fields(cls, True)]
        retfields = [(name, user) for name, (_,user) in field_hints]

        if (ch := get_checker()) is None:
            return retfields
        
        temp = type('TempStruct', (get_structure(),), {'_fields_': retfields})()

        ch.configure(lambda x: x)
        for field_name, (main_hint,_) in field_hints:
            ch.check(field_name, cls, main_hint, type(getattr(temp, field_name)))             
        return retfields

    def wrap(cls : _T)-> _T:
        validate(cls)
        di = dict({'_fields_': handle_fields(cls), **cls.__dict__})
        if pack>0: di['_pack_'] = pack

        cls = type(f'{cls.__name__}SernFixed', (cls, get_structure()), di)
        return dataclasses.dataclass(init=False, frozen=False, **kwargs)(cls) if dataclass else cls

    return wrap if cls is None else wrap(cls) 

@dataclass_transform(field_specifiers=(core.sernAs,))
def le_fixed_dataclass(cls = None, **kwargs): return fixed_dataclass(cls, endian='little', **kwargs)
@dataclass_transform(field_specifiers=(core.sernAs,))
def be_fixed_dataclass(cls = None, **kwargs): return fixed_dataclass(cls, endian='big', **kwargs)

def fixeddata(cls = None):
    return fixed_dataclass if cls is None else fixed_dataclass()(cls)


class _unmapped_type_support:
    ATTR_NAME = '__sern_unmapped_type'
    @classmethod
    def mark(cls, typ:type):
        if hasattr(typ, cls.ATTR_NAME): raise ValueError(f'Name conflict detected, {typ}')
        if not core.FixedUtils.is_fixed_type(typ):
            raise TypeError(f'Attempt to use this decorator for a type incompatible with ctypes, {typ}')
        setattr(typ, cls.ATTR_NAME, True)
        #TODO Очень вероятно, что этот декоратор уместен только для массивов c_char*n и c_wchar*n
        return typ
    
    @classmethod
    def is_marked(cls, typ):
        return hasattr(typ, cls.ATTR_NAME)

def unmapped_type(cls):
    return _unmapped_type_support.mark(cls)