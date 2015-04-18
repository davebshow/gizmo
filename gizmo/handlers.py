"""
gizmo.handlers

This module defines error handlers for the websockets and the Gremlin Server.
"""

from .exceptions import RequestError, GremlinServerError, SocketError


def status_error_handler(status_code, message):
    if status_code < 500:
        raise RequestError(status_code, message)
    else:
        raise GremlinServerError(status_code, message)


def socket_error_handler(sock):
    if not bool(sock):
        raise SocketError("There is no socket connection.")
    if not sock.open:
        raise SocketError("Socket has been closed.")
