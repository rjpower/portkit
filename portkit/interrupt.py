import signal


class InterruptSignal(Exception):
    """Exception raised when user interrupts."""

    def __init__(self, user_message: str = ""):
        self.user_message = user_message
        super().__init__(f"User interrupt: {user_message}")


class InterruptHandler:
    """Signal-based interrupt handling."""

    def __init__(self):
        self._interrupt_requested = False
        self._user_message = ""
        self._original_handler = None

    def setup(self):
        """Install SIGINT handler."""
        self._original_handler = signal.signal(signal.SIGINT, self._handle_signal)

    def cleanup(self):
        """Restore original handler."""
        if self._original_handler:
            signal.signal(signal.SIGINT, self._original_handler)

    def _handle_signal(self, signum, frame):
        """Handle SIGINT by prompting user."""
        print("\nProcess interrupted! Enter your message (or press Enter to continue):")
        try:
            user_input = input().strip()
            self._interrupt_requested = True
            self._user_message = user_input
        except (EOFError, KeyboardInterrupt):
            self._interrupt_requested = True
            self._user_message = ""

    def check_interrupt(self) -> str | None:
        """Check if interrupt was requested and reset state."""
        if self._interrupt_requested:
            self._interrupt_requested = False
            message = self._user_message
            self._user_message = ""
            return message
        return None
