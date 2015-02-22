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
        self.consumer = lambda x: x["result"]["data"]

    def test_connection(self):
        @asyncio.coroutine
        def conn_coro():
            conn = yield from self.client.connect()
            self.assertTrue(conn.open)
        self.client.run_until_complete(conn_coro())

    ### Basic server communication tests. This implements the opening example
    ### from http://www.tinkerpop.com/docs/3.0.0.M7/###

    def test_graph_create(self):
        @asyncio.coroutine
        def graph_open_coro():
            yield from self.client.task(self.client.send_receive,
                                        "g = TinkerGraph.open()",
                                        consumer=lambda x: x)
            while not self.client.messages.empty():
                f = yield from self.client.messages.get()
                self.assertEqual(f["status"]["code"], 200)
        self.client.run_until_complete(graph_open_coro())

    def test_node_edge_create(self):
        @asyncio.coroutine
        def node_edge_create_coro():
            yield from self.client.task(
                self.client.send_receive,
                "g.V().remove(); g.E().remove();",
                collect=False
            )

            yield from self.client.task(
                self.client.send_receive,
                ("gremlin = g.addVertex(label,'software','name','gremlin');" +
                 "gremlin.property('created', 2009);" +
                 "blueprints = g.addVertex(label,'software','name','blueprints');" +
                 "gremlin.addEdge('dependsOn',blueprints);" +
                 "blueprints.property('created',2010);" +
                 "blueprints.property('created').remove()"),
                collect=False)

            yield from self.client.task(
                self.client.send_receive,
                "g.V().count()",
                consumer=lambda x: x)
            while not self.client.messages.empty():
                f = yield from self.client.messages.get()
                self.assertEqual(f["result"]["data"][0], 2)

            yield from self.client.task(
                self.client.send_receive,
                "g.E().count()",
                consumer=lambda x: x)
            while not self.client.messages.empty():
                f = yield from self.client.messages.get()
                self.assertEqual(f["result"]["data"][0], 1)

            yield from self.client.task(
                self.client.send_receive,
                "g.V()")
            while not self.client.messages.empty():
                nodes = ["gremlin", "blueprints"]
                f = yield from self.client.messages.get()
                label = f["result"]["data"][0]["label"]
                self.assertEqual(label, "software")
                name1 = f["result"]["data"][0]["properties"]["name"][0]["value"]
                self.assertTrue(name1 in nodes)
                nodes.remove(name1)
                print("Successfully created node of type software: gremlin")
                name2 = f["result"]["data"][1]["properties"]["name"][0]["value"]
                self.assertTrue(name2 in nodes)
                crtd = f["result"]["data"][1]["properties"].get("created", "")
                self.assertEqual(crtd, "")
                print("Successfully created node of type software: blueprints")

            yield from self.client.task(
                self.client.send_receive,
                "g.E()")
            while not self.client.messages.empty():
                f = yield from self.client.messages.get()
                label = f["result"]["data"][0]["label"]
                in_label = f["result"]["data"][0]["inVLabel"]
                out_label = f["result"]["data"][0]["outVLabel"]
                self.assertEqual(label, "dependsOn")
                self.assertEqual(in_label, "software")
                self.assertEqual(out_label, "software")
                print("Successfully created edge of type dependsOn: " +
                      "software dependsOn software")
        self.client.run_until_complete(node_edge_create_coro())

    ### Tests for the consumer - if returns value, add to the message queue.

    def test_consumer_return(self):
        @asyncio.coroutine
        def consumer_return_coro():
            yield from self.client.task(
                self.client.send_receive,
                "1 + 1",
                consumer=lambda x: x["result"]["data"][0] ** 2)
            while not self.client.messages.empty():
                f = yield from self.client.messages.get()
                self.assertEqual(f, 4)
                print("Consumer added results to messages")
        self.client.run_until_complete(consumer_return_coro())

    def test_consumer_noreturn(self):
        @asyncio.coroutine
        def consumer_noreturn_coro():
            yield from self.client.task(
                self.client.send_receive,
                "1 + 1",
                consumer=lambda x: print(x["result"]["data"][0] ** 2))
            self.assertTrue(self.client.messages.empty())
            print("Consumer did not add results to messages")
        self.client.run_until_complete(consumer_noreturn_coro())

    ### Collect false turns off collection.

    def test_collect_false(self):
        @asyncio.coroutine
        def consumer_return_coro():
            yield from self.client.task(
                self.client.send_receive,
                "1 + 1",
                consumer=lambda x: x["result"]["data"][0] ** 2,
                collect=False)
            self.assertTrue(self.client.messages.empty())
            print("No collection performed")
        self.client.run_until_complete(consumer_return_coro())

    ### Run async parallel tasks.

    @asyncio.coroutine
    def slowjson(self, consumer=None):
        if consumer is None:
            consumer = lambda x: x["result"]["data"][0]
        yield from asyncio.sleep(0.25)
        yield from self.client.task(
            self.client.send_receive,
            "g.V().has(n, val).values(n)",
            bindings={"n": "name", "val": "gremlin"},
            consumer=consumer)

    def test_parallel_tasks(self):
        task1 = self.client.add_task(self.slowjson)
        task2 = self.client.add_task(
            self.client.send_receive,
            "g.V().has(n, val).values(n)",
            bindings={"n": "name", "val": "blueprints"},
            consumer=lambda x: x["result"]["data"][0])
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

    def test_enqueue_dequeue(self):
        @asyncio.coroutine
        def enqueue_dequeue_coro():
            yield from self.client.enqueue_task(self.slowjson)
            yield from self.client.enqueue_task(
                self.client.send_receive,
                "g.V().has(n, val).values(n)",
                bindings={"n": "name", "val": "blueprints"},
                consumer=lambda x: x["result"]["data"][0])
            yield from self.client.dequeue_task()
            yield from self.client.dequeue_task()
            mssg1 = yield from self.client.messages.get()
            self.assertEqual(mssg1, "gremlin")
            print("Successfully dequeued slow operation: gremlin")
            mssg2 = yield from self.client.messages.get()
            self.assertEqual(mssg2, "blueprints")
            print("Successfully dequeued fast operation: blueprints")

        self.client.run_until_complete(enqueue_dequeue_coro())

    def test_dequeue_all(self):
        messages = []
        @asyncio.coroutine
        def dequeue_all_coro():
            yield from self.client.enqueue_task(
                self.slowjson,
                consumer=lambda x: x["result"]["data"][0])
            yield from self.client.enqueue_task(
                self.client.send_receive,
                "g.V().has(n, val).values(n)",
                bindings={"n": "name", "val": "blueprints"},
                consumer=lambda x: x["result"]["data"][0])
            yield from self.client.dequeue_all()
            while not self.client.messages.empty():
                mssg = yield from self.client.messages.get()
                messages.append(mssg)
            self.assertEqual(len(messages), 2)
            self.assertEqual(messages[0], "gremlin")
            self.assertEqual(messages[1], "blueprints")
            print("Successfully deququeued all.")
        self.client.run_until_complete(dequeue_all_coro())


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
            consumer=lambda x: x["result"]["data"][0])
        self.assertEqual(self.client._messages[0], "blueprints")
        self.client.execute(
            "g.V().has(n, val).values(n)",
            bindings={"n": "name", "val": "gremlin"},
            consumer=lambda x: x["result"]["data"][0])
        self.assertEqual(self.client._messages[1], "gremlin")
        for x in self.client:
            print("Retrieved: {}".format(x))

if __name__ == "__main__":
    unittest.main()
