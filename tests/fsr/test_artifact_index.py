from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
if os.fspath(REPOSITORY) not in sys.path:
    sys.path.insert(0, os.fspath(REPOSITORY))

from tools.fsr.artifact_index import (
    INDEX_PATH,
    MAX_INDEX_BYTES,
    ArtifactIndexError,
    classify_receipt,
    current_artifact,
    load_artifact_index,
)


CURRENT_P7 = "b791639c857af05a90ee6fefd492f310f472338265cdab4ae077203d4139d38b"
CURRENT_P8 = "2a4c3960304dd19a2c00d70bcbe1309fad23b19017638250e15ce2263cbf8ede"
HISTORICAL_ZERO_LSB_P8 = "4170b2824a5242b1bdfaac6bb39fbc06e23963e323e568f26bdbc5113a7769b6"
HISTORICAL_ONE_LSB_P8 = "67e80e4f030165995167b974016ef77fd76757bdce6a2164579ffac72f213f33"


class ArtifactIndexTests(unittest.TestCase):
    def setUp(self) -> None:
        self.index = load_artifact_index(INDEX_PATH)

    def write_and_load(self, value):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "artifact-index.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            return load_artifact_index(path)

    def test_repository_index_selects_only_current_receipts_by_digest(self):
        p7 = current_artifact(self.index, "p7-receipt")
        p8 = current_artifact(self.index, "p8-receipt")
        self.assertEqual(CURRENT_P7, p7["receipt_sha256"])
        self.assertEqual(CURRENT_P8, p8["receipt_sha256"])
        self.assertEqual(CURRENT_P7, p8["p7_receipt_sha256"])
        self.assertEqual(0, p8["max_int8_lsb_difference"])
        self.assertEqual("accepted-current", p7["classification"])
        self.assertEqual("accepted-current", p8["classification"])

        old_zero = classify_receipt(self.index, "p8-receipt", HISTORICAL_ZERO_LSB_P8)
        old_one = classify_receipt(self.index, "p8-receipt", HISTORICAL_ONE_LSB_P8)
        self.assertEqual("historical-stale", old_zero["classification"])
        self.assertEqual(0, old_zero["max_int8_lsb_difference"])
        self.assertEqual("historical-stale", old_one["classification"])
        self.assertEqual(1, old_one["max_int8_lsb_difference"])
        self.assertNotEqual(CURRENT_P8, old_one["receipt_sha256"])
        self.assertTrue(
            any(entry["classification"] == "audit-temporary" for entry in self.index["artifacts"])
        )

    def test_unknown_receipt_and_kind_are_not_selected(self):
        with self.assertRaisesRegex(ArtifactIndexError, "not uniquely classified"):
            classify_receipt(self.index, "p8-receipt", "0" * 64)
        with self.assertRaisesRegex(ArtifactIndexError, "unknown artifact kind"):
            current_artifact(self.index, "weights")

    def test_closed_schema_rejects_unknown_missing_duplicate_and_bad_values(self):
        cases = []

        value = copy.deepcopy(self.index)
        value["unknown"] = True
        cases.append((value, "unknown field"))
        value = copy.deepcopy(self.index)
        del value["artifacts"][0]["note"]
        cases.append((value, "missing field"))
        value = copy.deepcopy(self.index)
        value["artifacts"][1]["artifact_id"] = value["artifacts"][0]["artifact_id"]
        cases.append((value, "duplicate artifact_id"))
        value = copy.deepcopy(self.index)
        value["artifacts"][1]["receipt_sha256"] = value["artifacts"][0]["receipt_sha256"]
        cases.append((value, "duplicate p7-receipt receipt SHA-256"))
        value = copy.deepcopy(self.index)
        value["artifacts"][0]["receipt_sha256"] = "A" * 64
        cases.append((value, "lowercase SHA-256"))
        value = copy.deepcopy(self.index)
        value["artifacts"][0]["classification"] = "current-ish"
        cases.append((value, "classification is invalid"))
        value = copy.deepcopy(self.index)
        value["artifacts"][0]["p7_receipt_sha256"] = "0" * 64
        cases.append((value, "P7 linkage/tolerance fields must be null"))

        for value, diagnostic in cases:
            with self.subTest(diagnostic=diagnostic):
                with self.assertRaisesRegex(ArtifactIndexError, diagnostic):
                    self.write_and_load(value)

        for field in ("kind", "classification"):
            for invalid in ([], {}, True, None):
                with self.subTest(field=field, invalid=invalid):
                    value = copy.deepcopy(self.index)
                    value["artifacts"][0][field] = invalid
                    with self.assertRaisesRegex(ArtifactIndexError, f"{field} is invalid"):
                        self.write_and_load(value)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text('{"schema_version":"a","schema_version":"b","artifacts":[]}', encoding="utf-8")
            with self.assertRaisesRegex(ArtifactIndexError, "duplicate object key"):
                load_artifact_index(path)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "oversized.json"
            path.write_bytes(b" " * (MAX_INDEX_BYTES + 1))
            with self.assertRaisesRegex(ArtifactIndexError, "exceeds .* byte limit"):
                load_artifact_index(path)

    def test_current_selection_and_p8_trust_link_are_unambiguous(self):
        cases = []
        value = copy.deepcopy(self.index)
        value["artifacts"][1]["classification"] = "accepted-current"
        cases.append((value, "exactly one accepted-current p7-receipt"))
        value = copy.deepcopy(self.index)
        current_p8 = next(
            entry for entry in value["artifacts"] if entry["artifact_id"] == "p8-r10b-20260922"
        )
        current_p8["p7_receipt_sha256"] = "0" * 64
        cases.append((value, "must bind the accepted-current P7 digest"))
        value = copy.deepcopy(self.index)
        current_p8 = next(
            entry for entry in value["artifacts"] if entry["artifact_id"] == "p8-r10b-20260922"
        )
        current_p8["max_int8_lsb_difference"] = 1
        cases.append((value, "must have zero-LSB tolerance"))
        value = copy.deepcopy(self.index)
        current_p7 = next(
            entry for entry in value["artifacts"] if entry["artifact_id"] == "p7-r10a-20260922"
        )
        current_p7["receipt_schema"] = "p7-fsr-intake-receipt-v1"
        cases.append((value, "must use the R10a v2"))

        for value, diagnostic in cases:
            with self.subTest(diagnostic=diagnostic):
                with self.assertRaisesRegex(ArtifactIndexError, diagnostic):
                    self.write_and_load(value)


if __name__ == "__main__":
    unittest.main()
