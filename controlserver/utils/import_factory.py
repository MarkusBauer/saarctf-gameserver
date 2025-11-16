import importlib
import inspect
import sys
from abc import ABC
from functools import lru_cache
from pathlib import Path
from typing import Type, ParamSpec, TypeVar, Generic

P = ParamSpec("P")
T = TypeVar("T")


class ImportFactory(ABC, Generic[T]):
    base_class: Type[T]

    @classmethod
    @lru_cache()
    def get_class(cls, requested_class: str) -> Type[T]:
        cls.fix_import_path()

        module_name, class_name = requested_class.split(":", 1)
        package = cls.__module__[: cls.__module__.rindex(".")]

        module = importlib.import_module(package + "." + module_name, package=package)
        clstype = getattr(module, class_name)
        if not inspect.isclass(clstype) or not issubclass(clstype, cls.base_class):
            raise Exception(f"Class {class_name} in {package} is missing or not a {cls.base_class.__name__}")
        return clstype

    @classmethod
    @lru_cache()
    def fix_import_path(cls) -> None:
        path = str(Path(__file__).absolute().parent.parent.parent)
        if path not in sys.path:
            sys.path = [path] + sys.path
