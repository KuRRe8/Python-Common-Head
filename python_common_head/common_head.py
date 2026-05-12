'''
Usage: from common_head import *

Since I don't want to expose everything from imported modules, I will set __all__
'''

import sys
import os
import logging
from datetime import datetime
import time
import functools
import threading
if sys.version_info >= (3, 13):
    from warnings import warn, deprecated
else:
    from warnings import warn

try:
    from .common_config import *
except ImportError:
    from common_config import *

if NEED_LOGGER:
    def _setup_logger(log_file="app.log", level=logging.INFO):
        logger = logging.getLogger()
        logger.setLevel(level)

        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)

        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)

        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

        logger.info('###Logger initialized.###')
        return logger

    _current_date = datetime.now().strftime("%Y-%m-%d")
    _LOG_FILE_PATH = LOGGER_PATH if LOGGER_PATH else os.path.join(os.path.dirname(__file__), "logs", f"app.{_current_date}__{datetime.now().strftime('%H-%M')}.log")
    os.makedirs(os.path.dirname(_LOG_FILE_PATH), exist_ok=True)
    logger = _setup_logger(log_file=_LOG_FILE_PATH,level=LOGGER_LVL)

if NEED_TIMER_CONTEXT:
    class Timer:
        def __init__(self, name="Timer"):
            self.name = name

        def __enter__(self):
            self.start = time.perf_counter()
            return self

        def __exit__(self, *args):
            elapsed = time.perf_counter() - self.start
            print(f"[{self.name}] Elapsed: {elapsed:.6f} seconds")

    '''
    # Use case example:
    with Timer("Sum 1 million"):
        sum(range(1000000))
    '''

if NEED_CLASSONLYMETHOD:
    class classonlymethod(classmethod):
        def __get__(self, instance, cls=None):
            if instance is not None:
                raise AttributeError("This method is available only on the class, not on instances.")
            return super(classonlymethod, self).__get__(instance, cls)

if NEED_MS_SINGLETON:
    class Singleton(object):
        """A base class for a class of a singleton object.

        For any derived class T, the first invocation of T() will create the instance,
        and any future invocations of T() will return that instance.

        Concurrent invocations of T() from different threads are safe.
        """

        # A dual-lock scheme is necessary to be thread safe while avoiding deadlocks.
        # _lock_lock is shared by all singleton types, and is used to construct their
        # respective _lock instances when invoked for a new type. Then _lock is used
        # to synchronize all further access for that type, including __init__. This way,
        # __init__ for any given singleton can access another singleton, and not get
        # deadlocked if that other singleton is trying to access it.
        _lock_lock = threading.RLock()
        _lock = None

        # Specific subclasses will get their own _instance set in __new__.
        _instance = None

        _is_shared = None  # True if shared, False if exclusive

        def __new__(cls, *args, **kwargs):
            # Allow arbitrary args and kwargs if shared=False, because that is guaranteed
            # to construct a new singleton if it succeeds. Otherwise, this call might end
            # up returning an existing instance, which might have been constructed with
            # different arguments, so allowing them is misleading.
            assert not kwargs.get("shared", False) or (len(args) + len(kwargs)) == 0, (
                "Cannot use constructor arguments when accessing a Singleton without "
                "specifying shared=False."
            )

            # Avoid locking as much as possible with repeated double-checks - the most
            # common path is when everything is already allocated.
            if not cls._instance:
                # If there's no per-type lock, allocate it.
                if cls._lock is None:
                    with cls._lock_lock:
                        if cls._lock is None:
                            cls._lock = threading.RLock()

                # Now that we have a per-type lock, we can synchronize construction.
                if not cls._instance:
                    with cls._lock:
                        if not cls._instance:
                            cls._instance = object.__new__(cls)
                            # To prevent having __init__ invoked multiple times, call
                            # it here directly, and then replace it with a stub that
                            # does nothing - that stub will get auto-invoked on return,
                            # and on all future singleton accesses.
                            cls._instance.__init__()
                            cls.__init__ = lambda *args, **kwargs: None

            return cls._instance

        def __init__(self, *args, **kwargs):
            """Initializes the singleton instance. Guaranteed to only be invoked once for
            any given type derived from Singleton.

            If shared=False, the caller is requesting a singleton instance for their own
            exclusive use. This is only allowed if the singleton has not been created yet;
            if so, it is created and marked as being in exclusive use. While it is marked
            as such, all attempts to obtain an existing instance of it immediately raise
            an exception. The singleton can eventually be promoted to shared use by calling
            share() on it.
            """

            shared = kwargs.pop("shared", True)
            with self:
                if shared:
                    assert (
                        type(self)._is_shared is not False
                    ), "Cannot access a non-shared Singleton."
                    type(self)._is_shared = True
                else:
                    assert type(self)._is_shared is None, "Singleton is already created."

        def __enter__(self):
            """Lock this singleton to prevent concurrent access."""
            type(self)._lock.acquire()
            return self

        def __exit__(self, exc_type, exc_value, exc_tb):
            """Unlock this singleton to allow concurrent access."""
            type(self)._lock.release()

        def share(self):
            """Share this singleton, if it was originally created with shared=False."""
            type(self)._is_shared = True


    class ThreadSafeSingleton(Singleton):
        """A singleton that incorporates a lock for thread-safe access to its members.

        The lock can be acquired using the context manager protocol, and thus idiomatic
        use is in conjunction with a with-statement. For example, given derived class T::

            with T() as t:
                t.x = t.frob(t.y)

        All access to the singleton from the outside should follow this pattern for both
        attributes and method calls. Singleton members can assume that self is locked by
        the caller while they're executing, but recursive locking of the same singleton
        on the same thread is also permitted.
        """

        threadsafe_attrs = frozenset()
        """Names of attributes that are guaranteed to be used in a thread-safe manner.

        This is typically used in conjunction with share() to simplify synchronization.
        """

        readonly_attrs = frozenset()
        """Names of attributes that are readonly. These can be read without locking, but
        cannot be written at all.

        Every derived class gets its own separate set. Thus, for any given singleton type
        T, an attribute can be made readonly after setting it, with T.readonly_attrs.add().
        """

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            # Make sure each derived class gets a separate copy.
            type(self).readonly_attrs = set(type(self).readonly_attrs)

        # Prevent callers from reading or writing attributes without locking, except for
        # reading attributes listed in threadsafe_attrs, and methods specifically marked
        # with @threadsafe_method. Such methods should perform the necessary locking to
        # ensure thread safety for the callers.

        @staticmethod
        def assert_locked(self):
            lock = type(self)._lock
            assert lock.acquire(blocking=False), (
                "ThreadSafeSingleton accessed without locking. Either use with-statement, "
                "or if it is a method or property, mark it as @threadsafe_method or with "
                "@autolocked_method, as appropriate."
            )
            lock.release()

        def __getattribute__(self, name):
            value = object.__getattribute__(self, name)
            if name not in (type(self).threadsafe_attrs | type(self).readonly_attrs):
                if not getattr(value, "is_threadsafe_method", False):
                    ThreadSafeSingleton.assert_locked(self)
            return value

        def __setattr__(self, name, value):
            assert name not in type(self).readonly_attrs, "This attribute is read-only."
            if name not in type(self).threadsafe_attrs:
                ThreadSafeSingleton.assert_locked(self)
            return object.__setattr__(self, name, value)


    def threadsafe_method(func):
        """Marks a method of a ThreadSafeSingleton-derived class as inherently thread-safe.

        A method so marked must either not use any singleton state, or lock it appropriately.
        """

        func.is_threadsafe_method = True
        return func


    def autolocked_method(func):
        """Automatically synchronizes all calls of a method of a ThreadSafeSingleton-derived
        class by locking the singleton for the duration of each call.
        """

        @functools.wraps(func)
        @threadsafe_method
        def lock_and_call(self, *args, **kwargs):
            with self:
                return func(self, *args, **kwargs)

        return lock_and_call

if NEED_MY_SINGLETON:
    class SingletonMeta(type):
        def __init__(cls, *args, **kwargs):
            cls.__instance = None
            cls.__lock = threading.RLock()
            super().__init__(*args, **kwargs)
        def __call__(cls, *args, **kwargs):
            if cls.__instance is None:
                with cls.__lock:
                    if cls.__instance is None:
                        cls.__instance = super().__call__(*args, **kwargs)
            return cls.__instance
    
    def singleton(cls):
        instances = {}
        locker = threading.RLock()

        @functools.wraps(cls)
        def wrapper(*args, **kwargs):
            if cls not in instances:
                with locker:
                    if cls not in instances:
                        instances[cls] = cls(*args, **kwargs)
            return instances[cls]

        return wrapper
    
if NEED_TERMINAL_CTRL:
    def clear_screen():
        sys.stdout.write("\033[2J\033[1;1H")
        sys.stdout.flush()
    
    def set_cursor_position(row, col):
        sys.stdout.write(f"\033[{row};{col}H")
        sys.stdout.flush()
    
    def hide_cursor():
        sys.stdout.write("\033[?25l")
        sys.stdout.flush()
    
    def show_cursor():
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()
    
    def set_text_color(fg=None, bg=None, bold=False, dim=False, italic=False, underline=False):
        codes = []
        if bold:
            codes.append("1")
        if dim:
            codes.append("2")
        if italic:
            codes.append("3")
        if underline:
            codes.append("4")
        if fg is not None:
            codes.append(str(30 + fg))
        if bg is not None:
            codes.append(str(40 + bg))
        if codes:
            sys.stdout.write(f"\033[{';'.join(codes)}m")
            sys.stdout.flush()
    
    def reset_text_style():
        sys.stdout.write("\033[0m")
        sys.stdout.flush()
    
    def erase_line():
        sys.stdout.write("\033[2K")
        sys.stdout.flush()
    
    def erase_from_cursor_to_end():
        sys.stdout.write("\033[0J")
        sys.stdout.flush()

    def enter_alternate_screen_buffer():
        sys.stdout.write("\033[?1049h")
        sys.stdout.flush()

    def exit_alternate_screen_buffer():
        sys.stdout.write("\033[?1049l")
        sys.stdout.flush()

    def query_device_attributes():
        sys.stdout.write("\033[c")
        sys.stdout.flush()
    
    
if NEED_TRAINING_DETERMINISTIC:
    def set_deterministic(seed=42):
        import random
        random.seed(seed)

        try:
            import numpy as np
            np.random.seed(seed)
        except ImportError:
            print("NumPy not found, skipping NumPy random seed setting.")

        try:
            import torch
            torch.manual_seed(seed)
            torch.cuda.manual_seed_all(seed)
            torch.backends.cudnn.deterministic = True
            torch.backends.cudnn.benchmark = False
        except ImportError:
            print("PyTorch not found, skipping PyTorch random seed setting.")

        os.environ['PYTHONHASHSEED'] = str(seed)

_all = [
    'logger',
    'Timer',
    'classonlymethod',
    'Singleton',
    'ThreadSafeSingleton',
    'threadsafe_method',
    'autolocked_method',
    'SingletonMeta',
    'singleton',
    'clear_screen',
    'set_cursor_position',
    'hide_cursor',
    'show_cursor',
    'set_text_color',
    'reset_text_style',
    'erase_line',
    'erase_from_cursor_to_end',
    'enter_alternate_screen_buffer',
    'exit_alternate_screen_buffer',
    'query_device_attributes',
    'set_deterministic'
]

__all__ = [name for name in _all if name in globals()]
