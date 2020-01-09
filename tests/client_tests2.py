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
default_port = 10000


def new_svr(host=host, port=default_port, auth=None, log_level=logging.DEBUG,
            dont_change_port=False, max_size=max_size):
    p = port
    while 1:
        try:
            return WuKongQueue(
                host=host, port=port, maxsize=max_size,
                log_level=log_level,
                auth_key=auth
            ), p
        except OSError as e:
            if 'already' in str(e.args) or '只允许使用一次' in str(e.args):
                if dont_change_port is True:
                    raise e
                p += 1


class ClientTests(TestCase):
    def test_concurrent_call_block_method(self):
        max_size = 1
        svr,mport = new_svr(max_size=max_size, log_level=logging.FATAL)

        def put(c: WuKongQueueClient):
            c.put('1')
            try:
                c.put('1', block=True)
            except Disconnected:
                pass

        with svr.helper():
            client = WuKongQueueClient(host=host, port=mport)
            with client:
                new_thread(put, kw={'c': client})
                import time
                time.sleep(1)
                # client.join()
                self.assertRaises(CannotConcurrentCallBlockMethod, client.join)
                self.assertRaises(CannotConcurrentCallBlockMethod, client.put, item='1', block=True)

                while True:
                    try: # clear queue
                        client.get(block=False)
                    except:
                        break
                self.assertRaises(CannotConcurrentCallBlockMethod, client.get, block=True)
                self.assertRaises(CannotConcurrentCallBlockMethod, client.full)
                self.assertRaises(CannotConcurrentCallBlockMethod, client.empty)
                self.assertRaises(CannotConcurrentCallBlockMethod, client.task_done)
                self.assertRaises(CannotConcurrentCallBlockMethod, client.connected)
                self.assertRaises(CannotConcurrentCallBlockMethod, client.realtime_qsize)
                self.assertRaises(CannotConcurrentCallBlockMethod, client.realtime_maxsize)
                self.assertRaises(CannotConcurrentCallBlockMethod, client.reset, maxsize=1)
                self.assertRaises(CannotConcurrentCallBlockMethod, client.connected_clients)


if __name__ == '__main__':
    main()
