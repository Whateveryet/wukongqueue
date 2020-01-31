# Protocol of communication

import json
import socket
from base64 import b64encode, b64decode
from copy import deepcopy

from ._item_wrapper import item_wrapper, item_unwrap

__all__ = [
    "read_wukong_data",
    "write_wukong_data",
    "WukongPkg",
    "TcpSvr",
    "TcpClient",
    "wrap_queue_msg",
    "unwrap_queue_msg",
    "QUEUE_HI",
    "QUEUE_AUTH_KEY",
    "QUEUE_NEED_AUTH",
    "QUEUE_AUTH_FAIL",
    "QUEUE_FULL",
    "QUEUE_GET",
    "QUEUE_PUT",
    "QUEUE_EMPTY",
    "QUEUE_NORMAL",
    "QUEUE_QUERY_STATUS",
    "QUEUE_OK",
    "QUEUE_FAIL",
    "QUEUE_PING",
    "QUEUE_PONG",
    "QUEUE_DATA",
    "QUEUE_SIZE",
    "QUEUE_MAXSIZE",
    "QUEUE_RESET",
    "QUEUE_CLIENTS",
    "QUEUE_TASK_DONE",
    "QUEUE_JOIN",
]


class SupportBytesOnly(Exception):
    pass


# stream delimiter
delimiter = b"bye:)"
delimiter_escape = b"bye:]"
delimiter_len = len(delimiter)


class WukongPkg:
    """customized communication msg package"""

    def __init__(
            self, msg: bytes = b"", err=None, closed=False, encoding="utf8"
    ):
        """
        :param msg: raw bytes
        :param err: error encountered reading socket
        :param closed: whether the socket is closed.
        """
        if not isinstance(msg, bytes):
            raise SupportBytesOnly("Support bytes only")
        self.raw_data = msg
        self.err = err
        self.encoding = encoding
        self.closed = closed

    def __repr__(self):
        return self.raw_data.decode(encoding=self.encoding)

    def __bool__(self):
        return len(self.raw_data) > 0

    def is_valid(self) -> bool:
        return any([self.closed, self.err]) is False


# max read/write to 4KB
MAX_BYTES = 1 << 12

# buffer
_STREAM_BUFFER = []


def read_wukong_data(conn: socket.socket) -> WukongPkg:
    """Block read from tcp socket connection"""
    global _STREAM_BUFFER

    buffer = deepcopy(_STREAM_BUFFER)
    _STREAM_BUFFER.clear()

    while True:
        try:
            data = conn.recv(MAX_BYTES)
        except Exception as e:
            return WukongPkg(err="%s,%s" % (e.__class__, e.args))
        # if data is empty byte,that represents the conn was closed by peer.
        if data == b"":
            return WukongPkg(closed=True)

        bye_index = data.find(delimiter)
        if bye_index == -1:
            buffer.append(data)
            continue

        buffer.append(data[:bye_index])
        if len(data) < bye_index + delimiter_len:
            _STREAM_BUFFER.append(data[bye_index + delimiter_len:])
        break
    msg = b"".join(buffer).replace(delimiter_escape, delimiter)
    ret = WukongPkg(msg)
    return ret


def write_wukong_data(conn: socket.socket, msg: WukongPkg) -> (bool, str):
    """NOTE: Sending an empty string is allowed"""

    # `+delimiter` ensure never send a empty byte to peer
    _bytes_msg = msg.raw_data.replace(delimiter, delimiter_escape) + delimiter
    _bytes_msg_len = len(_bytes_msg)
    sent_index = -1
    err = ""

    def _send_msg(msg: bytes):
        try:
            conn.send(msg)
            return True
        except Exception as e:
            nonlocal err
            err = "%s,%s" % (e.__class__, e.args)
            return False

    while sent_index < _bytes_msg_len:
        sent_index = 0 if sent_index == -1 else sent_index
        will_send_data = _bytes_msg[sent_index: sent_index + MAX_BYTES]
        if not _send_msg(will_send_data):
            return False, err
        sent_index += MAX_BYTES

    return True, err


class TcpConn:
    def __init__(self):
        self.skt = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.err = None

    def write(self, data) -> bool:
        ok, self.err = write_wukong_data(self.skt, WukongPkg(data))
        return ok

    def read(self):
        return read_wukong_data(self.skt)

    def close(self):
        self.skt.close()


class TcpSvr(TcpConn):
    def __init__(self, host, port):
        """
        :param host: ...
        :param port: ...
        """
        super().__init__()
        try:
            self.skt.bind((host, port))
        except OSError as e:
            self.skt.close()
            raise e

        # the backlog parameter is commonly set a large value to
        # handle High concurrent connection requests, It's enough
        # to set 0 here.
        # https://tangentsoft.net/wskfaq/advanced.html#backlog
        # https://www.mkssoftware.com/docs/man3/listen.3.asp
        self.skt.listen(0)

    def accept(self):
        return self.skt.accept()


class TcpClient(TcpConn):
    def __init__(self, host, port):
        """
        :param host: ...
        :param port: ...
        :param pre_connect: declare a connection previously, establish
        a real connection when you want to communicate
        """
        super().__init__()
        try:
            self.skt.connect((host, port))
        except Exception as e:
            self.skt.close()
            raise e


def wrap_queue_msg(
        queue_cmd: bytes, args: dict = None, data=b'') -> bytes:
    # base64 does not contain ``*``
    # parameter `args` must be JSON serializable
    if args is None:
        args = {}

    return b"*".join(
        [
            b64encode(queue_cmd),
            b64encode(json.dumps(args).encode()),
            b64encode(data)
        ]
    )


def unwrap_queue_msg(msg: bytes) -> dict:
    _lst = msg.split(b"*")
    ret = {"cmd": _lst[0], "data": b"", "args": {}, "err": ""}
    if len(_lst) == 1:
        return ret
    ret["cmd"] = b64decode(_lst[0])
    ret["args"] = json.loads(b64decode(_lst[1]).decode())
    ret["data"] = b64decode(_lst[2])

    return ret


def _check_all_queue_cmds():
    """check all cmds variety definition"""
    all_cmds = [
        v
        for k, v in globals().items()
        if k.startswith("QUEUE_") and isinstance(v, bytes)
    ]
    # print(all_cmds)
    tried_cmds = 0
    while tried_cmds < len(all_cmds):
        check_cmd = all_cmds[tried_cmds]
        for i in range(len(all_cmds)):
            if i != tried_cmds:
                if all_cmds[i].startswith(check_cmd):
                    raise ValueError(
                        "%s is equivalent to %s, "
                        "please alter cmd's variable name definition"
                        % (all_cmds[i], check_cmd)
                    )
        tried_cmds += 1


QUEUE_HI = b"HI"
QUEUE_AUTH_KEY = b"AUTH_KEY"
QUEUE_NEED_AUTH = b"NEED_AUTH"
QUEUE_AUTH_FAIL = b"AUTH_FAIL"
QUEUE_PUT = b"PUT"
QUEUE_GET = b"GET"
QUEUE_DATA = b"DATA"
QUEUE_FULL = b"FULL"
QUEUE_EMPTY = b"EMPTY"
QUEUE_NORMAL = b"NORMAL"
QUEUE_QUERY_STATUS = b"STATUS"
QUEUE_OK = b"OK"
QUEUE_FAIL = b"FAIL"
QUEUE_PING = b"PING"
QUEUE_PONG = b"PONG"
QUEUE_SIZE = b"SIZE"
QUEUE_MAXSIZE = b"MAXSIZE"
QUEUE_RESET = b"RESET"
QUEUE_CLIENTS = b"CLIENTS"
QUEUE_TASK_DONE = b"TASK_DONE"
QUEUE_JOIN = b"JOIN"

_check_all_queue_cmds()
