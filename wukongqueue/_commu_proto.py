# Protocol of communication

import json
import socket
from copy import deepcopy

__all__ = [
    "read_wukong_data",
    "write_wukong_data",
    "WukongPkg",
    "TcpSvr",
    "TcpClient",
    "wrap_queue_msg",
    "unwrap_queue_msg",
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
        self._is_skt_closed = closed

    def __repr__(self):
        return self.raw_data.decode(encoding=self.encoding)

    def __bool__(self):
        return len(self.raw_data) > 0

    def is_valid(self) -> bool:
        return any([self._is_skt_closed, self.err]) is False


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
            data: bytes = conn.recv(MAX_BYTES)
        except Exception as e:
            return WukongPkg(err=f"{e.__class__, e.args}")
        if data == b"":
            return WukongPkg(closed=True)

        bye_index = data.find(delimiter)
        if bye_index == -1:
            buffer.append(data)
            continue

        buffer.append(data[:bye_index])
        if len(data) < bye_index + delimiter_len:
            _STREAM_BUFFER.append(data[bye_index + delimiter_len :])
        break
    msg = b"".join(buffer).replace(delimiter_escape, delimiter)
    ret = WukongPkg(msg)
    return ret


def write_wukong_data(
    conn: socket.socket, msg: WukongPkg
) -> (bool, str):
    """NOTE: Sending an empty string is allowed"""
    _bytes_msg = (
        msg.raw_data.replace(delimiter, delimiter_escape) + delimiter
    )
    _bytes_msg_len = len(_bytes_msg)
    sent_index = -1
    err = ""

    def _send_msg(msg: bytes):
        try:
            conn.send(msg)
            return True
        except Exception as e:
            nonlocal err
            err = f"{e.__class__, e.args}"
            return False

    while sent_index < _bytes_msg_len:
        sent_index = 0 if sent_index == -1 else sent_index
        will_send_data = _bytes_msg[sent_index : sent_index + MAX_BYTES]
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
    def __init__(self, host, port, max_conns=0):
        """
        :param host: ...
        :param port: ...
        :param max_conns: maximum connects
        """
        super().__init__()
        self.skt.bind((host, port))
        self.max_conns = max_conns

    def accept(self):
        self.skt.listen(self.max_conns)
        return self.skt.accept()


class TcpClient(TcpConn):
    def __init__(self, host, port, pre_connect=False):
        """
        :param host: ...
        :param port: ...
        :param pre_connect: declare a connection previously, establish
        a real connection when you want to communicate
        """
        super().__init__()
        if pre_connect is False:
            try:
                self.skt.connect((host, port))
            except Exception as e:
                self.skt.close()
                raise e


queue_args_splits = b"-"
queue_args_splits_escape = b"-:"


def wrap_queue_msg(queue_cmd: bytes, args={}, data: bytes = b""):
    return queue_args_splits.join(
        [
            c.replace(queue_args_splits, queue_args_splits_escape)
            for c in [queue_cmd, json.dumps(args).encode(), data]
        ]
    )


def unwrap_queue_msg(data: bytes):
    ret = {"cmd": b"", "args": b"", "data": b""}
    splits = data.split(queue_args_splits)
    if len(splits) == 1:
        ret["cmd"] = splits[0]
    elif len(splits) == 2:
        ret["cmd"], ret["data"] = splits
    elif len(splits) == 3:
        ret["cmd"], ret["args"], ret["data"] = splits
    else:
        raise ValueError("this is a bug~! contact author, thanks~")

    ret = {
        k: v.replace(queue_args_splits_escape, queue_args_splits)
        for k, v in ret.items()
    }
    if ret["args"]:
        ret["args"] = json.loads(ret["args"])
    else:
        ret["args"] = {}
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
                        f"{all_cmds[i]} is equivalent to {check_cmd}, "
                        f"please alter cmd's variable name definition"
                    )
        tried_cmds += 1


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

_check_all_queue_cmds()
