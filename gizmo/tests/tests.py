"""
Basic test cases, will build a larger graph and make end2end tests.
"""

import asyncio
import websockets
import unittest
from gizmo import (AsyncGremlinClient, async, group, chain, chord, RequestError,
    GremlinServerError, SocketError, ConnectionManager)


@asyncio.coroutine
def consumer_coro1(x):
    yield from asyncio.sleep(0.25)
    return x[0] ** 0


def consumer_coro2(x):
    yield from asyncio.sleep(0.50)
    return x[0] ** 1


class AsyncGremlinClientTests(unittest.TestCase):

    def setUp(self):
        self.gc = AsyncGremlinClient("ws://localhost:8182/")

    def test_connection(self):
        @asyncio.coroutine
        def conn_coro():
            conn = yield from self.gc.connect()
            self.assertTrue(conn.open)
        loop = asyncio.get_event_loop()
        loop.run_until_complete(conn_coro())

    def test_task(self):
        t = async(self.gc.submit, "x + x", bindings={"x": 2},
            consumer=lambda x : x[0] ** 2, loop=self.gc._loop)
        t.execute()
        message = self.gc.read()
        self.assertEqual(16, message)

    def test_task_error(self):
        t = async(self.gc.submit, "x + x g.adasdfd", bindings={"x": 2},
            consumer=lambda x : x[0] ** 2, loop=self.gc._loop)
        try:
            t.execute()
            error = False
        except:
            error = True
        self.assertTrue(error)

    def test_submittask(self):
        t = self.gc.s("x + x", bindings={"x": 2},
            consumer=lambda x : x[0] ** 2)
        t()
        t.execute()
        message = self.gc.read()
        self.assertEqual(16, message)

    def test_group(self):
        t = self.gc.s("x + x", bindings={"x": 2},
            consumer=lambda x : x[0] ** 2)
        slow = self.gc.s("x + x", bindings={"x": 2},
            consumer=consumer_coro1)
        g = group(slow, t)
        g.execute()
        results = []
        while not self.gc.messages.empty():
            results.append(self.gc.read())
        self.assertEqual(results[0], 16)
        self.assertEqual(results[1], 1)

    def test_group_error(self):
        t = self.gc.s("x + x g.sdfa", bindings={"x": 2},
            consumer=lambda x : x[0] ** 2)
        slow = self.gc.s("x + x", bindings={"x": 2},
            consumer=consumer_coro1)
        g = group(slow, t)
        try:
            g.execute()
            error = False
        except:
            error = True
        self.assertTrue(error)

    #This operation is problematic
    def test_group_of_groups(self):
        fast = self.gc.s("x + x", bindings={"x": 2},
            consumer=lambda x : x[0] ** 2)
        fast1 = self.gc.s("x + x", bindings={"x": 2},
            consumer=lambda x : x[0] ** 2)
        slow = self.gc.s("x + x", bindings={"x": 2}, consumer=consumer_coro1)
        slow1 = self.gc.s("x + x", bindings={"x": 2}, consumer=consumer_coro1)
        g = group(fast, fast1)
        g1 = group(slow, slow1)
        group(g, g1).execute()
        results = []
        while not self.gc.messages.empty():
            results.append(self.gc.read())
        self.assertEqual(results[0], 16)
        self.assertEqual(results[1], 16)
        self.assertEqual(results[2], 1)
        self.assertEqual(results[3], 1)

    def test_group_itrbl_arg(self):
        t = self.gc.s("x + x", bindings={"x": 2},
            consumer=lambda x : x[0] ** 2)
        slow = self.gc.s("x + x", bindings={"x": 2},
            consumer=consumer_coro1)
        g = group([slow, t])
        g.execute()
        results = []
        while not self.gc.messages.empty():
            results.append(self.gc.read())
        self.assertEqual(results[0], 16)
        self.assertEqual(results[1], 1)

    def test_chain(self):
        t = self.gc.s("x + x", bindings={"x": 2},
            consumer=lambda x : x[0] ** 2)
        slow = self.gc.s("x + x", bindings={"x": 2},
            consumer=consumer_coro1)
        chain(slow, t).execute()
        results = []
        while not self.gc.messages.empty():
            results.append(self.gc.read())
        self.assertEqual(results[0], 1)
        self.assertEqual(results[1], 16)

    def test_chain_error(self):
        t = self.gc.s("x + x g.sadf", bindings={"x": 2},
            consumer=lambda x : x[0] ** 2)
        slow = self.gc.s("x + x", bindings={"x": 2},
            consumer=consumer_coro1)
        try:
            chain(slow, t).execute()
            error = False
        except:
            error = True
        self.assertTrue(error)

    def test_chains_in_group(self):
        slow = self.gc.s("x + x", bindings={"x": 2},
            consumer=consumer_coro2)
        slow1 = self.gc.s("x + x", bindings={"x": 2},
            consumer=consumer_coro1)
        slow_chain = chain(slow, slow1)

        t = self.gc.s("x + x", bindings={"x": 2},
            consumer=lambda x : x[0] ** 2)
        group(slow_chain, t).execute()
        results = []
        while not self.gc.messages.empty():
            results.append(self.gc.read())
        print(results)
        self.assertTrue(results.index(4) < results.index(1))
        self.assertTrue(results.index(16) < results.index(1))
        self.assertTrue(results.index(16) < results.index(4))

    def test_chains_in_group_error(self):
        slow = self.gc.s("x + x g.edfsa", bindings={"x": 2},
            consumer=consumer_coro2)
        slow1 = self.gc.s("x + x g.eafwa", bindings={"x": 2},
            consumer=consumer_coro1)
        slow_chain = chain(slow, slow1)

        t = self.gc.s("x + x", bindings={"x": 2},
            consumer=lambda x : x[0] ** 2)
        try:
            group(slow_chain, t).execute()
            error = False
        except:
            error = True
        self.assertTrue(error)

    def test_chain_itrbl_arg(self):
        t = self.gc.s("x + x", bindings={"x": 2},
            consumer=lambda x : x[0] ** 2)
        slow = self.gc.s("x + x", bindings={"x": 2},
            consumer=consumer_coro1)
        chain([slow, t]).execute()
        results = []
        while not self.gc.messages.empty():
            results.append(self.gc.read())
        self.assertEqual(results[0], 1)
        self.assertEqual(results[1], 16)

    def test_group_chain(self):
        results = []
        slow = self.gc.s("x + x", bindings={"x": 2}, consumer=consumer_coro1)
        slow1 = self.gc.s("x + x", bindings={"x": 2}, consumer=consumer_coro1)
        slow_group = group(slow, slow1)
        fast = self.gc.s("x + x", bindings={"x": 2},
            consumer=lambda x : x[0] ** 2)
        fast1 = self.gc.s("x + x", bindings={"x": 2},
            consumer=lambda x : x[0] ** 2)
        fast_group = group(fast, fast1)
        chain(slow_group, fast_group).execute()
        while not self.gc.messages.empty():
            results.append(self.gc.read())
        self.assertEqual(results[0], 1)
        self.assertEqual(results[1], 1)
        self.assertEqual(results[2], 16)
        self.assertEqual(results[3], 16)

    def test_chord(self):
        slow1 = self.gc.s("x + x", bindings={"x": 2},
            consumer=consumer_coro1)
        slow2 = self.gc.s("x + x", bindings={"x": 2},
            consumer=consumer_coro2)
        t = self.gc.s("x + x", bindings={"x": 2},
            consumer=lambda x : x[0] ** 2)
        chord([slow2, slow1], t).execute()
        results = []
        while not self.gc.messages.empty():
            results.append(self.gc.read())
        self.assertEqual(results[0], 1)
        self.assertEqual(results[1], 4)
        self.assertEqual(results[2], 16)

    def test_chord_group_error(self):
        slow1 = self.gc.s("x + x g.asdf", bindings={"x": 2},
            consumer=consumer_coro1)
        slow2 = self.gc.s("x + x", bindings={"x": 2},
            consumer=consumer_coro2)
        t = self.gc.s("x + x", bindings={"x": 2},
            consumer=lambda x : x[0] ** 2)
        try:
            chord([slow2, slow1], t).execute()
            error = False
        except:
            error = True
        self.assertTrue(error)

    def test_z_e2e(self):
        t = self.gc.s("g.V().remove(); g.E().remove();", collect=False)
        t1 = self.gc.s("g.addVertex('uniqueId', x)", bindings={"x": "joe"},
            collect=False)
        t2 = self.gc.s("g.addVertex('uniqueId', x)", bindings={"x": "maria"},
            collect=False)
        t3 = self.gc.s("g.addVertex('uniqueId', x)", bindings={"x": "jill"},
            collect=False)
        t4 = self.gc.s("g.addVertex('uniqueId', x)", bindings={"x": "jack"},
            collect=False)
        g1 = group(t1, t2, t3, t4)
        t5 = self.gc.s("""
            joe = g.V().has('uniqueId', 'joe').next();
            maria = g.V().has('uniqueId', 'maria').next();
            joe.addEdge('marriedTo', maria);""")
        t6 = self.gc.s("""
            jill = g.V().has('uniqueId', 'jill').next();
            jack = g.V().has('uniqueId', 'jack').next();
            jill.addEdge('marriedTo', jack);""")
        t7 = self.gc.s("""
            jill = g.V().has('uniqueId', 'jill').next();
            joe = g.V().has('uniqueId', 'joe').next();
            jill.addEdge('hasSibling', joe);""")
        g2 = group(t5, t6, t7)
        t8 = self.gc.s("g.V();", consumer=lambda x: print(x))
        t9 = self.gc.s("g.E();", consumer=lambda x: print(x))
        t10 = self.gc.s("g.V().count();", consumer=lambda x: self.assertEqual(x[0], 4))
        t11 = self.gc.s("g.E().count();", consumer=lambda x: self.assertEqual(x[0], 3))
        c = chain(t, g1, g2, t8, t9, t10, t11, t)
        c.execute()
        results = []
        while not self.gc.messages.empty():
            results.append(self.gc.read())
        print(results)

    def test_recv(self):
        @asyncio.coroutine
        def recv_coro():
            results = []
            websocket = yield from self.gc.send("x + x", bindings={"x": 4})
            while True:
                f = yield from self.gc.recv(websocket)
                if f is None:
                    break
                else:
                    results.append(f)
            self.assertEqual(results[0][0], 8)
        loop = asyncio.get_event_loop()
        loop.run_until_complete(recv_coro())


    def test_submit_error(self):

        @asyncio.coroutine
        def submit_coro():
            yield from self.gc.submit("x + x g.asdfas", bindings={"x": 4})

        loop = asyncio.get_event_loop()
        try:
            loop.run_until_complete(submit_coro())
            error = False
        except:
            error = True
        self.assertTrue(error)


class ConnectionManagerTests(unittest.TestCase):

    def setUp(self):
        self.factory = ConnectionManager(max_conn=2, timeout=1)
        self.loop = asyncio.get_event_loop()

    def test_connect(self):

        @asyncio.coroutine
        def conn():
            conn = yield from self.factory.connect()
            self.assertIsNotNone(conn.socket)
            self.assertTrue(conn.socket.open)
            conn.close()
            self.assertEqual(self.factory.num_active_conns, 0)

        self.loop.run_until_complete(conn())

    def test_multi_connect(self):

        @asyncio.coroutine
        def conn():
            conn1 = yield from self.factory.connect()
            conn2 = yield from self.factory.connect()
            self.assertIsNotNone(conn1.socket)
            self.assertTrue(conn1.socket.open)
            self.assertIsNotNone(conn2.socket)
            self.assertTrue(conn2.socket.open)
            conn1.close()
            self.assertEqual(self.factory.num_active_conns, 1)
            conn2.close()
            self.assertEqual(self.factory.num_active_conns, 0)

        self.loop.run_until_complete(conn())

    def test_timeout(self):

        @asyncio.coroutine
        def conn():
            conn1 = yield from self.factory.connect()
            conn2 = yield from self.factory.connect()
            try:
                conn3 = yield from self.factory.connect()
                timeout = False
            except asyncio.TimeoutError:
                timeout = True
            self.assertTrue(timeout)

        self.loop.run_until_complete(conn())

    def test_socket_reuse(self):

        @asyncio.coroutine
        def conn():
            conn1 = yield from self.factory.connect()
            conn2 = yield from self.factory.connect()
            try:
                conn3 = yield from self.factory.connect()
                timeout = False
            except asyncio.TimeoutError:
                timeout = True
            self.assertTrue(timeout)
            conn2.close()
            conn3 = yield from self.factory.connect()
            self.assertIsNotNone(conn1.socket)
            self.assertTrue(conn1.socket.open)
            self.assertIsNotNone(conn3.socket)
            self.assertTrue(conn3.socket.open)
            self.assertEqual(conn2.socket, conn3.socket)

        self.loop.run_until_complete(conn())

    def test_socket_repare(self):

        @asyncio.coroutine
        def conn():
            conn1 = yield from self.factory.connect()
            conn2 = yield from self.factory.connect()
            self.assertIsNotNone(conn1.socket)
            self.assertTrue(conn1.socket.open)
            self.assertIsNotNone(conn2.socket)
            self.assertTrue(conn2.socket.open)
            conn1.socket.state = 'CLOSED'
            conn2.socket.state = 'CLOSED'
            self.assertFalse(conn1.socket.open)
            self.assertFalse(conn1.open)
            self.assertFalse(conn2.socket.open)
            self.assertFalse(conn2.open)
            conn1.close()
            conn2.close()
            conn1 = yield from self.factory.connect()
            conn2 = yield from self.factory.connect()
            self.assertIsNotNone(conn1.socket)
            self.assertTrue(conn1.socket.open)
            self.assertIsNotNone(conn2.socket)
            self.assertTrue(conn2.socket.open)

        self.loop.run_until_complete(conn())


if __name__ == "__main__":
    unittest.main()
