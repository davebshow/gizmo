import asyncio
import json
import uuid
import websockets


class GremlinClient(object):

    def __init__(self, uri='ws://localhost:8182/'):
        self.uri = uri
        self.loop = asyncio.get_event_loop()
        self._rows = []
        self._rownumber = 0
        self._sock = None
        self._messages = []

    def get_rows(self):
        for row in self._rows:
            yield row
    rows = property(get_rows)

    def get_sock(self):
        return self._sock
    sock = property(get_sock)

    def get_messages(self):
        return self._messages
    messages = property(get_messages)

    def __iter__(self):
        return self

    def __next__(self):
        try:
            return self.fetchone()
        except IndexError:
            raise StopIteration()

    def next(self):
        return self.__next__()

    def fetchone(self):
        row = self._rows[self._rownumber]
        self._rownumber += 1
        return row

    @asyncio.coroutine
    def connect(self):
        websocket = yield from websockets.connect(self.uri)
        self._sock = websocket
        return websocket

    @asyncio.coroutine
    def send(self, gremlin, bindings=None, lang="gremlin-groovy", op="eval",
             processor="", consumer=None, stream=False):
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
        websocket = self.sock
        if websocket is None or not websocket.open:
            websocket = yield from self.connect()
        try:
            yield from websocket.send(json.dumps(payload))
        except TypeError:
            websocket.__next__()
            yield from websocket.send(json.dumps(payload))
        while True:
            message = yield from websocket.recv()
            message_json = json.loads(message)
            code = message_json["status"]["code"]
            if code == 200:
                if consumer:
                    message_json = consumer(message_json)
                if not stream:
                    self._rows.append(message_json)
            elif code == 299:
                break
            else:
                # Raise exceptions and add messages here.
                message = message_json["status"]["message"]
                verbose = "Request {} failed with status code {}: {}".format(
                    payload["requestId"], code, message
                )
                self._messages.append(verbose)
                print(verbose)

    def execute(self, gremlin, bindings=None, lang="gremlin-groovy", op="eval",
                processor="", consumer=None, stream=False):
        self.run_until_complete(
            self.send(gremlin, bindings=bindings, lang=lang, op=op,
                      processor=processor, consumer=consumer, stream=stream)
        )
        return self

    def run_until_complete(self, func):
        self.loop.run_until_complete(func)


# gc = GremlinClient('ws://localhost:8182/')
# gc.execute("g.V(x).out()", bindings={"x":1}, consumer=lambda x: print(x))
