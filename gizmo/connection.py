import asyncio
import websockets
from .handlers import socket_error_handler


class ConnectionManager:

    def __init__(self, uri, max_conn=10, timeout=None, loop=None):
        """
        Very simple manager for socket connections. Basically just creates and
        loans out connected sockets.
        """
        self.uri = uri
        self.max_conn = max_conn
        self.timeout = timeout
        self._loop = loop or asyncio.get_event_loop()
        self.pool = asyncio.Queue(maxsize=self.max_conn)
        self.active_conns = set()
        self.num_connecting = 0

    @property
    def num_active_conns(self):
        return len(self.active_conns)

    def remove_active_conn(self, conn):
        self.active_conns.discard(conn)
        self._put(conn)

    @asyncio.coroutine
    def connect(self, uri=None):
        uri = uri or self.uri
        if not self.pool.empty():
            print("Reusing")
            socket = self.pool.get_nowait()
        elif (self.num_active_conns + self.num_connecting >= self.max_conn or
            not self.max_conn):
            print("Waiting")
            socket = yield from asyncio.wait_for(self.pool.get(),
                self.timeout, loop=self._loop)
        else:
            self.num_connecting += 1
            try:
                print("Connecting. {} active sockets".format(self.num_active_conns))
                socket = yield from websockets.connect(uri)
            finally:
                self.num_connecting -= 1
        try:
            socket_error_handler(socket)
        except SocketError:
            print("Error")
            socket = yield from self.connect()
        else:
            self.active_conns.add(socket)
        connection = Connection(socket, self)
        return connection

    def _put(self, socket):
        try:
            self.pool.put_nowait(socket)
        except asyncio.QueueFull:
            print("Queue full")
            pass


class Connection:

    def __init__(self, socket, manager):
        """
        Simple wrapper for websocket.
        """
        self.socket = socket
        self.manager = manager

    def __nonzero__(self):
        return bool(self.socket)

    @property
    def open(self):
        return self.socket.open

    def close(self, destroy=False):
        self.manager.remove_active_conn(self.socket)

    @asyncio.coroutine
    def send(self, data):
        yield from self.socket.send(data)

    @asyncio.coroutine
    def recv(self):
        return (yield from self.socket.recv())
