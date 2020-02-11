# -*- coding: utf-8 -*-

from wukongqueue import WuKongQueueClient
import sys
sys.path.append('../')

client = WuKongQueueClient(host='127.0.0.1', port=666)
with client:
    print("got", client.get())  # b"1"
    client.task_done()
    import time
    wait = 5
    time.sleep(wait)
    print("after %s seconds, got" % wait,
          client.get(block=True))  # wait for a while, then print b"2"
    client.task_done()
    print("clientA: all task done!")
