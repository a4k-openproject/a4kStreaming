# -*- coding: utf-8 -*-

import threading
from types import SimpleNamespace

class Spawned(list):
    # ui/home.py spawn stand-in: records each thread (target, args, delay, cancel) and runs it at once when run is set
    def __init__(self, run=True):
        super(Spawned, self).__init__()
        self.run = run

    def __call__(self, window, target, *args, delay=None):
        cancel = threading.Event()
        self.append(SimpleNamespace(target=target, args=args, delay=delay, cancel=cancel, fire=lambda: target(*args)))
        if self.run:
            target(*args)
        return cancel

class Spy(object):
    def __init__(self):
        self.args = []
        self.kwargs = []
        self.result = []
        self.call_count = 0

    def called_with(self, *args, **kwargs):
        assert self.args[0] == args
        assert self.kwargs[0] == kwargs

def spy_fn(target, fn_name, return_result=True):
    spy = Spy()
    fn = getattr(target, fn_name)

    def fn_wrap(*args, **kwargs):
        spy.args.append(args)
        spy.kwargs.append(kwargs)
        result = fn(*args, **kwargs)
        spy.result.append(result)
        spy.call_count += 1

        if return_result:
            return result

    setattr(target, fn_name, fn_wrap)
    spy.restore = lambda: setattr(target, fn_name, fn)

    return spy
