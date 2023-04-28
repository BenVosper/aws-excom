import contextlib
import signal
from itertools import zip_longest


def grouper(iterable, n):
    args = [iter(iterable)] * n
    return zip_longest(*args, fillvalue=None)


# https://github.com/hreeder/assh/issues/3


@contextlib.contextmanager
def ignore_user_entered_signals():
    """
    Ignores user entered signals to avoid process getting killed.
    """
    signal_list = [signal.SIGINT, signal.SIGQUIT, signal.SIGTSTP]
    actual_signals = []
    for user_signal in signal_list:
        actual_signals.append(signal.signal(user_signal, signal.SIG_IGN))
    try:
        yield
    finally:
        for sig, user_signal in enumerate(signal_list):
            signal.signal(user_signal, actual_signals[sig])
