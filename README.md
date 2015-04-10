# gizmo 0.1.10

**API BREAKING CHANGES HAVE OCCURRED BETWEEN 0.1.7 AND 0.1.9 - Full API documented below.**

`gizmo` is a **Python 3** driver for the the [TP3 Gremlin Server](http://www.tinkerpop.com/docs/3.0.0.M7/#gremlin-server). This module is built on [asyncio](https://docs.python.org/3/library/asyncio.html) and [websockets](http://aaugustin.github.io/websockets/). `gizmo` is currently in **alpha** mode, but all major functionality has test coverage.

## Getting started

Since Python 3.4 is not the default version on many systems, it's nice to create a virtualenv that uses Python 3.4 by default. Then use pip to install `gizmo`. Using virtualenvwrapper on Ubuntu 14.04:

```bash
$ mkvirtualenv -p /usr/bin/python3.4 gizmo
$ pip install gizmo
```

Fire up the Gremlin Server:

```bash
$ ./bin/gremlin-server.sh conf/gremlin-server-modern.yaml
```

Create and execute a task that submits a script to the Gremlin Server:

```python
>>> from gizmo import AsyncGremlinClient
>>> gc = AsyncGremlinClient()
>>> task = gc.s("x + x", bindings={"x": 2}, consumer=lambda x: print(x[0] ** 2))
>>> task.execute()
16
```


## The Basics - AsyncGremlinClient

The `AsyncGremlinClient` uses `asyncio` and `websockets` to communicate asynchronously with the Gremlin Server. The client uses a combination [asyncio.coroutine](https://docs.python.org/3/library/asyncio-task.html#coroutines)and [asyncio.Task](https://docs.python.org/3/library/asyncio-task.html#task) run on asyncio's pluggable event loop to achieve this communication.

At its most basic, the `AsyncGremlinClient` sends and receives messages through a socket. The majority of ``AsyncGremlinClient`` methods are an `asyncio.coroutine`, so you will also need to use either `asyncio` or the `gizmo` [Task API](#task-api). The following examples use `asyncio` to demonstrate the use of the AsyncioGremlineClient.

The Gremlin Server sends responses in chunks, so it is important to keep receiving messages until the `AsyncGremlinClient.recv` returns None:

```python
>>> import asyncio
>>> gc = AsyncGremlinClient('ws://localhost:8182/')


@asyncio.coroutine
def recv_coro(gc):
    # send method returns the websocket used to submit the script.
    websocket = yield from gc.send("g.V().has(n, val).values(n)",
        bindings={"n": "name", "val": "gremlin"})
    while True:
        f = yield from gc.recv(websocket)
        if f is None:
            break
        self.assertEqual(f[0], "gremlin")


>>> asyncio.get_event_loop()
>>> loop.run_until_complete(recv_coro(gc))
```


### Message queue API

Sometimes you'll want to store the server results for later usage. To do so, `AsyncGremlinClient` provides the `submit` method, which allows you to submit a script to the server for evaluation, and then modify the responses on the fly as they come from the server before they are stored in `AsyncGremlinClient.messages`, an `asycio.Queue`. You can read messages off the queue using the `read` method. Observe:

```python
# This is applied to each message as it is received from the server.
>>> consumer = lambda x: x[0] ** 2


@asyncio.coroutine
def message_queue_coro(gc):
    yield from gc.submit("2 + 2", consumer=consumer)
    while True:
        f = yield from gc.read()
        if f is None:
            break
        assert(f == 16)


>>> loop.run_until_complete(message_queue_coro(gc))


# A consumer could also be a coroutine.
@asyncio.coroutine
def consumer_coro(x):
    yield from asyncio.sleep(0)
    return x[0] ** 2


@asyncio.coroutine
def coroutine_consumer_coro():
    yield from gc.submit("2 + 2", consumer=consumer_coro)
    # Access the messages queue directly.
    while not gc.messages.empty():
        f = yield from gc.read()
        assert(f == 16)


>>> loop.run_until_complete(coroutine_consumer_coro(gc))
```

This is great if you are already using `asyncio`, or another compatible framework like `Tornado`. However, `gizmo` also provides another way to interact with the server using its Task API.

## Task API

The Task API provides a simple set of wrappers that allow you to easily manage the flow of the asynchronous websocket communication. It is loosely based on Python [Celery's Canvas](http://celery.readthedocs.org/en/latest/userguide/canvas.html), albeit much simpler. *Note* - a `gizmo.Task` mustn't be confused with an `asyncio.Task`. Also similar to `asyncio`, `gizmo` provides a constructor function `async` that returns a `gizmo.Task`.

To get started, you can simply schedule a task by wrapping a coroutine. Then the task provide a method `execute` that runs the `asyncio` event loop:

```python
# Here we will use the async constructor function to create a ``gizmo.Task`` inst.
>>> from gizmo import async
>>> coro = gc.submit("x + x", bindings={"x": 2}, consumer=consumer)
>>> task = async(coro)
>>> task.execute()
16
```

Creating a task by wrapping the submit method is so common, there is a shortcut: `AsyncGremlinClient.s`:

```python
# In practice, you will rarely use gizmo.Task explicitly. AsyncGremlinClient.s and
# gizmo.async are the preferred way to create tasks.
>>> task = gc.s("x + x", bindings={"x": 2}, consumer=consumer)
>>> task.execute()
16
```

In order to design workflows by combining asynchronous tasks, `gizmo` provides a series of classes that wrap a `gizmo.Task`: `gizmo.Group`, `gizmo.Chain`, `gizmo.Chord`. These classes are quite similar to their Celery counterparts. Note - all of the classes in the Task API inherit from `gizmo.Task` and are therefore you may pass any task to any other task to compose complex workflows.

#### Group

`gizmo.Group` allows you to group and then asynchronously execute tasks in parallel:

```python
# These simulate slow tasks with various completion times.
@asyncio.coroutine
def consumer_coro1(x):
    yield from asyncio.sleep(0.25)
    return x[0] ** 0


def consumer_coro2(x):
    yield from asyncio.sleep(0.50)
    return x[0] ** 1


>>> t = gc.s("x + x", bindings={"x": 2}, consumer=lambda x : x[0] ** 2)
>>> slow = gc.s("x + x", bindings={"x": 2}, consumer=consumer_coro1)
>>> g = group(slow, t)
>>> g.execute()
>>> results = [m for m in gc]
>>> assert(results[0] == 16)
>>> assert(results[1] == 1)
```

#### Chain

`gizmo.Chain` allows you to create a chain of tasks that execute in a synchronous fashion:

```python
>>> t = gc.s("x + x", bindings={"x": 2}, consumer=lambda x : x[0] ** 2)
>>> slow = gc.s("x + x", bindings={"x": 2}, consumer=consumer_coro1)
>>> chain(slow, t).execute()
>>> results = [m for m in gc]
>>> assert(results[0] == 1)
>>> assert(results[1] == 16)
```

#### Chord

`gizmo.Chord` allows you to asynchronously execute a group of tasks in parallel, with an added callback.

```python
>>> slow1 = gc.s("x + x", bindings={"x": 2}, consumer=consumer_coro1)
>>> slow2 = gc.s("x + x", bindings={"x": 2}, consumer=consumer_coro2)
>>> t = gc.s("x + x", bindings={"x": 2}, consumer=lambda x : x[0] ** 2)
>>> chord([slow2, slow1], t).execute()
>>> results = [m for m in gc]
>>> assert(results[0] == 1)
>>> assert(results[1] == 4)
>>> assert(results[1] == 16)
```

#### A more complex example:

```python
def simple_graph():
    gc = AsyncGremlinClient()
    # Define various tasks.
    t = gc.s("g.V().remove(); g.E().remove();", collect=False)
    t1 = gc.s("g.addVertex('uniqueId', x)", bindings={"x": "joe"},
        collect=False)
    t2 = gc.s("g.addVertex('uniqueId', x)", bindings={"x": "maria"},
        collect=False)
    t3 = gc.s("g.addVertex('uniqueId', x)", bindings={"x": "jill"},
        collect=False)
    t4 = gc.s("g.addVertex('uniqueId', x)", bindings={"x": "jack"},
        collect=False)
    t5 = gc.s("""
        joe = g.V().has('uniqueId', 'joe').next();
        itziri = g.V().has('uniqueId', 'itziri').next();
        joe.addEdge('marriedTo', itziri);""")
    t6 = gc.s("""
        jill = g.V().has('uniqueId', 'jill').next();
        jack = g.V().has('uniqueId', 'jack').next();
        jill.addEdge('marriedTo', jack);""")
    t7 = gc.s("""
        jill = g.V().has('uniqueId', 'jill').next();
        joe = g.V().has('uniqueId', 'joe').next();
        jill.addEdge('hasSibling', joe);""")
    t8 = gc.s("g.V();", consumer=lambda x: print(x))
    t9 = gc.s("g.E();", consumer=lambda x: print(x))
    t10 = gc.s("g.V().count();", consumer=lambda x: assert(x[0] == 4))
    t11 = gc.s("g.E().count();", consumer=lambda x: assert(x[0] == 3))
    # Define groups.
    g1 = group(t1, t2, t3, t4)
    g2 = group(t5, t6, t7)
    # Use chain to control order of task execution.
    c = chain(t, g1, g2, t8, t9, t10, t11, t)
    c.execute()


>>> simple_graph()
[{'type': 'vertex', 'id': 17, 'label': 'vertex', 'uniqueId': ['maria']}, {'type': 'vertex', 'id': 11, 'label': 'vertex', 'uniqueId': ['jack']}, {'type': 'vertex', 'id': 13, 'label': 'vertex', 'uniqueId': ['joe']}, {'type': 'vertex', 'id': 15, 'label': 'vertex', 'uniqueId': ['jill']}]
[{'outVLabel': 'vertex', 'label': 'hasSibling', 'inV': 13, 'type': 'edge', 'id': 19, 'outV': 15, 'inVLabel': 'vertex'}, {'outVLabel': 'vertex', 'label': 'marriedTo', 'inV': 11, 'type': 'edge', 'id': 20, 'outV': 15, 'inVLabel': 'vertex'}, {'outVLabel': 'vertex', 'label': 'marriedTo', 'inV': 17, 'type': 'edge', 'id': 21, 'outV': 13, 'inVLabel': 'vertex'}]
[[{'outVLabel': 'vertex', 'label': 'hasSibling', 'inV': 13, 'type': 'edge', 'id': 19, 'outV': 15, 'inVLabel': 'vertex'}], [{'outVLabel': 'vertex', 'label': 'marriedTo', 'inV': 11, 'type': 'edge', 'id': 20, 'outV': 15, 'inVLabel': 'vertex'}], [{'outVLabel': 'vertex', 'label': 'marriedTo', 'inV': 17, 'type': 'edge', 'id': 21, 'outV': 13, 'inVLabel': 'vertex'}]]

```

### GremlinResponse

`gizmo` just barely parses the Gremlin Server response message by wrapping it in a `GremlinResponse` object. This object inherits from a Python `list`, and the content of the response is available using all normal `list` methods, iteration etc. The `GremlinResponse` also includes the metadata contained in the server response as properties.

### asyncio with gizmo

As the above examples demonstrate, `AsyncGremlinClient` is made to be interoperable with `asyncio`. Really you can do just about anything. Here is an example that uses `asyncio` to create synchronous communication with the Gremlin Server.

```python

@asyncio.coroutine
def sleepy(gc):
    yield from asyncio.sleep(0.25)
    yield from gc.submit()"g.V().has(n, val).values(n)",
        bindings={"n": "name", "val": "gremlin"})

# Define a coroutine that sequentially executes instructions.
@asyncio.coroutine
def client(gc):
    yield from sleepy(gc)
    yield from gc.submit("g.V().values(n)",
        bindings={"n": "name"})
    # Response messages sent by server are stored in an asyncio.Queue
    while True:
        f = yield from gc.messages.get()
        if f is None:
            break
        print(f)


>>> gc = AsyncGremlinClient('ws://localhost:8182/')
>>> loop.run_until_complete(client(gc))
['gremlin']
['marko', 'vadas', 'lop', 'josh', 'ripple', 'peter']
```

## gizmo with Titan

[IPython notebook example](http://nbviewer.ipython.org/github/davebshow/projx/blob/master/titan.ipynb)

## Tornado Interoperability Example

Use `gizmo` with [Tornado](http://tornado.readthedocs.org/en/latest/index.html):

```python
import asyncio
import json
from tornado import gen
from tornado.web import RequestHandler, Application, url
from tornado.platform.asyncio import AsyncIOMainLoop

from gizmo import AsyncGremlinClient


class GremlinHandler(RequestHandler):
    @gen.coroutine
    def get(self):
        gc = AsyncGremlinClient(uri='ws://localhost:8182/')
        yield from gc.submit("g.V().values(n)", bindings={"n": "name"})
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
