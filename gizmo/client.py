import asyncio
import json
import ssl
import uuid
import websockets
from .response import GremlinResponse


class BaseGremlinClient:

    def __init__(self, uri='ws://localhost:8182/', loop=None, ssl=None,
                 protocol=None, **kwargs):
        self.uri = uri
        # SLL is untested. Need to set up secure server and try it out.
        # Will look something like this.
        if ssl:
            protocol = protocol or ssl.PROTOCOL_TLSv1
            ssl_context = ssl.SSLContext(protocol)
            ssl_context.load_verify_locations(ssl)
            ssl_context.verify_mode = ssl.CERT_REQUIRED
            kwargs['ssl'] = ssl_context
        self._sock = asyncio.async(self.connect(**kwargs))
        self._errors = []
        self._loop = loop or asyncio.get_event_loop()

    def get_sock(self):
        return self._sock
    sock = property(get_sock)

    def get_errors(self):
        return self._errors
    errors = property(get_errors)

    @asyncio.coroutine
    def connect(self, **kwargs):
        websocket = yield from websockets.connect(self.uri, **kwargs)
        return websocket

    @asyncio.coroutine
    def send(self, gremlin, bindings=None, lang="gremlin-groovy", op="eval",
             processor=""):
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
            websocket = yield from self.sock
            self._sock = websocket
        except TypeError:
            websocket = self.sock
        yield from websocket.send(json.dumps(payload))
        return websocket

    def receive(consumer=None, collect=True):
        raise NotImplementedError

    @asyncio.coroutine
    def send_receive(self, gremlin, bindings=None, lang="gremlin-groovy",
                     op="eval", processor="", consumer=None, collect=True):
        yield from self.send(gremlin, bindings=bindings, lang=lang, op=op,
                             processor=processor)
        yield from self.receive(consumer=consumer, collect=collect)

    def run_until_complete(self, func):
        self._loop.run_until_complete(func)


class AsyncGremlinClient(BaseGremlinClient):

    def __init__(self, uri='ws://localhost:8182/', loop=None, **kwargs):
        super().__init__(uri=uri, loop=loop, **kwargs)
        self.messages = asyncio.Queue()
        self._tasks = []
        self.task_queue = asyncio.Queue()

    def get_tasks(self):
        return self._tasks
    tasks = property(get_tasks)

    def task(self, coro, *args, **kwargs):
        return asyncio.async(coro(*args, **kwargs))

    def add_task(self, coro, *args, **kwargs):
        task = self.task(coro, *args, **kwargs)
        self._tasks.append(task)
        return task

    @asyncio.coroutine
    def enqueue_task(self, coro, *args, **kwargs):
        task = (coro, args, kwargs)
        yield from self.task_queue.put(task)

    @asyncio.coroutine
    def dequeue_task(self):
        if not self.task_queue.empty():
            coro, args, kwargs = yield from self.task_queue.get()
            task = self.task(coro, *args, **kwargs)
            return (yield from task)

    @asyncio.coroutine
    def dequeue_all(self):
        while not self.task_queue.empty():
            coro, args, kwargs = yield from self.task_queue.get()
            task = self.task(coro, *args, **kwargs)
            f = yield from task

    def async_dequeue_all(self, coro, *args, **kwargs):
        q = self.task_queue
        coros = [asyncio.async(coro(q, *args, **kwargs)) for i in
            range(q.qsize())]
        self.run_until_complete(asyncio.wait(coros))

    @asyncio.coroutine
    def receive(self, consumer=None, collect=True):
        websocket = self.sock
        while True:
            # Will need to handle error here if websocket no message has been
            # sent.
            message = yield from websocket.recv()
            message = json.loads(message)
            message = GremlinResponse(message)
            if message.status_code == 200:
                if consumer:
                    message = consumer(message)
                if message and collect:
                    yield from self.messages.put(message)
            elif message.status_code == 299:
                break
            else:
                # Error handler here.
                verbose = "Request {} failed with status code {}: {}".format(
                    message.request_id, message.status_code, message.message)
                self._errors.append(verbose)
                print(verbose)

    def run_tasks(self):
        self.run_until_complete(asyncio.wait(self.tasks))


class GremlinClient(BaseGremlinClient):

    def __init__(self, uri='ws://localhost:8182/', loop=None, **kwargs):
        super().__init__(uri=uri, loop=loop, **kwargs)
        self._messages = []
        self._message_number = 0

    def get_messages(self):
        for message in self._messages:
            yield message
    messages = property(get_messages)

    def __iter__(self):
        return iter(self._messages)

    @asyncio.coroutine
    def receive(self, consumer=None, collect=True):
        websocket = self.sock
        while True:
            # Will need to handle error here if websocket no message has been
            # sent.
            message = yield from websocket.recv()
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
                # Error handler here.
                verbose = "Request {} failed with status code {}: {}".format(
                    message.request_id, message.satus_code, message.message)
                self._errors.append(verbose)
                print(verbose)

    def execute(self, gremlin, bindings=None, lang="gremlin-groovy", op="eval",
                processor="", consumer=None, collect=True):
        coro = self.send_receive(gremlin, bindings=bindings, lang=lang, op=op,
            processor=processor, consumer=consumer, collect=collect)
        self.run_until_complete(coro)
        return self
