# -*- coding: utf-8 -*-

import logging

from ._commu_proto import *
from .connection import ConnectionPool
from .exceptions import (
    NotYetSupportType,
    Empty,
    Full,
    ConnectionError,
    WuKongError,
)
from .utils import Unify_encoding, get_logger, md5, helper


class WuKongQueueClient:
    def __init__(
        self,
        host="localhost",
        port=8848,
        auth_key=None,
        socket_connect_timeout=None,
        connection_pool=None,
        silence_err=False,
        **kwargs
    ):
        """
        :param host: host
        :param port: port
        :param auth_key: str used for server side authentication, it will be
        encrypted for transmission over the network
        :param silence_err:when connection is not ready yet or disconnected,
        most of apis raises ConnectionError by default; if silence_err is set
        to True, apis returns default value, and logs error info to stderr
        :param socket_connect_timeout: maximum time to establish connection with
        server, raises ConnectionTimeout if time out; but not raises exception
        if silence_err is set to True
        :param connection_pool: use connection pool to improve efficiency in a
        multi-threaded environment by default

        A number of optional keyword arguments may be specified, which
        can alter the default behaviour

        log_level: pass with stdlib logging.DEBUG/INFO/WARNING.., to
        control the WuKongQueue's logging level that output to stderr

        connection_cls: tcp connection management class

        check_health_interval: in seconds, if the time from last time of check
        health exceeds `check_health_interval`, client will check if the
        connection is health, see the default value in wukongqueue.Connection
        class

        single_connection_client: use connection pool with no limitation to
        connections by default, you can use only single connection by set
        this arg to True

        encoding: unified encoding standard

        encoding_error: set a different error handling scheme
        """

        self._logger = get_logger(self, kwargs.pop("log_level", logging.DEBUG))
        self.server_addr = (host, port)

        encoding = kwargs.pop("encoding", Unify_encoding)
        encoding_err = kwargs.pop("encoding_err", "strict")

        self._is_new_pool = True
        if connection_pool is None:
            auth_key = (
                auth_key
                if auth_key is None
                else md5(
                    auth_key.encode(encoding=encoding, errors=encoding_err)
                )
            )
            check_health_interval = kwargs.pop("check_health_interval", None)
            connection_kwargs = {
                "host": host,
                "port": port,
                "auth_key": auth_key,
                "socket_connect_timeout": socket_connect_timeout,
                "check_health_interval": check_health_interval,
                "silence_err": silence_err,
                "logger": self._logger,
                "socket_timeout": kwargs.pop("socket_timeout", None),
                "max_connections": kwargs.pop("max_connections", 0),
                "encoding": encoding,
                "encoding_err": encoding_err,
            }

            self._is_new_pool = False
            connection_pool = ConnectionPool(**connection_kwargs)
        else:
            self.server_addr = connection_pool.server_addr
        self.connection_pool = connection_pool
        self.connection = None

        single_connection_client = kwargs.pop("single_connection_client", False)
        if single_connection_client:
            self.connection = self.connection_pool.get_connection()

    def put(self, item, block=True, timeout=None):
        """
        :param item: put an item to queue server
        :param block: see also WuKongQueue.put
        :param timeout: see also WuKongQueue.put
        """
        assert type(timeout) in [int, float, type(None)], (
            "invalid timeout %s" % timeout
        )
        try:
            cmd = wrap_queue_msg(
                queue_cmd=QUEUE_PUT,
                args={"block": block, "timeout": timeout},
                data=item,
            )
        except Exception as e:
            raise NotYetSupportType(
                "%s is not supported yet, wrapping err:%s %s"
                % (type(item), e, e.args)
            )

        reply_msg = self._send_command(cmd)
        if reply_msg is None:
            return
        elif reply_msg.raw_data == QUEUE_FULL:
            raise Full(
                "WuKongQueue server-addr:%s is full" % str(self.server_addr)
            )

    def get(self, block=True, timeout=None, convert_method=None):
        """
        :param block: see also WuKongQueue.get
        :param timeout: see also WuKongQueue.get
        :param convert_method: callable object to convert item
        :return: AnyType

        Note: if self.silence_err is set to True, return None when disconnected
        """
        if convert_method:
            assert callable(convert_method), (
                "not a callable obj:%s" % convert_method
            )

        assert type(timeout) in [int, float, type(None)], (
            "invalid timeout %s" % timeout
        )

        cmd = wrap_queue_msg(
            queue_cmd=QUEUE_GET, args={"block": block, "timeout": timeout}
        )
        reply_msg = self._send_command(cmd)
        if reply_msg is None:
            return
        elif reply_msg.raw_data == QUEUE_EMPTY:
            raise Empty(
                "WuKongQueue server-addr:%s is empty" % str(self.server_addr)
            )
        reply_msg.unwrap()
        item = reply_msg.queue_params_object.data

        if convert_method:
            return convert_method(item)
        return item

    def full(self):
        """Whether the queue is full"""
        default_ret = False
        reply_msg = self._send_command(QUEUE_QUERY_STATUS)
        if reply_msg is None:
            return default_ret
        return reply_msg.raw_data == QUEUE_FULL

    def empty(self):
        """Whether the queue is empty"""
        default_ret = True
        reply_msg = self._send_command(QUEUE_QUERY_STATUS)
        if reply_msg is None:
            return default_ret
        return reply_msg.raw_data == QUEUE_EMPTY

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
        """
        reply_msg = self._send_command(QUEUE_TASK_DONE)
        if reply_msg is None:
            return
        reply_msg.unwrap()
        if reply_msg.queue_params_object.cmd == QUEUE_OK:
            return
        else:
            raise reply_msg.queue_params_object.exception

    def join(self):
        """Blocks until all items in the Queue have been gotten and processed.

        The count of unfinished tasks goes up whenever an item is added to the
        queue. The count goes down whenever a consumer thread calls task_done()
        to indicate the item was retrieved and all work on it is complete.

        When the count of unfinished tasks drops to zero, join() unblocks.
        """
        self._send_command(QUEUE_JOIN)

    def realtime_qsize(self):
        default_ret = 0
        reply_msg = self._send_command(QUEUE_SIZE)
        if reply_msg is None:
            return default_ret
        reply_msg.unwrap()
        return reply_msg.queue_params_object.data

    def realtime_maxsize(self):
        default_ret = 0
        reply_msg = self._send_command(QUEUE_MAXSIZE)
        if reply_msg is None:
            return default_ret
        reply_msg.unwrap()
        return reply_msg.queue_params_object.data

    def reset(self, maxsize=0):
        """reset clear queue server and reset maxsize"""
        default_ret = False
        msg = wrap_queue_msg(queue_cmd=QUEUE_RESET, args={"maxsize": maxsize})
        reply_msg = self._send_command(msg)
        if reply_msg is None:
            return default_ret
        return reply_msg.raw_data == QUEUE_OK

    def connected_clients(self):
        default_ret = 0
        reply_msg = self._send_command(QUEUE_CLIENTS)
        if reply_msg is None:
            return default_ret
        reply_msg.unwrap()
        return reply_msg.queue_params_object.data

    def connected(self):
        try:
            reply_msg = self._send_command(QUEUE_PING)
        except ConnectionError:
            return False
        if reply_msg is None:
            return False
        return reply_msg.raw_data == QUEUE_PONG

    def _release_conn(self, conn):
        # release connection except single connection
        if self.connection is None:
            self.connection_pool.release_connection(conn)

    def _send_command(self, cmd_bytes):
        conn = self.connection or self.connection_pool.get_connection()
        if conn is None:
            # it's released, no need to release again
            return
        try:
            reply_msg = conn.talk_with_svr(cmd_bytes)
        except WuKongError as e:
            self._release_conn(conn)
            conn.on_disconnected(exception=e, err_msg=str(e.args))
            return

        if not reply_msg.is_valid():
            self._release_conn(conn)
            conn.on_disconnected(err_msg=reply_msg.err)
            return

        self._release_conn(conn)
        return reply_msg

    def close(self):
        """close the connection to server, not off server"""
        if self.connection:
            self.connection_pool.release_connection(self.connection)
            self.connection = None
        if not self._is_new_pool:
            self.connection_pool.close()

    def helper(self):
        """If the place client created isn't same with using,
        you may use helper to close client easier, like this:
        ```
        with client.helper():
            ...
        # this is equivalent to use below:
        with client:
            ...
        ```
        """
        return helper(self)

    def __repr__(self):
        return "%s<pool:%s>" % (type(self).__name__, self.connection_pool)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
