"""COMFYUI_MCP_PANEL_DISABLE_TRAINING=1 must skip the training routes.

Both training routes hand a filesystem path to the trainer, which runs in
ANOTHER process: `resolve-paths` turns a ComfyUI image reference into an
absolute host path for `train_prepare_dataset`, and `list-outputs` enumerates
the output directory for the wizard's picker. On a host that keeps ComfyUI's
session files somewhere that other process cannot open (a RAM-only pod, where
every file lives in memory behind a marker path), those routes answer with
paths that resolve to nothing, and the wizard fails late and obscurely. The
flag turns that into an explicit, logged refusal at load time.

These tests drive the SHIPPED `_register_routes` against a route collector, so
a flag honoured in a helper while the call site still registers would fail
here. Nothing inspects source text.

Run from the repo root:

    python -m unittest browser_tests.unit.test_training_disable_flag
"""

import importlib.util
import io
import os
import sys
import types
import unittest

_REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
_MODULE_NAME = "cmcp_panel_init_training_flag"


def _load_init():
    """Load the pack's `__init__.py` AS A PACKAGE.

    `submodule_search_locations` plus an entry in `sys.modules` is what makes
    its `from .py import training_routes` resolve, and that is the whole point:
    the flag has to be measured by the routes that really get registered, not
    by a log line standing in for them.
    """
    spec = importlib.util.spec_from_file_location(
        _MODULE_NAME,
        os.path.join(_REPO, "__init__.py"),
        submodule_search_locations=[_REPO],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    # The module calls _register_routes() on the way out; with no `server`
    # module importable it returns immediately, so nothing is registered here.
    spec.loader.exec_module(module)
    return module


mod = _load_init()

_TRAINING_PREFIX = "/comfyui_mcp_panel/training/"
_TRAINING_ROUTES = {
    ("POST", "/comfyui_mcp_panel/training/resolve-paths"),
    ("GET", "/comfyui_mcp_panel/training/file"),
    ("GET", "/comfyui_mcp_panel/training/list-outputs"),
}


class _Web:
    """Stand-in for aiohttp.web: register() only needs it to exist."""

    @staticmethod
    def json_response(payload, status=200, headers=None):
        del headers
        return (payload, status)

    @staticmethod
    def middleware(handler):
        return handler


class _Routes:
    """Route collector shaped like aiohttp's RouteTableDef."""

    def __init__(self):
        self.handlers = {}

    def get(self, path):
        return self._register("GET", path)

    def post(self, path):
        return self._register("POST", path)

    def put(self, path):
        return self._register("PUT", path)

    def delete(self, path):
        return self._register("DELETE", path)

    def _register(self, method, path):
        def decorate(handler):
            self.handlers[(method, path)] = handler
            return handler

        return decorate

    def training(self):
        return {key for key in self.handlers if key[1].startswith(_TRAINING_PREFIX)}


class _CaptureStdout:
    def __init__(self):
        self.buffer = io.StringIO()

    def __enter__(self):
        self._old = sys.stdout
        sys.stdout = self.buffer
        return self.buffer

    def __exit__(self, *exc):
        sys.stdout = self._old
        return False


class _Env:
    """Set (or clear) one environment variable for the duration of a block."""

    def __init__(self, name, value):
        self.name = name
        self.value = value

    def __enter__(self):
        self._saved = os.environ.get(self.name)
        if self.value is None:
            os.environ.pop(self.name, None)
        else:
            os.environ[self.name] = self.value
        return self

    def __exit__(self, *exc):
        if self._saved is None:
            os.environ.pop(self.name, None)
        else:
            os.environ[self.name] = self._saved
        return False


def _register_panel_routes():
    """Run the SHIPPED `_register_routes` and return (collector, log text).

    `server` and `aiohttp` are stood in so the function gets past its guard.
    The stub PromptServer has no `.app`, so the no-cache middleware declines
    and says so in the log; that line is captured with the rest.
    """
    routes = _Routes()
    fake_server = types.ModuleType("server")
    fake_server.PromptServer = types.SimpleNamespace(
        instance=types.SimpleNamespace(routes=routes)
    )
    fake_aiohttp = types.ModuleType("aiohttp")
    fake_aiohttp.web = _Web
    saved = {name: sys.modules.get(name) for name in ("server", "aiohttp")}
    sys.modules["server"] = fake_server
    sys.modules["aiohttp"] = fake_aiohttp
    try:
        with _CaptureStdout() as out:
            mod._register_routes()
    finally:
        for name, value in saved.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value
    return routes, out.getvalue()


_DISABLED_LINE = "training routes disabled by COMFYUI_MCP_PANEL_DISABLE_TRAINING"


class TrainingRoutesFlag(unittest.TestCase):
    def test_absent_flag_registers_all_three_training_routes(self):
        with _Env("COMFYUI_MCP_PANEL_DISABLE_TRAINING", None):
            routes, log = _register_panel_routes()
        self.assertEqual(routes.training(), _TRAINING_ROUTES)
        self.assertNotIn(_DISABLED_LINE, log)

    def test_truthy_flag_registers_none_of_them(self):
        for value in ("1", "true", "TRUE", "yes", "Yes", " true "):
            with self.subTest(value=value):
                with _Env("COMFYUI_MCP_PANEL_DISABLE_TRAINING", value):
                    routes, log = _register_panel_routes()
                self.assertEqual(routes.training(), set())
                self.assertIn(_DISABLED_LINE, log)

    def test_falsy_and_empty_values_leave_the_routes_alone(self):
        # An exported-but-empty variable is the one that matters: a pod template
        # that always exports the name must not disable training by accident.
        for value in ("", " ", "0", "false", "no", "off", "maybe"):
            with self.subTest(value=value):
                with _Env("COMFYUI_MCP_PANEL_DISABLE_TRAINING", value):
                    routes, _log = _register_panel_routes()
                self.assertEqual(routes.training(), _TRAINING_ROUTES)

    def test_the_flag_touches_nothing_else(self):
        # The apps routes and the panel's own routes must survive the flag: it
        # narrows the training surface, it does not degrade the panel.
        with _Env("COMFYUI_MCP_PANEL_DISABLE_TRAINING", None):
            enabled, _log = _register_panel_routes()
        with _Env("COMFYUI_MCP_PANEL_DISABLE_TRAINING", "1"):
            disabled, _log = _register_panel_routes()
        self.assertEqual(
            set(enabled.handlers) - set(disabled.handlers), _TRAINING_ROUTES
        )
        self.assertEqual(set(disabled.handlers) - set(enabled.handlers), set())
        self.assertIn(("GET", "/comfyui_mcp_panel/apps"), disabled.handlers)
        self.assertIn(("GET", "/comfyui_mcp_panel/version"), disabled.handlers)


class EnvFlag(unittest.TestCase):
    def test_accepted_and_rejected_spellings(self):
        for value in ("1", "true", "True", "YES", "  yes  "):
            with _Env("CMCP_PANEL_TEST_FLAG", value):
                self.assertTrue(mod._env_flag("CMCP_PANEL_TEST_FLAG"), value)
        for value in ("", "   ", "0", "false", "no", "2", "y", "on"):
            with _Env("CMCP_PANEL_TEST_FLAG", value):
                self.assertFalse(mod._env_flag("CMCP_PANEL_TEST_FLAG"), value)

    def test_absent_variable_is_false(self):
        with _Env("CMCP_PANEL_TEST_FLAG", None):
            self.assertFalse(mod._env_flag("CMCP_PANEL_TEST_FLAG"))


if __name__ == "__main__":
    unittest.main()
