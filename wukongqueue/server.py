"""
A small and convenient cross process FIFO queue service based on
TCP protocol.
"""

from queue import Queue, Full, Empty
from types import FunctionType
from typing import Union

from ._commu_proto import *
from .utils import *

__all__ = ["WuKongQueue", "new_thread", "Full", "Empty"]


class UnknownCmd(Exception):
    pass


class _ClientStatistic:
    def __init__(self, client_addr, conn):
        self.client_addr = client_addr
        self.me = str(client_addr)
        self.conn = conn
        self.is_authenticated = False


class _WkSvrHelper:
    def __init__(self, wk_inst, client_stat):
        self.wk_inst = wk_inst
        self.client_stat = client_stat

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        with self.wk_inst._lock:
            self.wk_inst.clients_stats.pop(self.client_stat.me, None)
        self.client_stat.conn.close()


class WuKongQueue:
    def __init__(self, host, port, *, name="", max_size=0, **kwargs):
        """
        :param host: host for queue server listen
        :param port: port for queue server listen
        :param name: queue's str identity
        :param max_size: queue max size

        A number of optional keyword arguments may be specified, which
        can alter the default behaviour.

        max_clients: max number of clients

        log_level: pass with stdlib logging.DEBUG/INFO/WARNING.., to control
        the WuKongQueue's logging level that output to stderr

        auth_key: it is a string used for client authentication. If is None,
        the client does not need authentication.
        """
        self.name = name if name else get_builtin_name()
        self.addr = (host, port)

        self.max_clients = kwargs.pop("max_clients", 0)
        self._tcp_svr = TcpSvr(host, port)
        log_level = kwargs.pop("log_level", logging.DEBUG)
        self._logger = get_logger(self, log_level)

        # key->"-".join(client.addr)
        # value-> `_ClientStatistic`
        self.clients_stats = {}
        self._lock = threading.Lock()
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
        self._logger.debug(
            "<WuKongQueue [%s] is listening to %s" % (self.name, self.addr)
        )
        while True:
            try:
                conn, addr = self._tcp_svr.accept()
            except OSError:
                return

            client_stat = _ClientStatistic(client_addr=addr, conn=conn)
            with self._lock:
                if self.max_clients > 0 and self.max_clients == len(
                        self.clients_stats.keys()):
                    # client will receive a empty byte, that represents
                    # clients fulled!
                    conn.close()
                    continue
                self.clients_stats[client_stat.me] = client_stat
            # send hi message when connection is successful
            ok, err = write_wukong_data(conn, WukongPkg(QUEUE_HI))
            if ok:

                new_thread(self.process_conn,
                           kw={"client_stat": client_stat})
                self._logger.info("new client from %s" % str(addr))
            else:
                # please report this problem with your python version and
                # wukongqueue package version on
                # https://github.com/chaseSpace/wukongqueue/issues
                self._logger.fatal("write_wukong_data err:%s" % err)
                return

    def close(self):
        """close only makes sense for the clients, server side is still
        available.
        Note: When close is executed, all connected clients will be
        disconnected immediately
        """
        self.closed = True
        self._tcp_svr.close()
        with self._lock:
            for client_stat in self.clients_stats.values():
                client_stat.conn.close()
        self.clients_stats.clear()
        self._logger.debug(
            "<WuKongQueue listened {} was closed>".format(self.addr)
        )

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
        assert type(item) in [bytes, str, ], "Unsupported type %s" % type(item)
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

    def process_conn(self, client_stat: _ClientStatistic):
        """run as thread at all"""
        with _WkSvrHelper(wk_inst=self, client_stat=client_stat):
            conn = client_stat.conn
            while True:
                wukongpkg = read_wukong_data(conn)
                if not wukongpkg.is_valid():
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
                    return
                else:
                    # check whether authenticated if need
                    if self._auth_key is not None:
                        if not client_stat.is_authenticated:
                            write_wukong_data(conn, WukongPkg(QUEUE_NEED_AUTH))
                            return
                # Respond client normally
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
                                data=str(
                                    len(self.clients_stats.keys())).encode()
                            )
                        ),
                    )
                else:
                    raise UnknownCmd(cmd)
