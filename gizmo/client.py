"""
gizmo.client

This module defines clients for the Gremlin Server.
"""

import asyncio
import json
import ssl
import uuid

from .connection import ConnectionManager
from .exceptions import GremlinServerError
from .handlers import status_error_handler
from .response import GremlinResponse
from .tasks import async


class AsyncGremlinClient:

    def __init__(self, uri='ws://localhost:8182/', loop=None, ssl=None,
                 protocol=None, lang="gremlin-groovy", op="eval",
                 processor="", manager=None, factory=None, max_conn=10,
                 timeout=None, **kwargs):
        """
        Asynchronous Client for the asyncio API.

        :param uri: str. Database uri.
        :param loop: asyncio.BaseEventLoop.
        :param ssl: str. Path to ssl certfile.
        :param protocol: ssl.PROTOCOL.
        """
        self.uri = uri
        # SLL is untested. Need to set up secure server and try it out.
        # Will look something like this.
        if ssl:
            protocol = protocol or ssl.PROTOCOL_TLSv1
            ssl_context = ssl.SSLContext(protocol)
            ssl_context.load_verify_locations(ssl)
            ssl_context.verify_mode = ssl.CERT_REQUIRED
            kwargs['ssl'] = ssl_context
        self._loop = loop or asyncio.get_event_loop()
        self.lang = lang or "gremlin-groovy"
        self.op = op or "eval"
        self.processor = processor or ""
        self.manager = manager or ConnectionManager(uri, factory=factory,
            max_conn=max_conn, timeout=timeout, loop=self._loop)
        self.factory = factory or self.manager.factory

    @asyncio.coroutine
    def connect(self, **kwargs):
        """
        Coroutine that returns a connected connection.

        :returns: websockets.WebSocketClientProtocol
        """
        loop = kwargs.get("loop", "") or self._loop
        connection = yield from self.factory.connect(self.uri, loop=loop,
            **kwargs)
        return connection

    @asyncio.coroutine
    def send(self, gremlin, connection=None, bindings=None, lang="gremlin-groovy",
             op="eval", processor=""):
        """
        Coroutine that sends a message to the Gremlin Server.

        :param gremlin: str. Gremlin script to be submitted to server.
        :param bindings: dict. Bound kwargs for script.
        :param lang: str. Language used for script.
        :param op: str. Operation to execute on the Gremlin Server.
        :param processor: str. OpProcessor to utilize on the Gremlin Server.
        :returns: websockets.WebSocketClientProtocol
        """
        lang = lang or self.lang
        op = op or self.op
        processor = processor or self.processor
        mime_len = b"\x10"
        mime_type = b"application/json"
        payload = json.dumps({
            "requestId": str(uuid.uuid4()),
            "op": op,
            "processor": processor,
            "args":{
                "gremlin": gremlin,
                "bindings": bindings,
                "language":  lang
            }
        })
        message = b"".join([mime_len, mime_type, bytes(payload, "utf-8")])
        if connection is None:
            connection = yield from self.manager.connect(self.uri, loop=self._loop)
        yield from connection.send(message)
        return connection

    @asyncio.coroutine
    def submit(self, gremlin, bindings=None, lang="gremlin-groovy",
               op="eval", processor="", consumer=None, collect=True, **kwargs):
        """
        A convience coroutine method that both sends a message to the Gremlin
        Server and calls run to handle the response and populate the message
        queue.

        :param gremlin: str. Gremlin script to be submitted to server.
        :param bindings: dict. Bound kwargs for script.
        :param lang: str. Language used for script.
        :param op: str. Operation to execute on the Gremlin Server.
        :param processor: str. OpProcessor to utilize on the Gremlin Server.
        :param consumer: func. Function to map to server messages.
        :param collect: bool. Retain server messages on client object.
        :returns: None.
        """
        connection = yield from self.send(gremlin, bindings=bindings, lang=lang,
                op=op, processor=processor)
        results = yield from self.run(connection, consumer=consumer,
            collect=collect)
        return results

    def s(self, *args, **kwargs):
        """
        Convenience method that combines task and submit.
        """
        if not kwargs.get("loop", ""):
            kwargs["loop"] = self._loop
        return async(self.submit, *args, **kwargs)

    @asyncio.coroutine
    def recv(self, connection):
        """
        This method manages the Gremlin Server passing the response to the recv
        method one message at a time.
        """
        message = yield from connection.recv()
        message = json.loads(message)
        if message["status"]["code"] == 200:
            return message
        elif message["status"]["code"] == 299:
            connection.close()
        else:
            status_error_handler(message["status"]["code"],
                message["status"]["message"])

    @asyncio.coroutine
    def run(self, connection, consumer=None, collect=True):
        """
        This message handles the whole Gremlin Server response, enqueueing the
        chunks on the message queue as they arrive.

        :param consumer: func. Function to map to server messages.
        :param collect: bool. Retain server messages on client object.
        """
        results = []
        while True:
            message = yield from self.recv(connection)
            if message is None:
                break
            message = GremlinResponse(message)
            if consumer:
                message = consumer(message)
                if asyncio.iscoroutine(message):
                    message = yield from asyncio.async(message)
            if message and collect:
                results.append(message)
        return results
