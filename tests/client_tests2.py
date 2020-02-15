import logging
import sys
import time
from unittest import TestCase, main

sys.path.append("../")
try:
    from wukongqueue.wukongqueue import *
except ImportError:
    from wukongqueue import *

max_size = 2
host = "127.0.0.1"
default_port = 10000

_check_health_port = 10010

skip_ports = [_check_health_port]


def new_svr(host=host, port=default_port, specific=False, auth=None,
            log_level=logging.DEBUG,
            dont_change_port=False, max_size=max_size):
    p = port
    while 1:
        try:
            return WuKongQueue(
                host=host, port=p, maxsize=max_size,
                log_level=log_level,
                auth_key=auth
            ), p
        except OSError as e:
            if 'already' in str(e.args) or '只允许使用一次' in str(e.args):
                if dont_change_port is True:
                    raise e
                if p >= 65535:
                    raise e
                while True:
                    p += 1
                    if p in skip_ports:
                        if specific:
                            break
                    else:
                        break
            else:
                raise e


class ClientTests(TestCase):
    # Can't call block method such as join/put(block=True) concurrently within
    # single connection.
    def atest_concurrent_call_block_method(self):
        max_size = 1
        svr, mport = new_svr(max_size=max_size, log_level=logging.FATAL)

        def put(c: WuKongQueueClient):
            c.put('1')
            try:
                c.put('1', block=True)
            except ConnectionError:
                pass

        with svr.helper():
            client = WuKongQueueClient(host=host, port=mport,
                                       log_level=logging.FATAL,
                                       single_connection_client=True)
            with client:
                new_thread(put, kw={'c': client})
                import time
                time.sleep(0.1)
                self.assertRaises(ConnectionError, client.join)
                self.assertRaises(ConnectionError, client.put,
                                  item='1', block=True)
                self.assertRaises(ConnectionError, client.get, block=True)
                self.assertRaises(ConnectionError, client.full)
                self.assertRaises(ConnectionError, client.empty)
                self.assertRaises(ConnectionError, client.task_done)
                self.assertRaises(ConnectionError, client.realtime_qsize)
                self.assertRaises(ConnectionError, client.realtime_maxsize)
                self.assertRaises(ConnectionError, client.reset, maxsize=1)
                self.assertRaises(ConnectionError, client.connected_clients)

                # release a item, then client unblocks
                svr.get()
                client.get() and client.full() and client.empty()
                client.task_done() and client.realtime_qsize()
                client.connected_clients()

    def atest_connection_pool(self):
        max_size = 0
        svr, mport = new_svr(max_size=max_size, log_level=logging.FATAL)
        with svr.helper():
            svr.put(1)

            max_connections = 5
            pool = ConnectionPool(host=host, port=mport,
                                  silence_err=True,
                                  log_level=logging.FATAL,
                                  max_connections=max_connections)
            client = WuKongQueueClient(connection_pool=pool,
                                       log_level=logging.FATAL)
            with client:
                def concurrent_join(c: WuKongQueueClient, seq):
                    if seq == max_connections:
                        # up to max connections
                        self.assertRaises(ConnectionError, c.join)
                        return
                    self.assertEqual(c.join(), None)

                # call with six connections
                for i in range(max_connections + 1):
                    new_thread(concurrent_join, kw={"c": client, "seq": i})
                    time.sleep(0.1)

                # same pool
                new_client = WuKongQueueClient(connection_pool=pool)
                self.assertRaises(ConnectionError, new_client.join)
                new_client.close()

                # new pool
                new_client = WuKongQueueClient(host=host, port=mport)
                new_client.get()
                new_client.task_done()
                new_client.close()

                pool.close()

                time.sleep(2)

    def test_check_health(self):
        svr, mport = new_svr(port=_check_health_port,
                             specific=True,
                             dont_change_port=True,
                             max_size=max_size,
                             log_level=logging.WARNING)

        client = WuKongQueueClient(host=host,
                                   port=mport,
                                   log_level=logging.WARNING,
                                   check_health_interval=2)
        with client:
            with svr:
                client.full()
            self.assertRaises(ConnectionError, client.full)
            self.assertRaises(ConnectionError, client.full)
            svr.run()
            time.sleep(1)
            # it's not health check time
            self.assertRaises(ConnectionError, client.full)
            time.sleep(1)
            # health check time is up, then try recover connection
            client.full()


if __name__ == '__main__':
    main()
