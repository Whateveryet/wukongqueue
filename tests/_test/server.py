# -*- coding: utf-8 -*-

import time
from wukongqueue.wukongqueue import WuKongQueue

# start a queue server
svr = WuKongQueue(host='127.0.0.1', port=666, max_conns=10, max_size=0)
with svr:
    print("svr is started!")
    svr.put(b"1")
    time.sleep(10)
    svr.put(b"2")
    print("wait for clients...")
    time.sleep(10)
print("putted b'1' and b'2', svr closed!")
