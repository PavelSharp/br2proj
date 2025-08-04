import importlib
from types import ModuleType
import ctypes as ct
import typing
from typing import Callable, Protocol, runtime_checkable, Any, NamedTuple, Literal, assert_never, Annotated
from dataclasses import dataclass, field
from functools import lru_cache
from warnings import warn
from collections.abc import Mapping, Iterable, Iterator
import inspect

def try_import_lib(*modules:str, min_version: tuple[int, ...] | None = None, allow_partical_none:bool = False) -> list[ModuleType | None]:
    parse_version = lambda ver: tuple(map(int, ver.split('.')))
    ret = []
    for name in modules:
        try:
            module = importlib.import_module(name)
            if (min_version is not None) and (parse_version(module.__version__)<min_version):
                raise ValueError(f'Unsupported version for {name}, excpected as min {min_version}')
        except ImportError:
            module = None
            if len(ret)>0 and (ret[-1] is not None) and not allow_partical_none:
                raise
        ret.append(module)
    return ret

def not_none(obj, default): return default if obj is None else obj
def type_name(obj_or_type): return getattr(obj_or_type if isinstance(obj_or_type, type) else type(obj_or_type), '__name__')
def type_repr(typ):  return typ.__name__ if isinstance(typ, type) else repr(typ)
def type_str(typ):  return typ.__name__ if isinstance(typ, type) else str(typ)

def is_typed_namedtuple(typ:type[Any]) -> bool:
    return (isinstance(typ, type) and issubclass(typ, tuple) 
        and hasattr(typ, '_fields') and hasattr(typ, '__annotations__') 
        and (typ._fields ==  tuple(typ.__annotations__.keys())))

def exactly_read(stream, n:int):
    data = stream.read(n)
    if (readed:=len(data)) != n:
        raise EOFError(f"Expected to read {n} bytes, but got {readed} bytes.")
    return data

NO_RETURN = object() #Means that the return type is not annotated.
def methodReturnType(owner:type[Any], method_name:str, localns: Mapping[str, object] | None = None):
    method = getattr(owner, method_name, None)
    assert callable(method), f"{type_name(owner)}.{method_name} is not method"
    typ = inspect.get_annotations(method, eval_str=False).get('return', NO_RETURN)
    if typ is NO_RETURN: return NO_RETURN

    localns = dict(localns) if localns else {}
    if (nm:=type_name(owner)) not in localns:
        localns[nm] = owner
    glob = getattr(method, '__globals__', {})        
    def resolve_generic(typ):        
        if isinstance(typ, str):
            return eval(typ, glob, localns)
        if (origin:=typing.get_origin(typ)) is not None:
            return origin[tuple(resolve_generic(arg) for arg in typing.get_args(typ))]
        else: return typ
    return resolve_generic(typ)

class FixedUtils:
    @classmethod
    def sizeof(cls, obj_or_type, default=None):
        def has_callable(obj, *names):
            return all(callable(getattr(obj, name, None)) for name in names )
        def maybe_sizeof(typ):
            return issubclass(typ, (ct._SimpleCData, ct.Array, ct.Structure, ct.Union))
        
        typ = obj_or_type if isinstance(obj_or_type, type) else type(obj_or_type)
        if maybe_sizeof(typ) or has_callable(typ, 'from_buffer', 'from_buffer_copy', 'from_address'):
            #We need to use try/except for cases like obj_or_type=ct.Array - base class that doesn't know the length
            try: return ct.sizeof(obj_or_type) 
            except TypeError: return default
        else:
            return default
        
    @classmethod
    def is_fixed_type(cls, obj_or_type):
        sz = cls.sizeof(obj_or_type, None)
        #Keep in mind that, unlike C++, python sizeof can return 0 for a type
        #that inherits from sturcture but does not introduce fields.
        #Another example: ct.c_int*0
        return False if sz is None else True

    @staticmethod
    @lru_cache
    def _cached_fixed_to_py(typ:type[Any]) -> type[Any]:
        class checker(ct.Structure):
            _fields_ = [('fl', typ)]
        return type(checker().fl)

#Пусть есть класс-наследник от ctypes.Structure, с полями field1...fieldN
#Стандартная реализация ctypes.Structure выполняет мэппинг 
#типов некоторых полей к ближайшим аналагам языка Python, а именно:
#1. Все целочисленные c_int и т.д.(наследники исключены) -> int
#2. c_bool (наследники исключены) -> bool
#3. c_float, c_double (наследники исключены) -> float
#4. Си-строки c_char*n(и наследники), char_n -> bytes
#5. Широкие строки c_wchar*n(и наследник), c_wchar -> str
#Мэппинг для иных типов, включая массивы(ctypes.Array) не выполняется
#Пусть дан массив ctype*count, тогда при обращение по индексу мэппинг не выполняется если:
#Для всех наследников, напр: type((c_int32_child * 5)()[0]) == c_int32_child
    @classmethod
    def fixed_to_py(cls, typ:type[Any], mapfunc:bool = False) -> type[Any] | tuple[type[Any], Callable[[Any], Any]]:
        def mapped_type(typ):
            if issubclass(typ, ct.Structure): return typ
            if issubclass(typ, ct.Array):
                if issubclass(typ._type_, ct.c_char): return bytes
                if issubclass(typ._type_, ct.c_wchar): return str
                return typ
            return cls._cached_fixed_to_py(typ)

        ret_typ=mapped_type(typ)
        def map_func(x):
            assert type(v := x.value)==ret_typ
            return v
        if mapfunc:return ret_typ, map_func if typ!=ret_typ else (lambda x:x)
        else: return ret_typ

    # @classmethod
    # def fixed_to_py(cls, obj) -> Any:
    #     if isinstance(obj, ct.Structure): return obj
    #     if isinstance(obj, ct.Array): return obj.value if issubclass(obj._type_, ct.c_char | ct.c_wchar) else obj
    #     @lru_cache
    #     def test(tp):
    #         class checker(ct.Structure):
    #             _fields_ = [('fl', tp)]
    #         return type(checker().fl)
    #     return obj.value if test(type(obj))!=type(obj) else obj
    
    @classmethod
    def tobytes(cls, obj) -> bytes:
        return ct.string_at(ct.addressof(obj), ct.sizeof(obj))
    
    @classmethod
    def frombytes(cls, typ, bytes:bytes, map:bool = False): 
        ret = typ.from_buffer_copy(bytes)
        return ret.value if map else ret

    @classmethod
    def frombytes_inplace(cls, typ, bytes:bytes, map:bool = False): 
        ret = typ.from_buffer(bytes)
        return ret.value if map else ret

    @classmethod
    def read_fixed(cls, stream, typ, count: int | None = None, allow_mapping = True):
        if count is not None: typ = typ * count
        obj = typ.from_buffer_copy(exactly_read(stream, ct.sizeof(typ)))
        return obj.value if allow_mapping and cls.fixed_to_py(type(obj))!=type(obj) else obj


class SernException(Exception):
    pass

class SernWarning(UserWarning):
    pass

class DuplicateSernAsError(SernException):
    def __init__(self, field: str, owner: type):
        super().__init__(f'Duplicated annotation found in {type_name(owner)}.{field}')
        self.field, self.owner = field, owner

class SernAsNotTrivialError(SernException):
    def __init__(self):
        super().__init__('A trivial SernAs was expected, which can only contain a reflected type')


class ValidationInfo(NamedTuple):
    offset:int
    length:int
    field_name:str
    typ:type[Any]

class ValidationError(SernException):
    @staticmethod
    def format_message(msg:str, info:ValidationInfo):
        space = ' ' if len(msg)>0 else ''
        return f'{msg}{space}Offset: {info.offset}, length: {info.length}, field: {info.field_name}, type: {type_name(info.typ)}'
    
    def __init__(self, message:str, info:ValidationInfo):            
        super().__init__(self.format_message(message, info))
        self.info = info

class ValidationWarning(SernWarning):
    def __init__(self, message: str, info:ValidationInfo):
        super().__init__(ValidationError.format_message(message, info))
        self.info = info


@runtime_checkable
class Validator(Protocol):
    def __call__(self, val, info:ValidationInfo):
        raise NotImplementedError()

class FuncValidator(NamedTuple):
    LEVELS = Literal['error', 'warning']
    FUNC_TYPE = Callable[[Any], bool | tuple[bool, Any]]
    @staticmethod
    def do_error(msg:str, info:ValidationInfo, level:LEVELS):
        match level:
            case 'error': raise ValidationError(msg, info)
            case 'warning': warn(ValidationWarning(msg, info))
            case _:assert_never(level)

    func:FUNC_TYPE
    msg:str | None = None
    level:LEVELS = 'error'

    def call_func(self, val) -> tuple[bool, Any]:
        obj = self.func(val)
        if isinstance(obj,bool): return (obj,val)
        elif isinstance(obj, tuple) and len(obj)==2 and isinstance(obj[0], bool): return obj
        else: raise TypeError(f'Inncorrect type for validator function, type was: {type(obj)}')

    def __call__(self, val, info:ValidationInfo):
        if not (msg:=self.msg): msg = '{} was not expected.'
        ok, res = self.call_func(val)
        if not ok: self.do_error(msg.format(val), info, self.level)
        return res
    
    def __or__(self, other: 'FuncValidator') -> 'FuncValidator':
        def chain(val):
            ok, res = self.call_func(val)
            return other.func(res) if ok else (False, val)
        return FuncValidator(chain, msg=other.msg, level=other.level)
    
    def and_then(self, other: 'FuncValidator') -> 'FuncValidator':
        return self | other 

    def __bool__(self):
        return self is not TRIVIAL_VALIDATOR
        
#class TrivialValidator:
#    def __call__(self, val, info:ValidationInfo): return val
#    def __bool__(self): return False
TRIVIAL_VALIDATOR = FuncValidator(lambda _:True)

class _Validators(NamedTuple):
    level:FuncValidator.LEVELS
    validator:FuncValidator | None = None
    def __call__(self, val, info:ValidationInfo):
        if self.validator is None: raise ValueError('Validator was not set')
        return self.validator(val, info)

    def func(self, func:FuncValidator.FUNC_TYPE, msg:str | None = None):
        concat = lambda a,b: b if a is None else a | b
        return _Validators(self.level, concat(self.validator, FuncValidator(func, msg, self.level)))

    def map(self, transform:Callable[[Any], Any], msg = None):
        return self.func(lambda x: (True, transform(x)), msg)
    
    def try_map(self, transform:Callable[[Any], Any], msg = None):
        def trans(x):
            try:
                return True, transform(x)
            except:
                return False, None
        return self.func(trans, msg)

    def check(self, test:Callable[[Any], bool], msg = None):
        return self.func(lambda x: (test(x), x), msg)

    def const(self, expected):
        return self.func(lambda x: x==expected, f'Expected {expected}, got {{}}.')
    
    def range(self, *,min = None, max = None):
        if min is not None and max is not None:
            return self.func(lambda x: min <= x <= max, f'Expected value in range [{min}, {max}], got {{}}.')  
        elif min is not None:
            return self.func(lambda x: min <= x, f'Expected a value not less than {min}, got {{}}.')
        elif max is not None:
            return self.func(lambda x: x <= max, f'Expected a value not greater than {max}, got {{}}.')
        else:
            return self.func(lambda _: True)


WarnValidators = _Validators('warning')
ErrorValidators = _Validators('error')
Validators =  _Validators('error')

@dataclass
class KnownArg:
    name:str
    _chain:list[str] = field(init=False, default_factory=list)
    def _access(self, obj):    
        for attr in self._chain:
            obj = getattr(obj, attr)
        return obj
    def _access_from_fields(self, fields:dict[str, Any]):
        #TODO бросить исключение если нет поля
        return self._access(fields[self.name])
    
    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name) #Может возникать сложный конфликт с отладчиком, 
            #который пытеются обратиться к внутренним полям(__iter__). Ограничем такой доступ, но это - не лучшее решение       
        self._chain.append(name)
        return self

_VALIDATOR_TYPE = Validator | tuple[Any, ...] | None
_ARGS_TYPE = Iterable[Any] | None

class SernAs(NamedTuple):
    typ:type[Any] | None
    
    read_args:_ARGS_TYPE
    write_args:_ARGS_TYPE

    read_validator: Validator
    write_validator: Validator
    
    @property
    def is_trivial(self): #TODO typ не должен быть ManualReadable
        return not (self.read_args or self.write_args or self.read_validator or self.write_validator)
    
    def default(self, other:Any) -> Any: return SernAsWithDefault(self,other)
    def __or__(self, other: Any) -> Any: return self.default(other)
        
class SernAsWithDefault(NamedTuple):
    sernas:SernAs
    default:Any

_NO_ARGUMENT = object()
#TODO write_validator должен получить self текущего объекта. (Например, сверить длину списка с его количесвтом, которое может быть задано в предыдущем поле)
#Сделать ли read_validator двух параметровым - второй параметр - текущий словарь с прочитанными полями?
#Note. Не добавлять параметры с именами: https://typing.python.org/en/latest/spec/dataclasses.html#field-specifier-parameters
def sernAs( typ:type[Any] | None = None,*,
            validator:_VALIDATOR_TYPE = None,
            rvalidator: _VALIDATOR_TYPE = None, wvalidator: _VALIDATOR_TYPE = None,
            args:_ARGS_TYPE = None,
            rargs:_ARGS_TYPE = None, wargs:_ARGS_TYPE = None,
            rarg:Any = _NO_ARGUMENT, warg:Any = _NO_ARGUMENT
            ) -> Any: #Any is special hack to avoid type checking
        
        def to_args(args:_ARGS_TYPE, arg:Any):
            if args is not None and arg is not _NO_ARGUMENT:
                raise ValueError(f'SernAs can not be initialized, since many and signle arguments were passed')
            if args is not None: return args
            if arg is not _NO_ARGUMENT: return (arg,)
            return None

        def choose(single, read, write, name:str):
            single_mode, rw_mode = (single is not None), (read is not None or write is not None)
            if single_mode and rw_mode:
                raise ValueError(f'SernAs can only be initialized with only one {name} or with read/write {name}s')
            if single_mode: return single, single
            elif rw_mode: return read, write
            return None, None
        
        def normalizev(v):
            if v is None: return TRIVIAL_VALIDATOR
            elif type(v)==tuple: return FuncValidator(*v)
            else: return v
        
        return SernAs(typ,  *choose(args, to_args(rargs, rarg), to_args(wargs, warg), 'argument'),
                      *map(normalizev, choose(validator, rvalidator, wvalidator, 'validator')))

class AnnoUtils:
    class ErrorResult(NamedTuple):
        status: Literal['NotFound', 'Duplication']

    class OKResult(NamedTuple):
        value: SernAs
        status: Literal['OK'] = 'OK'

    FoundResult = ErrorResult | OKResult

    @classmethod
    def find_sern_as(cls, anno_args:Iterable[Any]) -> FoundResult:
        gen = (arg for arg in anno_args if isinstance(arg, SernAs))
        if (ret := next(gen, None)) is not None:
            if next(gen, None) is not None:
                return cls.ErrorResult('Duplication')
            return cls.OKResult(ret)
        else:
            return cls.ErrorResult('NotFound')
    
    @classmethod
    def handle_field_hint(cls, hint) -> tuple[Any, FoundResult]:
        if typing.get_origin(hint) is Annotated:
            args = typing.get_args(hint)
            return args[0], cls.find_sern_as(args[1:])
        return hint, cls.ErrorResult('NotFound')
            
    @classmethod
    def sernAs_to_annotated(cls, name:str, hint, owner) -> SernAs | None:
        def get_annotated(hint, sernas) -> Annotated:
            if typing.get_origin(hint) is Annotated:
                return Annotated[*typing.get_args(hint), sernas]
            else:
                return Annotated[hint, sernas]
            
        sernas = getattr(owner, name, None)
        if isinstance(sernas, SernAs):
            owner.__annotations__[name] = get_annotated(hint, sernas)
            delattr(owner, name)
            return sernas
        elif isinstance(sernas, SernAsWithDefault):
            owner.__annotations__[name] = get_annotated(hint, sernas)
            setattr(owner, name, sernas.default)
            return sernas.sernas
        return None

    @classmethod
    def clever_find_sernas(cls, name:str, hint, owner) -> tuple[Any, SernAs | None]:
        sernas = cls.sernAs_to_annotated(name, hint, owner)
        duberr = lambda: DuplicateSernAsError(name, owner)

        if sernas is not None:
            main_hint, found_res = cls.handle_field_hint(hint)
            match found_res.status:
                case 'Duplication': raise duberr()
                case 'NotFound': return main_hint, sernas
                case 'OK': raise duberr()
                case _:assert_never(found_res.status)
        else:
            main_hint, found_res = cls.handle_field_hint(hint)
            match found_res.status:
                case 'Duplication': raise duberr()
                case 'NotFound': return main_hint, None
                case 'OK': return main_hint, found_res.value
                case _:assert_never(found_res.status)