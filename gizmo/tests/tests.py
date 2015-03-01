import asyncio
import unittest
from gizmo import BaseGremlinClient, AsyncGremlinClient, GremlinClient


class BaseGremlinClientTests(unittest.TestCase):

    def setUp(self):
        self.client = BaseGremlinClient("ws://localhost:8182/")

    def test_connection(self):
        @asyncio.coroutine
        def conn_coro():
            conn = yield from self.client.connect()
            self.assertTrue(conn.open)
        self.client.run_until_complete(conn_coro())


class AsyncGremlinClientTests(unittest.TestCase):

    def setUp(self):
        self.client = AsyncGremlinClient("ws://localhost:8182/")

    def test_01_connection(self):
        @asyncio.coroutine
        def conn_coro():
            conn = yield from self.client.connect()
            self.assertTrue(conn.open)
        self.client.run_until_complete(conn_coro())

    ### Basic server communication tests. This implements the opening example
    ### from http://www.tinkerpop.com/docs/3.0.0.M7/###

    def test_02_graph_create(self):
        @asyncio.coroutine
        def graph_open_coro():
            yield from self.client.task(self.client.submit,
                                        "g = TinkerGraph.open()")
            f = yield from self.client.messages.get()
            self.assertEqual(f.status_code, 200)
        self.client.run_until_complete(graph_open_coro())

    def test_03_node_edge_create(self):
        @asyncio.coroutine
        def node_edge_create_coro():
            yield from self.client.task(
                self.client.submit,
                "g.V().remove(); g.E().remove();",
                collect=False
            )

            yield from self.client.task(
                self.client.submit,
                ("gremlin = g.addVertex(label,'software','name','gremlin');" +
                 "gremlin.property('created', 2009);" +
                 "blueprints = g.addVertex(label,'software','name','blueprints');" +
                 "gremlin.addEdge('dependsOn',blueprints);" +
                 "blueprints.property('created',2010);" +
                 "blueprints.property('created').remove()"),
                collect=False)

            yield from self.client.task(
                self.client.submit,
                "g.V().count()")
            f = yield from self.client.messages.get()
            self.assertEqual(f[0], 2)

            yield from self.client.task(
                self.client.submit,
                "g.E().count()")
            f = yield from self.client.messages.get()
            self.assertEqual(f[0], 1)

            yield from self.client.task(
                self.client.submit,
                "g.V()")
            nodes = ["gremlin", "blueprints"]
            f = yield from self.client.messages.get()
            label = f[0]["label"]
            self.assertEqual(label, "software")
            name1 = f[0]["name"][0]
            self.assertTrue(name1 in nodes)
            nodes.remove(name1)
            print("Successfully created node of type software: gremlin")
            name2 = f[1]["name"][0]
            self.assertTrue(name2 in nodes)
            crtd = f[1].get("created", "")
            self.assertEqual(crtd, "")
            print("Successfully created node of type software: blueprints")

            yield from self.client.task(
                self.client.submit,
                "g.E()")
            f = yield from self.client.messages.get()
            label = f[0]["label"]
            in_label = f[0]["inVLabel"]
            out_label = f[0]["outVLabel"]
            self.assertEqual(label, "dependsOn")
            self.assertEqual(in_label, "software")
            self.assertEqual(out_label, "software")
            print("Successfully created edge of type dependsOn: " +
                  "software dependsOn software")
        self.client.run_until_complete(node_edge_create_coro())

    ### Tests for the consumer - if returns value, add to the message queue.

    def test_04_consumer_return(self):
        @asyncio.coroutine
        def consumer_return_coro():
            yield from self.client.task(
                self.client.submit,
                "1 + 1",
                consumer=lambda x: x[0] ** 2)
            while not self.client.messages.empty():
                f = yield from self.client.messages.get()
                self.assertEqual(f, 4)
                print("Consumer added results to messages")
        self.client.run_until_complete(consumer_return_coro())

    def test_05_consumer_noreturn(self):
        @asyncio.coroutine
        def consumer_noreturn_coro():
            yield from self.client.task(
                self.client.submit,
                "1 + 1",
                consumer=lambda x: print(x[0] ** 2))
            self.assertTrue(self.client.messages.empty())
            print("Consumer did not add results to messages")
        self.client.run_until_complete(consumer_noreturn_coro())

    ### Collect false turns off collection.

    def test_06_collect_false(self):
        @asyncio.coroutine
        def consumer_return_coro():
            yield from self.client.task(
                self.client.submit,
                "1 + 1",
                consumer=lambda x: x[0] ** 2,
                collect=False)
            self.assertTrue(self.client.messages.empty())
            print("No collection performed")
        self.client.run_until_complete(consumer_return_coro())

    ### Run async parallel tasks.

    @asyncio.coroutine
    def slowjson(self, consumer=None):
        if consumer is None:
            consumer = lambda x: x[0]
        yield from asyncio.sleep(0.25)
        yield from self.client.task(
            self.client.submit,
            "g.V().has(n, val).values(n)",
            bindings={"n": "name", "val": "gremlin"},
            consumer=consumer)

    def test_07_parallel_tasks(self):
        task1 = self.client.add_task(self.slowjson)
        task2 = self.client.add_task(
            self.client.submit,
            "g.V().has(n, val).values(n)",
            bindings={"n": "name", "val": "blueprints"},
            consumer=lambda x: x[0])
        self.client.run_tasks()
        names = []
        @asyncio.coroutine
        def parallel_task_coro():
            while not self.client.messages.empty():
                f = yield from self.client.messages.get()
                names.append(f)
        self.client.run_until_complete(parallel_task_coro())

        self.assertEqual(names[0], "blueprints")
        self.assertEqual(names[1], "gremlin")
        print("Asynchronous task execution successful.")

    ### Enqueue/dequeue tests.

    def test_08_enqueue_dequeue(self):
        @asyncio.coroutine
        def enqueue_dequeue_coro():
            yield from self.client.enqueue_task(self.slowjson)
            yield from self.client.enqueue_task(
                self.client.submit,
                "g.V().has(n, val).values(n)",
                bindings={"n": "name", "val": "blueprints"},
                consumer=lambda x: x[0])
            yield from self.client.dequeue_task()
            yield from self.client.dequeue_task()
            mssg1 = yield from self.client.messages.get()
            self.assertEqual(mssg1, "gremlin")
            print("Successfully dequeued slow operation: gremlin")
            mssg2 = yield from self.client.messages.get()
            self.assertEqual(mssg2, "blueprints")
            print("Successfully dequeued fast operation: blueprints")

        self.client.run_until_complete(enqueue_dequeue_coro())

    def test_09_dequeue_all(self):
        messages = []
        @asyncio.coroutine
        def dequeue_all_coro():
            yield from self.client.enqueue_task(
                self.slowjson,
                consumer=lambda x: x[0])
            yield from self.client.enqueue_task(
                self.client.submit,
                "g.V().has(n, val).values(n)",
                bindings={"n": "name", "val": "blueprints"},
                consumer=lambda x: x[0])
            yield from self.client.dequeue_all()
            while True:
                mssg = yield from self.client.read()
                if mssg is None:
                    break
                messages.append(mssg)
            self.assertEqual(len(messages), 2)
            self.assertEqual(messages[0], "gremlin")
            self.assertEqual(messages[1], "blueprints")
            print("Successfully deququeued all.")
        self.client.run_until_complete(dequeue_all_coro())

    def test_10_async_dequeue_all(self):

        @asyncio.coroutine
        def check_messages_coro():
            mssg1 = yield from self.client.messages.get()
            mssg2 = yield from self.client.messages.get()
            self.assertEqual(mssg1, "blueprints")
            print("Async dequeued blueprints")
            self.assertEqual(mssg2, "gremlin")
            print("Async dequeued gremlin")

        @asyncio.coroutine
        def async_dequeue_consumer(q):
            coro, args, kwargs = yield from q.get()
            task = self.client.task(coro, *args, **kwargs)
            f = yield from task

        @asyncio.coroutine
        def enqueue_all_coro():
            yield from self.client.enqueue_task(self.slowjson,
                consumer=lambda x: x[0])
            yield from self.client.enqueue_task(
                self.client.submit,
                "g.V().has(n, val).values(n)",
                bindings={"n": "name", "val": "blueprints"},
                consumer=lambda x: x[0])
        self.client.run_until_complete(enqueue_all_coro())
        self.client.async_dequeue_all(async_dequeue_consumer)
        self.client.run_until_complete(check_messages_coro())

    def test_11_recv(self):
        @asyncio.coroutine
        def recv_coro():
            yield from self.client.send("g.V().has(n, val).values(n)",
                bindings={"n": "name", "val": "gremlin"})
            while True:
                f = yield from self.client.recv()
                if f is None:
                    break
                self.assertEqual(f[0], "gremlin")
                print("Simple recv yielded {}".format(f))
        self.client.run_until_complete(recv_coro())

    def test_12_coroutine_consumer(self):
        @asyncio.coroutine
        def consumer_coro(x):
            yield from asyncio.sleep(0)
            return x[0] ** 2

        @asyncio.coroutine
        def coroutine_consumer_coro():
            yield from self.client.submit("2 + 2", consumer=consumer_coro)
            while True:
                f = yield from self.client.read()
                if f is None:
                    break
                self.assertEqual(f, 16)
                print("Simple recv yielded {}".format(f))
        self.client.run_until_complete(coroutine_consumer_coro())


class GremlinClientTests(unittest.TestCase):

    def setUp(self):
        self.client = GremlinClient("ws://localhost:8182/")

    def test_connection(self):
        @asyncio.coroutine
        def conn_coro():
            conn = yield from self.client.connect()
            self.assertTrue(conn.open)
        self.client.run_until_complete(conn_coro())

    def test_execute(self):
        self.client.execute(
            "g.V().has(n, val).values(n)",
            bindings={"n": "name", "val": "blueprints"},
            consumer=lambda x: x[0])
        self.assertEqual(self.client._messages[0], "blueprints")
        self.client.execute(
            "g.V().has(n, val).values(n)",
            bindings={"n": "name", "val": "gremlin"},
            consumer=lambda x: x[0])
        self.assertEqual(self.client._messages[1], "gremlin")
        for x in self.client:
            print("Retrieved: {}".format(x))

if __name__ == "__main__":
    unittest.main()
