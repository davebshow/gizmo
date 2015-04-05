"""
Basic test cases, will build a larger graph and make end2end tests.
"""

import asyncio
import unittest
from gizmo import (AsyncGremlinClient, task, group, chain, chord, RequestError,
    GremlinServerError, SocketError)

@asyncio.coroutine
def consumer_coro1(x):
    yield from asyncio.sleep(0.25)
    return x[0]

def consumer_coro2(x):
    yield from asyncio.sleep(0.50)
    return x[0] * 2


class AsyncGremlinClientTests(unittest.TestCase):

    def setUp(self):
        self.gc = AsyncGremlinClient("ws://localhost:8182/")

    def test_connection(self):
        @asyncio.coroutine
        def conn_coro():
            conn = yield from self.gc.connect()
            self.assertTrue(conn.open)
        self.gc.run_until_complete(conn_coro())

    def test_task(self):
        t = task(self.gc.submit("x + x", bindings={"x": 2},
            consumer=lambda x : x[0] ** 2), loop=self.gc._loop)
        t()
        message = self.gc.read()
        self.assertEqual(16, message)

    def test_submittask(self):
        t = self.gc.s("x + x", bindings={"x": 2},
            consumer=lambda x : x[0] ** 2)
        t()
        message = self.gc.read()
        self.assertEqual(16, message)

    def test_group(self):
        t = self.gc.submit("x + x", bindings={"x": 2},
            consumer=lambda x : x[0] ** 2)
        slow = self.gc.submit("x + x", bindings={"x": 2},
            consumer=consumer_coro1)
        group(slow, t)()
        results = []
        while not self.gc.messages.empty():
            results.append(self.gc.read())
        self.assertEqual(results[0], 16)
        self.assertEqual(results[1], 4)

    def test_group_itrbl_arg(self):
        t = self.gc.submit("x + x", bindings={"x": 2},
            consumer=lambda x : x[0] ** 2)
        slow = self.gc.submit("x + x", bindings={"x": 2},
            consumer=consumer_coro1)
        group([slow, t])()
        results = []
        while not self.gc.messages.empty():
            results.append(self.gc.read())
        self.assertEqual(results[0], 16)
        self.assertEqual(results[1], 4)

    def test_chain(self):
        t = self.gc.submit("x + x", bindings={"x": 2},
            consumer=lambda x : x[0] ** 2)
        slow = self.gc.submit("x + x", bindings={"x": 2},
            consumer=consumer_coro1)
        chain(slow, t)()
        results = []
        while not self.gc.messages.empty():
            results.append(self.gc.read())
        self.assertEqual(results[0], 4)
        self.assertEqual(results[1], 16)

    def test_chain_itrbl_arg(self):
        t = self.gc.submit("x + x", bindings={"x": 2},
            consumer=lambda x : x[0] ** 2)
        slow = self.gc.submit("x + x", bindings={"x": 2},
            consumer=consumer_coro1)
        chain([slow, t])()
        results = []
        while not self.gc.messages.empty():
            results.append(self.gc.read())
        self.assertEqual(results[0], 4)
        self.assertEqual(results[1], 16)

    def test_send_run_chain(self):
        send = self.gc.send("x + x", bindings={"x": 2})
        run = self.gc.run(consumer=lambda x : x[0] ** 2)
        chain(send, run)()
        results = []
        for x in self.gc:
            results.append(x)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0], 16)

    def test_chord(self):
        slow1 = self.gc.submit("x + x", bindings={"x": 2},
            consumer=consumer_coro1)
        slow2 = self.gc.submit("x + x", bindings={"x": 2},
            consumer=consumer_coro2)
        t = self.gc.submit("x + x", bindings={"x": 2},
            consumer=lambda x : x[0] ** 2)
        chord([slow2, slow1], t)()
        results = []
        while not self.gc.messages.empty():
            results.append(self.gc.read())
        self.assertEqual(results[0], 4)
        self.assertEqual(results[1], 8)
        self.assertEqual(results[2], 16)

    def test_recv(self):
        @asyncio.coroutine
        def recv_coro():
            results = []
            yield from self.gc.send("x + x", bindings={"x": 4})
            while True:
                f = yield from self.gc.recv()
                if f is None:
                    break
                else:
                    results.append(f)
            self.assertEqual(results[0][0], 8)
        self.gc.run_until_complete(recv_coro())


if __name__ == "__main__":
    unittest.main()
