"""Request validation/failure receipts; fixture programs are not simulations."""
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import yaml

from salam_workbench.gui_editor import build_gui_request, extract_components
from salam_workbench.gui_execution import (
    _summarize_fu_witness,
    apply_request,
    read_request,
    validate_request,
)
from salam_workbench.runner import file_hash


class GuiExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.engine = self.project / "independent-engine"
        self.source = self.engine / "benchmarks/suite/example/config.yml"
        self.source.parent.mkdir(parents=True)
        self.base = {
            "acc_cluster": [
                {"Name": "example_clstr"},
                {
                    "DMA": [
                        {
                            "Name": "dma",
                            "Type": "NonCoherent",
                            "MaxReqSize": 64,
                            "BufferSize": 128,
                        }
                    ]
                },
                {
                    "Accelerator": [
                        {
                            "Name": "example",
                            "IrPath": "benchmarks/suite/example/hw/example.ll",
                            "PIOSize": 1,
                        }
                    ]
                },
            ],
            "hw_config": {"example": None},
        }
        self.source.write_text(yaml.safe_dump(self.base))
        (self.project / "workspace.json").write_text(
            json.dumps(
                {
                    "configuration_engine": {
                        "path": str(self.engine),
                        "distribution": "fixture-distro",
                    }
                }
            )
        )
        cluster, components = extract_components(self.base)
        self.snapshot = {
            "cluster_name": cluster,
            "components": components,
            "hardware_by_accelerator": {},
            "alignment": 64,
            "base_address": "0x10320000",
            "system": {"mem-size": "2GB", "cpu-clock": "1GHz"},
            "hardware_profile": {
                "model": "40nm_model",
                "period": "5ns",
                "profile": "default_profile",
                "fu_overrides": {},
            },
        }
        self.request = build_gui_request(
            self.base,
            self.snapshot,
            benchmark="benchmarks/suite/example",
            engine_root=str(self.engine),
            distro="fixture-distro",
            source_config_relative="benchmarks/suite/example/config.yml",
            source_config_sha256=file_hash(self.source),
        )

    def test_duplicate_nonfinite_oversized_json_rejected(self):
        for text in (
            '{"a":1,"a":2}',
            '{"a":NaN}',
            " " * (2 * 1024 * 1024 + 1),
        ):
            with self.assertRaises(ValueError):
                read_request(text)

    def test_live_widget_snapshot_is_required_and_cannot_be_substituted(self):
        engine, _, source = validate_request(self.request, self.project)
        self.assertEqual(engine, self.engine)
        self.assertEqual(source, self.source)
        modified = deepcopy(self.request)
        modified["configuration_documents"][0]["acc_cluster"][1]["DMA"][0][
            "BufferSize"
        ] = 256
        with self.assertRaisesRegex(ValueError, "widget snapshot"):
            validate_request(modified, self.project)

    def test_stale_yaml_and_wrong_engine_cannot_apply(self):
        changed = deepcopy(self.request)
        changed["engine_root"] = str(self.project)
        with self.assertRaisesRegex(ValueError, "independent"):
            validate_request(changed, self.project)
        self.source.write_text("# changed\n")
        with self.assertRaisesRegex(ValueError, "reload"):
            validate_request(self.request, self.project)

    def test_failed_gui_request_has_receipt_before_any_build_or_run(self):
        changed = deepcopy(self.request)
        changed["configuration_documents"] = []
        with patch("salam_workbench.gui_execution.run_configuration") as run:
            result = apply_request(
                changed,
                project=self.project,
                evidence_dir=self.project / "evidence",
            )
        run.assert_not_called()
        self.assertEqual(result["state"], "failed")
        self.assertFalse(result["editor_form_applied"])
        saved = json.loads((self.project / "evidence/gui-execution.json").read_text())
        self.assertEqual(saved["state"], "failed")
        self.assertEqual(
            file_hash(self.source),
            self.request["provenance"]["source_config"]["sha256"],
        )

    def test_fu_telemetry_summarizes_only_complete_validated_direct_trace(
        self,
    ):
        unit = {
            "name": "integer_multiplier",
            "limit": 1,
            "attempts": 8,
            "grants": 2,
            "denials": 6,
            "releases": 2,
            "peak": 1,
            "outstanding": 0,
        }
        witness = {
            "state": "passed",
            "invocations": [
                {
                    "state": "passed",
                    "path": "/evidence/fu-scheduling-system.c.a.invocation-1.json",
                    "source_sha256": "a" * 64,
                    "trace": {
                        "state": "passed",
                        "trace_complete": True,
                        "units": [
                            unit,
                            {
                                "name": "unused",
                                "limit": 0,
                                "attempts": 0,
                                "grants": 0,
                                "denials": 0,
                                "releases": 0,
                                "peak": 0,
                                "outstanding": 0,
                            },
                        ],
                    },
                }
            ],
        }
        summary = _summarize_fu_witness(witness)
        self.assertEqual(summary["state"], "validated_direct_salam_trace")
        self.assertEqual(summary["invocations"][0]["accelerator"], "system.c.a")
        self.assertEqual(summary["invocations"][0]["units"], [unit])
        witness["invocations"][0]["trace"]["trace_complete"] = False
        with self.assertRaisesRegex(ValueError, "complete validated replay"):
            _summarize_fu_witness(witness)
