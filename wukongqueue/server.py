"""
A small and convenient cross process FIFO queue service based on
TCP protocol.
"""
import logging
import threading
from collections import deque
from queue import Full, Empty
from time import monotonic

from ._commu_proto import *
from .exceptions import UnknownCmd, Empty, Full
from .utils import (
    Unify_encoding,
    md5,
    new_thread,
    get_logger,
    get_builtin_name,
    helper,
)


class _ClientStatistic:
    def __init__(self, client_addr, conn):
        self.client_addr = client_addr
        self.me = str(client_addr)
        self.conn = conn


class _WkSvrHelper:
    def __init__(self, wk_inst, client_key):
        self.wk_inst = wk_inst
        self.client_key = client_key

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.wk_inst.remove_client(self.client_key)


class WuKongQueue:
    def __init__(
            self, host="localhost", port=8848, name="", maxsize=0, **kwargs
    ):
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
        the client does not need authentication

        socket_connect_timeout: maximum socket operations time allowed during
        connection establishment

        socket_timeout: maximum socket operations time allowed after successful
        connection, prevent the client from disconnecting in a way that the
        server cannot sense, thus making the resources unable to be released.
        """
        self.name = name or get_builtin_name()
        self.addr = (host, port)

        self.max_clients = kwargs.pop("max_clients", 0)
        self._tcp_svr = TcpSvr(host, port)
        log_level = kwargs.pop("log_level", logging.DEBUG)
        self._logger = get_logger(self, log_level)
        self.socket_connect_timeout = kwargs.pop("socket_connect_timeout", 30)
        self.socket_timeout = kwargs.pop(
            "socket_timeout", self.socket_connect_timeout
        )

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
            self._auth_key = md5(auth_key.encode(Unify_encoding))
        else:
            self._auth_key = None

    def run(self):
        """
        if not running, clients can't connect to server,but server side
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
            "<WuKongQueue listened {} " "was closed>".format(self.addr)
        )

    def __repr__(self):
        return "<WuKongQueue listened {}, " "is_closed:{}>".format(
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

    def get(self, block=True, timeout=None, convert_method=None):
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
        :param convert_method: eventually, `get` returns convert_method(item)
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
                endtime = monotonic() + timeout
                while not self._qsize():
                    remaining = endtime - monotonic()
                    if remaining <= 0.0:
                        raise Empty
                    self.not_empty.wait(remaining)
            item = self.queue.popleft()
            self.not_full.notify()
            return convert_method(item) if convert_method is not None else item

    def put(self, item, block=True, timeout=None):
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
        is ignored in that case)
        """
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
                    endtime = monotonic() + timeout
                    while self._qsize() >= self.maxsize:
                        remaining = endtime - monotonic()
                        if remaining <= 0.0:
                            raise Full
                        self.not_full.wait(remaining)
            self.queue.append(item)
            self.unfinished_tasks += 1
            self.not_empty.notify()

    def put_nowait(self, item):
        """
        Put an item into the queue without blocking.

        Only enqueue the item if a free slot is immediately available.
        Otherwise raise the Full exception.
        :param item: value for put
        :return:
        """
        return self.put(item, block=False)

    def get_nowait(self, convert_method=None) -> bytes:
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

    def connected_clients(self):
        with self._statistic_lock:
            return len(self.client_stats)

    def remove_client(self, client_key):
        with self._statistic_lock:
            try:
                self.client_stats[client_key].conn.close()
                self.client_stats.pop(client_key)
            except KeyError:
                pass

    @staticmethod
    def _parse_socket_msg(conn, **kw):
        ignore_socket_timeout = kw.pop("ignore_socket_timeout", False)
        reply_msg = read_wukong_data(conn,
                                     ignore_socket_timeout=ignore_socket_timeout)
        if not reply_msg.is_valid():
            return
        reply_msg.unwrap()
        return reply_msg

    def _auth(self, conn, client_stat: _ClientStatistic):
        def auth_core():
            if self._auth_key is None:
                return True
            reply_msg = self._parse_socket_msg(conn)
            if reply_msg is not None:
                cmd = reply_msg.queue_params_object.cmd
                args = reply_msg.queue_params_object.args
                if cmd == QUEUE_AUTH_KEY:
                    if args["auth_key"] == self._auth_key:
                        write_wukong_data(conn, WuKongPkg(QUEUE_OK))
                        return True
                    else:
                        write_wukong_data(conn, WuKongPkg(QUEUE_FAIL))
                        return False
            return False

        if auth_core():
            client_stat.conn.settimeout(self.socket_timeout)
            with self._statistic_lock:
                self.client_stats[client_stat.me] = client_stat
                return True
        return False

    def on_running(self):
        if self.closed:
            self.closed = False
            self._logger.debug(
                "<WuKongQueue [%s] is listening to %s" % (self.name, self.addr)
            )

    def _run(self):
        self.on_running()
        while True:
            try:
                conn, addr = self._tcp_svr.accept()
                conn.settimeout(self.socket_connect_timeout)
            except OSError:
                return
            client_stat = _ClientStatistic(client_addr=addr, conn=conn)
            with self._statistic_lock:
                if self.max_clients > 0:
                    if self.max_clients <= len(self.client_stats):
                        # client will receive a empty byte, that represents
                        # clients fulled!
                        conn.close()
                        continue

            # send hi message on connected
            ok, err = write_wukong_data(conn, WuKongPkg(QUEUE_HI))
            if ok:
                # it's a must to authenticate firstly
                if self._auth(conn=conn, client_stat=client_stat):
                    new_thread(
                        self.process_conn,
                        kw={"conn": conn, "me": client_stat.me},
                    )
                    self._logger.info("new client from %s" % str(addr))
                    continue
                # auth failed!
                conn.close()
                continue
            else:
                # please report this problem with your python version and
                # wukongqueue package version on
                # https://github.com/chaseSpace/wukongqueue/issues
                self._logger.fatal("write_wukong_data err:%s" % err)
                return

    def process_conn(self, me, conn):
        """run as thread at all"""
        with _WkSvrHelper(wk_inst=self, client_key=me):
            while True:
                reply_msg = self._parse_socket_msg(conn,
                                                   ignore_socket_timeout=True)
                if reply_msg is None:
                    return
                cmd = reply_msg.queue_params_object.cmd
                args = reply_msg.queue_params_object.args
                data = reply_msg.queue_params_object.data

                # Instruction for cmd and data interaction:
                #   1. if only queue_cmd, just send WukongPkg(QUEUE_OK)
                #   2. if there's arg or data besides queue_cmd, use
                #      wrap_queue_msg(queue_cmd=QUEUE_CMD, arg={}, data=b'')

                #
                # Communicate with client normally
                #

                # GET
                if cmd == QUEUE_GET:
                    try:
                        item = self.get(
                            block=args["block"], timeout=args["timeout"]
                        )
                    except Empty:
                        write_wukong_data(conn, WuKongPkg(QUEUE_EMPTY))
                    else:
                        write_wukong_data(
                            conn,
                            WuKongPkg(
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
                        write_wukong_data(conn, WuKongPkg(QUEUE_FULL))
                    else:
                        write_wukong_data(conn, WuKongPkg(QUEUE_OK))

                # STATUS QUERY
                elif cmd == QUEUE_QUERY_STATUS:
                    # FULL | EMPTY | NORMAL
                    if self.full():
                        write_wukong_data(conn, WuKongPkg(QUEUE_FULL))
                    elif self.empty():
                        write_wukong_data(conn, WuKongPkg(QUEUE_EMPTY))
                    else:
                        write_wukong_data(conn, WuKongPkg(QUEUE_NORMAL))

                # PING -> PONG
                elif cmd == QUEUE_PING:
                    write_wukong_data(conn, WuKongPkg(QUEUE_PONG))

                # QSIZE
                elif cmd == QUEUE_SIZE:
                    write_wukong_data(
                        conn,
                        WuKongPkg(
                            wrap_queue_msg(
                                queue_cmd=QUEUE_DATA, data=self.qsize(),
                            )
                        ),
                    )

                # MAXSIZE
                elif cmd == QUEUE_MAXSIZE:
                    write_wukong_data(
                        conn,
                        WuKongPkg(
                            wrap_queue_msg(
                                queue_cmd=QUEUE_DATA, data=self.maxsize,
                            )
                        ),
                    )

                # RESET
                elif cmd == QUEUE_RESET:
                    self.reset(args["maxsize"])
                    write_wukong_data(conn, WuKongPkg(QUEUE_OK))

                # CLIENTS NUMBER
                elif cmd == QUEUE_CLIENTS:
                    with self._statistic_lock:
                        clients = len(self.client_stats.keys())
                    write_wukong_data(
                        conn,
                        WuKongPkg(
                            wrap_queue_msg(queue_cmd=QUEUE_DATA, data=clients, )
                        ),
                    )

                # TASK_DONE
                elif cmd == QUEUE_TASK_DONE:
                    reply = {"cmd": QUEUE_OK, "err": ""}
                    try:
                        self.task_done()
                    except ValueError as e:
                        reply["cmd"] = QUEUE_FAIL
                        reply["err"] = e
                    write_wukong_data(
                        conn,
                        WuKongPkg(
                            wrap_queue_msg(
                                queue_cmd=reply["cmd"], exception=reply["err"]
                            )
                        ),
                    )

                # JOIN
                elif cmd == QUEUE_JOIN:
                    self.join()
                    write_wukong_data(conn, WuKongPkg(QUEUE_OK))
                else:
                    raise UnknownCmd(cmd)
