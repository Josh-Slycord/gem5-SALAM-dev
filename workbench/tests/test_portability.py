"""Portable publication paths and existing-engine binding contracts."""
import json
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from salam_workbench import bootstrap_existing, gui_hook
from salam_workbench.hardware_variants import _SKIP_COPY
from salam_workbench.runner import file_hash


class PortabilityTests(unittest.TestCase):
    def test_gui_hook_replaces_legacy_tail_and_is_idempotent(self):
        legacy = ('from pathlib import Path\nclass ConfigGeneratorDialog:\n'
                  '    pass\n\n' + gui_hook.OLD_MARKER + '\n'
                  'if Path(__file__).resolve().parents[3].name == "configurator-engine":\n'
                  '    pass\n')
        result = gui_hook.render_hook(legacy)
        self.assertIn('SALAM_WORKBENCH_ROOT', result)
        self.assertNotIn('configurator-engine', result)
        self.assertEqual(gui_hook.render_hook(result), result)
        self.assertIn('workbench', _SKIP_COPY)

    def test_gui_hook_install_preserves_before_image(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            engine = root / 'engine'
            engine.mkdir()
            (engine / 'SConstruct').write_text('', encoding='utf-8')
            gui = engine / gui_hook.GUI_RELATIVE
            gui.parent.mkdir(parents=True)
            original = 'class ConfigGeneratorDialog:\n    pass\n'
            gui.write_text(original, encoding='utf-8')
            result = gui_hook.install_hook(engine, root / 'evidence')
            self.assertEqual(result['state'], 'installed')
            self.assertEqual((root / 'evidence/config_generator.py.before').read_text(), original)
            self.assertIn(gui_hook.NEW_MARKER, gui.read_text())
            self.assertEqual(file_hash(gui), result['after_sha256'])

    def test_bootstrap_copies_exact_receipts_and_never_reuses_binding(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, project, engine = (root / name for name in ('old', 'new', 'external'))
            for path in (source / 'evidence', project, engine):
                path.mkdir(parents=True)
            toolchain = source / 'evidence/toolchain.json'
            toolchain.write_text('{"schema_version":1}\n', encoding='utf-8')
            build_relative = 'evidence/build/build.json'
            generation_relative = 'evidence/generation/hardware-codegen.json'
            build = source / build_relative
            generation = source / generation_relative
            build.parent.mkdir(parents=True)
            generation.parent.mkdir(parents=True)
            sidecar = build.parent / 'source-inputs.json'
            source_files = {'SConstruct': 'a' * 64}
            source_digest = hashlib.sha256(json.dumps(
                source_files, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            sidecar.write_text(json.dumps({'sha256': source_digest,
                                            'files': source_files}), encoding='utf-8')
            build.write_text(json.dumps({
                'kind': 'configured_engine_build',
                'state': 'built',
                'engine': str(engine),
                'compiled_source_sha256': source_digest,
                'source_inputs_sha256': file_hash(sidecar),
                'toolchain_record': {'sha256': file_hash(toolchain)},
                'toolchain': [{'path': sys.executable, 'sha256': file_hash(sys.executable)}],
            }), encoding='utf-8')
            generation.write_text('{"state":"generated","valid":true}', encoding='utf-8')
            self.assertEqual(bootstrap_existing.verify_build_inputs_receipt(build),
                             sidecar.resolve(strict=True))
            workspace = source / 'workspace.json'
            workspace.write_text(json.dumps({
                'engine': {'distribution': 'Ubuntu-20.04', 'path': str(root / 'fixed')},
                'configuration_engine': {'distribution': 'Ubuntu-20.04',
                    'path': str(engine), 'build_receipt': build_relative,
                    'generation_receipt': generation_relative},
            }), encoding='utf-8')
            with patch.object(bootstrap_existing, 'verify_engine'), \
                    patch.object(bootstrap_existing, '_verify_generated_outputs'), \
                    patch.object(bootstrap_existing, 'inspect_fu_capability', return_value={
                        'supported': True, 'build_verified': True,
                        'feature': 'salam_fu_scheduler_v1', 'reason': None}):
                result = bootstrap_existing.bootstrap_existing(workspace, project)
            self.assertEqual(result['state'], 'bound_existing')
            self.assertEqual((project / build_relative).read_bytes(), build.read_bytes())
            self.assertEqual((project / generation_relative).read_bytes(), generation.read_bytes())
            self.assertEqual((project / 'evidence/build/source-inputs.json').read_bytes(),
                             sidecar.read_bytes())
            self.assertEqual((project / 'evidence/toolchain.json').read_bytes(), toolchain.read_bytes())
            selected = json.loads((project / 'workspace.json').read_text())
            self.assertEqual(selected['configuration_engine']['path'], str(engine))
            with self.assertRaisesRegex(ValueError, 'new workbench binding'):
                bootstrap_existing.bootstrap_existing(workspace, project)

            saved = sidecar.with_name('source-inputs.saved.json')
            sidecar.rename(saved)
            missing_target = root / 'missing-target'
            missing_target.mkdir()
            with self.assertRaisesRegex(ValueError, 'missing or symlinked'), \
                    patch.object(bootstrap_existing, 'verify_engine'), \
                    patch.object(bootstrap_existing, '_verify_generated_outputs'), \
                    patch.object(bootstrap_existing, 'inspect_fu_capability'):
                bootstrap_existing.bootstrap_existing(workspace, missing_target)
            self.assertFalse((missing_target / 'workspace.json').exists())
            saved.rename(sidecar)
            sidecar.write_text('{"sha256":"corrupt","files":{}}', encoding='utf-8')
            corrupt_target = root / 'corrupt-target'
            corrupt_target.mkdir()
            with self.assertRaisesRegex(ValueError, 'sidecar differs'), \
                    patch.object(bootstrap_existing, 'verify_engine'), \
                    patch.object(bootstrap_existing, '_verify_generated_outputs'), \
                    patch.object(bootstrap_existing, 'inspect_fu_capability'):
                bootstrap_existing.bootstrap_existing(workspace, corrupt_target)
            self.assertFalse((corrupt_target / 'workspace.json').exists())


if __name__ == '__main__':
    unittest.main()
