# -*- coding: utf-8 -*-
import logging
import sys
from unittest import TestCase, main

import time

sys.path.append("../")
try:
    from wukongqueue.wukongqueue import *
except ImportError:
    from wukongqueue import *

max_size = 2
host = "127.0.0.1"
port = 9999


def new_svr(host=host, port=port, auth=None, log_level=logging.DEBUG):
    return WuKongQueue(
        host=host, port=port, maxsize=max_size,
        log_level=log_level,
        auth_key=auth
    )


class ClientTests(TestCase):
    def test_basic_method(self):
        """
        tested-api:
            full
            empty
            connected
        """
        global port
        port += 1
        svr = new_svr(port=port, log_level=logging.FATAL)
        with svr.helper():
            client = WuKongQueueClient(host=host, port=port)
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

            self.assertEqual(client.get(), put_str.encode())
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
        global port
        port += 1

        svr = new_svr(port=port, log_level=logging.FATAL)
        with svr.helper():
            # exit()
            c = []

            loop = 10
            for i in range(loop):
                client = WuKongQueueClient(host=host, port=port)
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
        global port
        port += 1
        svr = new_svr(port=port, log_level=logging.FATAL)
        with svr.helper():
            client = WuKongQueueClient(host=host, port=port)
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
        global port
        port += 1
        svr = new_svr(port=port, log_level=logging.FATAL)
        with svr.helper():
            client = WuKongQueueClient(host=host, port=port)
            with client.helper():
                client.reset(maxsize=1)
                client.put(block=True, timeout=1, item="1")
                # wait for 1 secs, then raises <Full> exception
                self.assertRaises(Full, client.put, item="1", timeout=1)

                self.assertEqual(client.get(), b"1")
                # wait for 1 secs, then raises <Empty> exception
                self.assertRaises(
                    Empty, client.get, block=True, timeout=1
                )

    def test_run_with_multithreading(self):
        global port, max_size
        port += 1
        max_size = 30
        svr = new_svr(port=port, log_level=logging.FATAL)

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
                client = WuKongQueueClient(host=host, port=port)
                new_thread(_thread, {"the_client": client})

            for str_num in put_strs:
                svr.put(str_num, block=False)

            time.sleep(2)
            self.assertEqual(Sum, _tmp_sum)

    def test_silence_err(self):
        global port
        port += 1
        client = WuKongQueueClient(
            host=host,
            port=port,
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
        global port
        port += 1
        # svr = new_svr(port=port, log_level=logging.INFO)
        # with svr.helper():
        #     # auth_key is None, don't need authenticate
        #     with WuKongQueueClient(host=host, port=port) as client:
        #         client.put("1")

        port += 1
        auth = '123'
        svr = new_svr(port=port, auth=auth, log_level=logging.INFO)
        with svr.helper():
            with WuKongQueueClient(host=host, port=port,
                                   auth_key=auth) as client:
                client.put("1")

            try:
                with WuKongQueueClient(host=host, port=port,
                                       auth_key=auth + '1'):
                    pass
            except AuthenticationFail:
                pass

    def test_auto_conn(self):
        global port
        port += 1
        with WuKongQueueClient(host=host, port=port, pre_connect=True,
                               auto_reconnect=True)as client:
            self.assertRaises(Disconnected, client.put, item='1')
            svr = new_svr(port=port, log_level=logging.INFO)
            with svr.helper():
                self.assertIs(client.connected(), True)

        # silence_err
        port += 1
        with WuKongQueueClient(host=host, port=port,
                               auto_reconnect=True, silence_err=True)as client:
            self.assertIs(None, client.put(item='1'))

    def test_join(self):
        global port
        port += 1
        svr = new_svr(port=port, log_level=logging.INFO)
        join = False

        def do_join():
            with WuKongQueueClient(host=host, port=port)as client:
                time.sleep(0.5)
                client.join()
                nonlocal join
                join = True

        with svr.helper():
            with WuKongQueueClient(host=host, port=port)as client:
                new_thread(do_join)
                client.put('1')
                client.put('2')
                time.sleep(1)
                client.task_done()
                client.task_done()
                time.sleep(0.5)
                self.assertIs(join, True)
                self.assertRaises(ValueError, client.task_done)


if __name__ == "__main__":
    main()
