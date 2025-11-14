import copy
import decimal
import json
import os
from types import GenericAlias, UnionType
from typing import Any, Callable

import json5

from .core import DEBUG_DS, error, warning
from .utils import sec, msec, MiB, tobool, totime, tomem, ftime, fmemory, stdopen

class Program():
    def __init__(self, prog: str = None, *args: str):
        self.prog = prog
        self.args = list(args)
        self.env: os._Environ = None

class _ModelNULLType():
    def __init_subclass__(cls):
        raise TypeError("_ModelNULLType 不能被继承，你应该直接使用 ModelNULL 常量。")
    def __copy__(self):
        return self
    def __deepcopy__(self, memo):
        return self
    def __bool__(self):
        return False
    def __eq__(self, value):
        return isinstance(value, _ModelNULLType)
    def __ne__(self, value):
        return not isinstance(value, _ModelNULLType)
    def __repr__(self):
        return "<ModelNULL>"
    def __hash__(self):
        return 0x66ccff
ModelNULL = _ModelNULLType()
class ModelTransform():
    """
    转换基类，实现为导入或导出不影响类的行为。
    """
    _method: list[tuple[type, Callable[[Any], Any]]] = []
    @classmethod
    def trans(cls, obj: Any):
        for typ, func in cls._method:
            if isinstance(obj, typ):
                if (x := func(obj)) != ModelNULL:
                    return x
        return ModelNULL
    @classmethod
    def decorate_none_to_null(cls, func: Callable[[Any], Any | None]):
        def foo(x):
            return ModelNULL if (x := func(x)) is None else x
        return foo
class ModelDirectTransform(ModelTransform):
    _method: dict[type, Callable[[Any], Any]] = {}
class SimpleModel():
    """
    初始化时会深拷贝默认值。
    不会处理所有下划线开头或在 _ignore 中的属性名，否则先通过 _alias 翻译别名再尝试操作。
    不可使用 isinstance 的类型注释请加入 _ignore 使其不被检查。（例如 typing.Optional 和 typing.Union，建议使用合并类型表达式）
    将 self._record_extra 和 self._record_invalid 设为支持 append 的容器即可打开错误记录。
    """
    _method: dict[str, ModelTransform] = {}
    _export: dict[str, ModelDirectTransform] = {}
    _alias: dict[str, str] = {}
    _ignore: set = set()
    @classmethod
    def haskey(cls, key: str):
        return key in cls.__annotations__
    @classmethod
    def get_types_of(cls, key: str) -> _ModelNULLType | tuple[Any, ...]:
        if key in cls._ignore or not cls.haskey(key):
            return ModelNULL
        if (typ := cls.__annotations__.get(key)) is None:
            return ()
        elif isinstance(typ, GenericAlias):
            return (typ.__origin__, )
        elif isinstance(typ, UnionType):
            return typ.__args__
        return (typ, )
    def __init__(self, *, record_extra = False, record_invalid = False, throw_on_extra = False, throw_on_invalid = False, **kwargs):
        self._default: dict[str, Any] = {}
        self._real: dict[str, Any] = {}
        self._record_extra: list[tuple[str, Any]] = [] if record_extra else None
        self._record_invalid: list[tuple[str, Any]] = [] if record_invalid else None
        self._throw_on_extra = throw_on_extra
        self._throw_on_invalid = throw_on_invalid
        for key in self.__class__.__annotations__:
            self._default[key] = copy.deepcopy(getattr(self, key, ModelNULL))
            setattr(self, key, ModelNULL)
        self._real.clear()
        for key, val in kwargs.items():
            if key.startswith("_"):
                raise TypeError(f"{self.__class__.__qualname__} 初始化时不支持键以下划线开头的项目 {key} = {repr(val)}")
            else:
                setattr(self, key, val)
    def record_extra(self, key: str, value, /):
        if self._record_extra is not None:
            self._record_extra.append((key, value))
        elif DEBUG_DS:
            warning(f"未记录的冗余项目 {repr(key)} = {repr(value)}")
        if self._throw_on_extra:
            raise ValueError(f"冗余项目 {repr(key)} = {repr(value)}")
    def record_invalid(self, key: str, value, /):
        if self._record_invalid is not None:
            self._record_invalid.append((key, value))
        elif DEBUG_DS:
            error(f"未记录的无效项目 {repr(key)} = {repr(value)}")
        if self._throw_on_invalid:
            raise ValueError(f"冗余项目 {repr(key)} = {repr(value)}")
    def __setattr__(self, key: str, value):
        if key.startswith("_") or key in self.__class__._ignore: # 忽略
            return super().__setattr__(key, value)
        key = self.get_translate(key)
        if (x := key.find(".")) != -1:
            rkey = key[:x]
            if (v := self.get_real(rkey)) == ModelNULL:
                tr = self.__class__._method.get(rkey, ModelNULL)
                if tr == ModelNULL:
                    self.record_invalid(key, value)
                    return
                self._real[rkey] = v = tr.trans({})
            if isinstance(v, SimpleModel):
                return setattr(v, key[x+1:], value)
            self.record_invalid(key, value)
            return
        self._real[key] = value # 记录原值
        if value == ModelNULL: # 逻辑删除
            del self._real[key]
            return super().__setattr__(key, self._default.get(key, ModelNULL))
        if (typs := self.__class__.get_types_of(key)) == ModelNULL: # 冗余项
            return self.record_extra(key, value)
        if len(typs) == 0: # 没有类型注释，忽略
            return super().__setattr__(key, value)
        for typ in typs:
            if isinstance(value, typ): # 符合要求
                return super().__setattr__(key, value)
        if (tr := self.__class__._method.get(key, ModelNULL)) != ModelNULL and (x := tr.trans(value)) != ModelNULL: # 可以转换，采用转换后的值
            return super().__setattr__(key, x)
        self.record_invalid(key, value)
        return super().__setattr__(key, self._default.get(key, ModelNULL))
    def get(self, key: str, /):
        """
        获取模型存储的值，等价于 getattr(model, key, ModelNULL)。
        """
        key = self.get_translate(key)
        return getattr(self, key, ModelNULL)
    def get_real(self, key: str, /):
        """
        获取模型实际存储的值。
        """
        key = self.get_translate(key)
        return self._real.get(key, ModelNULL)
    def get_import(self, key: str, value, /):
        """
        对于键 key，获取将 value 导入模型后的值。
        """
        key = self.get_translate(key)
        if value == ModelNULL or (typs := self.__class__.get_types_of(key)) == ModelNULL:
            return ModelNULL
        if len(typs) == 0:
            return value
        for typ in typs:
            if isinstance(value, typ):
                return value
        return ModelNULL if (tr := self.__class__._method.get(key, ModelNULL)) == ModelNULL else tr.trans(value)
    def get_export(self, key: str, val: Any = ModelNULL, /):
        """
        对于键 key，获取将模型存储的值或者 val 导出的结果。
        TODO 更丰富的导出
        """
        key = self.get_translate(key)
        if val == ModelNULL:
            if (val := self.get(key)) == ModelNULL:
                return ModelNULL
        return ModelNULL if (tr := self._export.get(key, ModelNULL)) == ModelNULL else tr.trans(val)
    def get_translate(self, key: str, /):
        """
        获取别名的翻译，如果不是别名则返回 key。
        """
        return self._alias[key] if key in self._alias else key
    def get_real_export(self, key: str, /):
        """
        对于键 key，获取将模型实际存储的值导出的结果。
        """
        key = self.get_translate(key)
        if (val := self.get_real(key)) == ModelNULL:
            return ModelNULL
        return val if (tr := self._export.get(key, ModelNULL)) == ModelNULL else tr.trans(val)
    def keys(self):
        """
        获取模型实际存储的键。
        """
        return self._real.keys()
    def items(self):
        """
        获取模型实际存储的项目。
        """
        return self._real.items()
    def isvalid(self, key: str, /):
        """
        判断 key 是否是有效的键。
        """
        return self.get_translate(key) in self.validkeys()
    def validkeys(self):
        """
        获取所有有效的键。
        """
        return self.__class__.__annotations__.keys()
    def __contains__(self, key: str):
        return key in self._real
    def __iter__(self):
        """
        迭代所有实际存储的键。
        """
        return self._real.keys().__iter__()
    # def validate(self, key: str):
    #     if not key in self._real or not hasattr(self, key):
    #         return False
    #     return self._real[key] == getattr(self, key)
    def update(self, dic: "SimpleModel | dict[str, Any]", /):
        """
        从 dic 更新模型。
        """
        if isinstance(dic, dict):
            return self.update(TestConf.from_dict(dic))
        for key in dic:
            setattr(self, key, dic.get_real(key))
    def get_extra_recursive(self, root: str = None):
        """
        递归获取已记录的冗余项目。
        """
        if root is None:
            root = ""
        else:
            root += "."
        ret = []
        for key, val in self._record_extra:
            ret.append((root + key, val))
        for key in self.validkeys():
            if self.get_real(key) != ModelNULL and isinstance(val := self.get(key), SimpleModel):
                ret += val.get_extra_recursive(root + key)
        return ret
    def get_invalid_recursive(self, root: str = None):
        """
        递归获取已记录的无效项目。
        """
        if root is None:
            root = ""
        else:
            root += "."
        ret = []
        for key, val in self._record_invalid:
            ret.append((root + key, val))
        for key in self.validkeys():
            if self.get_real(key) != ModelNULL and isinstance(val := self.get(key), SimpleModel):
                ret += val.get_invalid_recursive(root + key)
        return ret
    @classmethod
    def from_dict(cls, dic: dict[str, Any], /, record_extra = False, record_invalid = False, strict = True):
        ret = cls()
        if record_extra:
            ret._record_extra = []
        if record_invalid:
            ret._record_invalid = []
        for key, val in dic.items():
            if strict and key.startswith("_"): # 避免攻击
                ret.record_invalid(key, val)
                continue
            setattr(ret, key, val)
        return ret
    @classmethod
    def from_model(cls, dic: "SimpleModel", /, record_extra = False, record_invalid = False):
        ret = cls()
        if record_extra:
            ret._record_extra = []
        if record_invalid:
            ret._record_invalid = []
        for key, val in dic.items():
            setattr(ret, key, val)
        return ret

def ModelMakeTransformToModel(cls: type[SimpleModel], /, record_extra = False, record_invalid = False):
    class A(ModelTransform):
        _method = [(dict, lambda dic: cls.from_dict(dic, record_extra, record_invalid))]
    return A
class ModelTransformToBool(ModelTransform):
    _method = [(str, ModelTransform.decorate_none_to_null(tobool))]
class ModelTransformToTime(ModelTransform):
    _method = [(str, ModelTransform.decorate_none_to_null(totime))]
class ModelTransformToMemory(ModelTransform):
    _method = [(str, ModelTransform.decorate_none_to_null(tomem))]
class ModelTransformFmtTime(ModelTransform):
    _method = [(int, ftime)]
class ModelTransformFmtMemory(ModelTransform):
    _method = [(int, fmemory)]

# TODO
class LangTag(SimpleModel):
    pass

class Limit(SimpleModel):
    _method = {
        "time": ModelTransformToTime,
        "time_redundancy": ModelTransformToTime,
        "memory": ModelTransformToMemory,
        "memory_redundancy": ModelTransformToMemory,
        "stack": ModelTransformToMemory,
        "fsize": ModelTransformToMemory,
    }
    _export = {
        "time": ModelTransformFmtTime,
        "time_redundancy": ModelTransformFmtTime,
        "memory": ModelTransformFmtMemory,
        "memory_redundancy": ModelTransformFmtMemory,
        "stack": ModelTransformFmtMemory,
        "fsize": ModelTransformFmtMemory,
    }
    time: int = sec(1)
    time_redundancy: int = msec(200)
    memory: int = MiB(512)
    memory_redundancy: int = MiB(4)
    stack: int = -1
    fsize: int = MiB(64)
    def tl(self, t: int):
        return t > self.time
    def ml(self, n: int):
        return n > self.memory
    def cmdline(self):
        return (self.time+self.time_redundancy, self.memory+self.memory_redundancy, self.memory+self.memory_redundancy if self.stack is None else self.stack, self.fsize)
class TestConf(SimpleModel):
    _method = {
        "limit": ModelMakeTransformToModel(Limit, True, True),
    }
    _alias = {
        "time": "limit.time",
        "time_redundancy": "limit.time_redundancy",
        "memory": "limit.memory",
        "memory_redundancy": "limit.memory_redundancy",
        "stack": "limit.stack",
        "fsize": "limit.fsize",
    }
    limit: Limit = Limit(record_extra=True, record_invalid=True)
    keep: bool = False
class JudgeConf(SimpleModel):
    class _CheckerConf(SimpleModel):
        _method = {
            "limit": ModelMakeTransformToModel(Limit, True, True),
        }
        limit: Limit = Limit(record_extra=True, record_invalid=True)
        safe: bool = False
        lang: str = "c++14:O2"
    class _InteractorConf(SimpleModel):
        safe: bool = False
        lang: str = "c++14:O2"
    _method = {
        "checker_conf": ModelMakeTransformToModel(_CheckerConf, True, True),
        "interactor_conf": ModelMakeTransformToModel(_InteractorConf, True, True),
    }
    name: str = None
    checker: Program | str | None = None
    checker_backup: str = None
    checker_conf: _CheckerConf = _CheckerConf(record_extra=True, record_invalid=True)
    interactor: Program | str | None = None
    interactor_backup: str = None
    interactor_conf: _InteractorConf = _InteractorConf(record_extra=True, record_invalid=True)
    graders: list[str] = []
    headers: list[str] = []
    additional: list[str] = []
    retry: int = 0
def _read_conf(path: str):
    with stdopen(path) as file:
        try:
            data = json5.load(file)
        except json.JSONDecodeError as err:
            error(err, True)
            return
    if isinstance(data, dict):
        return data
    error(f"测试点配置文件 {repr(path)} 无效：数据类型不是字典。", True)
def read_test_conf(path: str):
    if (data := _read_conf(path)) is None:
        return
    ret = TestConf.from_dict(data, True, True)
    for key, val in ret._record_extra:
        warning(f"测试点配置文件 {repr(path)} 中有冗余的项目 {key} = {repr(val)}", True)
    for key, val in ret._record_invalid:
        error(f"测试点配置文件 {repr(path)} 中有无法解析的项目 {key} = {repr(val)}", True)
    return ret
def read_judge_conf(path: str):
    if (data := _read_conf(path)) is None:
        return
    ret = JudgeConf.from_dict(data, True, True)
    for key, val in ret.get_extra_recursive():
        warning(f"评测配置文件 {repr(path)} 中有冗余的项目 {key} = {repr(val)}", True)
    for key, val in ret.get_invalid_recursive():
        error(f"评测配置文件 {repr(path)} 中有无法解析的项目 {key} = {repr(val)}", True)
    # TODO 更多检查
    return ret
class Verdict():
    def __init__(self, verdict: str = "", tm: int = 0, mem: int = 0, stat: int = 0, msg: str = "", score: decimal.Decimal = None):
        self.verdict = verdict
        self.tm = tm
        self.mem = mem
        self.stat = stat
        self.msg = msg
        self.score = score
    def __repr__(self):
        return f"Verdict({self.verdict}, {ftime(self.tm)}, {fmemory(self.mem)}, stat={self.stat}, msg={repr(self.msg)})"
class Test():
    def __init__(self, tests: list[tuple[str, str]] = None, conf: TestConf = None):
        self.tests = [] if tests is None else tests
        self.conf = TestConf() if conf is None else conf
        self.result: list[Verdict] = []
