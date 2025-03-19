import dataclasses
import json
import enum
import ctypes as ct

#********************************
#jprint api for convenient debugging output
#********************************
#1. Если строковое предтсавление структуры(словоря) не превышает
#width количесвта символов то форматирование однострочное.
#Например форматировать точку намного удобнее в строку
#Прим. Python допускает хранение разных типов в списке
#2. При форматирование списка не добавлять новые строки между элементами
#а вместо это вызывать функцию форматиовоания для элемента
#если элементу понадобится он сам перейдет на новую строку
#3. Вместе с ключом можно выводить но некогда не выодить тип для эл-тов массива

#1. Правила форматирования словарей
#1.1 Обойти все элементы словаря и если накопленная длина превосходит лимит то вывод многострочный иначе однострочный
#2. Правила форматирования списков
#OLD 2.1 Если список состоит из элементов одного типа и каждый из однострочный и каждый из них не нрушает лимит  то по окончанию его обхода принять решения либо все его элементы выводить с разделителем ", " либо \n
#2.1 
#2.2 Если список состоит из разнотипных элементов то допустим смешанный режим - вывод через ", " и "\n"
#2.3 Если вывод очередного элемента списка превзойдет лимит то от вывода этого и всех последующих элементов откзаться, а вместо это написать "...(n)", n - общее число элементов
#3. Идеи для улучшения
#3.1 Есть глобальный режим отвечающий за вывод названия ключей - либо в кавычках либо без 
#3.2 При конструирование кодировщика дополнительным парамтром передаётся список типов словарное представление которых будет без ключей
#3.3 При констуирование для каждого типа можно задать режим вывода - однострочный многострочный или авто
#3.1+3.2+3.3 == 
#3.1 Глобальная переменная отвечающая за вывод ключей по умолчанию и за многострочность
#3.2 Принять словарь типов: режим вывода ключей и политика вывода 
#режим вывода ключей = (в кавычках, без кавычек, отключено)
#политика вывода = (авто, однострочная, многотрочная)
#[политика вывода, ВОПРОСЫ] dict_total_lim=None, list_total_lim=None
# гарантия однострочного вывода, что уже конкурирует с indent=0 

#3.4 [СДЕЛАНО] Лимиты передовать при конструировании
#3.5 Если очередной тип был выведен в многострочнм режиме то в начала добавить названия типа
#3.6 [ОТКАЗАТЬСЯ] Кортежи выводить как списки но с круглыми скобками

#Особое примечание, возможно пересмотреть тактику, так как генерация только валидных json позволит их удобно просматривать с функцией сворачивания в редакторах
#dict list|tuple

JKey = enum.Enum('JKey', 'QUOTED UNQUOTED HIDE')
JValue = enum.Enum('JValue', 'AUTO SINGLELINE MULTILINE')

class DebugJSONEncoder(json.JSONEncoder):
    def __init__(self, *args, **kwargs):
        kwargs['indent'] = kwargs.get('indent') or 4 #TODO что насчет нуля? Документация по json допускает здесь None
        self.dict_total_lim = kwargs.pop('dict_total_lim', 30)
        self.list_per_lim = kwargs.pop('list_per_lim', 100)
        self.list_total_lim = kwargs.pop('list_total_lim', None)
        self.jkey = kwargs.pop('jkey', JKey.QUOTED)
        if not isinstance(self.jkey, JKey):
            self.jkey = JKey[self.jkey]

        super().__init__(*args, **kwargs)
        self.cur_indent = 0

    def default(self, o):
        if dataclasses.is_dataclass(type(o)):
            return dataclasses.asdict(o)
        if isinstance(o, ct.Array | bytes | bytearray): #TODO vs iteratable
            return list(o)
        else:
            return str(o) #special hack
        return super().default(o)
    
    def encode(self, o): 
        return self._encode(o)[0]
    def iterencode(self, o, **kwargs):
        return self.encode(o)

    @staticmethod
    def pair(s:str): return s, len(s)

    @staticmethod
    def is_limit(sz:int, lim):
        return sz>lim if lim else False 
    
    def _base_encode(self, o):
        #Special hack to avoid endless recursion
        return self.pair(''.join(super().iterencode(o)))

    def _encode(self, o):
        if callable(getattr(type(o), "sern_jwrite", None)):
            return self._base_encode(o.sern_jwrite())
        if isinstance(o, dict):
            return self._dict_encode(o)
        if isinstance(o, list | tuple):
            return self._list_encode(o)
        if isinstance(o, float | int | bool):
            return self._num_encode(o)
        if isinstance(o, str) | (o is None):
            return self._base_encode(o)
        return self._encode(self.default(o))

    def _num_encode(self, o: float | int | bool):
        return self.pair(format(o, 'g')) if isinstance(o, float) else self._base_encode(o)

    def _list_encode(self, o:list | tuple):
        size = 0
        out = "["
        ending = ''
        first_ml = False
        prev_ml = True
        isf = True

        self.cur_indent += 1
        for ind, el in enumerate(o):
            val, vsz = self._encode(el)
            size += vsz
            sep = ('' if isf else ',') + ('' if prev_ml else ' ')

            if self.is_limit(size, self.list_total_lim): #size>self.LIST_TOTAL_LIMIT: 
                ending = f'...({ind}/{len(o)})'; break; 
            
            if '\n' in val or self.is_limit(vsz, self.list_per_lim): #vsz>self.LIST_PER_LIMIT:
                sep += '\n' + self.do_indent()
                first_ml |= isf
                prev_ml = True
            else:
                prev_ml = False
            out += sep + val
            isf = False

        if ending:
            if prev_ml and not isf: sep += '\n'+self.do_indent()
            out+=sep + ending
        self.cur_indent -= 1

        if first_ml: out+='\n'+self.do_indent()
        out+=']'
        return out, size
    
    def _encode_key(self, o, jkey = None):
        valid_keys = (str, int, float,bool, type(None))
        if not isinstance(o, valid_keys):
            if self.skipkeys: return None,None
            raise ValueError(f"Key {type(o)} is not valid type")
        if jkey is None: jkey = self.jkey
        ret = ''
        match jkey:
            case JKey.QUOTED:
                ret = self.encode(o)+self.key_separator
            case JKey.UNQUOTED:
                ks = self.encode(o)
                if (ks.startswith('"') and ks.endswith('"')):
                    ks = ks[1:-1]
                ret = ks + self.key_separator
            case JKey.HIDE:
                ret = ''
            case _:
                raise ValueError(f"Unkown key: {jkey}")
        return self.pair(ret)


    def _dict_encode(self, o:dict):
        size = 0
        lines = []

        self.cur_indent += 1
        for k, v in o.items():
            ks, ksz = self._encode_key(k)
            if ksz is None: continue
            vs, vsz = self._encode(v)
            size += ksz + vsz
            lines.append((f"{ks}{vs}", self.cur_indent))
        self.cur_indent -= 1

        out = ""
        if not self.is_limit(size, self.dict_total_lim): #size<=self.DICT_TOTAL_LIMIT
             out = '{' + ", ".join(map(lambda x:x[0], lines)) + '}'
        else:
            out = ',\n'.join(f"{self.do_indent(ind)}{line}" for line, ind in lines)
            out = '{\n'+out+'\n'+self.do_indent()+'}'

        return out, size

    def do_indent(self, ind = None) -> str:
        if ind is None: ind = self.cur_indent
        if isinstance(self.indent, int):
            return ind * self.indent * ' '
        elif isinstance(self.indent, str):
            return ind * self.indent
        else:
            raise ValueError(f"Unexpected indent type: {type(self.indent)}")

def _jprintt(obj, **kwargs ):
    kwargs.setdefault('dict_total_lim', 30)
    kwargs.setdefault('list_per_lim', 100)
    kwargs.setdefault('list_total_lim', 12000)
    kwargs.setdefault('jkey', JKey.UNQUOTED)
    kwargs.setdefault('cls', DebugJSONEncoder)
    assert issubclass(kwargs['cls'], DebugJSONEncoder)

    print(json.dumps(obj, **kwargs))

#TODO специальный аргумент для дозаписи в файл(append = True?)
#TODO специальный аргумент для установки точности форматирования вещественных чисел(затем посмотреть ещё раз на анимацию WW_BONE_CRUSHER_MAIN)
def _jprintf(o, **kwargs):
    #Note. Параметры сконфигурированы по умолчанию так, что бы был порожден корректный json, так его удобной просматривать в редакторах, за счет функций сворчаивания блоков  
    kwargs.setdefault('dict_total_lim', 30)
    kwargs.setdefault('list_per_lim', 100)
    kwargs.setdefault('list_total_lim', None)
    kwargs.setdefault('jkey', JKey.QUOTED)
    kwargs.setdefault('cls', DebugJSONEncoder)
    assert issubclass(kwargs['cls'], DebugJSONEncoder)

    with open(kwargs.pop('path'), 'w') as f:
        json.dump(o, f, **kwargs)

def jprint(o, **kwargs):
    return _jprintf(o, **kwargs) if 'path' in kwargs else _jprintt(o, **kwargs)
