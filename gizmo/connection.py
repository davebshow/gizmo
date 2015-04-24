import asyncio

from .exceptions import SocketClientError
from .log import INFO, conn_logger

# Hesitant to commit to aiohttp...
try:
    import aiohttp
except ImportError:
    conn_logger.warn(" ".join(["aiohttp is the preferred websocket client for",
        "gizmo. Attempting to use websockets instead."]))
    aiohttp = None
try:
    import websockets
except ImportError:
    websockets = None
    if not aiohttp:
        conn_logger.warn(" ".join(["websockets has been uninstalled. Please install",
            "either websockets using `pip install websockets` or aiohttp using",
            "`pip install aiohttp`. You can also define your own socket",
            "implementation using factory and connection classes see docs:"]))


class ConnectionManager:

    def __init__(self, uri='ws://localhost:8182/', factory=None, max_conn=10,
                 max_retries=10, timeout=None, loop=None, verbose=False):
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
        self._factory = factory or default_factory
        if not self._factory:
            raise RuntimeError("No factory provided. Choose a websocket client.")
        self.max_conn = max_conn
        self.max_retries = max_retries
        self.timeout = timeout
        self._loop = loop or asyncio.get_event_loop()
        self.pool = asyncio.Queue(maxsize=self.max_conn, loop=self._loop)
        self.active_conns = set()
        self.num_connecting = 0
        if verbose:
            conn_logger.setLevel(INFO)

    @property
    def loop(self):
        return self._loop

    @property
    def factory(self):
        return self._factory

    @property
    def num_active_conns(self):
        return len(self.active_conns)

    def remove_active_conn(self, conn):
        self.active_conns.discard(conn)
        self._put(conn)

    @asyncio.coroutine
    def connect(self, uri=None, loop=None, num_retries=None):
        if num_retries is None:
            num_retries = self.max_retries
        uri = uri or self.uri
        loop = loop or self._loop
        if not self.pool.empty():
            socket = self.pool.get_nowait()
            conn_logger.info("Reusing socket: {} at {}".format(socket, uri))
        elif (self.num_active_conns + self.num_connecting >= self.max_conn or
            not self.max_conn):
            conn_logger.info("Waiting for socket...")
            socket = yield from asyncio.wait_for(self.pool.get(),
                self.timeout, loop=loop)
            conn_logger.info("Socket acquired: {} at {}".format(socket, uri))
        else:
            self.num_connecting += 1
            try:
                socket = yield from self.factory.connect(uri, manager=self,
                    loop=loop)
                conn_logger.info("New connection on socket: {} at {}".format(
                    socket, uri))
            finally:
                self.num_connecting -= 1
        if socket.open:
            self.active_conns.add(socket)
        # Untested
        elif num_retries > 0:
            socket = yield from self.connect(uri, loop, num_retries - 1)
        else:
            raise SocketClientError("Unable to connect, max retries exceeded.")
        return socket

    def _put(self, socket):
        try:
            self.pool.put_nowait(socket)
        except asyncio.QueueFull:
            pass


class BaseFactory:

    @classmethod
    @asyncio.coroutine
    def connect(cls):
        raise NotImplementedError

    @property
    def factory(self):
        return self


class AiohttpFactory(BaseFactory):

    @classmethod
    @asyncio.coroutine
    def connect(cls, uri='ws://localhost:8182/', manager=None, protocols=(),
                connector=None, autoclose=False, autoping=True, loop=None):
        if manager:
            loop = loop or manager._loop
        try:
            socket = yield from aiohttp.ws_connect(uri, protocols=protocols,
                connector=connector, autoclose=autoclose, autoping=autoping,
                loop=loop)
        except aiohttp.WSServerHandshakeError as e:
            raise SocketClientError(e.message)
        return AiohttpConnection(socket, manager)


aiohttp_factory = AiohttpFactory


class WebsocketsFactory(BaseFactory):

    @classmethod
    @asyncio.coroutine
    def connect(cls, uri='ws://localhost:8182/', manager=None, **kwargs):
        socket = yield from websockets.connect(uri)
        return WebsocketsConnection(socket, manager)


websockets_factory = WebsocketsFactory


class BaseConnection:

    def __init__(self, socket, manager=None):
        self.socket = socket
        self.manager = manager

    def __nonzero__(self):
        return bool(self.socket)

    def close(self):
        if self.manager:
            if self in self.manager.active_conns:
                self.manager.remove_active_conn(self)

    def __str__(self):
        return repr(self.socket)

    @property
    def open(self):
        raise NotImplementedError

    @asyncio.coroutine
    def send(self):
        raise NotImplementedError

    @asyncio.coroutine
    def recv(self):
        raise NotImplementedError


class AiohttpConnection(BaseConnection):

    @property
    def open(self):
        return not self.socket.closed

    @asyncio.coroutine
    def send(self, msg, binary=True):
        if binary:
            method = self.socket.send_bytes
        else:
            method = self.socket.send_str
        try:
            method(msg)
        except RuntimeError:
            # Socket closed.
            self.close()
            raise
        except TypeError:
            # Bytes/string input error.
            self.close()
            raise

    @asyncio.coroutine
    def recv(self):
        while True:
            try:
                message = yield from self.socket.receive()
            except (asyncio.CancelledError, asyncio.TimeoutError):
                self.close()
                raise
            except RuntimeError:
                self.close()
                raise
            if message.tp == aiohttp.MsgType.binary:
                return message.data.decode()
            elif message.tp == aiohttp.MsgType.text:
                return message.data.strip()
            elif msg.tp == aiohttp.MsgType.ping:
                conn_logger.info("Ping received.")
                ws.pong()
                conn_logger.info("Sent pong.")
            elif msg.tp == aiohttp.MsgType.pong:
                conn_logger.info('Pong received')
            else:
                try:
                    if message.tp == aiohttp.MsgType.close:
                        conn_logger.warn("Socket connection closed by server.")
                        yield from self.socket.close()
                    elif message.tp == aiohttp.MsgType.error:
                        raise SocketClientError(self.socket.exception())
                    elif message.tp == aiohttp.MsgType.closed:
                        raise SocketClientError("Socket closed.")
                    break
                finally:
                    self.close()


class WebsocketsConnection(BaseConnection):

    @property
    def open(self):
        return self.socket.open

    @asyncio.coroutine
    def send(self, data):
        yield from self.socket.send(data)

    @asyncio.coroutine
    def recv(self):
        message = yield from self.socket.recv()
        return message.decode()
