from queue import Empty, Full
from types import FunctionType

from ._commu_proto import *
from ._item_wrapper import item_wrapper, item_unwrap
from .utils import *

__all__ = [
    "WuKongQueueClient",
    "Disconnected",
    "Empty",
    "Full",
    "AuthenticationFail",
    "ClientsFull",
    "ConnectionFail",
    "CannotConcurrentCallBlockMethod",
    "NotYetSupportType",
]


class ConnectionFail(Exception):
    pass


class ClientsFull(Exception):
    pass


class Disconnected(Exception):
    pass


class AuthenticationFail(Exception):
    pass


class CannotConcurrentCallBlockMethod(Exception):
    """client cannot call block method within multi-threading
    """

    pass


class NotYetSupportType(Exception):
    pass


class WuKongQueueClient:
    def __init__(
        self,
        host,
        port,
        *,
        auto_reconnect=False,
        pre_connect=False,
        silence_err=False,
        **kwargs
    ):
        """
        :param host: ...
        :param port: ...
        :param auto_reconnect: do reconnect when conn is disconnected,
        instead of `raise` an exception
        :param pre_connect: by default, the class raises an exception
        when it fails to initialize connection, if `pre_conn` is true,
        you can success to initialize client although server is not
        ready yet
        :param silence_err:when suddenly disconnected,api raises
        exception <Disconnected> by default; if silence_err is True,
        return default value, do logging for `get` and `put`

        A number of optional keyword arguments may be specified, which
        can alter the default behaviour.

        log_level: pass with stdlib logging.DEBUG/INFO/WARNING.., to
        control the WuKongQueue's logging level that output to stderr

        auth_key: str used for server side authentication, it will be
        encrypted for transmission over the network
        """
        self.server_addr = (host, port)
        self.auto_reconnect = bool(auto_reconnect)
        self._pre_conn = pre_connect
        self._silence_err = bool(silence_err)

        log_level = kwargs.pop("log_level", logging.DEBUG)
        self._logger = get_logger(self, log_level)

        self._auth_key = None
        auth_key = kwargs.pop("auth_key", None)
        if auth_key is not None:
            self._auth_key = md5(auth_key.encode(Unify_encoding))

        # some methods that will block cannot be called within
        # multi-threading
        self.socket_commu_lock = threading.Lock()
        self._do_connect()

    def _do_connect(self, on_init=True) -> bool:
        # not connect to server if _pre_conn is true and on_init
        if self._pre_conn:
            if on_init:
                self._tcp_client = None
                return False
            else:
                # if on_init is false, do connect to server
                pass
        try:
            # if fail to connect to server, self._tcp_client = None
            self._tcp_client = None
            self._tcp_client = TcpClient(*self.server_addr)
            wukong_pkg = self._tcp_client.read()
            if wukong_pkg.err:
                self._tcp_client.close()
                raise ConnectionFail(wukong_pkg.err)
            elif wukong_pkg.closed:
                self._tcp_client.close()
                raise ClientsFull(
                    "The WuKongQueue server %s is full" % str(self.server_addr)
                )
            elif wukong_pkg.raw_data == QUEUE_HI:
                if self._do_authenticate(self._auth_key) is False:
                    self._tcp_client.close()
                    raise AuthenticationFail(
                        "WuKongQueue server-addr:%s "
                        "authentication failed" % str(self.server_addr)
                    )
                # connect success!
                self._logger.info(
                    "successfully connected to %s!" % str(self.server_addr)
                )
                return True
            else:
                self._tcp_client.close()
                raise ValueError("unknown response:%s" % wukong_pkg.raw_data)

        except Exception as e:
            self._logger.warning(
                "failed to connect to %s, err:%s,%s"
                % (str(self.server_addr), e.__class__, e.args)
            )
            if self._silence_err is False or (self._silence_err and on_init):
                if not isinstance(e, ConnectionRefusedError):
                    raise e
            return False

    def put(self, item, block=True, timeout=None, encoding=Unify_encoding):
        """
        :param item: item will be put in server's queue
        :param encoding: not use now, just for compatibility.

        Usage for block and timeout see also WuKongQueue.put
        """
        assert isinstance(block, bool), "wrong block arg type:%s" % type(block)
        if timeout is not None:
            assert type(timeout) in [int, float], "invalid timeout"

        if self.connected() is False:
            self._process_disconnect()
            return

        try:
            item_wrapped = item_wrapper(item)
        except Exception as e:
            raise NotYetSupportType(
                "%s is not supported yet, wrapping err:%s %s"
                % (type(item), e, e.args)
            )

        wukong_pkg = self._talk_with_svr(
            wrap_queue_msg(
                queue_cmd=QUEUE_PUT,
                args={"block": block, "timeout": timeout},
                data=item_wrapped,
            )
        )

        if not wukong_pkg.is_valid():
            self._process_disconnect()
        elif wukong_pkg.raw_data == QUEUE_FULL:
            raise Full(
                "WuKongQueue server-addr:%s is full" % str(self.server_addr)
            )
        # wukong_pkg.raw_data == QUEUE_OK if put success!

    def get(
        self, block=True, timeout=None, convert_method: FunctionType = None,
    ):
        """
        :param convert_method: function for convert item

        Usage for block and timeout see also WuKongQueue.get
        """

        assert isinstance(block, bool), "wrong block arg type:%s" % type(block)
        if convert_method is not None:
            assert callable(convert_method), (
                "not a callable obj:%s" % convert_method
            )
        if timeout is not None:
            assert type(timeout) in [int, float], "invalid timeout"

        if self.connected() is False:
            self._process_disconnect()
            return

        wukong_pkg = self._talk_with_svr(
            wrap_queue_msg(
                queue_cmd=QUEUE_GET, args={"block": block, "timeout": timeout},
            )
        )

        if not wukong_pkg.is_valid():
            self._process_disconnect()
        if wukong_pkg.raw_data == QUEUE_EMPTY:
            raise Empty(
                "WuKongQueue server-addr:%s is empty" % str(self.server_addr)
            )

        ret = unwrap_queue_msg(wukong_pkg.raw_data)
        item = item_unwrap(ret["data"])

        if convert_method:
            return convert_method(item)
        return item

    def full(self) -> bool:
        """Whether the queue is full"""
        default_ret = False
        if self.connected() is False:
            self._process_disconnect()
            return default_ret

        wukong_pkg = self._talk_with_svr(QUEUE_QUERY_STATUS)

        if not wukong_pkg.is_valid():
            self._process_disconnect()
            return default_ret
        return wukong_pkg.raw_data == QUEUE_FULL

    def empty(self) -> bool:
        """Whether the queue is empty"""
        default_ret = True
        if self.connected() is False:
            self._process_disconnect()
            return default_ret

        wukong_pkg = self._talk_with_svr(QUEUE_QUERY_STATUS)

        if not wukong_pkg.is_valid():
            self._process_disconnect()
            return default_ret
        return wukong_pkg.raw_data == QUEUE_EMPTY

    def task_done(self):
        """Indicates that a formerly enqueued task is complete.

        Used by Queue consumer threads.  For each get() used to fetch a task,
        a subsequent call to task_done() tells the queue that the processing
        on the task is complete.

        If a join() is currently blocking, it will resume when all items
        have been processed (meaning that a task_done() call was received
        for every item that had been put() into the queue).

        Raises a ValueError if called more times than there were items
        placed in the queue.
        ---
        If is disconnected, and if self._silence_err is False, this raises a
        Disconnected
        """
        if self.connected() is False:
            self._process_disconnect()
            return

        wukong_pkg = self._talk_with_svr(QUEUE_TASK_DONE)

        if not wukong_pkg.is_valid():
            self._process_disconnect()
            return

        ret = unwrap_queue_msg(wukong_pkg.raw_data)

        if ret["cmd"] == QUEUE_OK:
            return
        else:
            raise ValueError(ret["data"])

    def join(self):
        """Blocks until all items in the Queue have been gotten and processed.

        The count of unfinished tasks goes up whenever an item is added to the
        queue. The count goes down whenever a consumer thread calls task_done()
        to indicate the item was retrieved and all work on it is complete.

        When the count of unfinished tasks drops to zero, join() unblocks.
        ---
        If is disconnected, and if self._silence_err is False, this raises a
        Disconnected
        """
        if self.connected() is False:
            self._process_disconnect()
            return

        wukong_pkg = self._talk_with_svr(QUEUE_JOIN)

        if not wukong_pkg.is_valid():
            self._process_disconnect()
            return
        return wukong_pkg.raw_data == QUEUE_OK

    def connected(self) -> bool:
        """Whether it is connected to the server.
        note:this api do reconnect when `auto_connect` is True, then return
        outcome of reconnection
        """
        if self._tcp_client is not None:
            wukong_pkg = self._talk_with_svr(QUEUE_PING)
            if not wukong_pkg.is_valid():
                if self.auto_reconnect:
                    return self._do_connect(on_init=False)
                else:
                    return False
            else:
                return wukong_pkg.raw_data == QUEUE_PONG
        return self._do_connect(on_init=False)

    def realtime_qsize(self) -> int:
        default_ret = 0
        if self.connected() is False:
            self._process_disconnect()
            return default_ret

        wukong_pkg = self._talk_with_svr(QUEUE_SIZE)

        if not wukong_pkg.is_valid():
            self._process_disconnect()
            return default_ret
        ret = unwrap_queue_msg(wukong_pkg.raw_data)
        return int(ret["data"])

    def realtime_maxsize(self) -> int:
        default_ret = 0
        if self.connected() is False:
            self._process_disconnect()
            return default_ret

        wukong_pkg = self._talk_with_svr(QUEUE_MAXSIZE)

        if not wukong_pkg.is_valid():
            self._process_disconnect()
            return default_ret
        ret = unwrap_queue_msg(wukong_pkg.raw_data)
        return int(ret["data"])

    def reset(self, maxsize=0) -> bool:
        """Clear queue server and reset maxsize
        """
        default_ret = False
        if self.connected() is False:
            self._process_disconnect()
            return default_ret

        wukong_pkg = self._talk_with_svr(
            wrap_queue_msg(queue_cmd=QUEUE_RESET, args={"maxsize": maxsize})
        )

        if not wukong_pkg.is_valid():
            self._process_disconnect()
            return default_ret
        return wukong_pkg.raw_data == QUEUE_OK

    def connected_clients(self) -> int:
        """Number of clients connected to the server"""
        default_ret = 0
        if self.connected() is False:
            self._process_disconnect()
            return default_ret

        wukong_pkg = self._talk_with_svr(QUEUE_CLIENTS)

        if not wukong_pkg.is_valid():
            self._process_disconnect()
            return default_ret
        ret = unwrap_queue_msg(wukong_pkg.raw_data)
        return int(ret["data"])

    def close(self):
        """Close the connection to server, not off server"""
        if self._tcp_client is not None:
            self._tcp_client.close()

    def _process_disconnect(self, msg=""):
        m = "WuKongQueue server-addr:%s is disconnected" % str(self.server_addr)
        m = msg if msg else m
        if self._silence_err:
            self._logger.warning(m)
        else:
            raise Disconnected(m)

    def _do_authenticate(self, auth_key) -> bool:
        if auth_key is None:
            return True

        wukong_pkg = self._talk_with_svr(
            wrap_queue_msg(
                queue_cmd=QUEUE_AUTH_KEY, args={"auth_key": auth_key}
            )
        )

        if not wukong_pkg.is_valid():
            self._process_disconnect()
            return False
        return wukong_pkg.raw_data == QUEUE_OK

    def _talk_with_svr(self, msg) -> WukongPkg:
        if not self.socket_commu_lock.acquire(blocking=False):
            self._tcp_client.close()
            raise CannotConcurrentCallBlockMethod
        self._tcp_client.write(msg)
        ret = self._tcp_client.read()
        # There is no need to use try to ensure the lock is closed,
        # because the client's method does not allow multi-threaded calls,
        # and the program should not continue to run when there is an exception
        # it maybe a bug, just report it ~!
        self.socket_commu_lock.release()
        return ret

    def helper(self):
        """If the place client created isn't same with using,
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

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
