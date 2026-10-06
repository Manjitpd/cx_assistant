import asyncio
import selectors
import sys


def loop_factory() -> asyncio.AbstractEventLoop:
    """Return an event loop psycopg can drive.

    Uvicorn uses ProactorEventLoop on Windows. Psycopg's async connections
    reject that loop, so the API process uses SelectorEventLoop instead.
    Start the server with ``--loop app.core.event_loop:loop_factory``.
    """
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop(selectors.SelectSelector())
    return asyncio.new_event_loop()
