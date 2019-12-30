# -*- coding: utf-8 -*-
import sys
from unittest import TestCase, main
sys.path.append('../')
from wukongqueue.wukongqueue import *

max_size = 2
host = '127.0.0.1'
port = 918


def new_svr(host=host, port=port):
    return WuKongQueue(host=host, port=port, max_size=max_size)


class ServerTests(TestCase):
    def test_basic_method(self):
        """
        tested-api:
            full
            empty
            close
        """
        svr = new_svr()
        with svr.helper():
            put_str = 'str' * 100
            put_bytes = b'byte' * 100

            svr.put(put_str)
            svr.put(put_bytes)

            self.assertRaises(Full, svr.put, item='1', block=False)
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
        svr = new_svr(port=port)
        with svr.helper():
            self.assertEqual(svr.qsize(), 0)
            svr.put('1')
            svr.put('1')
            self.assertEqual(svr.qsize(), 2)
            self.assertRaises(Full, svr.put, item='1', block=False)
            self.assertEqual(svr.max_size, 2)
            svr.reset(3)
            self.assertEqual(svr.max_size, 3)
            for i in range(3):
                svr.put('1')
            self.assertIs(svr.full(), True)

            client = WuKongQueueClient(host=host, port=port)
            self.assertIs(client.connected(), True)
            svr.close()
            self.assertIs(client.connected(), False)
            client.close()


if __name__ == '__main__':
    main()
