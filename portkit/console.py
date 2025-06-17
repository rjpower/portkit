#!/usr/bin/env python3

from rich.console import Console as RichConsole

class Console:
    """Simple console wrapper focused on output."""

    def __init__(self):
        self._rich = RichConsole()

    def print(self, *args, **kwargs):
        """Print using Rich console."""
        return self._rich.print(*args, **kwargs)

    def status(self, *args, **kwargs):
        """Create Rich status context."""
        return self._rich.status(*args, **kwargs)


