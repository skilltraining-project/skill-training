"""Everything that can be checked without calling a model.

    python -m unittest discover tests

Covers the parts that would otherwise only fail halfway through a training run:
the linter, the pool's git repo, prompt rendering, chapter extraction, and
stream-json parsing.
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import s0_prepare_data  # noqa: E402
import s2_forward  # noqa: E402
import s4_backward  # noqa: E402
import s5_train  # noqa: E402
from skilltrain import dataset, memory, prompts, run, trajectory  # noqa: E402

GOOD = """---
description: Use when two characters argue about something small and mean something large. Not for lines that only deliver facts.
---

## Rules
Route the real feeling through a concrete complaint.
"""


class TempCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def pool(self) -> Path:
        pool = self.tmp / "memory"
        memory.init(pool, self.tmp / "lint.txt")
        return pool

    def write(self, pool: Path, name: str, text: str) -> Path:
        path = pool / "01_craft_elements" / name
        path.write_text(text, encoding="utf-8")
        return path


class TestLinter(TempCase):
    def test_accepts_a_well_formed_entry(self):
        pool = self.pool()
        self.write(pool, "subtext.md", GOOD)
        self.assertEqual(memory.lint(pool, self.tmp / "r.txt"), 0)

    def test_rejects_missing_frontmatter(self):
        problems = memory.lint_entry(self.write(self.pool(), "a.md", "## Rules\nhi\n"))
        self.assertTrue(any("frontmatter" in p for p in problems))

    def test_rejects_extra_frontmatter_fields(self):
        entry = GOOD.replace("---\n\n## Rules", "used_count: 7\n---\n\n## Rules")
        problems = memory.lint_entry(self.write(self.pool(), "a.md", entry))
        self.assertTrue(any("only contain `description`" in p for p in problems))

    def test_rejects_second_heading(self):
        problems = memory.lint_entry(
            self.write(self.pool(), "a.md", GOOD + "\n## Examples\nnope\n"))
        self.assertTrue(any("exactly one heading" in p for p in problems))

    def test_rejects_oversized_body(self):
        entry = GOOD + "x" * (memory.MAX_BODY_CHARS + 1)
        problems = memory.lint_entry(self.write(self.pool(), "a.md", entry))
        self.assertTrue(any("body is" in p for p in problems))

    def test_rejects_episode_references_and_postmortem_prose(self):
        for bad in ("In EP 3 the hook lands late.",
                    "The model's version front-loads exposition."):
            problems = memory.lint_entry(self.write(self.pool(), "a.md", GOOD + bad))
            self.assertTrue(problems, f"should have been rejected: {bad}")

    def test_rejects_stray_files_and_nested_folders(self):
        pool = self.pool()
        (pool / "notes.md").write_text("loose\n", encoding="utf-8")
        (pool / "01_craft_elements" / "deep").mkdir()
        problems = memory.lint_layout(pool)
        self.assertTrue(any("nothing goes in the pool root" in p for p in problems))
        self.assertTrue(any("no nested folders" in p for p in problems))

    def test_report_may_not_live_inside_the_pool(self):
        pool = self.pool()
        with self.assertRaises(ValueError):
            memory.lint(pool, pool / "lint.txt")


class TestPoolGit(TempCase):
    def test_init_is_idempotent_and_leaves_a_clean_repo(self):
        pool = self.pool()
        first = memory.head(pool)
        memory.init(pool, self.tmp / "lint.txt")
        self.assertEqual(memory.head(pool), first)
        self.assertTrue(memory.is_clean(pool))

    def test_pre_commit_hook_blocks_a_malformed_entry(self):
        pool = self.pool()
        self.write(pool, "broken.md", "no frontmatter here\n")
        memory.git(pool, "add", "-A")
        proc = memory.git(pool, "commit", "-m", "should fail", capture=True)
        self.assertNotEqual(proc.returncode, 0)
        # Assert on the reason, not just the failure: a commit that fails for an
        # unrelated reason would otherwise look like the hook doing its job.
        self.assertIn("MEMORY_LINT_FAILED", proc.stdout + proc.stderr)

    def test_reset_discards_uncommitted_entries(self):
        pool = self.pool()
        before = memory.head(pool)
        self.write(pool, "scratch.md", GOOD)
        memory.reset(pool, before)
        self.assertFalse((pool / "01_craft_elements" / "scratch.md").exists())
        self.assertTrue(memory.is_clean(pool))
        # `git clean` deletes folders it empties; the layout still needs them.
        self.assertEqual(memory.lint_layout(pool), [])

    def test_headers_show_descriptions_not_bodies(self):
        pool = self.pool()
        self.write(pool, "subtext.md", GOOD)
        text = memory.headers(pool)
        self.assertIn("01_craft_elements/subtext.md", text)
        self.assertIn("Use when two characters argue", text)
        self.assertNotIn("Route the real feeling", text)


class TestPrompts(unittest.TestCase):
    def test_every_template_renders(self):
        slots = {
            "diffuse_heavy": dict(episode_number=1, screenplay="INT. ROOM - DAY"),
            "diffuse_light": dict(episode_number=1, screenplay="INT. ROOM - DAY"),
            "forward": dict(episode_range="1-5", episode_count=5, pool_dir="/p",
                            memory_headers="none", output_paths="- /a", story_path="/s",
                            chapters="# Chapter 1"),
            "loss": dict(work="w", episode_range="1-5", human_scripts="h",
                         model_scripts="m"),
            "memory_policy": dict(folder_guide="g", body_heading="## Rules",
                                  max_lines=50, max_body_chars=4800,
                                  max_description_chars=800),
            "reduce": dict(n=2, reports_section="## a\n\nr"),
            "backward": dict(pool_dir="/p", batch_section="b",
                             memory_headers="h", lint_section="l", memory_policy="p",
                             folder_add_targets="a b", commit_subject="s",
                             commit_body="c"),
        }
        for name, values in slots.items():
            self.assertIn("{{", (prompts.PROMPT_DIR / f"{name}.md").read_text())
            self.assertNotIn("{{", prompts.render(name, **values))

    def test_a_missing_slot_is_an_error(self):
        with self.assertRaises(KeyError):
            prompts.render("loss", work="w")


class TestPolicyExample(TempCase):
    def test_the_example_entry_passes_the_linter_it_teaches(self):
        """The optimizer copies the shape of this example, so it has to be legal.

        It was not: the description was wrapped onto three lines, which the
        frontmatter parser rejects. Every entry the optimizer wrote from it
        would have been refused at commit time, with nothing explaining why.
        """
        policy = (prompts.PROMPT_DIR / "memory_policy.md").read_text(encoding="utf-8")
        found = re.search(r"```\n01_craft_elements/(\S+)\n\n(---\n.*?)\n```",
                          policy, re.S)
        self.assertIsNotNone(found, "the example entry is gone from memory_policy.md")
        pool = self.pool()
        (pool / "01_craft_elements" / found.group(1)).write_text(
            found.group(2) + "\n", encoding="utf-8")
        self.assertEqual(memory.lint(pool, self.tmp / "r.txt"), 0)


class TestDataset(TempCase):
    def build(self) -> dataset.Work:
        work = dataset.Work(root=self.tmp / "example")
        work.human_dir.mkdir(parents=True)
        for n in (1, 2, 3):
            (work.human_dir / f"ep{n:02d}.txt").write_text(f"EP {n}\nbody {n}\n",
                                                           encoding="utf-8")
        (work.human_dir / "ep01_notes.txt").write_text("ignore me\n", encoding="utf-8")
        work.story_path.write_text(
            "# Chapter 1: One\nfirst\n\n# Chapter 2: Two\nsecond\n\n"
            "# Chapter 3: Three\nthird\n", encoding="utf-8")
        return work

    def test_only_epNN_files_count_as_episodes(self):
        self.assertEqual(sorted(self.build().human_episodes()), [1, 2, 3])

    def test_chapter_slicing_is_inclusive(self):
        text = self.build().chapters(2, 3)
        self.assertIn("second", text)
        self.assertIn("third", text)
        self.assertNotIn("first", text)

    def test_missing_chapter_is_an_error(self):
        with self.assertRaises(SystemExit):
            self.build().chapters(3, 4)


class TestClosedBook(TempCase):
    """The forward agent must never be pointed at the human screenplay.

    If this test starts failing, the experiment is measuring nothing: the writer
    can copy the answer instead of reconstructing it.
    """

    def setUp(self) -> None:
        super().setUp()
        self.work = dataset.Work(root=self.tmp / "data" / "example")
        self.work.human_dir.mkdir(parents=True)
        (self.work.human_dir / "ep01.txt").write_text("EP 1\nSECRET GROUND TRUTH\n",
                                                      encoding="utf-8")
        self.work.story_path.write_text("# Chapter 1: One\nnoised prose\n",
                                        encoding="utf-8")
        self.run = run.open_run(self.tmp / "runs" / "demo",
                                {"works": ["example"], "episodes_per_step": 1,
                                 "steps": 1, "epochs": 1, "model": None,
                                 "no_backward": False})
        s5_train.adopt_story(self.run, self.work)
        self.copy = self.run.story_path("example")

    def rendered_prompt(self, story_path) -> str:
        pool = self.tmp / "memory"
        memory.init(pool, self.tmp / "lint.txt")
        out_dir = self.run.work_dir(0, 0, "example")
        out_dir.mkdir(parents=True)
        (out_dir / "scripts").mkdir()
        return prompts.render(
            "forward", episode_range="1-1", episode_count=1, pool_dir=pool,
            memory_headers=memory.headers(pool),
            output_paths=str(out_dir / "scripts" / "ep01.txt"),
            story_path=story_path,
            chapters=dataset.chapters_from(story_path, 1, 1))

    def test_the_run_local_story_keeps_the_human_directory_out_of_the_prompt(self):
        prompt = self.rendered_prompt(self.copy)
        self.assertIn("noised prose", prompt)
        self.assertNotIn("SECRET GROUND TRUTH", prompt)
        self.assertNotIn(str(self.work.human_dir), prompt)
        # Not even the parent that human/ sits in, so `ls` on it finds nothing.
        self.assertNotIn(str(self.work.root), prompt)

    def test_the_prompt_tells_the_agent_not_to_hunt_for_the_original(self):
        prompt = self.rendered_prompt(self.copy)
        self.assertIn("closed-book", prompt.lower())

    def test_adopting_a_story_twice_is_fine(self):
        s5_train.adopt_story(self.run, self.work)
        self.assertEqual(self.copy.read_text(), self.work.story_path.read_text())

    def test_re_noising_mid_run_is_refused(self):
        self.work.story_path.write_text("# Chapter 1: One\ndifferent prose\n",
                                        encoding="utf-8")
        with self.assertRaises(SystemExit):
            s5_train.adopt_story(self.run, self.work)


class TestPoolIsolation(TempCase):
    """A pool whose own repo is broken must never act on the enclosing one."""

    def outer_repo(self) -> Path:
        outer = self.tmp / "outer"
        (outer / "runs" / "demo" / "memory").mkdir(parents=True)
        memory.git(outer, "init", "-q", capture=True)
        memory.git(outer, "config", "user.email", "t@localhost", capture=True)
        memory.git(outer, "config", "user.name", "t", capture=True)
        (outer / "work.txt").write_text("committed\n", encoding="utf-8")
        memory.git(outer, "add", "-A", capture=True)
        memory.git(outer, "commit", "-m", "outer", capture=True)
        return outer

    def test_a_broken_pool_repo_is_refused_instead_of_adopting_the_parent(self):
        outer = self.outer_repo()
        pool = outer / "runs" / "demo" / "memory"
        (pool / ".git").mkdir()  # present but not a repository
        with self.assertRaises(SystemExit):
            memory.init(pool, self.tmp / "lint.txt")

    def test_reset_refuses_rather_than_touching_the_enclosing_repo(self):
        outer = self.outer_repo()
        pool = outer / "runs" / "demo" / "memory"
        (pool / ".git").mkdir()
        head = memory.head(pool)          # resolves to the outer repo's HEAD
        (outer / "work.txt").write_text("uncommitted edits\n", encoding="utf-8")
        with self.assertRaises(SystemExit):
            memory.reset(pool, head or "HEAD")
        self.assertEqual((outer / "work.txt").read_text(), "uncommitted edits\n")

    def test_a_scratch_file_in_the_pool_root_does_not_survive_a_reset(self):
        pool = self.pool()
        before = memory.head(pool)
        (pool / "NOTES.md").write_text("scratch\n", encoding="utf-8")
        (pool / "scratch").mkdir()
        memory.reset(pool, before)
        self.assertEqual(memory.lint_layout(pool), [])
        self.assertTrue(memory.is_clean(pool))


class TestSeedPool(TempCase):
    """`--init-pool` is what makes a frozen-pool control possible."""

    def setUp(self) -> None:
        super().setUp()
        self.source = self.tmp / "trained"
        (self.source / "01_craft_elements").mkdir(parents=True)
        (self.source / "01_craft_elements" / "subtext.md").write_text(
            GOOD, encoding="utf-8")
        self.run = run.open_run(self.tmp / "runs" / "frozen",
                                {"works": ["example"], "episodes_per_step": 5,
                                 "steps": 1, "epochs": 1, "model": None,
                                 "no_backward": True, "init_pool": str(self.source)})
        memory.init(self.run.pool, self.tmp / "lint.txt")

    def test_entries_are_copied_and_pass_the_linter(self):
        s5_train.seed_pool(self.run, self.source)
        self.assertTrue((self.run.pool / "01_craft_elements" / "subtext.md").exists())
        self.assertEqual(memory.lint(self.run.pool, self.tmp / "r.txt"), 0)

    def test_seeding_twice_does_not_overwrite_later_training(self):
        s5_train.seed_pool(self.run, self.source)
        entry = self.run.pool / "01_craft_elements" / "subtext.md"
        entry.write_text(GOOD.replace("Route", "Reroute"), encoding="utf-8")
        s5_train.seed_pool(self.run, self.source)
        self.assertIn("Reroute", entry.read_text())

    def test_an_empty_source_is_an_error(self):
        empty = self.tmp / "empty"
        empty.mkdir()
        with self.assertRaises(SystemExit):
            s5_train.seed_pool(self.run, empty)

    def test_a_seeded_frozen_run_gets_its_own_id(self):
        self.assertEqual(run.auto_run_id(self.run.config), "1w_e5_default_seeded_frozen")


class TestClosedBookGuard(TempCase):
    def trace(self, *lines: str) -> Path:
        path = self.tmp / "forward_reads.txt"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def test_reading_the_human_directory_fails_the_pass(self):
        human = self.tmp / "data" / "example" / "human"
        human.mkdir(parents=True)
        trace = self.trace(str(self.tmp / "runs" / "demo" / "input" / "example.md"),
                           str(human / "ep01.txt"))
        self.assertFalse(s2_forward.check_closed_book(trace, [human]))

    def test_reading_a_loss_report_fails_the_pass(self):
        trace = self.trace("/runs/demo/loss/epoch_00/step_00/example.md")
        self.assertFalse(s2_forward.check_closed_book(trace, []))

    def test_an_ordinary_trace_passes(self):
        pool = self.tmp / "runs" / "demo" / "memory"
        trace = self.trace(str(pool / "00_general_rules" / "pacing.md"),
                           str(self.tmp / "runs" / "demo" / "input" / "example.md"))
        self.assertTrue(s2_forward.check_closed_book(trace, [self.tmp / "data"]))

    def test_a_missing_trace_is_not_treated_as_a_violation(self):
        self.assertTrue(s2_forward.check_closed_book(self.tmp / "gone.txt", []))


class TestResumeCache(TempCase):
    def test_a_forward_pass_without_its_read_trace_is_not_done(self):
        # Screenplays but no trace means the optimizer could never attribute
        # anything to this work, so the pass has to be redone rather than skipped.
        out = self.tmp / "work"
        (out / "scripts").mkdir(parents=True)
        for n in (1, 2):
            (out / "scripts" / f"ep{n:02d}.txt").write_text("EP\n", encoding="utf-8")
        self.assertFalse(s2_forward.is_done(out, 1, 2))
        (out / "forward_reads.txt").write_text("\n", encoding="utf-8")
        self.assertTrue(s2_forward.is_done(out, 1, 2))

    def test_a_missing_episode_is_not_done(self):
        out = self.tmp / "work"
        (out / "scripts").mkdir(parents=True)
        (out / "scripts" / "ep01.txt").write_text("EP\n", encoding="utf-8")
        (out / "forward_reads.txt").write_text("\n", encoding="utf-8")
        self.assertFalse(s2_forward.is_done(out, 1, 2))


class TestTrajectory(TempCase):
    def log(self) -> Path:
        events = [
            {"type": "system", "subtype": "init", "model": "test", "session_id": "s1"},
            {"type": "assistant", "message": {"content": [
                {"type": "thinking", "thinking": "which rules apply"},
                {"type": "tool_use", "id": "t1", "name": "Read",
                 "input": {"file_path": "/pool/01_craft_elements/subtext.md"}},
                {"type": "tool_use", "id": "t2", "name": "Bash",
                 "input": {"command": "cat /pool/00_general_rules/pacing.md "
                                      "&& echo done; ls -la /pool/"}},
            ]}},
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": "rules..."}]}},
            {"type": "result", "num_turns": 2, "duration_ms": 1234,
             "total_cost_usd": 0.01},
        ]
        path = self.tmp / "log.jsonl"
        path.write_text("".join(json.dumps(e) + "\n" for e in events)
                        + "{ broken json\n", encoding="utf-8")
        return path

    def test_read_trace_covers_read_and_shell_reads(self):
        # Only what was actually read. `echo done` and `ls -la` are chained onto
        # the same command line and must not be recorded as files.
        self.assertEqual(trajectory.collect_read_trace(self.log()),
                         ["/pool/01_craft_elements/subtext.md",
                          "/pool/00_general_rules/pacing.md"])

    def test_a_shell_command_that_reads_nothing_records_nothing(self):
        for command in ("ls -la /pool/", "find /pool -type f | head -50",
                        "git -C /pool log --oneline", "echo hello"):
            self.assertEqual(trajectory._paths_from_bash(command), [], command)

    def test_transcript_includes_thinking_tools_and_summary(self):
        text = trajectory.render_trajectory(self.log())
        for fragment in ("which rules apply", "tool call: Read",
                         "tool result: Read", "turns: 2"):
            self.assertIn(fragment, text)

    def test_missing_log_yields_an_empty_trace(self):
        self.assertEqual(trajectory.collect_read_trace(self.tmp / "nope.jsonl"), [])


class TestPrepareData(unittest.TestCase):
    NUMBERED = "\n".join(f"{i}) {'INT' if i % 2 else 'EXT'}. ROOM {i} - DAY\n"
                         f"   Something happens.\n" for i in range(1, 13))
    BARE = "\n".join(f"INT. ROOM {i} - DAY\n   Something happens.\n"
                     for i in range(1, 13))

    def test_finds_numbered_and_bare_sluglines(self):
        for text in (self.NUMBERED, self.BARE):
            self.assertEqual(len(s0_prepare_data.split_scenes(text)), 12)

    def test_a_numbered_slugline_counts_once(self):
        scenes = s0_prepare_data.split_scenes(self.NUMBERED)
        self.assertTrue(all(s.startswith(tuple("123456789")) for s in scenes))

    def test_montage_headings_are_scenes_too(self):
        text = self.NUMBERED + "\n13) * VARIOUS SCENES\n   A montage.\n"
        self.assertEqual(len(s0_prepare_data.split_scenes(text)), 13)

    def test_too_few_headings_is_an_error(self):
        with self.assertRaises(SystemExit):
            s0_prepare_data.split_scenes("INT. ROOM - DAY\nnot a screenplay\n")

    def test_grouping_always_produces_the_requested_count(self):
        # Wildly uneven scenes are the normal case, and the last episode must
        # not become a dumping ground for whatever is left over.
        scenes = ["x" * n for n in (200, 9000, 50, 50, 4000, 60, 70, 3000, 80, 90, 100, 120)]
        for count in (2, 3, 5, 8, 12):
            groups = s0_prepare_data.group(scenes, count)
            self.assertEqual(len(groups), count)
            self.assertEqual([s for g in groups for s in g], scenes)
            self.assertTrue(all(groups))

    def test_asking_for_more_episodes_than_scenes_is_an_error(self):
        with self.assertRaises(SystemExit):
            s0_prepare_data.group(["a", "b"], 3)

    def test_page_numbers_are_stripped_but_dialogue_is_not(self):
        cleaned = s0_prepare_data.clean("INT. ROOM - DAY\n\n     42\n\n   He waits.\n")
        self.assertNotIn("42", cleaned)
        self.assertIn("He waits.", cleaned)


class TestRunDirectory(TempCase):
    CONFIG = {"works": ["example"], "episodes_per_step": 5, "steps": 4,
              "epochs": 1, "model": None, "no_backward": False}

    def test_resume_keeps_the_same_directory(self):
        root = self.tmp / "runs" / "demo"
        first = run.open_run(root, dict(self.CONFIG))
        again = run.open_run(root, dict(self.CONFIG))
        self.assertEqual(first.root, again.root)

    def test_resume_refuses_a_changed_setting(self):
        root = self.tmp / "runs" / "demo"
        run.open_run(root, dict(self.CONFIG))
        with self.assertRaises(SystemExit):
            run.open_run(root, {**self.CONFIG, "episodes_per_step": 3})

    def test_extending_the_schedule_is_allowed(self):
        root = self.tmp / "runs" / "demo"
        run.open_run(root, dict(self.CONFIG))
        self.assertEqual(run.open_run(root, {**self.CONFIG, "steps": 8})
                         .config["steps"], 8)

    def test_summaries_live_with_the_loss_reports(self):
        """A summary quotes the human screenplay, so the writer must not find it."""
        r = run.open_run(self.tmp / "runs" / "demo", dict(self.CONFIG))
        summary = r.summary_path(0, 0, 1)
        self.assertTrue(summary.is_relative_to(r.loss_dir))
        self.assertFalse(summary.is_relative_to(r.step_dir(0, 0)))

    def test_a_non_default_group_size_gets_its_own_id(self):
        self.assertNotEqual(run.auto_run_id({**self.CONFIG, "group_size": 2}),
                            run.auto_run_id({**self.CONFIG, "group_size": 4}))

    def test_changing_the_group_size_refuses_to_resume(self):
        root = self.tmp / "runs" / "demo"
        run.open_run(root, {**self.CONFIG, "group_size": 4})
        with self.assertRaises(SystemExit):
            run.open_run(root, {**self.CONFIG, "group_size": 2})

    def test_episode_ranges_tile_the_story(self):
        r = run.open_run(self.tmp / "runs" / "demo", dict(self.CONFIG))
        self.assertEqual([r.episodes(i) for i in range(3)],
                         [(1, 5), (6, 10), (11, 15)])


class TestMicroSteps(unittest.TestCase):
    def test_groups_are_consecutive_and_keep_the_remainder(self):
        self.assertEqual(s5_train.make_groups(list("abcdefghij"), 4),
                         [list("abcd"), list("efgh"), list("ij")])

    def test_zero_puts_everything_in_one_group(self):
        self.assertEqual(s5_train.make_groups(list("abc"), 0), [list("abc")])
        self.assertEqual(s5_train.make_groups([], 0), [])

    def test_the_summary_is_listed_before_the_works(self):
        sample = {"work": "w", "first": 1, "last": 5, "loss_report": "/l",
                  "reads": "/r", "trajectory": "/t"}
        text = s4_backward.batch_section([sample], Path("/s.md"))
        self.assertLess(text.index("/s.md"), text.index("/l"))
        self.assertNotIn("Commonality", s4_backward.batch_section([sample]))


if __name__ == "__main__":
    unittest.main()
