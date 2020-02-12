# -*- coding: utf-8 -*-
import time
import unittest

from wukongqueue import _commu_proto
from wukongqueue._commu_proto import *
from wukongqueue.utils import new_thread

host = 'localhost'
port = 1024

# change it before the server runs
_commu_proto.SEGMENT_MAX_SIZE = 1

send_msg = b"bye 2019; hi 2020" * 888


# send_msg = b''

def svr():
    s = TcpSvr(host, port)
    print('listening')
    while 1:
        conn, addr = s.accept()
        write_wukong_data(conn, WuKongPkg(send_msg))
        print('svr sent')
        conn.close()
        s.close()
        break


class SocketTest(unittest.TestCase):
    def test_1(self):
        new_thread(svr)
        c = TcpClient(host, port, None)
        r = c.read()
        # if not r.is_valid():
        #     print(r.err)
        time.sleep(0.1)
        self.assertEqual(r.raw_data, send_msg)
        c.close()


if __name__ == '__main__':
    unittest.main()
