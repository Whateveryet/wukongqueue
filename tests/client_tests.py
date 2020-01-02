# -*- coding: utf-8 -*-
from unittest import TestCase, main

import logging
import sys
import time

sys.path.append("../")
try:
    from wukongqueue.wukongqueue import *
except ImportError:
    from wukongqueue import *

max_size = 2
host = "127.0.0.1"
port = 9918


def new_svr(host=host, port=port):
    return WuKongQueue(
        host=host, port=port, max_conns=10, max_size=max_size, log_level=logging.INFO
    )


class ClientTests(TestCase):
    def test_basic_method(self):
        """
        tested-api:
            full
            empty
            connected
        """
        svr = new_svr()
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

        svr = new_svr(port=port)
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
        svr = new_svr(port=port)
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
        svr = new_svr(port=port)
        with svr.helper():
            client = WuKongQueueClient(host=host, port=port)
            with client.helper():
                client.reset(max_size=1)
                client.put(block=True, timeout=1, item="1")
                # wait for 3 secs, then raises <Full> exception
                self.assertRaises(Full, client.put, item="1", timeout=3)

                self.assertEqual(client.get(), b"1")
                # wait for 3 secs, then raises <Empty> exception
                self.assertRaises(
                    Empty, client.get, block=True, timeout=3
                )

    def test_run_with_multithreading(self):
        global port, max_size
        port += 1
        max_size = 30
        svr = new_svr(port=port)

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
        time.sleep(1)
        global port
        port += 1
        client = WuKongQueueClient(
            host=host,
            port=port,
            silence_err=True,
            pre_connect=True,
            auto_reconnect=True,
            log_level=logging.DEBUG
        )
        with client.helper():
            self.assertRaises(Disconnected, client.put, item="1")
            self.assertRaises(Disconnected, client.get)
            self.assertIs(client.connected(), False)
            self.assertEqual(client.realtime_qsize(), 0)
            self.assertEqual(client.realtime_maxsize(), 0)
            self.assertIs(client.full() and client.empty(), False)


if __name__ == "__main__":
    main()
