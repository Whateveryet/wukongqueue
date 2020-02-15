# -*- coding: utf-8 -*-

import time

from wukongqueue import WuKongQueueClient, Full

host = '127.0.0.1'
port = 6666


def start_client(h, p):
    client = WuKongQueueClient(h, p)
    with client.helper():
        print('server addr', client.server_addr)
        print('is client connected to server?', client.connected())

        for i in range(10):
            if client.connected():
                print('client is already connected to server')
                break
            print('please start server~')
            time.sleep(1)

        client.put(item='1', block=True)
        print('put 1')
        item = client.get(block=True)
        print('client recv:', item)

        try:
            for i in range(3):
                client.put('1', block=False)
        except Full:
            print('server is full! then reset maxsize to 2')
            if client.reset(2):
                print('reset ok')
            print('check realtime_maxsize:', client.realtime_maxsize())
        for i in range(2):
            client.put('1')
        print('check realtime_qsize:', client.realtime_qsize())

        for i in range(2):
            client.get()

        print('is empty?', client.empty())

        time.sleep(3)


if __name__ == '__main__':
    start_client(host, port)
