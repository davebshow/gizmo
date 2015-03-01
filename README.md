# gizmo 0.1.5

**API BREAKING CHANGES HAVE OCCURRED BETWEEN 0.1.4 AND 0.1.5 - AsyncGremlinClient.send_receive is now AsyncGremlinClient.submit**

**gizmo** is a **Python 3** driver for the the [TP3 Gremlin Server](http://www.tinkerpop.com/docs/3.0.0.M7/#gremlin-server). This module is built on [asyncio](https://docs.python.org/3/library/asyncio.html) and [websockets](http://aaugustin.github.io/websockets/). **gizmo** is currently in **alpha** mode, but all major functionality has test coverage.

## Getting started

Since Python 3.4 is not the default version on many systems, it's nice to create a virtualenv that uses Python 3.4 by default. Then use pip to install **gizmo**. Using virtualenvwrapper on Ubuntu 14.04:

```bash
$ mkvirtualenv -p /usr/bin/python3.4 gizmo
$ pip install gizmo
```

Fire up the Gremlin-Server.
```bash
$ ./bin/gremlin-server.sh conf/gremlin-server-modern.yaml
```
## AsyncGremlinClient

The AsyncGremlinClient uses asyncio and websockets to communicate asynchronously with the Gremlin Server. The API is based upon the use of [asyncio.Task objects](https://docs.python.org/3/library/asyncio-task.html#task), which take an [asyncio coroutine](https://docs.python.org/3/library/asyncio-task.html#coroutines) generator, wrap it in a future, and schedule its execution on the event loop. With the async client, the user must manually launch the transport layer for socket communication using one of the various methods that run the event loop. Observe:

```python
# Create a websocket connection.
>>> gc = AsyncGremlinClient('ws://localhost:8182/')

# Create a task by passing a coroutine and its parameters as args and kwargs.
# In this case, submit is a method that submits a gremlin script to the
# server and stores the responses on the client object in a message queue.
>>> task = gc.task(gc.submit, "g.V(x).out()", bindings={"x":1})

# Run the event loop until the task is complete.
>>> gc.run_until_complete(task)
```

### Basic API

At it's most basic, the AsyncGremlinClient allows to send and receive message through a socket. The GremlinServer sends reponses in chunks, so it is important to keep receiving messages until the AsyncGremlinClient.recv returns None. Observe:

```python
@asyncio.coroutine
def recv_coro(gc):
    yield from gc.send("g.V().has(n, val).values(n)",
        bindings={"n": "name", "val": "gremlin"})
    while True:
        f = yield from gc.recv()
        if f is None:
            break
        self.assertEqual(f[0], "gremlin")


gc.run_until_complete(recv_coro(gc))
```

### Message queue API

Sometimes you'll want to store the server results for later usage. To do so, AsyncGremlinClient provides the submit method, which allows you to submit a script to the server for evaluation, and then modify the responses on the fly as they come from the server before they are stored in AsyncGremlinClient.messages, an asycio.Queue. You can read messages off the queue using the read method. Observe:

```python
# This is applied to each message as it is received from the server.
consumer = lambda x: x[0] ** 2

@asyncio.coroutine
def message_queue_coro(gc):
    yield from gc.submit("2 + 2"), consumer=consumer)
    while True:
        f = yield from gc.read()
        if f is None:
            break
        assert(f == 16)


>>> gc.run_until_complete(message_queue_coro(gc))

# A consumer could also be a coroutine
@asyncio.coroutine
def consumer_coro(x):
    yield from asyncio.sleep(0)
    return x[0] ** 2

@asyncio.coroutine
def coroutine_consumer_coro():
    yield from gc.submit("2 + 2"), consumer=consumer)
    # Access the messages queue directly.
    while not gc.messages.empty():
        f = yield from gc.read()
        assert(f == 16)


>>> gc.run_until_complete(coroutine_consumer_coro(gc))
```

### Parallel task execution

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
# The consumer is an optional param that allows access to the messages
# as they are returned from the server.
>>> gc.add_task(gc.submit, "g.V().values(n)", bindings={"n": "name"},
        consumer=lambda x: print(x))

# This runs all the declared tasks.
>>> gc.run_tasks()
# ['marko', 'vadas', 'lop', 'josh', 'ripple', 'peter']
# superslow
```

### GremlinResponse

**gizmo** just barely parses the Gremlin Server response message by wrapping it in a GremlinResponse object. This object inherits from list, and the content of the response is available using all normal list methods, iteration etc. The GremlinResponse also includes the metadata contained in the server response as properties.

### asyncio with gizmo

As the above examples demonstrate, AsyncGremlinClient is made to be interoperable with asyncio. Here is an example that uses asyncio to create synchronous communication with the Gremlin Server.

```python

# Define a coroutine that sequentially executes instructions.
@asyncio.coroutine
def client(gc):
    yield from superslow()
    yield from gc.task(gc.submit, "g.V().values(n)",
        bindings={"n": "name"})
    # Response messages sent by server are stored in an asyncio.Queue
    while True:
        f = yield from gc.messages.get()
        if f is None:
            break
        print(f)


>>> gc = AsyncGremlinClient('ws://localhost:8182/')
>>> gc.run_until_complete(client(gc))
# superslow
# ['marko', 'vadas', 'lop', 'josh', 'ripple', 'peter']
```

### AsyncGremlinClient.task_queue

You can use the AsyncGremlinClient task queue to enqueue and dequeue tasks. Tasks are executed as they are dequeued.

Let's set up the example graph used in the TP3 docs.

Fire up the Gremlin-Server.

```bash
$ ./bin/gremlin-server.sh conf/gremlin-server.yaml
```

```python
@asyncio.coroutine
def graph_create_coro(gc):
    # Open a TinkerGraph.
    yield from gc.task(gc.submit, "g = TinkerGraph.open()",
        consumer=lambda x: x)
    f = yield from gc.messages.get()
    assert(f.status_code == 200)

    # Clear the graph.
    yield from gc.task(gc.submit, "g.V().remove(); g.E().remove();",
        collect=False)

    # Add nodes, edge, add/remove properties.
    yield from gc.task(gc.submit,
        ("gremlin = g.addVertex(label,'software','name','gremlin');" +
         "gremlin.property('created', 2009);" +
         "blueprints = g.addVertex(label,'software','name','blueprints');" +
         "gremlin.addEdge('dependsOn',blueprints);" +
         "blueprints.property('created',2010);" +
         "blueprints.property('created').remove()"), collect=False)

    # Confirm node creation.
    yield from gc.task(gc.submit, "g.V().count()", consumer=lambda x: x)
    f = yield from gc.messages.get()
    assert(f[0] == 2)

    # Confirm edge creation.
    yield from gc.task(gc.submit, "g.E().count()", consumer=lambda x: x)
    f = yield from gc.messages.get()
    assert(f[0] == 1)

>>> gc = AsyncGremlinClient("ws://localhost:8182/")
>>> gc.run_until_complete(graph_create_coro(gc))
```

Ok, now use the task queue to interact with the graph.

```python
# A new slow coroutine for these examples.
@asyncio.coroutine
def sleepy(gc, consumer=None):
    if consumer is None:
        consumer = lambda x: x[0]
    yield from asyncio.sleep(0.25)
    yield from gc.task(gc.submit, "g.V().has(n, val).values(n)",
        bindings={"n": "name", "val": "gremlin"}, consumer=consumer)


# Enqueue two tasks, the first sleepy, the second fast. Then dequeue and
# execute them one by one
@asyncio.coroutine
def enqueue_dequeue_coro(gc):
    # Enqueues.
    yield from gc.enqueue_task(sleepy)
    yield from gc.enqueue_task(gc.submit, "g.V().has(n, val).values(n)",
        bindings={"n": "name", "val": "blueprints"},
        consumer=lambda x: x[0])

    # Dequeues.
    yield from gc.dequeue_task()
    yield from gc.dequeue_task()

    # Test that first in first out was maintained.
    mssg1 = yield from gc.messages.get()
    assert(mssg1 == "gremlin")
    print("Successfully dequeued slow operation: gremlin")
    mssg2 = yield from gc.messages.get()
    assert(mssg2 == "blueprints")
    print("Successfully dequeued fast operation: blueprints")


>>> gc.run_until_complete(enqueue_dequeue_coro(gc))
```


Use dequeue_all to dequeue and execute all tasks in the order in which they were enqueued.

```python
@asyncio.coroutine
def client(gc):
    yield from gc.enqueue_task(superslow)
    yield from gc.enqueue_task(gc.submit, "g.V().values(name)",
        bindings={"name": "name"})
    yield from gc.dequeue_all()


>>> gc.run_until_complete(client(gc))
```

A more advanced usage of the task queue would be to use async_dequeue_all, which requires you to define a coroutine that takes the task_queue as a param and uses the asyncio.Queue.get method to retrieve a coroutine and its args and kwargs. Behind the scenes, this creates a coroutine for each item in the queue, and then executes them on the queue asynchronously. Observe:

```python
# Get a coro from the queue and create a task.
@asyncio.coroutine
def async_dequeue_consumer(q):
    coro, args, kwargs = yield from q.get()
    task = gc.task(coro, *args, **kwargs)
    f = yield from task


@asyncio.coroutine
def enqueue_all_coro(gc):
    yield from gc.enqueue_task(sleepy,
        consumer=lambda x: x[0])
    yield from gc.enqueue_task(gc.submit, "g.V().has(n, val).values(n)",
        bindings={"n": "name", "val": "blueprints"},
        consumer=lambda x: x[0])


# Add all items to the task queue.
>>> gc.run_until_complete(enqueue_all_coro(gc))
# Map the consumer coroutines to the task queue.
>>> gc.async_dequeue_all(async_dequeue_consumer)


# This coroutine just tests the results of the above pattern.
@asyncio.coroutine
def test_messages_coro():
    mssg1 = yield from gc.messages.get()
    mssg2 = yield from gc.messages.get()
    assert(mssg1 == "blueprints")
    print("Async returned fast first: blueprints")
    assert(mssg2 == "gremlin")
    print("Async returned slow second gremlin")


>>> gc.run_until_complete(check_messages_coro())
```

### And much more...

Now it is up to you to explore to explore Gremlin and the different ways you can use asyncio and **gizmo** to interact with the Gremlin Server :D!

```python
from functools import partial


def on_chunk(chunk, f):
    chunk = chunk
    f.write(json.dumps(chunk) + '\n')


@asyncio.coroutine
def slowjson(gc):
    yield from asyncio.sleep(5)
    yield from gc.send("g.V().values(n)", bindings={"n": "name"})


@asyncio.coroutine
def client():
    gc = AsyncGremlinClient('ws://localhost:8182/')
    with open("testfile.txt", "w") as f:
        p = partial(on_chunk, f=f)
        yield from slowjson(gc)
        yield from gc.receive(consumer=p, collect=False)  # Don't collect messages.
        yield from gc.send("g.V(x).out()", bindings={"x":1})
        yield from gc.receive(consumer=p, collect=False)  # Don't collect messages.
        if gc.messages.empty():
            print("No messages collected.")


>>> asyncio.get_event_loop().run_until_complete(client())
```

Here's the output:

```python
>>> f = open("testfile.txt")
>>> for line in f:
...     print(line)
["marko", "vadas", "lop", "josh", "ripple", "peter"]

[{"label": "software", "name": ["lop"], "type": "vertex", "lang": ["java"], "id": 3}, {"label": "person", "name": ["vadas"], "age": [27], "type": "vertex", "id": 2}, {"label": "person", "name": ["josh"], "age": [32], "type": "vertex", "id": 4}]

```

## Tornado Interoperability Example

Use **gizmo** with [Tornado](http://tornado.readthedocs.org/en/latest/index.html):

```python
import asyncio
import json
from tornado import escape, gen
from tornado.web import RequestHandler, Application, url
from tornado.platform.asyncio import AsyncIOMainLoop

from gizmo import AsyncGremlinClient


class GremlinHandler(RequestHandler):
    @gen.coroutine
    def get(self):
        gc = AsyncGremlinClient(uri='ws://localhost:8182/')
        # Could define custom receive here, but for brevity...
        yield from gc.task(gc.submit, "g.V().values(n)",
            bindings={"n": "name"})
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
    # Must create IOLoop before calling app.listen.
    AsyncIOMainLoop().install()
    app.listen(8888)
    asyncio.get_event_loop().run_forever()


if __name__ == '__main__':
    print("Starting server at http://localhost:8888/")
    main()
```

## GremlinClient

GremlinClient.execute returns self, which provides an iterator over the messages received through the websocket.

```python
>>> from gizmo import GremlinClient
>>> gc = GremlinClient('ws://localhost:8182/')
>>> gc.execute("g.V(x).out()", bindings={"x":1}, consumer=lambda x: print(x))

>>> for x in gc.execute("g.V(x).out()", bindings={"x":1}):
...     if x:
...         print(x)
```


**TODO:**

* SSL Server Tests
* Error handling!!!
