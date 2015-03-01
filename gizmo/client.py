"""
gizmo.client

This module defines clients for the Gremlin Server.
"""

import asyncio
import json
import ssl
import uuid
import websockets
from .handlers import status_error_handler, socket_error_handler
from .response import GremlinResponse


class BaseGremlinClient:

    def __init__(self, uri='ws://localhost:8182/', loop=None, ssl=None,
                 protocol=None, **kwargs):
        """
        Base class for Gremlin clients. Handles ssl, websocket.send, and
        event loop.

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
        self._connector = asyncio.async(self.connect(**kwargs), loop=self._loop)
        self._sock = None

    def get_sock(self):
        """
        Read only access to the websocket connection.

        :returns: websockets.WebSocketClientProtocol
        """
        return self._sock
    sock = property(get_sock)

    def get_connector(self):
        """
        Read only access to the connector coroutine task.

        :returns: asyncio.Task
        """
        return self._connector
    connector = property(get_connector)

    @asyncio.coroutine
    def connect(self, **kwargs):
        """
        Coroutine that returns a connected websocket.

        :returns: websockets.WebSocketClientProtocol
        """
        websocket = yield from websockets.connect(self.uri, **kwargs)
        self._sock = websocket
        return websocket

    @asyncio.coroutine
    def send(self, gremlin, bindings=None, lang="gremlin-groovy", op="eval",
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
        try:
            # This is the initial connection.
            websocket = yield from self.connector
        except TypeError:
            # Connection has already been established.
            websocket = self.sock
        socket_error_handler(websocket)
        yield from websocket.send(json.dumps(payload))
        return websocket

    def run(consumer=None, collect=True):
        """
        Subclasses require this method to be implemented.

        :param consumer: func. Function to map to server messages.
        :param collect: bool. Retain server messages on client object.
        """
        raise NotImplementedError

    @asyncio.coroutine
    def submit(self, gremlin, bindings=None, lang="gremlin-groovy",
               op="eval", processor="", consumer=None, collect=True):
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
        yield from self.send(gremlin, bindings=bindings, lang=lang, op=op,
            processor=processor)
        yield from self.run(consumer=consumer, collect=collect)

    def run_until_complete(self, coro):
        """
        A convience method that calls asyncio.BaseEventLoop.run_until_complete.

        :param coro: aysncio.coroutine or asyncio.Future.
        :returns: None.
        """
        self._loop.run_until_complete(coro)


class AsyncGremlinClient(BaseGremlinClient):

    def __init__(self, uri='ws://localhost:8182/', loop=None, ssl=None,
                 protocol=None, **kwargs):
        """
        Asynchronous Client for the asyncio API.

        :param uri: str. Database uri.
        :param loop: asyncio.BaseEventLoop.
        :param ssl: str. Path to ssl certfile.
        :param protocol: ssl.PROTOCOL.
        """
        super().__init__(uri='ws://localhost:8182/', loop=None, ssl=None,
            protocol=None, **kwargs)
        self._messages = asyncio.Queue()
        self._tasks = []
        self._task_queue = asyncio.Queue()

    def get_messages(self):
        """
        A read only property that returns the messages queue.

        :returns: asyncio.Queue
        """
        return self._messages
    messages = property(get_messages)

    def get_tasks(self):
        """
        A read only property that returns the task list.

        :returns: list
        """
        return self._tasks
    tasks = property(get_tasks)

    def get_task_queue(self):
        """
        A read only property that returns the task queue.

        :returns: asyncio.Queue
        """
        return self._task_queue
    task_queue = property(get_task_queue)

    def __iter__(self):
        return self

    def __next__(self):
        """
        Step over the message queue.

        :returns: Next element in the message queue.
        """
        try:
            return self.messages.get_nowait()
        except asyncio.QueueEmpty:
            raise StopIteration

    @asyncio.coroutine
    def read(self):
        """
        Read off the message queue.

        :returns: Next element in the message queue.
        """
        try:
            return self.messages.get_nowait()
        except asyncio.QueueEmpty:
            pass

    def task(self, coro, *args, **kwargs):
        """
        Wraps a coroutine in a Future and schedules it on the event loop.

        :param coro: asyncio.coroutine.
        :param args: Positional args to be passed to the coroutine.
        :param kwargs: Keyword args to be passed to the coroutine.
        :returns: asyncio.Task.
        """
        return asyncio.async(coro(*args, **kwargs), loop=self._loop)

    def add_task(self, coro, *args, **kwargs):
        """
        Add a task to the list of tasks.

        :param coro: asyncio.coroutine.
        :param args: Positional args to be passed to the coroutine.
        :param kwargs: Keyword args to be passed to the coroutine.
        :returns: asyncio.Task.
        """
        task = self.task(coro, *args, **kwargs)
        self._tasks.append(task)
        return task

    @asyncio.coroutine
    def enqueue_task(self, coro, *args, **kwargs):
        """
        Enqueue a task on the task_queue.

        :param coro: asyncio.coroutine.
        :param args: Positional args to be passed to the coroutine.
        :param kwargs: Keyword args to be passed to the coroutine.
        :returns: None.
        """
        task = (coro, args, kwargs)
        self.task_queue.put_nowait(task)

    @asyncio.coroutine
    def dequeue_task(self):
        """
        Dequeue a task from the task_queue and execute it.

        :returns: The result of the task.
        """
        if not self.task_queue.empty():
            coro, args, kwargs = self.task_queue.get_nowait()
            task = self.task(coro, *args, **kwargs)
            return (yield from task)

    @asyncio.coroutine
    def dequeue_all(self):
        """
        Dequeue and execute all tasks in order.

        :returns: None
        """
        while not self.task_queue.empty():
            coro, args, kwargs = self.task_queue.get_nowait()
            task = self.task(coro, *args, **kwargs)
            f = yield from task

    def async_dequeue_all(self, coro, *args, **kwargs):
        """
        Generate a coroutine for each element in the task_queue, and
        asynchronously map them to the tasks.

        :param coro: asyncio.coroutine.
        :param args: Positional args to be passed to the coroutine.
        :param kwargs: Keyword args to be passed to the coroutine.
        """
        q = self.task_queue
        coros = [asyncio.async(coro(q, *args, **kwargs), loop=self._loop)
            for i in range(q.qsize())]
        self.run_until_complete(asyncio.wait(coros))

    @asyncio.coroutine
    def recv(self):
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
            [next_message, asyncio.async(self._receive(), loop=self._loop)],
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
    def _receive(self):
        """
        This method manages the Gremlin Server passing the response to the recv
        method one message at a time.
        """
        socket_error_handler(self.sock)
        message = yield from self.sock.recv()
        message = json.loads(message)
        message = GremlinResponse(message)
        if message.status_code == 200:
            self.messages.put_nowait(message)
        elif message.status_code == 299:
            pass
        else:
            status_error_handler(message.status_code, message.message)

    @asyncio.coroutine
    def run(self, consumer=None, collect=True):
        """
        This message handles the whole Gremlin Server response, enqueueing the
        chunks on the message queue as they arrive.

        :param consumer: func. Function to map to server messages.
        :param collect: bool. Retain server messages on client object.
        """
        socket_error_handler(self.sock)
        while True:
            message = yield from self.sock.recv()
            message = json.loads(message)
            message = GremlinResponse(message)
            if message.status_code == 200:
                if consumer:
                    if asyncio.iscoroutine(consumer):
                        message = yield from consumer(message)
                    else:
                        message = consumer(message)
                if message and collect:
                    self.messages.put_nowait(message)
            elif message.status_code == 299:
                break
            else:
                status_error_handler(message.status_code, message.message)

    def run_tasks(self):
        """
        Run all tasks in tasks list in "parallel"
        """
        self.run_until_complete(asyncio.wait(self.tasks, loop=self._loop))


class GremlinClient(BaseGremlinClient):

    def __init__(self, uri='ws://localhost:8182/', loop=None, ssl=None,
                 protocol=None, **kwargs):
        """
        This class provides a one method API (.execute) that does not require
        any use of the asyncio API. It is a candidate for deprication.

        :param uri: str. Database uri.
        :param loop: asyncio.BaseEventLoop.
        :param ssl: str. Path to ssl certfile.
        :param protocol: ssl.PROTOCOL.
        """
        super().__init__(uri='ws://localhost:8182/', loop=None, ssl=None,
            protocol=None, **kwargs)
        self._messages = []

    def get_messages(self):
        """
        :returns: list.
        """
        for message in self._messages:
            yield message
    messages = property(get_messages)

    def __iter__(self):
        return iter(self._messages)

    @asyncio.coroutine
    def run(self, consumer=None, collect=True):
        """
        :param consumer: func. Function to map to server messages.
        :param collect: bool. Retain server messages on client object.
        """
        socket_error_handler(self.sock)
        while True:
            message = yield from self.sock.recv()
            message = json.loads(message)
            message = GremlinResponse(message)
            if message.status_code == 200:
                if consumer:
                    message = consumer(message)
                if message and collect:
                    self._messages.append(message)
            elif message.status_code == 299:
                break
            else:
                status_error_handler(message.status_code, message.message)

    def execute(self, gremlin, bindings=None, lang="gremlin-groovy", op="eval",
                processor="", consumer=None, collect=True):
        """
        :returns: self.
        :param gremlin: str. Gremlin script to be submitted to server.
        :param bindings: dict. Bound kwargs for script.
        :param lang: str. Language used for script.
        :param op: str. Operation to execute on the Gremlin Server.
        :param processor: str. OpProcessor to utilize on the Gremlin Server.
        :param consumer: func. Function to map to server messages.
        :param collect: bool. Retain server messages on client object.
        """
        coro = self.submit(gremlin, bindings=bindings, lang=lang, op=op,
            processor=processor, consumer=consumer, collect=collect)
        self.run_until_complete(coro)
        return self
