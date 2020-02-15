# -*- coding: utf-8 -*-


import time

from wukongqueue import WuKongQueue

host = '127.0.0.1'
port = 6666
max_size = 2


def start_server(h, p):
    with WuKongQueue(h, p, maxsize=max_size) as svr:
        while True:
            time.sleep(3)
            print('client number:', svr.connected_clients())


if __name__ == '__main__':
    start_server(host, port)
