"""Only genuinely absent activation anchor skips the unknown optional addon."""
import ast
import builtins
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import integrate_private_sources as integration


SOURCE = '''def register(app):
    app.append("before")
    try:
        import photo_hide
        photo_hide.register(app)
    except Exception:
        app.append("optional failed")
    app.append("after")
    bootstrap(app)
'''


class OptionalPhotoHideGate(unittest.TestCase):
    def exercise(self, *, present, remove_before_bootstrap=False):
        with tempfile.TemporaryDirectory() as directory:
            anchor = Path(directory) / ".uaart_price_sync_anchor.json"
            if present:
                # Content is deliberately malformed. Presence must retain the
                # original registration, leaving strict bootstrap to reject it.
                anchor.write_text("not a valid anchor")
            namespace = {}
            helper = next(node for node in ast.parse(integration.ACTIVATION_BLOCK).body
                          if isinstance(node, ast.FunctionDef)
                          and node.name == "_ua114_optional_photo_hide_allowed")
            exec(compile(ast.Module(body=[helper], type_ignores=[]), "<actual-anchor-presence-helper>", "exec"), namespace)
            gated = integration._gate_optional_photo_hide(SOURCE)
            exec(gated, namespace)
            exec(integration.REGISTRATION_BOUNDARY_BLOCK, namespace)
            seen = []
            addon = types.ModuleType("photo_hide")
            addon.register = lambda app: app.append("registered optional photo_hide")
            original_import = builtins.__import__
            def import_spy(name, *args, **kwargs):
                if name == "photo_hide":
                    seen.append("import")
                return original_import(name, *args, **kwargs)
            runtime = types.ModuleType("uaart_price_sync_runtime")
            runtime.activation_available = lambda: False
            runtime.Binding = type("Binding", (), {})
            runtime.BINDING_KEY = "verified_binding"
            def bootstrap(app):
                if remove_before_bootstrap:
                    anchor.unlink()
                if anchor.exists():
                    app.bot_data[runtime.BINDING_KEY] = runtime.Binding()
            namespace["bootstrap"] = bootstrap
            with patch.dict(sys.modules, {"photo_hide": addon, "uaart_price_sync_runtime": runtime}), \
                 patch("pathlib.Path", lambda value: anchor if value == "/home/Carix/.uaart_price_sync_anchor.json" else Path(value)), \
                 patch("builtins.__import__", import_spy):
                class Application(list):
                    bot_data = {}
                app = Application()
                namespace["register"](app)
            return app, seen

    def test_absent_anchor_never_imports_or_registers_optional_media_extension(self):
        app, seen = self.exercise(present=False)
        self.assertEqual(app, ["before", "after"])
        self.assertEqual(seen, [])

    def test_present_anchor_keeps_original_optional_registration_while_readiness_false(self):
        app, seen = self.exercise(present=True)
        self.assertEqual(app, ["before", "registered optional photo_hide", "after"])
        self.assertEqual(seen, ["import"])

    def test_anchor_removed_after_registration_cannot_downgrade_to_unconfigured(self):
        with self.assertRaisesRegex(RuntimeError, "ANCHOR_DISAPPEARED_BEFORE_BOOTSTRAP"):
            self.exercise(present=True, remove_before_bootstrap=True)


if __name__ == "__main__":
    unittest.main()
