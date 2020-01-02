# -*- coding: utf-8 -*-

import socket,sys,time
sys.path.append("../")
try:
    from wukongqueue.wukongqueue import *
except ImportError:
    from wukongqueue import *

host = '127.0.0.1'
port = 6666


def new_svr():
    skt = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    with skt:
        skt.bind((host, port))
        skt.listen(3)
        conn, addr = skt.accept()
        print('new conn:', conn.getsockname())
        recv = conn.recv(1024)
        print('recv', recv)


def new_client():
    skt = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    with skt:
        skt.connect((host, port))
        skt.send(b'hello')

def test():
    new_thread(new_svr, )
    time.sleep(1)
    new_client()
    time.sleep(2)


if __name__ == '__main__':
    test()