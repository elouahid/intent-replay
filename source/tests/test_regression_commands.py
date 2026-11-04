"""Offline checks for exact packaged artifact command selection."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from scripts.serve_submission_demo import regression_command

ROOT = Path(__file__).resolve().parents[1]


class RegressionCommandTests(unittest.TestCase):
    def load(self, directory, case, provider):
        return json.loads((ROOT / directory / "prepared" / f"{case}-{provider}.json").read_text(encoding="utf-8"))

    def test_original_four_and_corrected_two_bind_exact_paths_and_hashes(self):
        for directory, providers in (("fresh_case_evidence", ("meta", "baseten")), ("repaired_live_proposal_evidence", ("meta",))):
            for case in ("fresh-withdrawal", "fresh-control"):
                for provider in providers:
                    with self.subTest(directory=directory, case=case, provider=provider):
                        prepared = self.load(directory, case, provider)
                        command = regression_command(prepared)
                        self.assertEqual(command["prepared_sha256"], prepared["sha256"])
                        self.assertEqual(command["powershell"], "python -B .\\scripts\\run_saved_regression.py --prepared .\\" + directory + "\\prepared\\" + case + "-" + provider + ".json")

    def test_changed_content_or_claimed_hash_offers_no_command(self):
        original = self.load("repaired_live_proposal_evidence", "fresh-withdrawal", "meta")
        for field in ("sha256", "capture"):
            modified = deepcopy(original)
            if field == "sha256":
                modified[field] = "0" * 64
            else:
                modified[field]["created_at"] = "changed"
            self.assertIsNone(regression_command(modified))

    def test_unknown_case_or_provider_cannot_select_a_path(self):
        original = self.load("repaired_live_proposal_evidence", "fresh-control", "meta")
        original["case"]["case_id"] = "../private"
        self.assertIsNone(regression_command(original))
        original = self.load("repaired_live_proposal_evidence", "fresh-control", "meta")
        original["capture"]["target"]["provider"] = "../private"
        self.assertIsNone(regression_command(original))


if __name__ == "__main__":
    unittest.main()
