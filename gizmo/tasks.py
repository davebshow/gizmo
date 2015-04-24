import asyncio
import itertools
from .log import task_logger, INFO


def async(coro, *args, **kwargs):
    return Task(coro, *args, **kwargs)


def group(*args, **kwargs):
    return Group(*args, **kwargs)


def chain(*args, **kwargs):
    return Chain(*args, **kwargs)


def chord(itrbl, callback, **kwargs):
    return Chord(itrbl, callback, **kwargs)


class Task:

    def __init__(self, coro, *args, **kwargs):
        self.loop = kwargs.get("loop", "") or asyncio.get_event_loop()
        self.coro = self.set_raise_result(coro(*args, **kwargs))
        self._result = None
        verbose = kwargs.get("verbose", False)
        if verbose:
            task_logger.setLevel(INFO)

    @property
    def result(self):
        return self._result

    def __call__(self):
        self.task = asyncio.async(self.coro, loop=self.loop)
        task_logger.info("Task scheduled: {}".format(self))
        return self.task

    def execute(self):
        if not hasattr(self, "task"):
            self.__call__()
        task_logger.info("Execute task: {}".format(self.loop))
        self.loop.run_until_complete(self.task)
        task_logger.info("Completed task: {}".format(self.task))
        return self._result

    @asyncio.coroutine
    def set_raise_result(self, coro):
        result = yield from coro
        try:
            self._result = list(itertools.chain.from_iterable(result))
        except TypeError:
            self._result = result
        return self._result

    def get(self):
        return self.execute()


class Group(Task):

    def __init__(self, *args, **kwargs):
        if len(args) == 1:
            args = args[0]
        self.loop = kwargs.get("loop", "") or asyncio.get_event_loop()
        coro = asyncio.wait([t.coro for t in args], loop=self.loop,
            return_when=asyncio.FIRST_EXCEPTION)
        self.coro = self.set_raise_result(coro)
        self._result = None
        verbose = kwargs.get("verbose", False)
        if verbose:
            task_logger.setLevel(INFO)

    @asyncio.coroutine
    def set_raise_result(self, tasks):
        done, pending = yield from tasks
        result = [f.result() for f in done]
        self._result = result
        return self._result


class Chain(Task):

    def __init__(self, *args, **kwargs):
        if len(args) == 1:
            args = args[0]
        self.loop = kwargs.get("loop", "") or asyncio.get_event_loop()
        task_queue = asyncio.Queue()
        for t in args:
            task_queue.put_nowait(t)
        self.coro = self.dequeue(task_queue)
        self._result = None
        verbose = kwargs.get("verbose", False)
        if verbose:
            task_logger.setLevel(INFO)

    @asyncio.coroutine
    def dequeue(self, queue):
        self._result = []
        while not queue.empty():
            t = queue.get_nowait()
            result = yield from t()
            self._result.append(result)
        return self._result


class Chord(Chain):

    def __init__(self, itrbl, callback, **kwargs):
        self.loop = kwargs.get("loop", "") or asyncio.get_event_loop()
        g = Group(itrbl)
        task_queue = asyncio.Queue()
        task_queue.put_nowait(g)
        task_queue.put_nowait(callback)
        self.coro = self.dequeue(task_queue)
        self._result = None
        verbose = kwargs.get("verbose", False)
        if verbose:
            task_logger.setLevel(INFO)
