# -*- coding: utf-8 -*-

import logging
import socket
import threading
import time

from ._commu_proto import *
from .exceptions import (
    WuKongError,
    ConnectionTimeout,
    ConnectionError,
    ClientsFull,
    UnknownResponse,
    AuthenticationError,
)
from .utils import get_logger


class Connection:
    """Tcp connection management, thread safe"""

    def __init__(
        self,
        host,
        port,
        auth_key=None,
        check_health_interval=30,
        socket_timeout=None,
        socket_connect_timeout=None,
        silence_err=True,
        logger=None,
        encoding=None,
        encoding_err=None,
    ):
        # validate these args outside.
        self.server_addr = (host, port)
        self.socket_timeout = socket_timeout
        self.socket_connect_timeout = socket_connect_timeout or socket_timeout
        self.auth_key = auth_key
        self.check_health_interval = 30
        if isinstance(check_health_interval, int) and check_health_interval > 0:
            self.check_health_interval = check_health_interval
        self._logger = logger or get_logger(self, logging.DEBUG)
        self._silence_err = silence_err
        self._tcp_client = None
        self._last_check_health_time = int(time.time())
        self._lock = threading.Lock()

        # self._encoding = encoding
        # self._encoding_err = encoding_err

    def __repr__(self):
        identity_kv = [("server_addr", self.server_addr), ("id", id(self))]
        repr_str = ",".join(["%s=%s" % (k, v) for k, v in identity_kv])
        return "%s<%s>" % (type(self).__name__, repr_str)

    def connect(self, force=False):
        if self._tcp_client:
            if not force:
                return
            self.close()

        try:
            tcp_client = self._connect()
        except socket.timeout:
            raise ConnectionTimeout("Timeout connecting to server")
        except socket.error as e:
            raise ConnectionError(
                "Error to connect %s, %s" % (self.server_addr, e.args)
            )
        except WuKongError:
            raise

        self._tcp_client = tcp_client
        try:
            self.on_connected()
        except WuKongError:
            self.close()
            raise

        self._logger.info("successfully connect to %s!" % str(self.server_addr))

    def _connect(self):
        tcp_client = None
        try:
            tcp_client = TcpClient(
                *self.server_addr, self.socket_connect_timeout
            )
            tcp_client.sock.settimeout(self.socket_timeout)
            wukong_pkg = tcp_client.read()
            if wukong_pkg.err:
                raise ConnectionError(wukong_pkg.err)
            elif wukong_pkg.is_socket_closed:
                raise ClientsFull(
                    "The WuKongQueue server %s is full" % str(self.server_addr)
                )
            elif wukong_pkg.raw_data == QUEUE_HI:
                return tcp_client
            else:
                raise UnknownResponse(
                    "_connect Unknown response:%s" % wukong_pkg.raw_data
                )
        except (WuKongError, socket.error):
            if tcp_client:
                tcp_client.close()
            raise

    def on_connected(self):
        if self.auth_key is not None:
            msg = wrap_queue_msg(
                queue_cmd=QUEUE_AUTH_KEY, args={"auth_key": self.auth_key}
            )
            reply_msg = self.talk_with_svr(msg)
            if not reply_msg.is_valid():
                raise ConnectionError
            if reply_msg.raw_data != QUEUE_OK:
                raise AuthenticationError(
                    "WuKongQueue server-addr:%s "
                    "authentication failed" % str(self.server_addr)
                )

    def on_disconnected(self, exception=None, err_msg=""):
        err_msg = "%s%s" % (", " if err_msg != "" else "", err_msg)
        m = "WuKongQueue server-addr:%s is disconnected%s" % (
            str(self.server_addr),
            err_msg,
        )
        if self._silence_err:
            self._logger.warning(m)
        else:
            if exception:
                raise exception
            raise ConnectionError(m)

    def close(self):
        if self._tcp_client:
            self._tcp_client.close()
            self._tcp_client = None

    def check_health(self):
        self._last_check_health_time = int(time.time())
        if self._tcp_client is not None:
            reply_msg = self.talk_with_svr(QUEUE_PING, check_health=False)
            if not reply_msg.is_valid():
                err_msg = reply_msg.err
                if reply_msg.is_socket_closed:
                    err_msg = "socket is closed"
                raise ConnectionError(err_msg)
            if reply_msg.raw_data != QUEUE_PONG:
                raise UnknownResponse(
                    "check_health, Unknown response:%s" % reply_msg.raw_data
                )
            return True
        self.connect()
        return True

    def talk_with_svr(self, msg: bytes, check_health=True) -> WuKongPkg:
        if (
            int(time.time()) - self._last_check_health_time
            >= self.check_health_interval
        ):
            if check_health:
                self.check_health()

        if self._tcp_client is None:
            if check_health:
                self.check_health()

        acquired = self._lock.acquire(blocking=True, timeout=0.1)
        try:
            if acquired:
                self._tcp_client.write(msg)
                return self._tcp_client.read()
            # if has only single connection,
            # Do not call blocking method concurrently
            raise ConnectionError("No available connection")
        finally:
            if acquired:
                self._lock.release()


class ConnectionPool:
    """
    ConnectionPool object will be used by WuKongQueueClient.

    connection_cls: tcp connection management class

    max_connections: if max_connections > 0, it will be set up,
    there raises wukongqueue.ConnectionError when the pool's
    limit is reached

    connection_kwargs: constructed from the outside, it will be
    passed to connection_cls.__init__
    """

    def __init__(
        self, connection_cls=Connection, max_connections=0, **connection_kwargs
    ):
        self.max_connections = 0
        if isinstance(max_connections, int) and max_connections >= 0:
            self.max_connections = max_connections

        self.connection_cls = connection_cls
        self.connection_kwargs = connection_kwargs

        self.server_addr = (
            connection_kwargs.get("host"),
            connection_kwargs.get("port"),
        )

        self._lock = threading.RLock()
        self._created_connections = 0
        self._available_connections = []
        self._in_use_connections = set()
        self.closed = False

    def __repr__(self):
        return "%s<%s>" % (
            type(self).__name__,
            repr(self.connection_cls(**self.connection_kwargs)),
        )

    def _create_connection(self):
        """sub method"""
        if self.max_connections > 0:
            if self._created_connections >= self.max_connections:
                raise ConnectionError("Too many connections")
        self._created_connections += 1
        return self.connection_cls(**self.connection_kwargs)

    def release_connection(self, connection):
        with self._lock:
            self._in_use_connections.remove(connection)
            self._available_connections.append(connection)

    def get_connection(self):
        with self._lock:
            if self.closed:
                raise ConnectionError("The pool is closed")
            if len(self._available_connections) > 0:
                conn = self._available_connections.pop()
            else:
                conn = self._create_connection()
            self._in_use_connections.add(conn)
            try:
                conn.connect()
                return conn
            except WuKongError as e:
                self.release_connection(conn)
                try:
                    conn.on_disconnected(exception=e, err_msg=str(e.args))
                except WuKongError:
                    raise
            return

    def close(self):
        with self._lock:
            for conn in self._available_connections + list(
                self._in_use_connections
            ):
                conn.close()
            self.closed = True
