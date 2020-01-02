"""
A small and convenient cross process FIFO queue service based on
TCP protocol.
"""

import socket
from queue import Queue, Full, Empty
from types import FunctionType
from typing import Union

from ._commu_proto import *
from .utils import *

__all__ = ["WuKongQueue", "new_thread", "Full", "Empty"]


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
    def __init__(self, host, port, *, name="", max_size=0, **kwargs):
        """
        :param host: host for queue server listen
        :param port: port for queue server listen
        :param name: queue's str identity
        :param max_size: queue max size

        A number of optional keyword arguments may be specified, which
        can alter the default behaviour.

        max_conns: max number of clients

        log_level: pass with stdlib logging.DEBUG/INFO/WARNING.., to control
        the WuKongQueue's logging level that output to stderr

        auth_key: it is a string used for client authentication. If is None,
        the client does not need authentication.
        """
        self.name = name
        self.addr = (host, port)

        max_conns = kwargs.pop("max_conns", 0)
        self._tcp_svr = TcpSvr(host, port, max_conns)
        log_level = kwargs.pop("log_level", logging.DEBUG)
        self._logger = get_logger(self, log_level)

        self.clients = 0
        self._lock = threading.Lock()
        self._conns = set()
        self._q = Queue(max_size)
        self.max_size = max_size
        self.closed = True

        auth_key = kwargs.pop("auth_key", None)
        if auth_key is not None:
            self._auth_key = md5(auth_key.encode("utf8"))
        else:
            self._auth_key = None
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
                self._logger.debug(
                    "<WuKongQueue listened {} was closed>".format(self.addr)
                )
                return
            with self._lock:
                self.clients += 1
            new_thread(
                self.process_conn, kw={"client_addr": addr, "conn": conn},
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
        return helper(self)

    def get(
        self, block=True, timeout=None, convert_method: FunctionType = None,
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
        assert type(item) in [bytes, str,], "Unsupported type %s" % type(item)
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
                # Instruction for cmd and data interaction:
                #   1. if only queue_cmd, just send WukongPkg(QUEUE_OK)
                #   2. if there's arg or data besides queue_cmd, use
                #      wrap_queue_msg(queue_cmd=QUEUE_CMD, arg={}, data=b'')

                # AUTH
                if cmd == QUEUE_AUTH_KEY:
                    if args["auth_key"] == self._auth_key:
                        write_wukong_data(conn, WukongPkg(QUEUE_OK))
                    else:
                        write_wukong_data(conn, WukongPkg(QUEUE_FAIL))

                # GET
                elif cmd == QUEUE_GET:
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
                                wrap_queue_msg(queue_cmd=QUEUE_DATA, data=item)
                            ),
                        )

                # PUT
                elif cmd == QUEUE_PUT:
                    try:
                        self.put(
                            data, block=args["block"], timeout=args["timeout"],
                        )
                    except Full:
                        write_wukong_data(conn, WukongPkg(QUEUE_FULL))
                    else:
                        write_wukong_data(conn, WukongPkg(QUEUE_OK))

                # STATUS QUERY
                elif cmd == QUEUE_QUERY_STATUS:
                    # FULL | EMPTY | NORMAL
                    if self.full():
                        write_wukong_data(conn, WukongPkg(QUEUE_FULL))
                    elif self.empty():
                        write_wukong_data(conn, WukongPkg(QUEUE_EMPTY))
                    else:
                        write_wukong_data(conn, WukongPkg(QUEUE_NORMAL))

                # PING -> PONG
                elif cmd == QUEUE_PING:
                    write_wukong_data(conn, WukongPkg(QUEUE_PONG))

                # QSIZE
                elif cmd == QUEUE_SIZE:
                    write_wukong_data(
                        conn,
                        WukongPkg(
                            wrap_queue_msg(
                                queue_cmd=QUEUE_DATA,
                                data=str(self.qsize()).encode(),
                            )
                        ),
                    )

                # MAXSIZE
                elif cmd == QUEUE_MAXSIZE:
                    write_wukong_data(
                        conn,
                        WukongPkg(
                            wrap_queue_msg(
                                queue_cmd=QUEUE_DATA,
                                data=str(self.max_size).encode(),
                            )
                        ),
                    )

                # RESET
                elif cmd == QUEUE_RESET:
                    self.reset(args["max_size"])
                    write_wukong_data(conn, WukongPkg(QUEUE_OK))

                # CLIENTS NUMBER
                elif cmd == QUEUE_CLIENTS:
                    write_wukong_data(
                        conn,
                        WukongPkg(
                            wrap_queue_msg(
                                queue_cmd=QUEUE_DATA,
                                data=str(self.clients).encode(),
                            )
                        ),
                    )
                else:
                    raise UnknownCmd(cmd)
