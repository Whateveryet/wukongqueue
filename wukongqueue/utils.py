# -*- coding: utf-8 -*-

import logging
import threading


class _helper:
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
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(name)s [%(levelname)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    return logger
