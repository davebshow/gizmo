"""
gizmo.client

This module defines clients for the Gremlin Server.
"""

import asyncio
import json
import ssl
import uuid
import websockets
from .connection import ConnectionManager
from .exceptions import SocketError, GremlinServerError
from .handlers import status_error_handler, socket_error_handler
from .response import GremlinResponse
from .tasks import async


class AsyncGremlinClient:

    def __init__(self, uri='ws://localhost:8182/', loop=None, ssl=None,
                 protocol=None, lang="gremlin-groovy", op="eval",
                 processor="", connection=None, max_conn=10, timeout=None,
                 **kwargs):
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
            # Passed through to websockets.connect
            kwargs['ssl'] = ssl_context
        self._loop = loop or asyncio.get_event_loop()
        self.lang = lang or "gremlin-groovy"
        self.op = op or "eval"
        self.processor = processor or ""
        self.connection = connection or ConnectionManager(uri, max_conn=max_conn,
            timeout=timeout, loop=self._loop)
        self._messages = asyncio.Queue()

    def get_messages(self):
        """
        A read only property that returns the messages queue.

        :returns: asyncio.Queue
        """
        return self._messages
    messages = property(get_messages)

    def __next__(self):
        """
        Step over the message queue.

        :returns: Next element in the message queue.
        """
        try:
            return self.messages.get_nowait()
        except asyncio.QueueEmpty:
            raise StopIteration

    def __iter__(self):
        return self

    def read(self):
        """
        Read off the message queue.

        :returns: Next element in the message queue.
        """
        try:
            return self.messages.get_nowait()
        except asyncio.QueueEmpty:
            pass

    @asyncio.coroutine
    def connect(self, **kwargs):
        """
        Coroutine that returns a connected websocket.

        :returns: websockets.WebSocketClientProtocol
        """
        websocket = yield from websockets.connect(self.uri, **kwargs)
        # self._sock = websocket
        return websocket

    @asyncio.coroutine
    def send(self, gremlin, websocket=None, bindings=None, lang="gremlin-groovy", op="eval",
             processor=""):
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
        payload = {
            "requestId": str(uuid.uuid4()),
            "op": op,
            "processor": processor,
            "args":{
                "gremlin": gremlin,
                "bindings": bindings,
                "language":  lang
            }
        }
        if websocket is None:
            websocket = yield from self.connection.connect(self.uri)
        else:  # Expect raw websocket.
            try:
                socket_error_handler(websocket)
            except SocketError:
                websocket = yield from asyncio.async(self.connect(),
                    loop=self._loop)
        yield from websocket.send(json.dumps(payload))
        return websocket

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
        websocket = yield from self.send(gremlin, bindings=bindings, lang=lang,
                op=op, processor=processor)
        yield from self.run(websocket, consumer=consumer, collect=collect)

    def s(self, *args, **kwargs):
        """
        Convenience method that combines task and submit.
        """
        if not kwargs.get("loop", ""):
            kwargs["loop"] = self._loop
        return async(self.submit, *args, **kwargs)

    @asyncio.coroutine
    def recv(self, websocket):
        """
        This recv is based on the websockets.WebSocketCommonProtocol.recv, but
        it uses AsyncGremlinClinet._receive to manage the Gremlin Server
        response (the original uses a worker task to manage the websocket
        connection.)
        https://github.com/aaugustin/websockets/blob/master/websockets/protocol.py#L150

        :returns: Message.
        """
        try:
            return self.messages.get_nowait()
        except asyncio.QueueEmpty:
            pass
        # Future message to be enqueued by _receive method.
        next_message = asyncio.async(self.messages.get(), loop=self._loop)
        # If message return message future, else return None (or set_exception).
        done, pending = yield from asyncio.wait(
            [next_message, asyncio.async(self._receive(websocket), loop=self._loop)],
            loop=self._loop, return_when=asyncio.FIRST_COMPLETED)
        # If message completed future was returned.
        if next_message in done:
            return next_message.result()
        # Cancel the future, recv returns None or raises Error.
        else:
            next_message.cancel()
            f, = done  # Unpack set.
            f.result() # None or raise Error.

    @asyncio.coroutine
    def _receive(self, websocket):
        """
        This method manages the Gremlin Server passing the response to the recv
        method one message at a time.
        """
        socket_error_handler(websocket)
        message = yield from websocket.recv()
        message = json.loads(message)
        message = GremlinResponse(message)
        if message.status_code == 200:
            self.messages.put_nowait(message)
        elif message.status_code == 299:
            self.close_socket(websocket)
            pass
        else:
            status_error_handler(message.status_code, message.message)

    @asyncio.coroutine
    def run(self, websocket, consumer=None, collect=True):
        """
        This message handles the whole Gremlin Server response, enqueueing the
        chunks on the message queue as they arrive.

        :param consumer: func. Function to map to server messages.
        :param collect: bool. Retain server messages on client object.
        """
        socket_error_handler(websocket)
        while True:
            message = yield from websocket.recv()
            message = json.loads(message)
            message = GremlinResponse(message)
            if message.status_code == 200:
                if consumer:
                    message = consumer(message)
                    if asyncio.iscoroutine(message):
                        message = yield from asyncio.async(message)
                if message and collect:
                    self.messages.put_nowait(message)
            elif message.status_code == 299:
                self.close_socket(websocket)
                break
            else:
                self.close_socket(websocket)
                status_error_handler(message.status_code, message.message)

    def close_socket(self, websocket):
        try:
            websocket.close()
        except AttributeError:
            pass
