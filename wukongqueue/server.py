"""
A small and convenient cross process FIFO queue service based on
TCP protocol.
"""

import socket
import threading
from queue import Queue, Full, Empty
from types import FunctionType
from typing import Union, Set

from ._commu_proto import *
from .utils import _helper, new_thread


class UnknownCmd(Exception):
    pass


class _wk_svr_helper:
    def __init__(self, wk_inst):
        self.wk_inst = wk_inst

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        with self.wk_inst._lock:
            self.wk_inst.clients -= 1


class WuKongQueue:
    def __init__(
        self,
        host="127.0.0.1",
        port=918,
        *,
        name="",
        max_conns=0,
        max_size=0
    ):
        self.name = name
        self._tcp_svr = TcpSvr(host, port, max_conns)
        self.addr = (host, port)
        self.clients = 0
        self._lock = threading.Lock()
        self._conns: Set[socket.socket] = set()
        self._q = Queue(max_size)
        self.max_size = max_size
        self.closed = True
        self.run()

    def run(self):
        """if not run,clients cannot connect to server,but server side
        is still available
        """
        new_thread(self._run)

    def _run(self):
        self.closed = False
        while True:
            try:
                conn, addr = self._tcp_svr.accept()
                self._conns.add(conn)
            except OSError:
                break
            with self._lock:
                self.clients += 1
            new_thread(
                self.process_conn,
                kw={"client_addr": addr, "conn": conn},
            )

    def close(self):
        """close only makes sense for the clients, server side is still
        available.
        Note: When close is executed, all connected clients will be
        disconnected immediately
        """
        self.closed = True
        self._tcp_svr.close()
        for conn in self._conns:
            conn.close()
        self._conns.clear()

    def __repr__(self):
        return "<WuKongQueue listened {}, closed:{}>".format(
            self.addr, self.closed
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def helper(self):
        return _helper(self)

    def get(
        self,
        block=True,
        timeout=None,
        convert_method: FunctionType = None,
    ) -> bytes:
        """
        :param block: see also stdlib `queue.Queue.get` docstring
        :param timeout: see also stdlib `queue.Queue.get` docstring
        :param convert_method: return convert_method(raw_bytes)
        :return:
        """
        item = self._q.get(block=block, timeout=timeout)
        return convert_method(item) if convert_method else item

    def put(
        self,
        item: Union[bytes, str],
        block=True,
        timeout=None,
        encoding="utf8",
    ):
        assert type(item) in [
            bytes,
            str,
        ], "Unsupported type %s" % type(item)
        if type(item) is str:
            item = item.encode(encoding=encoding)
        self._q.put(item, block, timeout)

    def put_nowait(self, item: Union[bytes, str]):
        return self.put(item, block=False)

    def get_nowait(self, convert_method: FunctionType = None) -> bytes:
        return self.get(block=False, convert_method=convert_method)

    def full(self) -> bool:
        with self._lock:
            return self._q.full()

    def empty(self) -> bool:
        with self._lock:
            return self._q.empty()

    def qsize(self) -> int:
        with self._lock:
            return self._q.qsize()

    def reset(self, max_size=None):
        """reset clears current queue and creates a new queue with
        max_size, if max_size is None, use initial value of max_size
        """
        with self._lock:
            del self._q
            self.max_size = max_size if max_size else self.max_size
            self._q = Queue(self.max_size)

    def process_conn(self, client_addr, conn: socket.socket):
        """run as thread at all"""
        with _wk_svr_helper(self):
            while True:
                wukongpkg = read_wukong_data(conn)
                if not wukongpkg.is_valid():
                    conn.close()
                    return

                data = wukongpkg.raw_data
                resp = unwrap_queue_msg(data)
                cmd, args, data = (
                    resp["cmd"],
                    resp["args"],
                    resp["data"],
                )

                # GET
                if cmd == QUEUE_GET:
                    try:
                        item = self.get(
                            block=args["block"], timeout=args["timeout"]
                        )
                    except Empty:
                        write_wukong_data(conn, WukongPkg(QUEUE_EMPTY))
                    else:
                        write_wukong_data(
                            conn,
                            WukongPkg(
                                wrap_queue_msg(
                                    queue_cmd=QUEUE_DATA, data=item
                                )
                            ),
                        )
                    continue

                # PUT
                if cmd == QUEUE_PUT:
                    try:
                        self.put(
                            data,
                            block=args["block"],
                            timeout=args["timeout"],
                        )
                    except Full:
                        write_wukong_data(conn, WukongPkg(QUEUE_FULL))
                    else:
                        write_wukong_data(conn, WukongPkg(QUEUE_OK))
                    continue

                # STATUS QUERY
                if cmd == QUEUE_QUERY_STATUS:
                    # FULL | EMPTY | NORMAL
                    if self.full():
                        write_wukong_data(conn, WukongPkg(QUEUE_FULL))
                    elif self.empty():
                        write_wukong_data(conn, WukongPkg(QUEUE_EMPTY))
                    else:
                        write_wukong_data(conn, WukongPkg(QUEUE_NORMAL))
                    continue

                # PING -> PONG
                if cmd == QUEUE_PING:
                    write_wukong_data(conn, WukongPkg(QUEUE_PONG))
                    continue

                # QSIZE
                if cmd == QUEUE_SIZE:
                    write_wukong_data(
                        conn,
                        WukongPkg(
                            wrap_queue_msg(
                                queue_cmd=QUEUE_DATA,
                                data=str(self.qsize()).encode(),
                            )
                        ),
                    )
                    continue

                # MAXSIZE
                if cmd == QUEUE_MAXSIZE:
                    write_wukong_data(
                        conn,
                        WukongPkg(
                            wrap_queue_msg(
                                queue_cmd=QUEUE_DATA,
                                data=str(self.max_size).encode(),
                            )
                        ),
                    )
                    continue

                # RESET
                if cmd == QUEUE_RESET:
                    self.reset(args["max_size"])
                    write_wukong_data(conn, WukongPkg(QUEUE_OK))
                    continue

                # CLIENTS NUMBER
                if cmd == QUEUE_CLIENTS:
                    write_wukong_data(
                        conn,
                        WukongPkg(
                            wrap_queue_msg(
                                queue_cmd=QUEUE_DATA,
                                data=str(self.clients).encode(),
                            )
                        ),
                    )
                    continue

                raise UnknownCmd(cmd)
