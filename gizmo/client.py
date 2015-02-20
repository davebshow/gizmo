import asyncio
import json
import uuid
from functools import partial
import websockets


class BaseGremlinClient(object):

    def __init__(self, uri='ws://localhost:8182/', loop=None):
        self.uri = uri
        self._sock = asyncio.async(self.connect())
        self._errors = []
        self.loop = loop
        if loop is None:
            self.loop = asyncio.get_event_loop()

    def get_sock(self):
        return self._sock
    sock = property(get_sock)

    def get_errors(self):
        return self._errors
    errors = property(get_errors)

    @asyncio.coroutine
    def connect(self):
        websocket = yield from websockets.connect(self.uri)
        self._sock = websocket
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
        self.loop.run_until_complete(func)


class GremlinClient(BaseGremlinClient):

    def __init__(self, uri='ws://localhost:8182/', loop=None):
        super().__init__(uri=uri, loop=loop)
        self._messages = []
        self._message_number = 0

    def get_messages(self):
        for message in self._messages:
            yield message
    messages = property(get_messages)

    def __iter__(self):
        return self

    def __next__(self):
        try:
            row = self._messages[self._message_number]
            self._message_number += 1
            return row
        except IndexError:
            raise StopIteration()

    def next(self):
        return self.__next__()

    @asyncio.coroutine
    def receive(self, consumer=None, collect=True):
        websocket = self.sock
        while True:
            # Will need to handle error here if websocket no message has been
            # sent.
            message = yield from websocket.recv()
            message = json.loads(message)
            code = message["status"]["code"]
            if code == 200:
                if consumer:
                    message = consumer(message)
                if collect:
                    self._messages.append(message)
            elif code == 299:
                break
            else:
                # Error handler here.
                message = message["status"]["message"]
                verbose = "Request {} failed with status code {}: {}".format(
                    payload["requestId"], code, message
                )
                self._errors.append(verbose)
                print(verbose)

    def execute(self, gremlin, bindings=None, lang="gremlin-groovy", op="eval",
                processor="", consumer=None, collect=True):
        self.run_until_complete(
            self.send_receive(gremlin, bindings=bindings, lang=lang, op=op,
                              processor=processor, consumer=consumer,
                              collect=collect)
        )
        return self


class AsyncGremlinClient(BaseGremlinClient):

    def __init__(self, uri='ws://localhost:8182/', loop=None):
        super().__init__(uri=uri, loop=loop)
        self.messages = asyncio.Queue()
        self._tasks = []

    def get_tasks(self):
        return self._tasks
    tasks = property(get_tasks)

    def task(self, coroutine, *args, **kwargs):
        return asyncio.async(coroutine(*args, **kwargs))

    def add_task(self, coroutine, *args, **kwargs):
        task = self.task(coroutine, *args, **kwargs)
        self._tasks.append(task)
        return task

    def reset_messages():
        self.messages = asyncio.Queue()

    @asyncio.coroutine
    def receive(self, consumer=None, collect=True):
        websocket = self.sock
        while True:
            # Will need to handle error here if websocket no message has been
            # sent.
            message = yield from websocket.recv()
            message = json.loads(message)
            code = message["status"]["code"]
            if code == 200:
                if consumer:
                    message = consumer(message)
                if message:
                    yield from self.messages.put(message)
            elif code == 299:
                break
            else:
                # Error handler here.
                message = message["status"]["message"]
                verbose = "Request {} failed with status code {}: {}".format(
                    payload["requestId"], code, message
                )
                self._errors.append(verbose)
                print(verbose)

    def run_tasks(self):
        self.run_until_complete(asyncio.wait(self.tasks))

    def run_forever(self):
        self.loop.run_forever()

    def stop(self, f=None):
        self.loop.stop()


# gc = GremlinClient('ws://localhost:8182/')
# gc.execute("g.V(x).out()", bindings={"x":1}, consumer=lambda x: print(x))
#
# #Basic Async Examples
#
# gc = AsyncGremlinClient('ws://localhost:8182/')
# consumer = lambda x: print(x["result"]["data"])
# task = gc.task(gc.send_receive, "g.V(x).out()", bindings={"x":1}, consumer=consumer)
# # task = asyncio.async(gc.send_receive("g.V(x).out()", bindings={"x":1}, consumer=lambda x: print(x)))
# gc.run_until_complete(task)

# @asyncio.coroutine
# def superslow():
#     yield from asyncio.sleep(5)
#     print("superslow")
#
#
# gc = AsyncGremlinClient('ws://localhost:8182/')
# consumer = lambda x: print(x["result"]["data"])
# gc.add_task(superslow)
# gc.add_task(gc.send_receive, "g.V().values(name)", bindings={"name": "name"}, consumer=consumer)
# gc.run_tasks()
#
# task = gc.task(gc.send_receive, "g.V(x).out()", bindings={"x":1}, consumer=lambda x: print(x))
# task.add_done_callback(gc.stop)
# # Run the event loop until the task is complete.
# gc.run_forever()


#
# Define a coroutine that sequentially executes instructions.
# @asyncio.coroutine
# def client_consumer(gc):
#     yield from superslow()
#     yield from gc.task(
#         gc.send_receive,
#         "g.V().values(name)",
#         bindings={"name": "name"},
#         consumer=consumer
#     )
#     # Response messages sent by server are stored in an asyncio.Queue
#     while not gc.messages.empty():
#         f = yield from gc.messages.get()
#         print(f)
# #
# # gc = AsyncGremlinClient('ws://localhost:8182/')
# # gc.run_until_complete(client_consumer(gc))
#
# loop = asyncio.get_event_loop()
# gc = AsyncGremlinClient('ws://localhost:8182/', loop=loop)
# task = gc.task(gc.send_receive, "g.V(x).out()", bindings={"x":1}, consumer=consumer)
# loop.run_until_complete(task)
