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
port = 10000


def new_svr(host=host, port=port, auth=None, max_size=max_size,
            log_level=logging.DEBUG):
    return WuKongQueue(
        host=host, port=port, maxsize=max_size,
        log_level=log_level,
        auth_key=auth
    )


class ClientTests(TestCase):
    def test_concurrent_call_block_method(self):
        global port
        port += 1
        max_size = 1
        svr = new_svr(port=port, max_size=max_size, log_level=logging.FATAL)

        def put(c: WuKongQueueClient):
            c.put('1')
            try:
                c.put('1', block=True)
            except Disconnected:
                pass

        with svr.helper():
            client = WuKongQueueClient(host=host, port=port)
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
