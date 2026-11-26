"""Run a Python entry point with UTF-8 streams and matching console code pages."""
from __future__ import annotations

import os
import runpy
import sys

UTF8_CODE_PAGE = 65001


class WindowsConsoleAPI:
    """Typed Win32 calls for the input and output code pages."""

    def __init__(self):
        import ctypes
        from ctypes import wintypes

        self.ctypes = ctypes
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        for name in ("GetConsoleCP", "GetConsoleOutputCP"):
            function = getattr(self.kernel32, name)
            function.argtypes = []
            function.restype = wintypes.UINT
        for name in ("SetConsoleCP", "SetConsoleOutputCP"):
            function = getattr(self.kernel32, name)
            function.argtypes = [wintypes.UINT]
            function.restype = wintypes.BOOL

    def get_input(self):
        return self.kernel32.GetConsoleCP()

    def get_output(self):
        return self.kernel32.GetConsoleOutputCP()

    def set_input(self, code_page):
        if not self.kernel32.SetConsoleCP(code_page):
            raise self.ctypes.WinError(self.ctypes.get_last_error())

    def set_output(self, code_page):
        if not self.kernel32.SetConsoleOutputCP(code_page):
            raise self.ctypes.WinError(self.ctypes.get_last_error())


class ConsoleCodePages:
    """Restore changed pages only while the applied value is still present."""

    def __init__(self, api):
        self.api = api
        self.original = {}
        self.attempted = []

    def activate(self):
        if self.api is None:
            return
        # Capture both values before changing either one. A zero value means
        # this process has no corresponding console code page to change.
        self.original = {
            "input": self.api.get_input(),
            "output": self.api.get_output(),
        }
        for channel in ("input", "output"):
            original = self.original[channel]
            if original and original != UTF8_CODE_PAGE:
                # Record the attempt first so an interrupt immediately after a
                # successful Win32 call still receives conditional restoration.
                self.attempted.append(channel)
                getattr(self.api, "set_" + channel)(UTF8_CODE_PAGE)

    def restore(self):
        errors = []
        for channel in reversed(self.attempted):
            try:
                if getattr(self.api, "get_" + channel)() == UTF8_CODE_PAGE:
                    getattr(self.api, "set_" + channel)(self.original[channel])
            except BaseException as exc:
                # Continue restoring the other channel even if this one fails.
                errors.append(exc)
        self.attempted.clear()
        return errors


def configure_utf8_streams():
    for stream, output in ((sys.stdin, False), (sys.stdout, True), (sys.stderr, True)):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            options = {"encoding": "utf-8"}
            if output:
                options["errors"] = "backslashreplace"
            reconfigure(**options)


def run_engine(arguments, *, api=None, runner=None):
    """Execute the entry point, preserving its arguments, result, and failures."""
    if not arguments:
        raise SystemExit("Usage: console_utf8.py ENTRY_POINT [ARGUMENT ...]")
    configure_utf8_streams()
    if api is None and os.name == "nt":
        api = WindowsConsoleAPI()
    pages = ConsoleCodePages(api)
    previous_argv = sys.argv
    failed = False
    try:
        pages.activate()
        sys.argv = list(arguments)
        execute = runner if runner is not None else runpy.run_path
        return execute(arguments[0], run_name="__main__")
    except BaseException:
        failed = True
        raise
    finally:
        sys.argv = previous_argv
        errors = []
        # Flush UTF-8 bytes while the console still uses UTF-8, including when
        # the entry point raises SystemExit, KeyboardInterrupt, or another error.
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.flush()
            except BaseException as exc:
                errors.append(exc)
        errors.extend(pages.restore())
        if errors and not failed:
            raise errors[0]


if __name__ == "__main__":
    run_engine(sys.argv[1:])
