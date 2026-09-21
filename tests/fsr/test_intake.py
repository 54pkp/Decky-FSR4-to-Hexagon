from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
if os.fspath(REPOSITORY) not in sys.path:
    sys.path.insert(0, os.fspath(REPOSITORY))

from tools.fsr.intake import FileRule, IntakeContract, IntakeError, run_intake


SUCCESS_EXTRACTOR = b'''from pathlib import Path
import json, os, zipfile
source = Path(os.environ["FIDELITYFX_SDK_ROOT"]) / "fixture" / "input.dat"
if source.read_bytes() != b"\\x01\\x02\\x03\\x04stable-marker":
    raise SystemExit(9)
out = Path(__file__).resolve().parents[1] / "artifacts"
out.mkdir()
with zipfile.ZipFile(out / "result.npz", "w") as archive:
    archive.writestr("array.npy", b"\\x93NUMPYfixture-array")
(out / "spec.json").write_text(json.dumps({"kind": "fixture-v1"}), encoding="utf-8")
'''

FAILURE_EXTRACTOR = b'''import sys
print("fixture extractor rejected its input", file=sys.stderr)
raise SystemExit(7)
'''

INVALID_OUTPUT_EXTRACTOR = b'''from pathlib import Path
import json
out = Path(__file__).resolve().parents[1] / "artifacts"
out.mkdir()
(out / "result.npz").write_bytes(b"not-an-archive")
(out / "spec.json").write_text(json.dumps({"kind": "wrong-fixture"}), encoding="utf-8")
'''


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class IntakeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.sdk = self.root / "sdk"
        self.asset = self.sdk / "fixture" / "input.dat"
        self.asset.parent.mkdir(parents=True)
        self.payload = b"\x01\x02\x03\x04stable-marker"
        self.asset.write_bytes(self.payload)
        self.extractor = self.root / "extractor.py"
        self.extractor.write_bytes(SUCCESS_EXTRACTOR)
        self.output = self.root / "published"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def contract(
        self,
        *,
        payload: bytes | None = None,
        payload_hash: str | None = None,
        marker: bytes = b"stable-marker",
        prefix: bytes = b"\x01\x02\x03\x04",
        extractor_payload: bytes = SUCCESS_EXTRACTOR,
    ) -> IntakeContract:
        expected = self.payload if payload is None else payload
        return IntakeContract(
            source_url="https://example.invalid/source",
            source_commit="source-commit",
            extractor_url="https://example.invalid/extractor",
            extractor_commit="extractor-commit",
            inputs=(
                FileRule(
                    "fixture/input.dat",
                    len(expected),
                    payload_hash or digest(expected),
                    (marker,),
                    prefix,
                ),
            ),
            extractor=FileRule(
                "extractor.py",
                len(extractor_payload),
                digest(extractor_payload),
            ),
            archive_name="result.npz",
            spec_name="spec.json",
            spec_markers=(("kind", "fixture-v1"),),
        )

    def execute(self, contract: IntakeContract):
        return run_intake(self.sdk, self.extractor, Path(sys.executable), self.output, contract)

    def test_success_publishes_only_validated_outputs_and_complete_receipt(self):
        receipt = self.execute(self.contract())
        self.assertEqual(
            {path.name for path in self.output.iterdir()},
            {"result.npz", "spec.json", "intake_receipt.json"},
        )
        saved = json.loads((self.output / "intake_receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(saved, receipt)
        self.assertEqual(saved["source"], {"url": "https://example.invalid/source", "commit": "source-commit"})
        self.assertEqual(saved["extractor"]["commit"], "extractor-commit")
        self.assertEqual(saved["inputs"][0]["sha256"], digest(self.payload))
        for name in ("result.npz", "spec.json"):
            data = (self.output / name).read_bytes()
            self.assertEqual(saved["outputs"][name]["byte_count"], len(data))
            self.assertEqual(saved["outputs"][name]["sha256"], digest(data))
        self.assertEqual(saved["device_execution"], "not_run")

    def test_truncated_input_is_rejected_without_output(self):
        self.asset.write_bytes(self.payload[:-1])
        with self.assertRaisesRegex(IntakeError, "size mismatch"):
            self.execute(self.contract())
        self.assertFalse(self.output.exists())

    def test_wrong_hash_is_rejected_without_output(self):
        with self.assertRaisesRegex(IntakeError, "SHA-256 mismatch"):
            self.execute(self.contract(payload_hash="0" * 64))
        self.assertFalse(self.output.exists())

    def test_wrong_version_marker_is_rejected_without_output(self):
        with self.assertRaisesRegex(IntakeError, "version/content marker"):
            self.execute(self.contract(marker=b"different-version"))
        self.assertFalse(self.output.exists())

    def test_byte_swapped_prefix_is_rejected_before_extraction(self):
        swapped = b"\x04\x03\x02\x01" + self.payload[4:]
        self.asset.write_bytes(swapped)
        with self.assertRaisesRegex(IntakeError, "byte-order/version prefix"):
            self.execute(self.contract())
        self.assertFalse(self.output.exists())

    def test_existing_output_is_never_overwritten(self):
        self.output.mkdir()
        sentinel = self.output / "keep.txt"
        sentinel.write_text("keep", encoding="utf-8")
        with self.assertRaisesRegex(IntakeError, "already exists"):
            self.execute(self.contract())
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")

    def test_extractor_failure_does_not_publish_output(self):
        self.extractor.write_bytes(FAILURE_EXTRACTOR)
        with self.assertRaisesRegex(IntakeError, "exit code 7"):
            self.execute(self.contract(extractor_payload=FAILURE_EXTRACTOR))
        self.assertFalse(self.output.exists())

    def test_invalid_extractor_outputs_are_not_published(self):
        self.extractor.write_bytes(INVALID_OUTPUT_EXTRACTOR)
        with self.assertRaisesRegex(IntakeError, "valid NPZ/ZIP"):
            self.execute(self.contract(extractor_payload=INVALID_OUTPUT_EXTRACTOR))
        self.assertFalse(self.output.exists())

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_symlinked_input_is_rejected_when_creation_is_permitted(self):
        real = self.root / "real.dat"
        real.write_bytes(self.payload)
        self.asset.unlink()
        try:
            os.symlink(real, self.asset)
        except OSError as exc:
            self.skipTest(f"symlink creation unavailable: {exc}")
        with self.assertRaisesRegex(IntakeError, "symlink or reparse"):
            self.execute(self.contract())
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
