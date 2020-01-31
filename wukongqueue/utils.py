# -*- coding: utf-8 -*-

import hashlib
import logging
import sys
import threading

Unify_encoding = "utf-8"


class helper:
    """used by WuKongQueueClient and WuKongQueue"""

    def __init__(self, inst):
        self.inst = inst

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return self.inst.__exit__(exc_type, exc_val, exc_tb)


def new_thread(f, kw={}):
    t = threading.Thread(target=f, kwargs=kw)
    t.setDaemon(True)
    t.start()


def singleton(f):
    """used only by get_logger()"""
    _inst = {}

    def w(*args):
        self = args[0]
        key = ".".join([self.__module__, self.__class__.__name__])
        inst = _inst.get(key)
        if inst:
            return inst
        _inst[key] = f(*args)
        return _inst[key]

    return w


@singleton
def get_logger(self, level) -> logging.Logger:
    name = ".".join([self.__module__, self.__class__.__name__])
    logger = logging.getLogger(name)
    formatter = logging.Formatter(
        "%(asctime)s %(name)s %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    h = logging.StreamHandler(stream=sys.stderr)
    h.setLevel(level)
    h.setFormatter(formatter)
    logger.addHandler(h)
    logger.setLevel(level)
    return logger


def md5(msg: bytes):
    d = hashlib.md5()
    d.update(msg)
    return d.hexdigest()


_Names = [
    "ShangHai",
    "TianJin",
    "ChongQing",
    "XiangGang",
    "Aomen",
    "AnHui",
    "FuJian",
    "GuangDong",
    "GuangXi",
    "GuiZhou",
    "GanSu",
    "HaiNan",
    "HeBei",
    "HeNan",
    "HeiLongJiang",
    "HuBei",
    "HuNan",
    "JiLin",
    "JiangSu",
    "JiangXi",
    "LiaoNing",
    "NeiMengGu",
    "NingXia",
    "QingHai",
    "ShanXi",
    "ShanXi",
    "ShanDong",
    "SiChuan",
    "TaiWan",
    "XiZang",
    "XinJiang",
    "YunNan",
    "ZheJiang",
    "BeiJing",
    "ShangHai",
    "TianJin",
    "ChongQing",
    "XiangGang",
    "AoMen",
]


def get_builtin_name():
    global _Names
    if not _Names:
        return "none"
    index = len(_Names) // 2
    return _Names.pop(index)


if __name__ == "__main__":
    _Names = _Names[:10]
    while _Names:
        print(get_builtin_name())
    print(get_builtin_name())
