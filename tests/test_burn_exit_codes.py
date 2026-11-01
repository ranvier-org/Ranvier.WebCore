import os
from pathlib import Path
import re
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
BASH = Path(r"C:/Program Files/Git/bin/bash.exe")


@unittest.skipUnless(os.name == "nt", "pinned mode launches Windows processes")
class BurnExitCodeTests(unittest.TestCase):
    def run_child(self, mode, value="", pinned=True):
        script = Path(os.environ.get("RANVIER_BURN_SCRIPT_UNDER_TEST", ROOT / "scripts" / "burn.sh"))
        environment = os.environ.copy()
        environment.update({
            "RANVIER_BURN_SCRIPT_UNDER_TEST": script.as_posix(),
            "BURN_PYTHON": sys.executable.replace("\\", "/"),
            "BURN_FIXTURE": (ROOT / "tests" / "fixtures" / "burn_exit_child.py").as_posix(),
            "BURN_MODE": mode,
            "BURN_VALUE": value,
            "BURN_PIN": "1" if pinned else "",
            "BURN_AFF": "3",
        })
        shell = (
            '. "$RANVIER_BURN_SCRIPT_UNDER_TEST"; '
            'PIN="$BURN_PIN"; AFF="$BURN_AFF"; '
            'pinned "$BURN_PYTHON" "$BURN_FIXTURE" "$BURN_MODE" "$BURN_VALUE"; '
            'status=$?; printf "STATUS=%s\\n" "$status"'
        )
        result = subprocess.run(
            [str(BASH), "--noprofile", "--norc", "-c", shell],
            capture_output=True,
            text=True,
            env=environment,
            timeout=15,
            check=False,
        )
        status = re.search(r"STATUS=(\d+)", result.stdout)
        self.assertIsNotNone(status, f"shell did not report child status: {result.stdout} {result.stderr}")
        return int(status.group(1)), result.stdout, result.stderr

    def test_pinned_mode_preserves_success_and_nonzero_exit_codes(self):
        for value in ("0", "7"):
            with self.subTest(child_exit=value):
                status, stdout, stderr = self.run_child("exit", value)
                self.assertEqual(status, int(value), stderr)
                self.assertIn(f"BURN_CHILD_EXIT_CODE={value}", stdout)

    def test_pinned_mode_preserves_unhandled_exception_exit(self):
        status, stdout, stderr = self.run_child("unhandled")
        self.assertEqual(status, 1, stderr)
        self.assertIn("BURN_CHILD_EXIT_CODE=1", stdout)

    def test_pinned_mode_preserves_crash_dword_and_nonzero_status(self):
        status, stdout, stderr = self.run_child("crash")
        self.assertNotEqual(status, 0, stderr)
        self.assertIn("BURN_CHILD_EXIT_CODE=3221225477", stdout)

    def test_pinned_mode_keeps_affinity_and_argument_boundaries(self):
        status, stdout, stderr = self.run_child("affinity", 'argument with spaces "quoted"')
        self.assertEqual(status, 0, stderr)
        self.assertIn("AFFINITY=3", stdout)
        self.assertIn('ARG=argument with spaces "quoted"', stdout)
        self.assertIn("BURN_CHILD_EXIT_CODE=0", stdout)

    def test_unpinned_mode_keeps_direct_child_exit_code(self):
        status, _, stderr = self.run_child("exit", "7", pinned=False)
        self.assertEqual(status, 7, stderr)


if __name__ == "__main__":
    unittest.main()
