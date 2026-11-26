#!/usr/bin/env python3
"""Focused code-page, stream, and cleanup checks for the UTF-8 bootstrap."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
MODULE = ROOT / "runtime/console_utf8.py"
spec = importlib.util.spec_from_file_location("console_utf8", MODULE)
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


class FakeAPI:
    def __init__(self, input_cp=932, output_cp=932):
        self.input = input_cp
        self.output = output_cp
        self.events = []
        self.failure = None

    def get_input(self):
        self.events.append(("get", "input", self.input))
        return self.input

    def get_output(self):
        self.events.append(("get", "output", self.output))
        return self.output

    def _set(self, channel, value):
        self.events.append(("set", channel, value))
        if self.failure is not None:
            self.failure(channel, value, self)
        setattr(self, channel, value)

    def set_input(self, value):
        self._set("input", value)

    def set_output(self, value):
        self._set("output", value)


class FakeStream:
    def __init__(self, name, api):
        self.name = name
        self.api = api
        self.encoding = "cp932"
        self.errors = "strict"
        self.flush_error = None

    def reconfigure(self, **options):
        self.encoding = options["encoding"]
        self.errors = options.get("errors", self.errors)
        self.api.events.append(("configure", self.name, self.encoding))

    def flush(self):
        self.api.events.append(("flush", self.name, self.api.input, self.api.output))
        if self.flush_error is not None:
            raise self.flush_error


@contextmanager
def streams_for(api):
    streams = {name: FakeStream(name, api) for name in ("stdin", "stdout", "stderr")}
    with patch.multiple(sys, **streams):
        yield streams


class BootstrapTests(unittest.TestCase):
    def test_standard_pages_streams_arguments_and_return_value(self):
        api = FakeAPI()
        before = sys.argv
        arguments = ["PyEmuera.pyz", ".", "--entry", "日本語"]
        expected = {"completed": True}
        with streams_for(api) as streams:
            def run(path, *, run_name):
                self.assertEqual((api.input, api.output), (65001, 65001))
                self.assertEqual(sys.argv, arguments)
                self.assertEqual((path, run_name), (arguments[0], "__main__"))
                self.assertTrue(all(s.encoding == "utf-8" for s in streams.values()))
                return expected
            self.assertIs(bootstrap.run_engine(arguments, api=api, runner=run), expected)
        self.assertIs(sys.argv, before)
        self.assertEqual((api.input, api.output), (932, 932))
        self.assertEqual(api.events[-4:], [("get", "output", 65001), ("set", "output", 932),
                                          ("get", "input", 65001), ("set", "input", 932)])
        self.assertEqual([x for x in api.events if x[0] == "flush"],
                         [("flush", "stdout", 65001, 65001), ("flush", "stderr", 65001, 65001)])

    def test_different_original_input_and_output_pages(self):
        api = FakeAPI(932, 437)
        with streams_for(api):
            bootstrap.run_engine(["entry.py"], api=api, runner=lambda *a, **k: None)
        self.assertEqual((api.input, api.output), (932, 437))

    def test_no_console_and_already_utf8_need_no_set_calls(self):
        for value in (0, 65001):
            with self.subTest(code_page=value):
                api = FakeAPI(value, value)
                with streams_for(api):
                    bootstrap.run_engine(["entry.py"], api=api, runner=lambda *a, **k: None)
                self.assertFalse(any(x[0] == "set" for x in api.events))

    def test_zero_input_page_keeps_output_independent(self):
        api = FakeAPI(0, 932)
        with streams_for(api):
            bootstrap.run_engine(["entry.py"], api=api, runner=lambda *a, **k: None)
        self.assertEqual((api.input, api.output), (0, 932))
        self.assertFalse(any(x[:2] == ("set", "input") for x in api.events))

    def test_partial_setup_failure_rolls_back_completed_change(self):
        api = FakeAPI()
        failure = OSError("output setup failed")
        def fail(channel, value, api):
            if (channel, value) == ("output", 65001):
                raise failure
        api.failure = fail
        with streams_for(api), self.assertRaises(OSError) as caught:
            bootstrap.run_engine(["entry.py"], api=api, runner=lambda *a, **k: self.fail("entry point ran"))
        self.assertIs(caught.exception, failure)
        self.assertEqual((api.input, api.output), (932, 932))

    def test_interrupt_immediately_after_set_is_restored(self):
        api = FakeAPI()
        failure = KeyboardInterrupt()
        def interrupt(channel, value, api):
            if (channel, value) == ("output", 65001):
                api.output = value
                raise failure
        api.failure = interrupt
        with streams_for(api), self.assertRaises(KeyboardInterrupt) as caught:
            bootstrap.run_engine(["entry.py"], api=api, runner=lambda *a, **k: self.fail("entry point ran"))
        self.assertIs(caught.exception, failure)
        self.assertEqual((api.input, api.output), (932, 932))

    def test_entry_exceptions_and_exit_codes_are_preserved(self):
        for failure in (SystemExit(0), SystemExit(7), RuntimeError("entry failed"), KeyboardInterrupt()):
            with self.subTest(exception=type(failure).__name__, detail=str(failure)):
                api = FakeAPI(932, 437)
                before = sys.argv
                def run(*args, **kwargs):
                    raise failure
                with streams_for(api), self.assertRaises(type(failure)) as caught:
                    bootstrap.run_engine(["entry.py", "argument"], api=api, runner=run)
                self.assertIs(caught.exception, failure)
                self.assertIs(sys.argv, before)
                self.assertEqual((api.input, api.output), (932, 437))
                self.assertEqual([x for x in api.events if x[0] == "flush"],
                                 [("flush", "stdout", 65001, 65001), ("flush", "stderr", 65001, 65001)])

    def test_later_external_page_change_is_kept(self):
        api = FakeAPI()
        def run(*args, **kwargs):
            api.output = 936
        with streams_for(api):
            bootstrap.run_engine(["entry.py"], api=api, runner=run)
        self.assertEqual((api.input, api.output), (932, 936))
        self.assertNotIn(("set", "output", 932), api.events)

    def test_cleanup_error_does_not_replace_entry_failure(self):
        api = FakeAPI()
        entry_error = KeyboardInterrupt()
        cleanup_error = OSError("output restoration failed")
        def fail(channel, value, api):
            if (channel, value) == ("output", 932):
                raise cleanup_error
        api.failure = fail
        def run(*args, **kwargs):
            raise entry_error
        with streams_for(api), self.assertRaises(KeyboardInterrupt) as caught:
            bootstrap.run_engine(["entry.py"], api=api, runner=run)
        self.assertIs(caught.exception, entry_error)
        self.assertEqual(api.input, 932)

    def test_flush_failure_still_restores_pages_and_keeps_exit(self):
        api = FakeAPI()
        entry_exit = SystemExit(4)
        def run(*args, **kwargs):
            raise entry_exit
        with streams_for(api) as streams, self.assertRaises(SystemExit) as caught:
            streams["stdout"].flush_error = OSError("flush failed")
            bootstrap.run_engine(["entry.py"], api=api, runner=run)
        self.assertIs(caught.exception, entry_exit)
        self.assertEqual((api.input, api.output), (932, 932))

    def test_cleanup_failure_is_reported_after_normal_return(self):
        api = FakeAPI()
        failure = OSError("flush failed")
        with streams_for(api) as streams, self.assertRaises(OSError) as caught:
            streams["stderr"].flush_error = failure
            bootstrap.run_engine(["entry.py"], api=api, runner=lambda *a, **k: None)
        self.assertIs(caught.exception, failure)
        self.assertEqual((api.input, api.output), (932, 932))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=Path(__file__).with_suffix(".json"))
    args = parser.parse_args()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(BootstrapTests)
    names = [case.id().rsplit(".", 1)[-1] for case in suite]
    result = unittest.TestResult()
    suite.run(result)
    report = {
        "pass": result.wasSuccessful(),
        "scope": "Console code-page lifecycle with controlled API responses; stream, argument, failure, and cleanup semantics",
        "bootstrap": "runtime/console_utf8.py",
        "bootstrap_sha256": hashlib.sha256(MODULE.read_bytes()).hexdigest(),
        "tests_run": result.testsRun, "cases": names,
        "failures": [{"test": case.id(), "traceback": trace} for case, trace in result.failures],
        "errors": [{"test": case.id(), "traceback": trace} for case, trace in result.errors],
    }
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"pass": report["pass"], "tests_run": report["tests_run"]}))
    raise SystemExit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main()
