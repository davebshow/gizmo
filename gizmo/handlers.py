"""
gizmo.handlers

This module defines error handlers for the websockets and the Gremlin Server.
"""

from .exceptions import RequestError, GremlinServerError


def status_error_handler(status_code, message):
    if status_code < 500:
        raise RequestError(status_code, message)
    else:
        raise GremlinServerError(status_code, message)
