# -*- coding: utf-8 -*-
import logging
import sys
from unittest import TestCase

import time

sys.path.append("../")
try:
    from wukongqueue.wukongqueue import *
except ImportError:
    from wukongqueue import *

max_size = 2
host = "127.0.0.1"
default_port = 9999
port = list(range(1024, 1100))


def new_svr(host=host, port=default_port, auth=None, log_level=logging.DEBUG,
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
                p += 1
            else:
                raise e


class ClientTests(TestCase):
    def test_basic_method(self):
        """
        tested-api:
            full
            empty
            connected
        """
        svr, mport = new_svr(log_level=logging.FATAL)
        with svr.helper():
            client = WuKongQueueClient(host=host, port=mport)
            put_str = "str" * 100
            put_bytes = b"byte" * 100
            self.assertIs(client.full(), False)
            self.assertIs(client.empty(), True)

            client.put(put_str)
            client.put(put_bytes)

            self.assertRaises(
                Full, client.put, "str will raise exception", timeout=1
            )

            self.assertIs(client.full(), True)
            self.assertIs(client.empty(), False)

            self.assertEqual(client.get(), put_str)
            self.assertEqual(client.get(), put_bytes)

            self.assertIs(client.full(), False)
            self.assertIs(client.empty(), True)

            self.assertIs(client.connected(), True)
            client.close()
            self.assertIs(client.connected(), False)

            self.assertRaises(Disconnected, client.get)

    def test_connected_clients(self):
        """
        tested-api:
            connected_clients
        """
        svr, mport = new_svr(log_level=logging.FATAL)
        with svr.helper():
            # exit()
            c = []

            loop = 10
            for i in range(loop):
                client = WuKongQueueClient(host=host, port=mport)
                c.append(client)
                # print(client.connected_clients(),i+1)
                self.assertEqual(client.connected_clients(), i + 1)
            for i in range(loop):
                c[i].close()
                time.sleep(
                    0.5
                )  # We must consider the necessary network delay
                if i < loop - 1:
                    # print(c[i+1].connected_clients(), len(c)-i-1)
                    self.assertEqual(
                        c[i + 1].connected_clients(), len(c) - i - 1
                    )

    def test_reset_and_qsize(self):
        """
        tested-api:
            reset
            realtime_maxsize
            realtime_qsize
        """
        svr, mport = new_svr(log_level=logging.FATAL)
        with svr.helper():
            client = WuKongQueueClient(host=host, port=mport)
            with client.helper():
                client.reset(5)
                self.assertEqual(client.realtime_maxsize(), 5)
                client.reset(2)
                self.assertEqual(client.realtime_maxsize(), 2)
                client.put("1")
                self.assertEqual(client.realtime_qsize(), 1)
                client.put("1")
                self.assertEqual(client.realtime_qsize(), 2)
                self.assertEqual(client.full(), True)

    def test_put_get(self):
        """
        tested-api:
            put
            get
        """
        svr, mport = new_svr(log_level=logging.FATAL)
        with svr.helper():
            client = WuKongQueueClient(host=host, port=mport)
            with client.helper():
                client.reset(maxsize=1)
                client.put(block=True, timeout=1, item="1")
                # wait for 1 secs, then raises <Full> exception
                self.assertRaises(Full, client.put, item="1", timeout=1)

                self.assertEqual(client.get(), "1")
                # wait for 1 secs, then raises <Empty> exception
                self.assertRaises(
                    Empty, client.get, block=True, timeout=1
                )

    def test_run_with_multithreading(self):
        max_size = 30
        svr, mport = new_svr(max_size=max_size, log_level=logging.FATAL)

        put_strs = [str(i) for i in range(max_size)]
        Sum = sum(list(range(max_size)))

        _tmp_sum = 0

        def _thread(the_client: WuKongQueueClient):
            with the_client.helper():
                while True:
                    try:
                        item = the_client.get()
                    except Disconnected:
                        break
                    nonlocal _tmp_sum
                    _tmp_sum += int(item)
                    continue

        with svr.helper():
            clients = 10
            for i in range(clients):
                client = WuKongQueueClient(host=host, port=mport)
                new_thread(_thread, {"the_client": client})

            for str_num in put_strs:
                svr.put(str_num, block=False)

            time.sleep(2)
            self.assertEqual(Sum, _tmp_sum)

    def test_silence_err(self):
        client = WuKongQueueClient(
            host=host,
            port=65530,
            silence_err=True,
            pre_connect=True,
            auto_reconnect=True,
            log_level=logging.FATAL
        )
        with client.helper():
            self.assertIs(client.connected(), False)
            self.assertEqual(client.realtime_qsize(), 0)
            self.assertEqual(client.realtime_maxsize(), 0)
            self.assertIs(client.full() and client.empty(), False)

    def test_authenticate(self):
        svr, mport = new_svr(log_level=logging.INFO)
        with svr.helper():
            # auth_key is None, don't need authenticate
            with WuKongQueueClient(host=host, port=mport) as client:
                client.put("1")

        auth = '123'
        svr, mport = new_svr(auth=auth, log_level=logging.INFO)
        with svr.helper():
            with WuKongQueueClient(host=host,
                                   port=mport,
                                   auth_key=auth) as client:
                client.put("1")

            try:
                with WuKongQueueClient(host=host,
                                       port=mport,
                                       auth_key=auth + '1'):
                    pass
            except AuthenticationFail:
                pass

    def test_auto_conn(self):
        p = 65531
        with WuKongQueueClient(host=host,
                               port=p,
                               pre_connect=True,
                               auto_reconnect=True)as client:
            self.assertRaises(Disconnected, client.put, item='1')
            svr, mport = new_svr(port=p, log_level=logging.INFO,
                                 dont_change_port=True)
            with svr.helper():
                self.assertIs(client.connected(), True)

        # silence_err
        with WuKongQueueClient(host=host,
                               port=p,
                               auto_reconnect=True,
                               silence_err=True)as client:
            self.assertIs(None, client.put(item='1'))

    def test_join(self):
        svr, mport = new_svr(log_level=logging.INFO)
        join = False

        def do_join():
            with WuKongQueueClient(host=host, port=mport)as client:
                time.sleep(0.5)
                client.join()
                nonlocal join
                join = True

        with svr.helper():
            with WuKongQueueClient(host=host, port=mport)as client:
                new_thread(do_join)
                client.put('1')
                client.put('2')
                time.sleep(1)
                client.task_done()
                client.task_done()
                time.sleep(0.5)
                self.assertIs(join, True)
                self.assertRaises(ValueError, client.task_done)

    def test_all_type_item(self):
        svr, mport = new_svr(max_size=0, log_level=logging.INFO)
        with svr.helper():
            with WuKongQueueClient(host=host, port=mport)as client:
                test_item = [
                    b'123',
                    '123',
                    123,
                    123 - 1j,
                    123.01,
                    False,
                    [True, False, 123],
                    (True, False, 123),
                    {"1": 123, "2": True, "3": [1, 2, 3]},
                    {1, 2, 3},
                    None
                ]
                for i in test_item:
                    client.put(i)

                recv_items = []
                while True:
                    try:
                        i = client.get(block=False)
                        recv_items.append(i)
                    except Empty:
                        break
                self.assertEqual(test_item, recv_items)


if __name__ == "__main__":
    import unittest
    unittest.main()
