# -*- coding: utf-8 -*-

from wukongqueue.wukongqueue import WuKongQueueClient

client = WuKongQueueClient(host='127.0.0.1', port=666)
with client:
    client.join()
    print("clientB all task done!")
