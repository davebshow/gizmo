import asyncio


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
        self.client = coro.__self__
        self.coro = coro(*args, **kwargs)

    def __call__(self):
        task = asyncio.async(self.coro)
        coro = self.error_handler(task)
        self.task = asyncio.async(coro, loop=self.loop)
        return self.task

    def execute(self):
        if not hasattr(self, "task"):
            self()
        self.loop.run_until_complete(self.task)

    def error_handler(self, task):
        try:
            yield from task
        except Exception as e:
            raise e


class Group(Task):

    def __init__(self, *args, **kwargs):
        if len(args) == 1:
            args = args[0]
        self.loop = kwargs.get("loop", "") or asyncio.get_event_loop()
        self.coro = asyncio.wait([t.coro for t in args], loop=self.loop,
            return_when=asyncio.FIRST_EXCEPTION)

    def __call__(self):
        coro = self.wait_error_handler(self.coro)
        self.task = asyncio.async(coro, loop=self.loop)
        return self.task

    @asyncio.coroutine
    def wait_error_handler(self, tasks):
        done, pending = yield from tasks
        errors = [f.result() for f in done]


class Chain(Group):

    def __init__(self, *args, **kwargs):
        if len(args) == 1:
            args = args[0]
        self.loop = kwargs.get("loop", "") or asyncio.get_event_loop()
        task_queue = asyncio.Queue()
        for t in args:
            task_queue.put_nowait(t)
        self.coro = self.dequeue(task_queue)

    def __call__(self):
        task = asyncio.async(self.coro, loop=self.loop)
        coro = self.error_handler(task)
        self.task = asyncio.async(coro, loop=self.loop)
        return self.task

    @asyncio.coroutine
    def dequeue(self, queue):
        while not queue.empty():
            t = queue.get_nowait()
            if asyncio.iscoroutine(t):
                yield from self.wait_error_handler(t)
            else:
                yield from t()


class Chord(Chain):

    def __init__(self, itrbl, callback, **kwargs):
        self.loop = kwargs.get("loop", "") or asyncio.get_event_loop()
        tasks = asyncio.wait([t.coro for t in itrbl], loop=self.loop,
            return_when=asyncio.FIRST_EXCEPTION)
        task_queue = asyncio.Queue()
        task_queue.put_nowait(tasks)
        task_queue.put_nowait(callback)
        self.coro = self.dequeue(task_queue)
