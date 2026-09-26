# Usage guide

[Project overview](../README.md) · English · [简体中文](guide.zh-CN.md)

Start with the [quick start](../README.md#quick-start) to prepare the environment and run the example. This guide covers your own data, individual stages, run artifacts, and controlled comparisons.

## Prepare your own material

Use source material you have permission to process. Each work has a separate directory:

```text
data/my-work/
├── human/
│   ├── ep01.txt
│   ├── ep02.txt
│   └── ...
└── story.md
```

The `human/` files are the reference episodes. `story.md` is the corrupted input produced by `s1_diffuse.py`. You can prepare episodes from a PDF or a text file:

```bash
python s0_prepare_data.py --text /path/to/source.txt \
  --work data/my-work --episodes 20
python s1_diffuse.py --work data/my-work --only 1 --force
```

Inspect the split and one outline before processing the rest. The splitter is a convenience; check that its episode boundaries suit your source. After reviewing or editing `prompts/diffuse_heavy.md`, run:

```bash
python s1_diffuse.py --work data/my-work --noise heavy --force
```

`heavy` produces a sparse story outline; `light` keeps more prose detail. Noising caches chapter outputs. `--force` refreshes them, including after prompt edits. `--only` writes the selected chapter cache and prints its output, but does not replace the assembled `story.md`.

## Train on several works

Prepare each work separately, then repeat `--work`:

```bash
python s5_train.py \
  --work data/work-a --work data/work-b \
  --run-id two-works --steps 4 --episodes-per-step 5 \
  --epochs 3 --workers 4 --group-size 4
```

For each step, the writer reconstructs the selected episodes using the current library. A comparison agent reads each reconstruction and its human reference. Works are grouped for feedback reduction, and each group's backward pass updates the shared library in sequence. A single-work group uses its loss report directly. Each completed backward micro-step produces a Git commit.

`--workers` controls concurrent work-level jobs; `--group-size` controls how many works contribute to each library update. Both default to four. `--group-size 0` places all works in one group. The noising script has a separate `--workers` option, defaulting to eight.

Re-run the **same command** to resume an interrupted run. The orchestrator checks completed artifacts and skips those stages. Start a new `--run-id` when changing the experiment, its prompts, or its input. A run stores a copy of its corrupted input and rejects a changed input on resume.

## The skill library

The trainable artifact is a folder of Markdown cards, with its own Git history:

```text
memory/
├── 00_general_rules/     General writing rules
├── 01_craft_elements/    Dialogue, hooks, action, and other techniques
└── 02_genre_specifics/   Rules with a genre-specific scope
```

Each card has a YAML `description` field followed by a `## Rules` section. The description states **when the rule applies**; the body explains **what to do**. The writer is instructed to read general rules and select relevant craft and genre cards. Its file-read trace records the rules it actually opened, providing evidence for backward credit assignment.

The update agent can reinforce useful rules, correct misleading ones, create missing rules, and merge duplicates. A format checker enforces card structure and size limits, including 50 lines, 4,800 body characters, and 800 description characters by default. It also rejects specified episode-specific or model-versus-human comparison patterns. See [`skilltrain/memory.py`](../skilltrain/memory.py) for the exact checks.

The checker is installed as a pre-commit hook inside the library. A backward step is marked complete only after validation passes, a commit exists, and the working tree is clean.

```bash
git -C runs/demo/memory log --oneline
git -C runs/demo/memory show HEAD
```

## Inspect a run

```text
runs/demo/
├── config.json
├── memory/                         Skill cards and their Git history
├── input/example.md                The input used by this run
├── loss/epoch_00/step_00/
│   ├── example.md                  Comparison with the human reference
│   └── summary_g01.md              Reduced feedback for a multi-work group
└── epoch_00/step_00/
    ├── example/
    │   ├── scripts/ep01.txt ...    Reconstructed episodes
    │   ├── forward_prompt.md
    │   ├── forward.jsonl
    │   ├── forward_trajectory.md
    │   └── forward_reads.txt
    └── backward/g01/
        ├── batch.json
        ├── backward_prompt.md
        ├── backward.jsonl
        ├── backward_trajectory.md
        ├── memory_before/
        ├── memory_after/
        ├── memory.patch
        ├── lint_report.txt
        └── commit.txt
```

Loss reports contain the human reference and live outside the writer's step directory. After a forward pass, the recorded read trace is checked for reads from the human-reference and loss directories; a detected read makes the pass fail. This trace check is not an operating-system sandbox.

To investigate a bad rule, follow its `memory.patch` back to the corresponding loss report, backward trajectory, and writer read trace. `commit.txt` is the completion marker used when resuming updates.

## Run individual stages

These commands use the library created by the quick-start run. They write to a separate `runs/manual/` directory and, unlike the orchestrator, rerun the selected stage each time:

```bash
mkdir -p runs/manual
python s2_forward.py --work data/example --pool runs/demo/memory \
  --out runs/manual/forward --first 1 --last 5
python s3_loss.py --work data/example --scripts runs/manual/forward/scripts \
  --out runs/manual/loss.md --first 1 --last 5
```

For an update, create `runs/manual/batch.json` with the following content, replacing `/absolute/path/to/skill-training` with your checkout path:

```json
[
  {
    "work": "example",
    "first": 1,
    "last": 5,
    "loss_report": "/absolute/path/to/skill-training/runs/manual/loss.md",
    "reads": "/absolute/path/to/skill-training/runs/manual/forward/forward_reads.txt",
    "trajectory": "/absolute/path/to/skill-training/runs/manual/forward/forward_trajectory.md"
  }
]
```

Then run the update. This **modifies the demo library**:

```bash
python s4_backward.py --pool runs/demo/memory \
  --batch runs/manual/batch.json --out runs/manual/backward
```

For a batch with several works, add one entry per work. The standalone backward command uses the batch's loss reports directly; you can provide an existing reduced report with `--summary /path/to/summary.md`. In ordinary training, `s5_train.py` prepares the batch and automatically reduces feedback for multi-work groups.

## Compare updating and frozen libraries

To isolate continued library updating, give both runs the **same initial library**, inputs, model, and prompts, and use separate run IDs. Here `runs/seed/memory` is an existing library that neither run modifies:

```bash
python s5_train.py --work data/example --run-id updating \
  --steps 4 --episodes-per-step 5 --init-pool runs/seed/memory

python s5_train.py --work data/example --run-id frozen \
  --steps 4 --episodes-per-step 5 --init-pool runs/seed/memory --no-backward
```

The first run copies the seed and updates its own copy; the second keeps its copy fixed. Omitting `--init-pool` from both runs compares learning from an empty library against a library that stays empty. Comparing an empty-start adaptive run with a final-library frozen run answers a different question because their starting points differ.

For claims about generalization, evaluate on held-out material. Loss reports on the training examples alone do not establish held-out improvement. This example workflow does not include the paper's proprietary benchmark corpus.

## Prompts and adaptation

| Template | Purpose |
| :--- | :--- |
| [`diffuse_heavy.md`](../prompts/diffuse_heavy.md) | Remove screenplay craft and retain a sparse outline. |
| [`diffuse_light.md`](../prompts/diffuse_light.md) | Produce a less destructive prose transformation. |
| [`forward.md`](../prompts/forward.md) | Reconstruct episodes with the skill library. |
| [`loss.md`](../prompts/loss.md) | Compare generated and human episodes. |
| [`reduce.md`](../prompts/reduce.md) | Consolidate evidence across works. |
| [`backward.md`](../prompts/backward.md) | Turn feedback into library edits. |
| [`memory_policy.md`](../prompts/memory_policy.md) | Define card structure and update operations. |

The released implementation is tailored to screenplays. Moving to another domain may also require changes to data parsing and output validation, including the expected `epNN.txt` files. Other domains are not evaluated in this release.

## Configuration and cost

Run any entry script with `--help` for its full options. `--model` is passed through to Claude Code; if omitted, the CLI determines the model. Authentication also comes from that CLI installation and its environment.

| Environment variable | Default | Meaning |
| :--- | :--- | :--- |
| `SKILLTRAIN_SETTING_SOURCES` | Empty | CLI settings layers to load; empty disables those layers. |
| `SKILLTRAIN_API_TIMEOUT_MS` | `600000` | Timeout for an individual API request, in milliseconds. |
| `SKILLTRAIN_MAX_LINES` | `50` | Maximum lines per skill card. |
| `SKILLTRAIN_MAX_BODY_CHARS` | `4800` | Maximum card-body characters. |
| `SKILLTRAIN_MAX_DESCRIPTION_CHARS` | `800` | Maximum description characters. |

An empty settings-source list is not a guarantee that every personal instruction source is excluded. The runner also disables Claude Code auto-memory for its child processes. Check the recorded prompts and trajectories when diagnosing unexpected behavior.

Training time and cost depend on the model, work count, episode length, retries, and agent tool turns. A CLI invocation can contain many model requests, so invocation counts are not token or billing estimates. Agents run with `--dangerously-skip-permissions`, as noted in the quick start.
