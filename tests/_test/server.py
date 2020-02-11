# -*- coding: utf-8 -*-

import time
from wukongqueue import WuKongQueue

wait = 10
if __name__ == '__main__':
    # start a queue server
    svr = WuKongQueue(host='127.0.0.1', port=666, max_conns=10, max_size=0)
    with svr:
        print("svr is started!")
        svr.put(b"1")
        svr.put(b"2")
        print("putted b'1' and b'2', wait for clients...")
        time.sleep(10)
    print("svr closed!")
