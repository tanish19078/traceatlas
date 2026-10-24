"""Shared outbound request accounting, deadlines and host cooldowns."""
import math
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

_ACTIVE = ContextVar('traceatlas_request_budget', default=None)
_COOLDOWNS = {}
_LOCK = threading.Lock()

class BudgetError(ValueError):
    pass

class RequestBudget:
    def __init__(self, limit, deadline):
        self.limit, self.deadline = limit, deadline
        self.used, self.by_input = 0, {}
        self.lock = threading.Lock()

    def reserve(self, index):
        with self.lock:
            if time.monotonic() >= self.deadline:
                raise BudgetError('deadline_exhausted')
            if self.used >= self.limit:
                raise BudgetError('global_request_budget_exhausted')
            self.used += 1
            self.by_input[index] = self.by_input.get(index, 0) + 1

@contextmanager
def request_scope(budget, index):
    token = _ACTIVE.set((budget, index))
    try:
        yield
    finally:
        _ACTIVE.reset(token)


def take_request(url, deadline=None):
    active = _ACTIVE.get()
    if active:
        deadline = min(deadline or active[0].deadline, active[0].deadline)
    host = urlsplit(url).hostname
    with _LOCK:
        wait = max(0, _COOLDOWNS.get(host, 0) - time.monotonic())
    if wait:
        if deadline is None or time.monotonic() + wait >= deadline:
            raise BudgetError('host_rate_limited')
        time.sleep(wait)
    if active:
        active[0].reserve(active[1])
    elif deadline is not None and time.monotonic() >= deadline:
        raise BudgetError('deadline_exhausted')


def rate_limited(url, retry_after=None):
    delay = 60.0
    try:
        delay = float(retry_after)
        if not math.isfinite(delay) or delay < 0:
            delay = 60.0
    except (ValueError, TypeError):
        try:
            stamp = parsedate_to_datetime(retry_after)
            if stamp.tzinfo is None:
                raise ValueError('timezone missing')
            delay = max(0, (stamp - datetime.now(timezone.utc)).total_seconds())
        except (ValueError, TypeError, AttributeError, OverflowError):
            pass
    with _LOCK:
        host = urlsplit(url).hostname
        _COOLDOWNS[host] = max(_COOLDOWNS.get(host, 0), time.monotonic() + delay)
