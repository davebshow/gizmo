import asyncio

try:
    import aiohttp
except ImportError:
    aiohttp = None
try:
    import websockets
except ImportError:
    websockets = None
    if not aiohttp:
        print(" ".join(["websockets has been uninstalled. Please install either",
            "websockets using `pip install websockets` or aiohttp using `pip",
            "install aiohttp`. You can also define your own socket",
            "implementation using factory and connection classes see docs:"]))

from .exceptions import SocketError
from .handlers import socket_error_handler


class ConnectionManager:

    def __init__(self, uri='ws://localhost:8182/', factory=None, max_conn=10,
                 timeout=None, loop=None):
        """
        Very simple manager for socket connections. Basically just creates and
        loans out connected sockets.
        """
        self.uri = uri
        if aiohttp:
            default_factory = aiohttp_factory
        elif websockets:
            default_factory = websockets_factory
        else:
            default_factory = None
        self.factory = factory or default_factory
        if not self.factory:
            raise Exception("No factory provided. Choose a websocket client.")
        self.max_conn = max_conn
        self.timeout = timeout
        self._loop = loop or asyncio.get_event_loop()
        self.pool = asyncio.Queue(maxsize=self.max_conn, loop=self._loop)
        self.active_conns = set()
        self.num_connecting = 0

    @property
    def num_active_conns(self):
        return len(self.active_conns)

    def remove_active_conn(self, conn):
        self.active_conns.discard(conn)
        self._put(conn)

    @asyncio.coroutine
    def connect(self, uri=None, loop=None):
        uri = uri or self.uri
        loop = loop or self._loop
        if not self.pool.empty():
            socket = self.pool.get_nowait()
        elif (self.num_active_conns + self.num_connecting >= self.max_conn or
            not self.max_conn):
            socket = yield from asyncio.wait_for(self.pool.get(),
                self.timeout, loop=loop)
        else:
            self.num_connecting += 1
            try:
                socket = yield from self.factory.connect(uri, manager=self,
                    loop=loop)
            finally:
                self.num_connecting -= 1
        try:
            socket_error_handler(socket)
        except SocketError:
            socket = yield from self.connect(uri)
        else:
            self.active_conns.add(socket)
        return socket

    def _put(self, socket):
        try:
            self.pool.put_nowait(socket)
        except asyncio.QueueFull:
            pass


class BaseFactory:

    @classmethod
    @asyncio.coroutine
    def connect(cls, uri='ws://localhost:8182/', manager=None, **kwargs):
        raise NotImplementedError


class WebsocketsFactory(BaseFactory):

    @classmethod
    @asyncio.coroutine
    def connect(cls, uri='ws://localhost:8182/', manager=None, **kwargs):
        socket = yield from websockets.connect(uri)
        return WebsocketsConnection(socket, manager)


websockets_factory = WebsocketsFactory


class AiohttpFactory(BaseFactory):

    @classmethod
    @asyncio.coroutine
    def connect(cls, uri='ws://localhost:8182/', manager=None, **kwargs):
        socket = yield from aiohttp.ws_connect(uri, **kwargs)
        return AiohttpConnection(socket, manager)


aiohttp_factory = AiohttpFactory


class BaseConnection:

    def __init__(self, socket, manager=None):
        self.socket = socket
        self.manager = manager

    def __nonzero__(self):
        return bool(self.socket)

    def close(self, destroy=False):
        if self.manager:
            self.manager.remove_active_conn(self)

    @property
    def open(self):
        raise NotImplementedError

    @asyncio.coroutine
    def send(self):
        raise NotImplementedError

    @asyncio.coroutine
    def recv(self):
        raise NotImplementedError


class WebsocketsConnection(BaseConnection):

    @property
    def open(self):
        return self.socket.open

    @asyncio.coroutine
    def send(self, data):
        yield from self.socket.send(data)

    @asyncio.coroutine
    def recv(self):
        return (yield from self.socket.recv())


class AiohttpConnection(BaseConnection):

    @property
    def open(self):
        return not self.socket.closed

    @asyncio.coroutine
    def send(self, msg):
        self.socket.send_bytes(msg)

    @asyncio.coroutine
    def recv(self):
        message = yield from self.socket.receive()
        return message.data
