from queue import Empty, Full
from types import FunctionType
from typing import Union

from ._commu_proto import *
from .utils import *

__all__ = [
    "WuKongQueueClient",
    "Disconnected",
    "Empty",
    "Full",
    "AuthenticationFail",
    "ClientsFull",
    "ConnectionFail"
]


class ConnectionFail(Exception):
    pass


class ClientsFull(Exception):
    pass


class Disconnected(Exception):
    pass


class AuthenticationFail(Exception):
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
        return default value , except for `get` and `put`

        A number of optional keyword arguments may be specified, which
        can alter the default behaviour.

        log_level: pass with stdlib logging.DEBUG/INFO/WARNING.., to control
        the WuKongQueue's logging level that output to stderr

        auth_key: str used for server side authentication, it will be encrypted
        for transmission over the network
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
            self._auth_key = md5(auth_key.encode("utf8"))

        self._do_connect()

    def _do_connect(self, on_init=True) -> bool:
        if self._pre_conn:
            if on_init:
                self._tcp_client = None
                return False

        try:
            self._tcp_client = TcpClient(*self.server_addr)
            wukong_pkg = self._tcp_client.read()
            if wukong_pkg.err:
                self._tcp_client.close()
                raise ConnectionFail(wukong_pkg.err)
            elif wukong_pkg.closed:
                self._tcp_client.close()
                raise ClientsFull("The client connected to the server is full")
            elif wukong_pkg.raw_data == QUEUE_HI:
                if self._do_authenticate(self._auth_key) is False:
                    self._tcp_client.close()
                    raise AuthenticationFail(
                        "WuKongQueue Svr-addr:%s "
                        "authentication failed" % str(self.server_addr)
                    )
                # connect success!
                self._logger.info("successfully connected to %s!" %
                                  str(self.server_addr))
                return True
            else:
                self._tcp_client.close()
                raise ValueError("unknown response:%s" % wukong_pkg.raw_data)

        except Exception as e:
            self._logger.warning(
                "failed to connect to %s, err:%s,%s" % (
                    str(self.server_addr), e.__class__, e.args)
            )
            # raises the exception only on init
            if self._silence_err:
                if on_init:
                    raise e
            return False

    def put(
            self,
            item: Union[str, bytes],
            block=True,
            timeout=None,
            encoding="utf8",
    ):
        assert type(item) in [bytes, str, ], "Unsupported type %s" % type(item)
        assert isinstance(block, bool), "wrong block arg type:%s" % type(block)
        if timeout is not None:
            assert isinstance(timeout, int), "invalid timeout"

        if self.connected() is False:
            raise Disconnected(
                "WuKongQueue Svr-addr:%s is disconnected"
                % str(self.server_addr)
            )

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
                "WuKongQueue Svr-addr:%s is disconnected"
                % str(self.server_addr)
            )
        elif wukong_pkg.raw_data == QUEUE_FULL:
            raise Full(
                "WuKongQueue Svr-addr:%s is full" % str(self.server_addr)
            )
        # wukong_pkg.raw_data == QUEUE_OK if put success!

    def get(
            self, block=True, timeout=None, convert_method: FunctionType = None,
    ):
        """
        :param convert_method: function
        :param block: ...
        :param timeout: ...
        NOTE: about usage of `block` and `timeout`, see also stdlib
        `queue.Queue.get` docstring
        """

        assert isinstance(block, bool), "wrong block arg type:%s" % type(block)
        if convert_method is not None:
            assert callable(convert_method), (
                    "not a callable obj:%s" % convert_method
            )
        if timeout is not None:
            assert isinstance(timeout, int) is True, "invalid timeout"

        if self.connected() is False:
            raise Disconnected(
                "WuKongQueue Svr-addr:%s is disconnected"
                % str(self.server_addr)
            )

        self._tcp_client.write(
            wrap_queue_msg(
                queue_cmd=QUEUE_GET, args={"block": block, "timeout": timeout},
            )
        )
        wukong_pkg = self._tcp_client.read()
        if not wukong_pkg.is_valid():
            raise Disconnected(
                "WuKongQueue Svr-addr:%s is disconnected"
                % str(self.server_addr)
            )

        if wukong_pkg.raw_data == QUEUE_EMPTY:
            raise Empty(
                "WuKongQueue Svr-addr:%s is empty" % str(self.server_addr)
            )

        ret = unwrap_queue_msg(wukong_pkg.raw_data)
        if convert_method:
            return convert_method(ret["data"])
        return ret["data"]

    def full(self) -> bool:
        """Whether the queue is full"""
        default_ret = False
        if self.connected() is False:
            if not self._silence_err:
                raise Disconnected(
                    "WuKongQueue Svr-addr:%s is disconnected"
                    % str(self.server_addr)
                )
            return default_ret

        self._tcp_client.write(QUEUE_QUERY_STATUS)
        wukong_pkg = self._tcp_client.read()
        if not wukong_pkg.is_valid():
            if self._silence_err:
                return default_ret
            raise Disconnected(
                "WuKongQueue Svr-addr:%s is disconnected"
                % str(self.server_addr)
            )
        return wukong_pkg.raw_data == QUEUE_FULL

    def empty(self) -> bool:
        """Whether the queue is empty"""
        default_ret = True
        if self.connected() is False:
            if not self._silence_err:
                raise Disconnected(
                    "WuKongQueue Svr-addr:%s is disconnected"
                    % str(self.server_addr)
                )
            return default_ret

        self._tcp_client.write(QUEUE_QUERY_STATUS)
        wukong_pkg = self._tcp_client.read()
        if not wukong_pkg.is_valid():
            if self._silence_err:
                return default_ret
            raise Disconnected(
                "WuKongQueue Svr-addr:%s is disconnected"
                % str(self.server_addr)
            )
        return wukong_pkg.raw_data == QUEUE_EMPTY

    def connected(self) -> bool:
        """Whether it is connected to the server.
        NOTE:this api do reconnect when `auto_connect` is True, then return
        outcome of reconnection
        """

        if self._tcp_client is not None:
            self._tcp_client.write(QUEUE_PING)
            wukong_pkg = self._tcp_client.read()
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
            if not self._silence_err:
                raise Disconnected(
                    "WuKongQueue Svr-addr:%s is disconnected"
                    % str(self.server_addr)
                )
            return default_ret

        self._tcp_client.write(QUEUE_SIZE)
        wukong_pkg = self._tcp_client.read()
        if not wukong_pkg.is_valid():
            if self._silence_err:
                return default_ret
            raise Disconnected(
                "WuKongQueue Svr-addr:%s is disconnected"
                % str(self.server_addr)
            )
        ret = unwrap_queue_msg(wukong_pkg.raw_data)
        return int(ret["data"])

    def realtime_maxsize(self) -> int:
        default_ret = 0
        if self.connected() is False:
            if not self._silence_err:
                raise Disconnected(
                    "WuKongQueue Svr-addr:%s is disconnected"
                    % str(self.server_addr)
                )
            return default_ret

        self._tcp_client.write(QUEUE_MAXSIZE)
        wukong_pkg = self._tcp_client.read()
        if not wukong_pkg.is_valid():
            if self._silence_err:
                return default_ret
            raise Disconnected(
                "WuKongQueue Svr-addr:%s is disconnected"
                % str(self.server_addr)
            )
        ret = unwrap_queue_msg(wukong_pkg.raw_data)
        return int(ret["data"])

    def reset(self, max_size=0) -> bool:
        """Clear queue server and create a new queue
        server with the given max_size
        """
        default_ret = False
        if self.connected() is False:
            if not self._silence_err:
                raise Disconnected(
                    "WuKongQueue Svr-addr:%s is disconnected"
                    % str(self.server_addr)
                )
            return default_ret

        self._tcp_client.write(
            wrap_queue_msg(queue_cmd=QUEUE_RESET, args={"max_size": max_size})
        )
        wukong_pkg = self._tcp_client.read()
        if not wukong_pkg.is_valid():
            if self._silence_err:
                return default_ret
            raise Disconnected(
                "WuKongQueue Svr-addr:%s is disconnected"
                % str(self.server_addr)
            )
        return wukong_pkg.raw_data == QUEUE_OK

    def connected_clients(self) -> int:
        """Number of clients connected to the server"""
        default_ret = 0
        if self.connected() is False:
            if not self._silence_err:
                raise Disconnected(
                    "WuKongQueue Svr-addr:%s is disconnected"
                    % str(self.server_addr)
                )
            return default_ret
        self._tcp_client.write(QUEUE_CLIENTS)
        wukong_pkg = self._tcp_client.read()
        if not wukong_pkg.is_valid():
            if self._silence_err:
                return default_ret
            raise Disconnected(
                "WuKongQueue Svr-addr:%s is disconnected"
                % str(self.server_addr)
            )
        ret = unwrap_queue_msg(wukong_pkg.raw_data)
        return int(ret["data"])

    def close(self):
        """Close the connection to server, not off server"""
        if self._tcp_client is not None:
            self._tcp_client.close()

    def _do_authenticate(self, auth_key) -> bool:
        if auth_key is None:
            return True

        self._tcp_client.write(
            wrap_queue_msg(
                queue_cmd=QUEUE_AUTH_KEY, args={"auth_key": auth_key}
            )
        )
        wukong_pkg = self._tcp_client.read()
        if not wukong_pkg.is_valid():
            if self._silence_err:
                return False
            raise Disconnected(
                "WuKongQueue Svr-addr:%s is disconnected"
                % str(self.server_addr)
            )
        return wukong_pkg.raw_data == QUEUE_OK

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def helper(self):
        return helper(self)
