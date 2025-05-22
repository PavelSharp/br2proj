from pathlib import Path
import dataclasses
from dataclasses import dataclass, fields

import typing
from typing import Any
from typing import Annotated


from collections.abc import Iterable

import ctypes as ct

import enum
import inspect
import json
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


class _utils:
    @staticmethod
    def sizeof(obj_or_type, default=None):
        try:
            return ct.sizeof(obj_or_type)
        except TypeError:
            return default
    @classmethod
    def is_fixed_type(cls, obj_or_type):
        sz = cls.sizeof(obj_or_type, None)
        #Keep in mind that, unlike C++, python sizeof can return 0 for a type
        #that inherits from sturcture but does not introduce fields.
        #Another example: ct.c_int*0
        return False if sz is None else True
    
    @staticmethod
    def exactly_read(file, n:int):
        data = file.read(n)
        readed = len(data)
        if readed != n:
            raise EOFError(f"Expected to read {n} bytes, but got {readed} bytes.")
        return data
    
    @staticmethod
    def pack_tuple(val): return val if isinstance(val, tuple) else (val, )

    @staticmethod
    def extract_anno(hint):
        if typing.get_origin(hint) is Annotated:
            return typing.get_args(hint)
        else:
            return (hint, )
        
    def type_str(typ): 
        return typ.__name__ if isinstance(typ, type) else repr(typ)
    


class SernError:
    def __init__(self, typ): self.typ = typ
    def __str__(self): return _utils.type_str(self.typ)
    def __repr__(self):
        return f"<{type(self).__name__}: {_utils.type_str(self.typ)}>"

def _error(obj): return isinstance(obj, SernError)

@dataclass
class _top_fields_known_arg:
    name:str
    _chain:list[str] = dataclasses.field(init=False, default_factory=list)
    def _access(self, obj):
        for attr in self._chain:
            obj = getattr(obj, attr)
        return obj
    
    def __getattr__(self, name):
        self._chain.append(name)
        return self
    
known_arg = _top_fields_known_arg

class reader:
    @staticmethod
    def has_sern_read(typ): return callable(getattr(typ, "sern_read", None))
    
    @classmethod
    def read_all(cls, path:Path | str, typ, *args, must_eof=True):
        with open(path, 'rb') as file:
            res = cls(file).auto_read(typ, args)
            if must_eof and ((pos := file.tell()) or True) and file.read(1) != b'':
                from warnings import warn
                warn(f"EOF has not been reached. File: {path}, pos: {pos}", BytesWarning)
                #file.seek(pos) #It's not necessary
            return res
        
    @staticmethod
    def map_fixed_type(obj):
        #if _unmapped_type_support.is_marked(type(obj)): return obj
        #TODO Насколько это медленно?
        #class checker(ct.Structure):
        #    _fields_ = [('fl', type(obj))]
        #return obj.value if type(checker().fl)!=type(obj) else obj
        valts = (
            ct.c_byte, ct.c_ubyte, ct.c_short, ct.c_ushort,
            ct.c_int, ct.c_uint, ct.c_long, ct.c_ulong,
            ct.c_longlong, ct.c_ulonglong, ct.c_size_t, ct.c_ssize_t,
            ct.c_float, ct.c_double,
            ct.c_bool,
            ct.c_char, ct.c_wchar
        )
        if _unmapped_type_support.is_marked(type(obj)): return obj
        if type(obj) in valts: return obj.value
        if isinstance(obj, ct.Array) and issubclass(obj._type_, ct.c_char | ct.c_wchar):
            return obj.value
        return obj

    #TODO Позволить конструктор из Path|str тогда открыть файл в бинарном режиме 
    def __init__(self, file:typing.IO[bytes]):
        self.file = file

    #fields is tuple(E1, E2, ...),
    #where E is tuple(str, args) or tuple(str,) or just str
    #args is tuple(arg1, arg2, ...) or just arg1
    def _top_fields_read(self, owner, *fields_):
        dict = {}
        args = []

        def prepare_args(args):
            map = lambda arg: arg._access(dict[arg.name]) if isinstance(arg, _top_fields_known_arg) else arg
            return tuple(map(arg) for arg in _utils.pack_tuple(args))

        for field in fields_:
            field = _utils.pack_tuple(field)
            field_name = field[0]
            cur_dict, cur_args = self._fields_read(owner, [field_name], *prepare_args(field[1:]))
            if cur_args: args.append(cur_args)
            if _error(cur_dict): return cur_dict, args
            dict[field_name] = cur_dict[field_name]   
        return dict, args

    def _fields_read(self, owner, fields_:Iterable[str], *args):
        dict = {}
        
        hints = typing.get_type_hints(owner)
        
        for field_name in fields_:
            field_type = _utils.extract_anno(hints[field_name])[0]
            obj, args = self._auto_read(field_type, *args)
            if _error(obj): return obj, args
            dict[field_name] = obj
            
        return dict, args

    def _manual_read(self, typ, *args):
        if self.has_sern_read(typ):
            #TODO перед вызовом sern_read сверить число аргументов, и учесть что этот метод может быть classmethod
            #Note. Отказаться от идеи, что если sern_read не принимает достаточное кол-во аргументов то не вызовать его, это небезопасно, так как пользователь мог их просто забыть указать
            obj = typ.sern_read(self, *(_utils.pack_tuple(args[0]) if args else ()))
            assert obj is not None, "Not supported, sern_read must return not a None"
            return obj, args[1:] if not _error(obj) else args
        return None, args
    
    #@staticmethod
    #def fixed_read_map(typ):


   #def fixed_read2(self, file, typ:type[Any], *args, inform=False):
   #         def safe_sizeof():
   #         try: return ct.sizeof(typ)
   #         except TypeError: return None          

    #    if inform:
    #        if safe_sizeof(): return typ
    #        if typing.get_origin(typ) is tuple:
    #            pass

    #def fixed_read2(self, file, typ, *args, n = 1):
    #    def safe_sizeof(typ):
    #        try: return ct.sizeof(typ)
    #        except TypeError: return None              
    #    size = safe_sizeof(typ)
    #    #TODO рекурсиный обход
    #    if not size and typing.get_origin(typ) is tuple:
    #        elts = typing.get_args(typ)
    #        aa = []
    #        for elt in elts:
    #            if not safe_sizeof(elt):
    #                aa = None
    #                break
    #            
    #        class DynamicStruct(ct.Structure):
    #            _fields_ = [(f"f{i}", type(x)) for i, x in typing.get_args(typ) if isinstance(x, ct._SimpleCData)]
    '''
    def convert_to_fixed(self, file, typ, *args):
        def flat_tuple(typ):
            if typing.get_origin(typ) is tuple:
                for arg in typing.get_args(typ): yield from flat_tuple(arg)
            else:
                yield typ

        def build_tuple(typ, gen):
            if typing.get_origin(typ) is not tuple: return next(gen)
            args = typing.get_args(typ)
            return tuple(build_tuple(arg, gen) for arg in args)

        fields = []
        for ind, tp in enumerate(flat_tuple(typ)):
            if not _utils.is_fixed_type(tp): return None, args
            fields.append((f'sern_{ind}', tp))

        class FixedTuple(ct.LittleEndianStructure):
            _pack_ = 1
            _fields_ = fields
        
        size = ct.sizeof(FixedTuple)
        obj = FixedTuple.from_buffer_copy(file.read(size))       
        ret = build_tuple(typ, (getattr(obj, name) for name, _ in FixedTuple._fields_))
        return ret, args

    def fixed_read2(self, file, typ, *args, count: int | None = None):
        size = _utils.sizeof(typ)
        if size is None: return self.convert_to_fixed(file, typ, *args)
        if count is not None: typ = typ * count
        ret = typ.from_buffer_copy(file.read(size))
        return self.map_fixed_type(ret), args

    def fixed_read2(self, file, typ, *args, n: int | None = None):
        if not _utils.is_fixed_type(typ): return None, args
        if n is not None: typ = typ * n
        return self.map_fixed_type(typ.from_buffer_copy(file.read(ct.sizeof(typ)))), args


    def fixed_read(self, file, typ:type[Any], *args):
        size = 0
        try:
            size = ct.sizeof(typ)
        except TypeError:
            return None, args
        #TODO как задать порядок байтов для from_buffer_copy?
        return self.map_fixed_type(typ.from_buffer_copy(file.read(size))), args
    '''

    def _fixed_read(self, typ, *args, size: int | None = None):
        if not _utils.is_fixed_type(typ): return None, args
        if size is not None: typ = typ * size
        #TODO интегрировать поддержку numpy
        #TODO ct.sizeof -> utils.sizeof
        obj = typ.from_buffer_copy(self.file.read(ct.sizeof(typ)))
        return self.map_fixed_type(obj), args


    #Поддерживаемые типы: 
    #list[T] tuple[T,...] dict[k,v]
    #str, bytes, bytearray
    #для типов стандартной библиотеки (список кортеж строка словарь)
    
    #Для типов list[T] dict[k,v] str, bytes, bytearray
    def _standard_read(self, typ, *args):
        def size_args():
          assert len(args)>0 and isinstance(args[0], int), "Size was not provided or its not int"
          return args[0], args[1:]
        
        def steps_read(ret_obj, elem_typ, size:int, args:tuple[Any, ...], assign):
            ret_args = []
            for _ in range(size): 
                cur_obj, cur_args = self._auto_read(elem_typ, *args)
                if cur_args: ret_args.append(cur_args)
                if _error(cur_obj): ret_obj = cur_obj; break
                assign(ret_obj, cur_obj)
            return ret_obj, ret_args

        if typ is bytes:
            size, args = size_args()
            return _utils.exactly_read(self.file, size), args
        if typ is bytearray:
            size, args = size_args()
            return bytearray(_utils.exactly_read(self.file, size)), args
        
        origin = typing.get_origin(typ)
        if origin is list:
            elt = typing.get_args(typ)[0]
            size, args = size_args()
            obj, args = self._fixed_read(elt, *args, size = size)
            if obj is not None: return list(obj), args
            def assign(r, v): r.append(v)
            return steps_read([], elt, size, args, assign)
        
        if origin is dict:
            kv = typing.get_args(typ)
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
       

    def _struct_read(self, typ, *args):            
        if dataclasses.is_dataclass(typ):
            dict, args = self._fields_read(typ, (field.name for field in fields(typ)), *args)
            ret = dict if _error(dict) else typ(**dict)
            return ret, args

        return None, args
                

    def _auto_read(self, typ, *args):
        obj, args = self._manual_read(typ, *args)
        if obj is not None:
            return obj, args

        obj, args = self._fixed_read(typ, *args)
        if obj is not None:
            return obj, args

        obj, args = self._standard_read(typ, *args)
        if obj is not None:
            return obj, args

        obj, args = self._struct_read(typ, *args)
        if obj is not None:
            return obj, args

        return SernError(typ), args
    

    #User-end method group
    @staticmethod
    def _readcheck(typ, obj, args):
        if _error(obj): raise ValueError(f"Unable to find a suitable deserializer for {_utils.type_str(obj.typ)}, owner is {_utils.type_str(typ)}")
        if args: raise ValueError(f"""Unnecessary arguments detected, type: {typ}, args: {args}.
Use tuple if you need to call sern_read with multiple arguments.""")
        return obj

    def fields_read(self, owner, fields_:Iterable[str], *args):
        return self._readcheck(owner, *self._fields_read(owner, fields_, *args))

    def top_fields_read(self, owner, *fields_):
        return self._readcheck(owner, *self._top_fields_read(owner, *fields_))
    
    def auto_read(self, typ, *args):
        return self._readcheck(typ, *self._auto_read(typ, *args) )  

#Пусть есть класс-наследник от ctypes.Structure, с полями field1...fieldN
#Стандартная реализация ctypes.Structure выполняет мэппинг 
#типов некоторых полей к ближайшим аналагам языка Python, а именно:
#1. Все целочисленные c_int и т.д.(наследники исключены) -> int
#2. c_bool (наследники исключены) -> bool
#3. c_float, c_double (наследники исключены) -> float
#4. Си-строки c_char*n(и наследники), char_n -> bytes
#5. Широкие строки c_wchar*n(и наследник), c_wchar -> str
#Мэппинг для иных типов, включая массивы(ctypes.Array) не выполняется

class endian(enum.Enum):
    LITTLE = ct.LittleEndianStructure
    BIG = ct.BigEndianStructure
    NATIVE = ct.Structure

def fixeddata(cls=None, /, **kwargs):
    if cls is None:
        return lambda cls: fixeddata(cls, **kwargs)
    if reader.has_sern_read(cls): raise TypeError(f'Type {cls.__name__} cannot be fixed if it has a custom function for reading')

    pack = kwargs.pop("pack", 1)
    order = kwargs.pop("endian", endian.LITTLE).value
    cls = type(cls.__name__, (cls, order), dict(cls.__dict__))
    cls = dataclass(init=False, **kwargs)(cls)
    cls._pack_ = pack
    cls._fields_ = [(field.name, field.type) for field in fields(cls)]

    if any(_unmapped_type_support.is_marked(tp) for _, tp in cls._fields_):
        raise TypeError(f'Type {cls.__name__} cannot be fixed, since one of its fields is unmapped marked')

    return cls


class _unmapped_type_support:
    ATTR_NAME = '__sern_unmapped_type'
    @classmethod
    def mark(cls, typ:type):
        if hasattr(typ, cls.ATTR_NAME): raise ValueError(f'Name conflict detected, {typ}')
        if not _utils.is_fixed_type(typ):
            raise TypeError(f'Attempt to use this decorator for a type incompatible with ctypes, {typ}')
        setattr(typ, cls.ATTR_NAME, True)
        #TODO Очень вероятно, что этот декоратор уместен только для массивов c_char*n и c_wchar*n
        return typ
    
    @classmethod
    def is_marked(cls, typ:type):
        return hasattr(typ, cls.ATTR_NAME)

def unmapped_type(cls):
    return _unmapped_type_support.mark(cls)