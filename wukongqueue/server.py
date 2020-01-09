"""
A small and convenient cross process FIFO queue service based on
TCP protocol.
"""
from collections import deque

from queue import Full, Empty
from time import monotonic as time
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
    def __init__(self, wk_inst, client_key):
        self.wk_inst = wk_inst
        self.client_key = client_key

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.wk_inst._remove_client(self.client_key)


class WuKongQueue:
    def __init__(self, host, port, *, name="", maxsize=0, **kwargs):
        """
        :param host: host for queue server listen
        :param port: port for queue server listen
        :param name: queue's str identity
        :param maxsize: queue max size

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
        self.client_stats = {}

        self.maxsize = maxsize
        self.queue = deque()

        # mutex must be held whenever the queue is mutating.  All methods
        # that acquire mutex must release it before returning.  mutex
        # is shared between the three conditions, so acquiring and
        # releasing the conditions also acquires and releases mutex.
        self.mutex = threading.Lock()

        # Notify not_empty whenever an item is added to the queue; a
        # thread waiting to get is notified then.
        self.not_empty = threading.Condition(self.mutex)

        # Notify not_full whenever an item is removed from the queue;
        # a thread waiting to put is notified then.
        self.not_full = threading.Condition(self.mutex)

        # Notify all_tasks_done whenever the number of unfinished tasks
        # drops to zero; thread waiting to join() is notified to resume
        self.all_tasks_done = threading.Condition(self.mutex)
        self.unfinished_tasks = 0

        self._statistic_lock = threading.Lock()
        # if closed is True, server would not to listen connection request
        # from network until execute self.run() again.
        self.closed = True

        auth_key = kwargs.pop("auth_key", None)
        self._prepare_process(auth_key=auth_key)
        self.run()

    def _prepare_process(self, auth_key):
        if auth_key is not None:
            self._auth_key = md5(auth_key.encode("utf8"))
        else:
            self._auth_key = None

    def run(self):
        """if not run,clients cannot connect to server,but server side
        is still available
        """
        if self.closed:
            new_thread(self._run)

    def close(self):
        """close only makes sense for the clients, server side is still
        available.
        Note: When close is executed, all connected clients will be
        disconnected immediately
        """
        self.closed = True
        self._tcp_svr.close()
        with self._statistic_lock:
            for client_stat in self.client_stats.values():
                client_stat.conn.close()
            self.client_stats.clear()
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
        """If the place server created isn't same with using,
        you can use helper to close client easier, like this:
        ```
        with svr.helper():
            ...
        # this is equivalent to use below:
        with svr:
            ...
        ```
        """
        return helper(self)

    def _qsize(self):
        return len(self.queue)

    def get(
            self, block=True, timeout=None, convert_method: FunctionType = None,
    ) -> bytes:
        """Remove and return an item from the queue.
        :param block
        :param timeout
        If optional args 'block' is true and 'timeout' is None (the default),
        block if necessary until an item is available. If 'timeout' is
        a non-negative number, it blocks at most 'timeout' seconds and raises
        the Empty exception if no item was available within that time.
        Otherwise ('block' is false), return an item if one is immediately
        available, else raise the Empty exception ('timeout' is ignored
        in that case).
        :param convert_method: eventually, `get` returns
        convert_method(raw_bytes)
        :return: bytes
        """
        with self.not_empty:
            if not block:
                if not self._qsize():
                    raise Empty
            elif timeout is None:
                while not self._qsize():
                    self.not_empty.wait()
            elif timeout < 0:
                raise ValueError("'timeout' must be a non-negative number")
            else:
                endtime = time() + timeout
                while not self._qsize():
                    remaining = endtime - time()
                    if remaining <= 0.0:
                        raise Empty
                    self.not_empty.wait(remaining)
            item = self.queue.popleft()
            self.not_full.notify()
            return convert_method(item) if convert_method else item

    def put(
            self,
            item: Union[bytes, str],
            block=True,
            timeout=None,
            encoding="utf8",
    ):
        """Put an item into the queue.

        :param item: value for put
        :param block
        :param timeout
        If optional args 'block' is true and 'timeout' is None (the default),
        block if necessary until a free slot is available. If 'timeout' is
        a non-negative number, it blocks at most 'timeout' seconds and raises
        the Full exception if no free slot was available within that time.
        Otherwise ('block' is false), put an item on the queue if a free slot
        is immediately available, else raise the Full exception ('timeout'
        is ignored in that case).
        :param encoding: if item type is string, we will convert it into
        bytes with given encoding.
        """
        assert type(item) in [bytes, str, ], "Unsupported type %s" % type(item)
        if type(item) is str:
            item = item.encode(encoding=encoding)

        with self.not_full:
            if self.maxsize > 0:
                if not block:
                    if self._qsize() >= self.maxsize:
                        raise Full
                elif timeout is None:
                    while self._qsize() >= self.maxsize:
                        self.not_full.wait()
                elif timeout < 0:
                    raise ValueError("'timeout' must be a non-negative number")
                else:
                    endtime = time() + timeout
                    while self._qsize() >= self.maxsize:
                        remaining = endtime - time()
                        if remaining <= 0.0:
                            raise Full
                        self.not_full.wait(remaining)
            self.queue.append(item)
            self.unfinished_tasks += 1
            self.not_empty.notify()

    def put_nowait(self, item: Union[bytes, str]):
        """
        Put an item into the queue without blocking.

        Only enqueue the item if a free slot is immediately available.
        Otherwise raise the Full exception.
        :param item: value for put
        :return:
        """
        return self.put(item, block=False)

    def get_nowait(self, convert_method: FunctionType = None) -> bytes:
        """
        Remove and return an item from the queue without blocking.

        Only get an item if one is immediately available. Otherwise
        raise the Empty exception.
        :param convert_method:
        :return:
        """
        return self.get(block=False, convert_method=convert_method)

    def full(self) -> bool:
        """Return True if the queue is full, False otherwise
        """
        with self.mutex:
            return 0 < self.maxsize <= self._qsize()

    def empty(self) -> bool:
        """Return True if the queue is empty, False otherwise
        """
        with self.mutex:
            return not self._qsize()

    def qsize(self) -> int:
        """Return the approximate size of the queue
        """
        with self.mutex:
            return self._qsize()

    def reset(self, maxsize=None):
        """reset clears current queue and creates a new queue with
        maxsize, if maxsize is None, use initial value of maxsize
        """
        with self.mutex:
            self.maxsize = maxsize if maxsize else self.maxsize
            self.queue.clear()

    def task_done(self):
        """Indicate that a formerly enqueued task is complete.

         Used by Queue consumer threads.  For each get() used to fetch a task,
         a subsequent call to task_done() tells the queue that the processing
         on the task is complete.

         If a join() is currently blocking, it will resume when all items
         have been processed (meaning that a task_done() call was received
         for every item that had been put() into the queue).

         Raises a ValueError if called more times than there were items
         placed in the queue.
         """
        with self.all_tasks_done:
            unfinished = self.unfinished_tasks - 1
            if unfinished <= 0:
                if unfinished < 0:
                    raise ValueError("task_done() called too many times")
                self.all_tasks_done.notify_all()
            self.unfinished_tasks = unfinished

    def join(self):
        """Blocks until all items in the Queue have been gotten and processed.

        The count of unfinished tasks goes up whenever an item is added to the
        queue. The count goes down whenever a consumer thread calls task_done()
        to indicate the item was retrieved and all work on it is complete.

        When the count of unfinished tasks drops to zero, join() unblocks.
        """
        with self.all_tasks_done:
            while self.unfinished_tasks:
                self.all_tasks_done.wait()

    def _remove_client(self, client_key):
        with self._statistic_lock:
            if client_key in self.client_stats:
                self.client_stats[client_key].conn.close()
                self.client_stats.pop(client_key)

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

            with self._statistic_lock:
                if self.max_clients > 0:
                    if self.max_clients == len(self.client_stats):
                        # client will receive a empty byte, that represents
                        # clients fulled!
                        conn.close()
                        continue
                self.client_stats[client_stat.me] = client_stat
            # send hi message when connection is successful
            ok, err = write_wukong_data(conn, WukongPkg(QUEUE_HI))
            if ok:
                new_thread(
                    self.process_conn, kw={"conn": conn, "me": client_stat.me}
                )
                self._logger.info("new client from %s" % str(addr))
            else:
                # please report this problem with your python version and
                # wukongqueue package version on
                # https://github.com/chaseSpace/wukongqueue/issues
                self._logger.fatal("write_wukong_data err:%s" % err)
                return

    def process_conn(self, me: str, conn):
        """run as thread at all"""
        with _WkSvrHelper(wk_inst=self, client_key=me):
            while True:
                wukongpkg = read_wukong_data(conn)
                if not wukongpkg.is_valid():
                    return

                data = wukongpkg.raw_data
                resp = unwrap_queue_msg(data)
                cmd, args, data = resp["cmd"], resp["args"], resp["data"]

                # Instruction for cmd and data interaction:
                #   1. if only queue_cmd, just send WukongPkg(QUEUE_OK)
                #   2. if there's arg or data besides queue_cmd, use
                #      wrap_queue_msg(queue_cmd=QUEUE_CMD, arg={}, data=b'')

                # AUTH, it's a must to authenticate firstly
                with self._statistic_lock:
                    client_stat = self.client_stats.get(me)
                    if client_stat is None:
                        return

                    if cmd == QUEUE_AUTH_KEY:
                        is_auth = False
                        if client_stat.is_authenticated:
                            is_auth = True
                        elif args["auth_key"] == self._auth_key:
                            is_auth = True
                            client_stat.is_authenticated = True
                        if is_auth:
                            write_wukong_data(conn, WukongPkg(QUEUE_OK))
                            continue
                        else:
                            write_wukong_data(conn, WukongPkg(QUEUE_FAIL))
                            return
                    else:
                        # check whether authenticated if need
                        if self._auth_key is not None:
                            if not client_stat.is_authenticated:
                                write_wukong_data(
                                    conn, WukongPkg(QUEUE_NEED_AUTH)
                                )
                                return
                #
                # Respond client normally
                #

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
                            data, block=args["block"], timeout=args["timeout"]
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
                                data=str(self.maxsize).encode(),
                            )
                        ),
                    )

                # RESET
                elif cmd == QUEUE_RESET:
                    self.reset(args["maxsize"])
                    write_wukong_data(conn, WukongPkg(QUEUE_OK))

                # CLIENTS NUMBER
                elif cmd == QUEUE_CLIENTS:
                    with self._statistic_lock:
                        clients = len(self.client_stats.keys())
                    write_wukong_data(
                        conn,
                        WukongPkg(
                            wrap_queue_msg(
                                queue_cmd=QUEUE_DATA,
                                data=str(clients).encode(),
                            )
                        ),
                    )

                # TASK_DONE
                elif cmd == QUEUE_TASK_DONE:
                    reply = {"cmd": QUEUE_OK, "err": ""}
                    try:
                        self.task_done()
                    except ValueError as e:
                        reply["cmd"] = QUEUE_FAIL
                        reply["err"] = str(e.args)
                    write_wukong_data(
                        conn,
                        WukongPkg(
                            wrap_queue_msg(
                                queue_cmd=reply["cmd"],
                                data=reply["err"].encode(),
                            )
                        ),
                    )

                # JOIN
                elif cmd == QUEUE_JOIN:
                    self.join()
                    write_wukong_data(
                        conn, WukongPkg(wrap_queue_msg(queue_cmd=QUEUE_OK, ))
                    )
                else:
                    raise UnknownCmd(cmd)
