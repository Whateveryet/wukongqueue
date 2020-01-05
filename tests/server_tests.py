# -*- coding: utf-8 -*-
import logging
import sys
from unittest import TestCase, main

sys.path.append("../")
try:
    from wukongqueue.wukongqueue import *
except ImportError:
    from wukongqueue import *

max_size = 2
host = "127.0.0.1"
port = 9918


def new_svr(host=host, port=port, max_clients=0, log_level=logging.DEBUG):
    return WuKongQueue(host=host, port=port, max_size=max_size,
                       max_clients=max_clients, log_level=log_level)


class ServerTests(TestCase):
    def test_basic_method(self):
        """
        tested-api:
            full
            empty
            close
        """
        svr = new_svr(log_level=logging.WARNING)
        with svr.helper():
            put_str = "str" * 100
            put_bytes = b"byte" * 100

            svr.put(put_str)
            svr.put(put_bytes)

            self.assertRaises(Full, svr.put, item="1", block=False)
            self.assertIs(svr.full(), True)
            self.assertIs(svr.empty(), False)
            self.assertEqual(svr.get(), put_str.encode())
            self.assertEqual(svr.get(), put_bytes)

            svr.close()
            self.assertIs(svr.put(put_bytes), None)
            self.assertIs(svr.closed, True)

    def test_other(self):
        """
        tested-api:
            reset
            qsize
            max_size
            close
        """
        global port
        port += 1
        svr = new_svr(port=port, log_level=logging.WARNING)
        with svr.helper():
            self.assertEqual(svr.qsize(), 0)
            svr.put("1")
            svr.put("1")
            self.assertEqual(svr.qsize(), 2)
            self.assertRaises(Full, svr.put, item="1", block=False)
            self.assertEqual(svr.max_size, 2)
            svr.reset(3)
            self.assertEqual(svr.max_size, 3)
            for i in range(3):
                svr.put("1")
            self.assertIs(svr.full(), True)

            client = WuKongQueueClient(host=host, port=port)
            self.assertIs(client.connected(), True)
            svr.close()
            self.assertIs(client.connected(), False)
            client.close()

    def test_port_conflict(self):
        global port
        port += 1
        with new_svr(port=port, log_level=logging.WARNING):
            pass
            # self.assertRaises(OSError, new_svr, port=port)

    def test_max_clients(self):
        global port
        port += 1
        svr = new_svr(port=port, max_clients=1, log_level=logging.DEBUG)
        with svr.helper():
            with WuKongQueueClient(host=host, port=port):
                try:
                    with WuKongQueueClient(host=host, port=port):
                        pass
                except ClientsFull:
                    pass


if __name__ == "__main__":
    main()
