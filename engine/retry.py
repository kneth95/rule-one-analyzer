"""Retry helper and the error type for data that could not be downloaded."""
import time


class FetchError(Exception):
    """Raised when outside data (SEC, Yahoo) could not be downloaded."""


def with_retries(fn, attempts=3, base_delay=1.0, sleep=time.sleep, retry_on=(Exception,)):
    for i in range(attempts):
        try:
            return fn()
        except retry_on:
            if i == attempts - 1:
                raise
            sleep(base_delay * 2 ** i)
