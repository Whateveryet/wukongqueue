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
default_port = 9999
port = list(range(1024, 1100))


def new_svr(host=host, port=default_port, max_clients=0, log_level=logging.DEBUG):
    return WuKongQueue(host=host, port=port, maxsize=max_size,
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
        mport = port.pop()
        svr = new_svr(port=mport, log_level=logging.WARNING)
        with svr.helper():
            self.assertEqual(svr.qsize(), 0)
            svr.put("1")
            svr.put("1")
            self.assertEqual(svr.qsize(), 2)
            self.assertRaises(Full, svr.put, item="1", block=False)
            self.assertEqual(svr.maxsize, 2)
            svr.reset(3)
            self.assertEqual(svr.maxsize, 3)
            for i in range(3):
                svr.put("1")
            self.assertIs(svr.full(), True)

            client = WuKongQueueClient(host=host, port=mport)
            self.assertIs(client.connected(), True)
            svr.close()
            self.assertIs(client.connected(), False)
            client.close()

    def test_port_conflict(self):
        global port
        mport = port.pop()
        with new_svr(port=mport, log_level=logging.WARNING):
            self.assertRaises(OSError, new_svr, port=mport)

    def test_max_clients(self):
        global port
        mport = port.pop()
        svr = new_svr(port=mport, max_clients=1, log_level=logging.WARNING)
        with svr.helper():
            with WuKongQueueClient(host=host, port=mport,
                                   log_level=logging.WARNING):
                try:
                    with WuKongQueueClient(host=host, port=mport,
                                           log_level=logging.WARNING):
                        pass
                except ClientsFull:
                    pass
        svr = new_svr(port=mport, log_level=logging.WARNING)
        with svr.helper():
            with WuKongQueueClient(host=host, port=mport,
                                   log_level=logging.WARNING):
                with WuKongQueueClient(host=host, port=mport,
                                       log_level=logging.WARNING):
                    with WuKongQueueClient(host=host, port=mport,
                                           log_level=logging.WARNING):
                        pass

    def test_join(self):
        global port
        mport = port.pop()

        join = False
        import time

        def do_join(s: WuKongQueue):
            import time
            time.sleep(0.5)
            s.join()
            nonlocal join
            join = True

        svr = new_svr(port=mport, log_level=logging.WARNING)
        with svr.helper():
            new_thread(do_join, kw={'s': svr})
            svr.put('1')
            svr.put('2')
            time.sleep(1)
            svr.task_done()
            svr.task_done()
            time.sleep(0.5)
            self.assertIs(join, True)
            self.assertRaises(ValueError, svr.task_done)


if __name__ == "__main__":
    main()
