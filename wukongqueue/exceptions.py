# -*- coding: utf-8 -*-
from queue import Full as qFull, Empty as qEmpty


class WuKongError(Exception):
    pass


class Full(WuKongError, qFull):
    pass


class Empty(WuKongError, qEmpty):
    pass


class ConnectionError(WuKongError, ConnectionError):
    pass


class ClientsFull(ConnectionError):
    pass


class AuthenticationError(ConnectionError):
    pass


class NotYetSupportType(WuKongError):
    pass


class ConnectionTimeout(ConnectionError):
    pass


class UnknownResponse(ConnectionError):
    pass


class UnknownCmd(ConnectionError):
    pass
