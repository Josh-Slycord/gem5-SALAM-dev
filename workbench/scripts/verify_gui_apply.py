"""Exercise actual Qt controls and QProcess against the real local backend.

Linux offscreen uses native Python instead of the Windows WSL launcher. The
request, generation, compiler, simulator and receipt checks are the same code.
This is an explicit integration run, never part of cheap unit-test discovery.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
os.environ["SALAM_WORKBENCH_ROOT"] = str(PROJECT)

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QFormLayout, QMessageBox, QWidget
from salam_workbench.runner import file_hash
from salam_workbench.gui_editor_qt import MODEL_FIELDS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=('runtime', 'cold', 'reuse', 'invalid-profile', 'renamed-cluster', 'fu-capacity'), required=True)
    parser.add_argument('--production-command', action='store_true', help='Use GUI production native command and its automatic evidence directory')
    parser.add_argument('--evidence-dir', required=True)
    parser.add_argument('--timeout', type=float, default=7200)
    args = parser.parse_args()
    evidence = Path(args.evidence_dir).resolve()
    evidence.mkdir(parents=True, exist_ok=False)
    backend_evidence = evidence / 'execution'
    manifest = json.loads((PROJECT / 'workspace.json').read_text(encoding='utf-8-sig'))
    engine = Path(manifest['configuration_engine']['path'])
    sys.path.insert(0, str(engine / 'gem5-SALAM-gui/src'))
    from gui.config_generator import ConfigGeneratorDialog

    app = QApplication.instance() or QApplication([])
    messages = []
    QMessageBox.information = lambda *values: messages.append({'kind': 'information', 'title': str(values[1]), 'text': str(values[2])})
    QMessageBox.warning = lambda *values: messages.append({'kind': 'warning', 'title': str(values[1]), 'text': str(values[2])})
    parent = QWidget()
    parent.wsl_status = type('WSLStatus', (), {'get_selected_distro': lambda self: manifest['configuration_engine']['distribution']})()
    dialog = ConfigGeneratorDialog(engine, parent)
    index = dialog.benchmark_combo.findData('gemm')
    if index < 0:
        raise ValueError('Actual GUI did not discover GEMM')
    dialog.benchmark_combo.setCurrentIndex(index)
    if dialog._base_document is None:
        raise ValueError('Actual GUI did not load source YAML')

    def component(name):
        for i in range(dialog.component_tree.topLevelItemCount()):
            item = dialog.component_tree.topLevelItem(i)
            if item.text(0) == name:
                dialog.component_tree.setCurrentItem(item)
                return item
        raise ValueError('Missing actual component widget: ' + name)

    def detail(label):
        for row in range(dialog.details_layout.rowCount()):
            name = dialog.details_layout.itemAt(row, QFormLayout.LabelRole)
            value = dialog.details_layout.itemAt(row, QFormLayout.FieldRole)
            if name and value and name.widget().text() == label:
                return value.widget()
        raise ValueError('Missing actual detail widget: ' + label)

    component('dma')
    detail('Max Request Size:').setValue(32)
    detail('Buffer Size:').setValue(256)
    component('MATRIX1')
    detail('Size (bytes):').setValue(16384)
    detail('Ports:').setValue(3)
    dialog.base_addr_edit.setText('0x10320000')
    if args.case == 'renamed-cluster':
        dialog.cluster_name_edit.setText('research_clstr')
        dialog.base_addr_edit.setText('0x10420000')
    dialog.mem_size_edit.setText('2GB')
    dialog.mem_type_edit.setText('DDR3_1600_8x8')
    dialog.cpu_clock_edit.setText('1GHz')
    dialog.sys_clock_edit.setText('500MHz')
    dialog.hardware_target_combo.setCurrentText('gemm')
    for i in range(dialog.inst_tree.topLevelItemCount()):
        row = dialog.inst_tree.topLevelItem(i)
        if row.text(0) == 'mul':
            row.setText(1, '16' if args.case == 'fu-capacity' else '3')
            break
    else:
        raise ValueError('Actual GUI did not expose multiply instruction')
    if args.case == 'fu-capacity':
        for i in range(dialog.fu_tree.topLevelItemCount()):
            row = dialog.fu_tree.topLevelItem(i)
            if row.text(0) == 'integer_multiplier':
                row.setText(1, '0')
                row.setText(2, '1')
                break
        else:
            raise ValueError('Actual GUI did not expose multiplier capacity')
    if args.case in ('cold', 'reuse'):
        for i in range(dialog.model_tree.topLevelItemCount()):
            row = dialog.model_tree.topLevelItem(i)
            if row.text(0) == 'integer_multiplier':
                row.setText(MODEL_FIELDS.index('internal_power') + 1, '0.0125')
                row.setText(MODEL_FIELDS.index('area') + 1, '7.25')
                break
        else:
            raise ValueError('Actual GUI did not expose multiplier model')
    if args.case == 'invalid-profile':
        dialog.cycle_time_combo.setCurrentText('10ns')

    if not args.production_command:
        dialog._backend_command_provider = lambda request: ('/usr/bin/python3.8', [
            '-B', '-m', 'salam_workbench.gui_execution', '--request-stdin',
            '--evidence-dir', str(backend_evidence)])
    exported = dialog._make_request()
    (evidence / 'widget-export.json').write_text(json.dumps(exported, indent=2) + '\n')
    (evidence / 'integration-driver.py').write_bytes(Path(__file__).read_bytes())
    timer_ticks = [0]
    ticker = QTimer()
    ticker.timeout.connect(lambda: timer_ticks.__setitem__(0, timer_ticks[0] + 1))
    ticker.start(100)
    dialog.resize(1700, 1100)
    dialog.show()
    dialog.tabs.setCurrentIndex(2)
    app.processEvents()
    dialog.grab().save(str(evidence / 'edited-form.png'))
    started = time.monotonic()
    dialog.generate_btn.click()
    disabled_during_launch = not dialog.generate_btn.isEnabled()
    while dialog._gui_process is not None:
        app.processEvents()
        if time.monotonic() - started > args.timeout:
            raise RuntimeError('Actual GUI backend did not finish within timeout')
        time.sleep(0.02)
    app.processEvents()
    ticker.stop()
    dialog.tabs.setCurrentIndex(3)
    app.processEvents()
    dialog.grab().save(str(evidence / 'finished-form.png'))
    (evidence / 'gui-log.txt').write_text(dialog.validation_output.toPlainText())
    summary = dialog._gui_summary
    if args.production_command and isinstance(summary, dict) and summary.get('evidence_directory'):
        backend_evidence = Path(summary['evidence_directory'])
    actual = json.loads((backend_evidence / 'gui-execution.json').read_text()) if (backend_evidence / 'gui-execution.json').is_file() else None
    record = {'kind': 'actual_qt_form_integration', 'case': args.case,
              'transport': 'Native Linux QProcess instead of Windows WSL launcher; real same Python backend',
              'actual_qt_widgets_edited': True, 'actual_button_clicked': True,
              'production_command_provider': args.production_command,
              'backend_results_mocked': False, 'event_loop_ticks': timer_ticks[0],
              'button_disabled_during_launch': disabled_during_launch,
              'button_enabled_after_finish': dialog.generate_btn.isEnabled(),
              'elapsed_seconds': time.monotonic() - started,
              'summary': summary, 'message_boxes': messages,
              'execution_receipt': str(backend_evidence / 'gui-execution.json'),
              'driver_sha256': file_hash(evidence / 'integration-driver.py')}
    expected = 'failed' if args.case == 'invalid-profile' else 'passed'
    errors = []
    if not isinstance(summary, dict) or summary.get('state') != expected:
        errors.append('GUI summary did not match expected ' + expected)
    if actual is None or actual.get('state') != expected:
        errors.append('Durable backend receipt did not match expected ' + expected)
    if not disabled_during_launch or not dialog.generate_btn.isEnabled() or timer_ticks[0] < 1:
        errors.append('Asynchronous GUI responsiveness checks failed')
    if args.case in ('cold', 'reuse') and actual:
        expected_hardware = 'built' if args.case == 'cold' else 'reused'
        if actual.get('hardware', {}).get('state') != expected_hardware:
            errors.append('Hardware path was not ' + expected_hardware)
    if expected == 'passed' and not any(m['kind'] == 'information' for m in messages):
        errors.append('GUI did not independently accept saved passing receipt')
    if expected == 'failed' and not any(m['kind'] == 'warning' for m in messages):
        errors.append('GUI did not display the rejection')
    if args.case == 'fu-capacity' and actual and actual.get('state') == 'passed':
        pipeline_root = backend_evidence / 'pipeline'
        witness = json.loads((pipeline_root / 'fu-scheduling-witness.json').read_text())
        if witness.get('state') != 'passed':
            errors.append('Direct FU scheduling replay did not pass')
        traces = list((Path(actual['run_directory']) / 'simulator/observability').glob('fu-scheduling-*.gemm.invocation-1.json'))
        if len(traces) != 1:
            errors.append('Expected one real GEMM scheduling trace')
        else:
            trace = json.loads(traces[0].read_text())
            unit = next(u for u in trace['units'] if u['name'] == 'integer_multiplier')
            record['multiplier_scheduling'] = unit
            if not (unit['limit'] == 1 and unit['peak'] == 1 and unit['denials'] > 0
                    and unit['grants'] == unit['releases'] > 0 and unit['outstanding'] == 0):
                errors.append('GUI capacity did not constrain actual multiply scheduling')
    record.update(state='passed' if not errors else 'failed', issues=errors)
    (evidence / 'qt-integration.json').write_text(json.dumps(record, indent=2) + '\n')
    dialog.close()
    parent.close()
    print(json.dumps({'state': record['state'], 'evidence_directory': str(evidence), 'issues': errors}))
    return 0 if not errors else 1


if __name__ == '__main__':
    raise SystemExit(main())
