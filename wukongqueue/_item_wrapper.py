# -*- coding: utf-8 -*-
import pickle
from typing import Any

from .utils import Unify_encoding

type_name_map = {
    bytes: b'byte',
    str: b'str',
    int: b'int',
    complex: b'complex',
    float: b'float',
    bool: b'bool',

    list: b'list',
    tuple: b'tuple',
    dict: b'dict',
    set: b'set',
    type(None): b'NoneType'
}

type_name_map_reversed = {v: k for k, v in type_name_map.items()}


# class ItemWrapped:
#     def __init__(self):
#         self.is_ok = False
#         self.err_info = ''
#         self.data_type = b''
#         self.data = b''
#         self.encoding = Unify_encoding


def item_wrapper(item: Any) -> bytes:
    return pickle.dumps(item)


def item_unwrap(item_pickled: bytes) -> Any:
    return pickle.loads(item_pickled, encoding=Unify_encoding)

# def item_wrapper(item: Any, encoding) -> ItemWrapped:
#     ret = ItemWrapped()
#
#     item_type = type(item)
#     ret.data_type = type_name_map.get(item_type)
#     if ret.data_type is None:
#         return ret
#
#     if item_type is bytes:
#         ret.data = item
#     if item_type is str:
#         ret.data = item.encode(encoding=encoding)
#     elif item_type in [int, complex, float]:
#         ret.data = str(item).encode(encoding=encoding)
#     elif item_type is bool:
#         if item is True:
#             ret.data = b'T'
#         else:
#             ret.data = b'F'
#     elif item_type in [list, tuple, dict, type(None)]:
#         if item_type is dict:
#             for k in item.keys():
#                 if type(k) is int:
#                     ret.err_info = ""
#         ret.data = json.dumps(item).encode(encoding=encoding)
#     elif item_type is set:
#         ret.data = json.dumps(list(item)).encode(encoding=encoding)
#
#     ret.is_ok = True
#     return ret
#
#
# def item_unwrap(item_wrapped: ItemWrapped) -> Any:
#     data_py_type = type_name_map_reversed.get(item_wrapped.data_type)
#     if data_py_type is bytes:
#         return item_wrapped.data
#     elif data_py_type is str:
#         return item_wrapped.data.decode(item_wrapped.encoding)
#     elif data_py_type is int:
#         return int(item_wrapped.data.decode(item_wrapped.encoding))
#     elif data_py_type is complex:
#         return complex(item_wrapped.data.decode(item_wrapped.encoding))
#     elif data_py_type is float:
#         return float(item_wrapped.data.decode(item_wrapped.encoding))
#     elif data_py_type is bool:
#         return item_wrapped.data == b'T'
#     elif data_py_type in [list, dict, tuple, set]:
#         ret = json.loads(item_wrapped.data.decode(item_wrapped.encoding))
#         if data_py_type is tuple:
#             return tuple(ret)
#         elif data_py_type is set:
#             return set(ret)
#         return ret
#     elif isinstance(None, type(None)):
#         return None
