from queue import Empty, Full
from types import FunctionType
from typing import Union

from ._commu_proto import *
from .utils import _helper, _logger

__all__ = [
    "WukongPkg",
    "WuKongQueueClient",
    "Disconnected",
    "Empty",
    "Full",
]


class Disconnected(Exception):
    pass


class WuKongQueueClient:
    def __init__(
        self,
        host="127.0.0.1",
        port=9918,
        *,
        auto_reconnect=False,
        pre_connect=False,
        silence_err=False
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
        :param silence_err: when suddenly disconnected,api raises
        exception <Disconnected> by default, return default value if
        silence_err is True, except for `get` and `put`
        """
        self.addr = (host, port)
        self._tcp_client = TcpClient(
            *self.addr, pre_connect=pre_connect
        )
        self.auto_reconnect = bool(auto_reconnect)
        self._silence_err = bool(silence_err)

    def put(
        self,
        item: Union[str, bytes],
        block=True,
        timeout=None,
        encoding="utf8",
    ):
        assert type(item) in [
            bytes,
            str,
        ], "Unsupported type %s" % type(item)
        assert isinstance(
            block, bool
        ), "wrong block arg type:%s" % type(block)
        if timeout is not None:
            assert isinstance(timeout, int), "invalid timeout"

        self._check_if_need_reconnect()

        if isinstance(item, str):
            item = item.encode(encoding=encoding)
        self._tcp_client.write(
            wrap_queue_msg(
                queue_cmd=QUEUE_PUT,
                args={"block": block, "timeout": timeout},
                data=item,
            )
        )
        wukong_pkg = self._tcp_client.read()
        if not wukong_pkg.is_valid():
            raise Disconnected(
                "WuKongQueue Svr-addr:(%s:%s) is disconnected"
                % self.addr
            )
        elif wukong_pkg.raw_data == QUEUE_FULL:
            raise Full(
                "WuKongQueue Svr-addr:(%s:%s) is full" % self.addr
            )
        # wukong_pkg.raw_data == QUEUE_OK if put success!

    def get(
        self,
        block=True,
        timeout=None,
        convert_method: FunctionType = None,
    ):
        """
        :param convert_method: function
        :param block: ...
        :param timeout: ...
        NOTE: about usage of `block` and `timeout`, see also stdlib
        `queue.Queue.get` docstring
        """

        assert isinstance(
            block, bool
        ), "wrong block arg type:%s" % type(block)
        if convert_method is not None:
            assert callable(convert_method), (
                "not a callable obj:%s" % convert_method
            )
        if timeout is not None:
            assert isinstance(timeout, int) is True, "invalid timeout"

        self._check_if_need_reconnect()

        self._tcp_client.write(
            wrap_queue_msg(
                queue_cmd=QUEUE_GET,
                args={"block": block, "timeout": timeout},
            )
        )
        wukong_pkg = self._tcp_client.read()
        if not wukong_pkg.is_valid():
            raise Disconnected(
                "WuKongQueue Svr-addr:(%s:%s) is disconnected"
                % self.addr
            )

        if wukong_pkg.raw_data == QUEUE_EMPTY:
            raise Empty(
                "WuKongQueue Svr-addr:(%s:%s) is empty" % self.addr
            )

        ret = unwrap_queue_msg(wukong_pkg.raw_data)
        if convert_method:
            return convert_method(ret["data"])
        return ret["data"]

    def full(self) -> bool:
        """Whether the queue is full"""
        self._tcp_client.write(QUEUE_QUERY_STATUS)
        wukong_pkg = self._tcp_client.read()
        if not wukong_pkg.is_valid():
            if self._silence_err:
                return False
            raise Disconnected(
                "WuKongQueue Svr-addr:(%s:%s) is disconnected"
                % self.addr
            )
        return wukong_pkg.raw_data == QUEUE_FULL

    def empty(self) -> bool:
        """Whether the queue is empty"""
        self._tcp_client.write(QUEUE_QUERY_STATUS)
        wukong_pkg = self._tcp_client.read()
        if not wukong_pkg.is_valid():
            if self._silence_err:
                return True
            raise Disconnected(
                "WuKongQueue Svr-addr:(%s:%s) is disconnected"
                % self.addr
            )
        return wukong_pkg.raw_data == QUEUE_EMPTY

    def connected(self) -> bool:
        """Whether it is connected to the server"""
        self._tcp_client.write(QUEUE_PING)
        wukong_pkg = self._tcp_client.read()
        if not wukong_pkg.is_valid():
            return False
        return wukong_pkg.raw_data == QUEUE_PONG

    def realtime_qsize(self) -> int:
        self._tcp_client.write(QUEUE_SIZE)
        wukong_pkg = self._tcp_client.read()
        if not wukong_pkg.is_valid():
            if self._silence_err:
                return 0
            raise Disconnected(
                "WuKongQueue Svr-addr:(%s:%s) is disconnected"
                % self.addr
            )
        ret = unwrap_queue_msg(wukong_pkg.raw_data)
        return int(ret["data"])

    def realtime_maxsize(self) -> int:
        self._tcp_client.write(QUEUE_MAXSIZE)
        wukong_pkg = self._tcp_client.read()
        if not wukong_pkg.is_valid():
            if self._silence_err:
                return 0
            raise Disconnected(
                "WuKongQueue Svr-addr:(%s:%s) is disconnected"
                % self.addr
            )
        ret = unwrap_queue_msg(wukong_pkg.raw_data)
        return int(ret["data"])

    def reset(self, max_size=0) -> bool:
        """Clear queue server and create a new queue
        server with the given max_size
        """
        self._tcp_client.write(
            wrap_queue_msg(
                queue_cmd=QUEUE_RESET, args={"max_size": max_size}
            )
        )
        wukong_pkg = self._tcp_client.read()
        if not wukong_pkg.is_valid():
            if self._silence_err:
                return False
            raise Disconnected(
                "WuKongQueue Svr-addr:(%s:%s) is disconnected"
                % self.addr
            )
        return wukong_pkg.raw_data == QUEUE_OK

    def connected_clients(self) -> int:
        """Number of clients connected to the server"""
        self._tcp_client.write(QUEUE_CLIENTS)
        wukong_pkg = self._tcp_client.read()
        if not wukong_pkg.is_valid():
            if self._silence_err:
                return 0
            raise Disconnected(
                "WuKongQueue Svr-addr:(%s:%s) is disconnected"
                % self.addr
            )
        ret = unwrap_queue_msg(wukong_pkg.raw_data)
        return int(ret["data"])

    def close(self):
        """Close the connection to server, not off server"""
        self._tcp_client.close()

    def _check_if_need_reconnect(self):
        if self.auto_reconnect:
            if not self.connected():
                try:
                    self._tcp_client = TcpClient(*self.addr)
                    _logger(self).info("reconnect success!")
                except Exception as e:
                    _logger(self).warning(
                        "_check_if_need_recover fail: %s,%s"
                        % (e.__class__, e.args)
                    )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def helper(self):
        return _helper(self)
