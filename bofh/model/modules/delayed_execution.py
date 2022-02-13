from collections import namedtuple
from logging import getLogger
from threading import Lock, Thread, Event
from time import time
from bisect import insort


class TaskEvent(namedtuple('Event', 'time, action, argument, kwargs')):
    __slots__ = []
    def __eq__(s, o): return s.time == o.time
    def __lt__(s, o): return s.time <  o.time
    def __le__(s, o): return s.time <= o.time
    def __gt__(s, o): return s.time >  o.time
    def __ge__(s, o): return s.time >= o.time

    def __call__(self):
        return self.action(*self.argument, **self.kwargs)


class QueueFullError(Exception): pass


class DelayQueue(Thread):
    log = getLogger("DelayQueue")

    def __init__(self, maxsize=0):
        super(DelayQueue, self).__init__(daemon=True)
        self.maxsize=maxsize
        self.queue = list()
        self.lock = Lock()
        self.new_tasks = Event()

    def post(self, delay, fn, a, ka):
        if self.maxsize and self.maxsize <= len(self.queue):
            raise QueueFullError
        deadline = time() + delay
        with self.lock:
            insort(self.queue, TaskEvent(time=deadline, action=fn, argument=a, kwargs=ka))
            self.new_tasks.set()

    def run(self):
        while True:
            while not self.queue:
                self._wait_new_tasks()
            with self.lock:
                until_deadline = time() - self.queue[0].time
            if until_deadline > 0:
                self._wait_new_tasks(until_deadline)
                continue
            with self.lock:
                task = self.queue.pop(0)
            try:
                task()
            except:
                self.log.exception("Error dispatching delayed task")

    def _wait_new_tasks(self, until_deadline=None):
        self.new_tasks.wait(until_deadline)
        self.new_tasks.clear()


class DelayedExecutor:
    def __init__(self, bofh):
        self.bofh = bofh
        self.queue = DelayQueue()
        self.queue.start()

    def post(self, task, *a, **ka):
        self.queue.post(self.bofh.args.dry_run_delay, task, a, ka)


