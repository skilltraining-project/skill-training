"""Exercise the public module entry point without calling a model."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestCLI(unittest.TestCase):
    def command(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "skilltrain", *args], cwd=ROOT,
            capture_output=True, text=True, timeout=15, check=False,
        )

    def test_top_level_help_and_no_arguments(self):
        for args in [(), ("--help",)]:
            with self.subTest(args=args):
                result = self.command(*args)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("python -m skilltrain", result.stdout)
                self.assertIn("Run or resume the complete training loop", result.stdout)

    def test_all_stage_help_uses_public_command(self):
        for command, option in {
            "prepare": "--text", "diffuse": "--noise", "forward": "--pool",
            "loss": "--scripts", "backward": "--batch", "train": "--init-pool",
        }.items():
            with self.subTest(command=command):
                result = self.command(command, "--help")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f"python -m skilltrain {command}", result.stdout)
                self.assertIn(option, result.stdout)

    def test_invalid_command_and_stage_arguments_fail(self):
        for args in [("unknown",), ("train",), ("prepare", "--unknown")]:
            with self.subTest(args=args):
                result = self.command(*args)
                self.assertEqual(result.returncode, 2)
                self.assertIn("error:", result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def test_prepare_writes_episodes_through_public_command(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.txt"
            work = Path(directory) / "example"
            source.write_text("\n\n".join(
                f"INT. ROOM {n} - DAY\nA visitor enters and sits down."
                for n in range(1, 9)
            ), encoding="utf-8")
            result = self.command(
                "prepare", "--text", str(source), "--work", str(work), "--episodes", "2",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            episodes = sorted((work / "human").glob("*.txt"))
            self.assertEqual([p.name for p in episodes], ["ep01.txt", "ep02.txt"])
            self.assertTrue(episodes[0].read_text().startswith("EP 1\n"))
            self.assertIn("ROOM 8", episodes[1].read_text())
