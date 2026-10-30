import unittest

from salam_workbench.observability_report import render_observability


class ObservationReportTests(unittest.TestCase):
    def fixture(self, valid=True):
        return {"directory": "/synthetic", "correctness_verified": valid,
                "observability": {"status": "valid", "valid": True, "records": [{
                    "identity": {"accelerator": "<accelerator>", "invocation": 1},
                    "contract_valid": True,
                    "artifact_path": "simulator/observability/function.json",
                    "provenance": {"hash_verified": True, "sha256": "a" * 64},
                    "metrics": {
                        "lifecycle.elapsed_ticks": {"value": 860340000, "unit": "tick",
                                                    "availability": "observed"},
                        "memory.reads.completed": {"value": 1973, "unit": "request",
                                                   "availability": "observed"},
                        "memory.reads.completed_bytes": {"value": 4096, "unit": "byte",
                                                         "availability": "observed"},
                        "execution.selected_commits_total": {"value": 500, "unit": "commit",
                                                             "availability": "observed"},
                        "queues.sample_count": {"value": 100, "unit": "sample",
                                                "availability": "observed"},
                        "queues.reservation.mean": {"value": "2.7886010529", "unit": "queue_entry",
                                                    "availability": "observed",
                                                    "derivation": {"exact_ratio": "27886/10000"}},
                        "memory.reads.latency_ticks.mean": {"value": "111993.693693693",
                                                            "unit": "tick",
                                                            "availability": "observed"},
                    },
                    "unsupported": {"power": {"reason": "no characterized model"}}
                }]}}

    def test_verified_values_units_and_escaped_identity(self):
        text = render_observability(self.fixture(), "/report")
        self.assertIn("<td>1973</td>", text)
        self.assertIn("<td>request</td>", text)
        self.assertIn("&lt;accelerator&gt;", text)
        self.assertIn("no characterized model", text)

    def test_grouped_overview_and_exact_detail(self):
        text = render_observability(self.fixture(), "/report")
        for heading in ("Lifecycle", "Logical memory", "Selected commits", "Queues and latency"):
            self.assertIn("<h5>" + heading + "</h5>", text)
        self.assertIn("860,340,000", text)
        self.assertIn("1,973", text)
        self.assertIn("≈2.79", text)
        self.assertIn("≈111,993.69", text)
        self.assertIn("2.7886010529", text)
        self.assertIn("exact ratio 27886/10000", text)
        self.assertIn('All recorded metrics, units, and definitions', text)

    def test_raw_json_link_and_verified_hash(self):
        text = render_observability(self.fixture(), "/report")
        self.assertIn('href="../synthetic/simulator/observability/function.json"', text)
        self.assertIn("Verified SHA-256 <code>" + "a" * 64 + "</code>", text)
        self.assertIn("not cache hits", text)
        self.assertIn("not time weighted", text)

    def test_unverified_run_does_not_present_numeric_cell(self):
        text = render_observability(self.fixture(False), "/report")
        self.assertNotIn("<td>1973</td>", text)
        self.assertNotIn("1,973", text)
        self.assertNotIn("2.7886010529", text)
        self.assertIn("<td>unknown</td>", text)
        self.assertIn("Hash or record unverified", text)

    def test_unavailable_and_nonfinite_values_stay_unknown(self):
        run = self.fixture()
        metrics = run["observability"]["records"][0]["metrics"]
        metrics["memory.reads.completed"] = {"value": 1973, "unit": "request",
                                             "availability": "unavailable"}
        metrics["queues.reservation.mean"]["value"] = "NaN"
        text = render_observability(run, "/report")
        self.assertNotIn("<td>1973</td>", text)
        self.assertNotIn("1,973", text)
        self.assertNotIn("2.7886010529", text)
        self.assertIn("<td>unknown</td>", text)

    def test_top_controller_label(self):
        run = self.fixture()
        run["observability"]["records"][0]["identity"]["accelerator"] = "system.fft_clstr.top"
        self.assertIn("Top controller", render_observability(run, "/report"))

    def test_historical_missing_contract_is_unknown(self):
        text = render_observability({"observability": {"status": "unavailable"}}, "/report")
        self.assertIn("no versioned observability contract", text)


if __name__ == "__main__":
    unittest.main()
