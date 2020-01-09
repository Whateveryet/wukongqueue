# -*- coding: utf-8 -*-

from wukongqueue.wukongqueue import WuKongQueueClient

client = WuKongQueueClient(host='127.0.0.1', port=666)
with client:
    print("got", client.get())  # b"1"
    client.task_done()
    print("after 10 seconds, got",
          client.get(block=True))  # wait for a while, then print b"2"
    client.task_done()
    print("clientA: all task done!")
