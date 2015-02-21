# gizmo

**gizmo** is a **Python 3** driver for the the [TP3 Gremlin Server](http://www.tinkerpop.com/docs/3.0.0.M7/#gremlin-server). This module is built on [asyncio](https://docs.python.org/3/library/asyncio.html) and [websockets](http://aaugustin.github.io/websockets/).

## Getting started:


Fire up the Gremlin-Server.
```bash
$ ./bin/gremlin-server.sh conf/gremlin-server-modern.yaml
```
## AsyncGremlinClient

The AsyncGremlinClient uses asyncio and websockets to communicate asynchronously with the Gremlin Server. The API is based upon the use of [asyncio.Task objects](https://docs.python.org/3/library/asyncio-task.html#task), which take an [asyncio coroutine](https://docs.python.org/3/library/asyncio-task.html#coroutines) generator, wrap it in a future, and schedule its execution on the event loop. With the async client, the user must manually launch the transport layer for socket communication using one of the various methods that run the event loop. Observe:

```python
# Create a websocket connection.
>>> gc = AsyncGremlinClient('ws://localhost:8182/')

# Define a consumer to use in the examples. This is mapped to the response
# messages from server as they arrive.
>>> consumer = lambda x: print(x["result"]["data"])

# Create a task by passing a coroutine and its parameters as args and kwargs.
# In this case, send_receive is a method that submits a gremlin script to the
# server and stores the responses on the client object in a message queue.
>>> task = gc.task(gc.send_receive, "g.V(x).out()", bindings={"x":1},
                   consumer=consumer)

# Run the event loop until the task is complete.
>>> gc.run_until_complete(task)

#[{'id': 3, 'type': 'vertex', 'properties': {'lang': [{'id': 5, 'value': 'java', 'properties': {}}], 'name': [{'id': 4, 'value': 'lop', 'properties': {}}]}, 'label': 'software'}, {'id': 2, 'type': 'vertex', 'properties': {'name': [{'id': 2, 'value': 'vadas', 'properties': {}}], 'age': [{'id': 3, 'value': 27, 'properties': {}}]}, 'label': 'person'}, {'id': 4, 'type': 'vertex', 'properties': {'name': [{'id': 6, 'value': 'josh', 'properties': {}}], 'age': [{'id': 7, 'value': 32, 'properties': {}}]}, 'label': 'person'}]


```

We can also use some typical patterns from asyncio to interact with the tasks and the event loop:

```python
# Create a task.
>>> task = gc.task(gc.send_receive, "g.V().values(n)", bindings={"n": "name"},
                   consumer=consumer)

# Add a callback to execute when the task is complete, in this case stop the event loop.
>>> task.add_done_callback(gc.stop)

# Run the event loop until the callback calls stop.
>>> gc.run_forever()

```

It's easy to run a bunch of tasks in "parallel", just add them to the client and run them. Warning: the following is an asynchronous technique and does not guarantee the order in which tasks will be completed. Observe:

```python
# Our "slow" function. This will always take longer than other tasks.
@asyncio.coroutine
def superslow():
    yield from asyncio.sleep(5)
    print("superslow")


# Submit the slow task first.
>>> gc.add_task(superslow)

# Now the fast task.
>>> gc.add_task(gc.send_receive, "g.V().values(n)", bindings={"n": "name"},
                consumer=consumer)

# This runs all the declared tasks.
>>> gc.run_tasks()

# ['marko', 'vadas', 'lop', 'josh', 'ripple', 'peter']
# superslow

```

As the above example demonstrates, AsyncGremlinClient is made to be interoperable with asyncio. Here is an example that uses asyncio to create synchronous communication with the Gremlin Server.

```python
# This consumer actually returns a value to the message queue.
>>> consumer = lambda x: x["result"]["data"]

# Define a coroutine that sequentially executes instructions.
@asyncio.coroutine
def client(gc):
    yield from superslow()
    yield from gc.task(gc.send_receive, "g.V().values(n)",
                       bindings={"n": "name"}, consumer=consumer)
    # Response messages sent by server are stored in an asyncio.Queue
    while not gc.messages.empty():
        f = yield from gc.messages.get()
        print(f)

>>> gc = AsyncGremlinClient('ws://localhost:8182/')
>>> gc.run_until_complete(client(gc))

# superslow
# ['marko', 'vadas', 'lop', 'josh', 'ripple', 'peter']

```

Alternatively, you can use the AsyncGremlinClient task queue to enqueue and dequeue tasks. Tasks are executed as they are dequeued.

```python
@asyncio.coroutine
def client(gc):
    yield from gc.enqueue_task(superslow)
    yield from gc.enqueue_task(
        gc.send_receive,
        "g.V().values(name)",
        bindings={"name": "name"},
        consumer=consumer
    )
    yield from gc.dequeue_all(consumer=consumer)


>>> gc.run_until_complete(client(gc))
```

**gizmo** handles its own event loop internally, but if you want to use a different event loop, just pass it to the constructor.

Now it is up to you to explore to explore Gremlin and the different ways you can use asyncio and gizmo to interact with the Gremlin Server :D!

```python
from functools import partial


def on_chunk(chunk, f):
    chunk = chunk["result"]["data"]
    f.write(json.dumps(chunk) + '\n')


@asyncio.coroutine
def slowjson(p):
    yield from asyncio.sleep(5)
    yield from gc.send("g.V().values(n)", bindings={"n": "name"},
                       consumer=p)


@asyncio.coroutine
def client(gc, f):
    p = partial(on_chunk, f=f)
    yield from slowjson(p)
    yield from gc.receive(consumer=p, collect=False)
    yield from gc.send("g.V(x).out()", bindings={"x":1})
    yield from gc.receive(consumer=p, collect=False)  # Don't collect messages.
    if gc.messages.empty():
        print("No messages")


>>> loop = asyncio.get_event_loop()
>>> gc = AsyncGremlinClient('ws://localhost:8182/', loop=loop)
>>> f = open("testfile.txt", "w")
>>> loop.run_until_complete(client(gc, f))
>>> f.close()
```

Here's the output:

```python
>>> f = open("testfile.txt")
>>> for line in f:
        print(line)

# ["marko", "vadas", "lop", "josh", "ripple", "peter"]

# [{"id": 3, "label": "software", "properties": {"lang": [{"id": 5, "value": "java", "properties": {}}], "name": [{"id": 4, "value": "lop", "properties": {}}]}, "type": "vertex"}, {"id": 2, "label": "person", "properties": {"age": [{"id": 3, "value": 27, "properties": {}}], "name": [{"id": 2, "value": "vadas", "properties": {}}]}, "type": "vertex"}, {"id": 4, "label": "person", "properties": {"age": [{"id": 7, "value": 32, "properties": {}}], "name": [{"id": 6, "value": "josh", "properties": {}}]}, "type": "vertex"}]
```

## Tornado Interoperability Example

Use **gizmo** with [Tornado](http://tornado.readthedocs.org/en/latest/index.html):

```python
import asyncio
import json
from gizmo import AsyncGremlinClient
from tornado import gen
from tornado.web import RequestHandler, Application, url
from tornado.platform.asyncio import AsyncIOMainLoop


class GremlinHandler(RequestHandler):
    @gen.coroutine
    def get(self):
        gc = AsyncGremlinClient(uri='ws://localhost:8182/')
        consumer = lambda x: x["result"]["data"]
        yield from gc.task(gc.send_receive, "g.V().values(n)",
                           bindings={"n": "name"}, consumer=consumer)
        while not gc.messages.empty():
            message = yield from gc.messages.get()
            message = json.dumps(message)
            self.write(message)


def make_app():
    return Application([
        url(r"/", GremlinHandler),
    ])


def main():
    app = make_app()
    app.listen(8888)
    AsyncIOMainLoop().install()
    asyncio.get_event_loop().loop.run_forever()


if __name__ == '__main__':
    print("Starting server at http://localhost:8888/")
    main()

```

## GremlinClient

Use websockets to submit Gremlin scripts to the server and receive the results. GremlinClient.execute returns self, which provides and iterator over the messages returned in the server response.
```python
>>> from gizmo import GremlinClient
>>> gc = GremlinClient('ws://localhost:8182/')
>>> gc.execute("g.V(x).out()", bindings={"x":1}, consumer=lambda x: print(x))

# {'result': {'data': [{'label': 'software', 'id': 3, 'properties': {'name': [{'value': 'lop', 'id': 4, 'properties': {}}], 'lang': [{'value': 'java', 'id': 5, 'properties': {}}]}, 'type': 'vertex'}, {'label': 'person', 'id': 2, 'properties': {'name': [{'value': 'vadas', 'id': 2, 'properties': {}}], 'age': [{'value': 27, 'id': 3, 'properties': {}}]}, 'type': 'vertex'}, {'label': 'person', 'id': 4, 'properties': {'name': [{'value': 'josh', 'id': 6, 'properties': {}}], 'age': [{'value': 32, 'id': 7, 'properties': {}}]}, 'type': 'vertex'}], 'meta': {}}, 'requestId': '9c2d1263-eebf-47e9-a169-5b790eb49d6f', 'status': {'code': 200, 'message': '', 'attributes': {}}}

>>> for x in gc.execute("g.V(x).out()", bindings={"x":1}):
        if x:
            print(x)

# {'result': {'data': [{'label': 'software', 'id': 3, 'properties': {'name': [{'value': 'lop', 'id': 4, 'properties': {}}], 'lang': [{'value': 'java', 'id': 5, 'properties': {}}]}, 'type': 'vertex'}, {'label': 'person', 'id': 2, 'properties': {'name': [{'value': 'vadas', 'id': 2, 'properties': {}}], 'age': [{'value': 27, 'id': 3, 'properties': {}}]}, 'type': 'vertex'}, {'label': 'person', 'id': 4, 'properties': {'name': [{'value': 'josh', 'id': 6, 'properties': {}}], 'age': [{'value': 32, 'id': 7, 'properties': {}}]}, 'type': 'vertex'}], 'meta': {}}, 'requestId': 'ab51311f-d532-401a-9f4b-df6434765bd3', 'status': {'code': 200, 'message': '', 'attributes': {}}}

```
