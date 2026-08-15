import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path



def load_plugin_module():
    """Load the plugin with the minimum MoviePilot/watchdog API surface stubbed."""
    app = types.ModuleType("app")
    app_plugins = types.ModuleType("app.plugins")

    class PluginBase:
        def post_message(self, **kwargs):
            return kwargs

    app_plugins._PluginBase = PluginBase
    app.plugins = app_plugins

    app_schemas = types.ModuleType("app.schemas")

    class Response:
        def __init__(self, success, message):
            self.success = success
            self.message = message

    app_schemas.Response = Response
    app_schemas_types = types.ModuleType("app.schemas.types")

    class EventType:
        PluginReload = "plugin.reload"
        PluginAction = "plugin.action"

    class NotificationType:
        Plugin = "plugin"

    app_schemas_types.EventType = EventType
    app_schemas_types.SystemConfigKey = object()
    app_schemas_types.NotificationType = NotificationType
    app.schemas = app_schemas

    app_core = types.ModuleType("app.core")
    app_config = types.ModuleType("app.core.config")
    app_config.settings = types.SimpleNamespace(API_TOKEN="test-token")
    app_event = types.ModuleType("app.core.event")

    class Event:
        def __init__(self, event_data=None):
            self.event_data = event_data

    class EventManager:
        @staticmethod
        def register(_event_type):
            return lambda func: func

    app_event.Event = Event
    app_event.eventmanager = EventManager()
    app_core.config = app_config
    app_core.event = app_event
    app_db = types.ModuleType("app.db")
    app_systemconfig = types.ModuleType("app.db.systemconfig_oper")

    class SystemConfigOper:
        def get(self, _key):
            return None

        def set(self, _key, _value):
            return None

    app_systemconfig.SystemConfigOper = SystemConfigOper
    app_db.systemconfig_oper = app_systemconfig
    app_log = types.ModuleType("app.log")
    app_log.logger = types.SimpleNamespace(
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
    )

    watchdog = types.ModuleType("watchdog")
    watchdog_observers = types.ModuleType("watchdog.observers")
    watchdog_events = types.ModuleType("watchdog.events")

    class Observer:
        def schedule(self, *args, **kwargs):
            return None

        def start(self):
            return None

        def stop(self):
            return None

        def join(self, timeout=None):
            return None

    class FileSystemEventHandler:
        pass

    watchdog_observers.Observer = Observer
    watchdog_events.FileSystemEventHandler = FileSystemEventHandler

    modules = {
        "app": app,
        "app.plugins": app_plugins,
        "app.schemas": app_schemas,
        "app.schemas.types": app_schemas_types,
        "app.core": app_core,
        "app.core.config": app_config,
        "app.core.event": app_event,
        "app.db": app_db,
        "app.db.systemconfig_oper": app_systemconfig,
        "app.log": app_log,
        "watchdog": watchdog,
        "watchdog.observers": watchdog_observers,
        "watchdog.events": watchdog_events,
    }
    old_modules = {name: sys.modules.get(name) for name in modules}
    sys.modules.update(modules)
    try:
        path = Path(__file__).parents[1] / "plugins.v2" / "autosubrename" / "__init__.py"
        spec = importlib.util.spec_from_file_location("autosubrename_under_test", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for name, old in old_modules.items():
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old


class AutoSubRenameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_plugin_module()

    def test_monitor_directory_prefix_is_not_treated_as_child(self):
        plugin = self.module.AutoSubRename.__new__(self.module.AutoSubRename)
        plugin._monitor_dirs = ["/media/tv"]
        plugin._processed_files = set()
        plugin._current_config = self.module.PluginConfigModel()
        plugin._renamer = self.module.SubtitleRenamer()

        with tempfile.TemporaryDirectory() as temp:
            outside = Path(temp) / "tv2"
            outside.mkdir()
            video = outside / "show.S01E01.mkv"
            subtitle = outside / "subtitle.S01E01.ass"
            video.touch()
            subtitle.touch()
            plugin.process_subtitle(str(subtitle))
            self.assertTrue(subtitle.exists())
            self.assertFalse((outside / video.with_suffix(".ass").name).exists())

    def test_remote_command_triggers_batch_rename(self):
        plugin = self.module.AutoSubRename.__new__(self.module.AutoSubRename)
        plugin._batch_thread = None
        called = []
        plugin.batch_rename = lambda: called.append(True)

        event = self.module.Event(event_data={"action": "batch_rename"})
        plugin.remote_batch_rename(event)
        plugin._batch_thread.join(timeout=2)
        self.assertEqual(called, [True])

    def test_batch_api_rejects_missing_api_token(self):
        plugin = self.module.AutoSubRename.__new__(self.module.AutoSubRename)
        response = plugin.batch_rename_api(apikey="wrong-token")
        self.assertEqual(response.success, False)

    def test_batch_api_accepts_valid_api_token(self):
        plugin = self.module.AutoSubRename.__new__(self.module.AutoSubRename)
        called = []
        plugin.batch_rename = lambda: called.append(True)
        response = plugin.batch_rename_api(apikey="test-token")
        plugin._batch_thread.join(timeout=2)
        self.assertEqual(response.success, True)
        self.assertEqual(called, [True])

    def test_batch_notifies_when_no_monitor_directory(self):
        plugin = self.module.AutoSubRename.__new__(self.module.AutoSubRename)
        plugin._monitor_dirs = []
        plugin._processed_files = set()
        plugin._current_config = self.module.PluginConfigModel(notify=True)
        messages = []
        plugin.post_message = lambda **kwargs: messages.append(kwargs)
        plugin.batch_rename()
        self.assertEqual(len(messages), 1)
        self.assertIn("未配置", messages[0]["text"])


if __name__ == "__main__":
    unittest.main()
