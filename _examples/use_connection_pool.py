# -*- coding: utf-8 -*-
"""
Examples for wukongqueue: Connection pool
"""
import logging

from wukongqueue import WuKongQueueClient, WuKongQueue
from wukongqueue.connection import ConnectionPool


def init_server():
    host, port = "localhost", 2020
    return WuKongQueue(host=host, port=port, log_level=logging.ERROR)


# use `ConnectionPool`, you must set host,port
# `max_connections` is 0 (no limits) by default,
# but you should set a proper value on your system
# usage about wukongqueue
def ex_1():
    with init_server():
        pool = ConnectionPool(host="localhost", port=2020, max_connections=3,
                              log_level=logging.ERROR)
        with WuKongQueueClient(connection_pool=pool)as client:
            # use connection pool in a multi-threaded environment generally.
            client.put(1)
            print(client.get() == 1)


def ex_2():
    # Set params `single_connection_client` to true in a
    # single-threaded env.
    # params `single_connection_client` is equivalent to
    # ConnectionPool(max_connections=1), it means always
    # has one connection from client started; if you called
    # client.get(block=True), then call client.put(item, block=True)
    # or any other blocking method,there raises
    # ConnectionError(no available connection)
    with init_server():
        with WuKongQueueClient(host="localhost", port=2020,
                               log_level=logging.ERROR,
                               single_connection_client=True) as client:
            client.put(1)
            print(client.get() == 1)


if __name__ == '__main__':
    ex_1()
    ex_2()
