# skill-training

**Train an agent's skill by running SGD on a pool of Markdown notes.**

[English](README.md) · [中文](README.zh-CN.md)

[![tests](https://github.com/skilltraining-project/skill-training/actions/workflows/test.yml/badge.svg)](https://github.com/skilltraining-project/skill-training/actions/workflows/test.yml)
![python](https://img.shields.io/badge/python-3.10%2B-blue)
![license](https://img.shields.io/badge/license-MIT-green)
![dependencies](https://img.shields.io/badge/dependencies-none-lightgrey)

No weights are touched. The trainable parameters are plain `.md` files that an
agent reads before it works. The gradient is a `git diff` over those files.

```
forward   an agent writes, using its notes and nothing else
loss      compare what it wrote against what a professional wrote
backward  a second agent reads the comparison and edits the notes
```

Run that in a loop. Every step of the training is a commit, so you can read the
whole thing in `git log`.

This is the reference implementation of the paper
**[Skill Training with Corruption and Reconstruction Loop](https://arxiv.org/abs/2607.27557)**.
The paper and this code use different words for the same parts:

| paper | this repository |
|---|---|
| skill library, or memory | the pool, `runs/<id>/memory/` |
| rule card | one entry, one `.md` file |
| expert folders | the three folders in the pool |
| corruption step | `s1_diffuse.py` |
| reconstruction by the script agent | the forward pass, `s2_forward.py` |
| loss agent | `s3_loss.py` |
| reduce step and commonality report | `reduce` in `s4_backward.py` |
| backward credit assignment, one micro-step | `s4_backward.py` |
| training with data-parallel micro-steps | `s5_train.py --group-size` |

---

## The problem this solves

Suppose you want a model to write screenplays the way a working screenwriter
does. Fine-tuning needs pairs: an input, and the screenplay that should come out
of it. Nobody has that dataset. Screenplays exist. The briefs that produced
them do not.

Diffusion models had the same problem with images and solved it by going
backwards. You cannot collect (noise, image) pairs, but you can take a real
image and destroy it, and now you have a pair for free. Train on the destruction
and you get a model that undoes it.

Do that to a screenplay. Take a real one and strip out everything the writer
contributed. The dialogue goes. The staging goes. The scene breaks go. What is
left is a flat prose summary: the events happened, but nobody made anything of
them.

That summary and the original screenplay are a training pair, and it cost
nothing to make. Feed the summary in, ask for a screenplay back, and compare
what you get to the original. The gap between them is the craft that was stripped
out. Closing it is the whole job.

## Three agents make one SGD step

| | in a neural net | here |
|---|---|---|
| parameters | weight tensors | a folder of Markdown rules |
| forward | run the network | an agent writes a screenplay from its notes |
| loss | compare to the label | compare to the human screenplay |
| backward | backpropagate | an agent reads the comparison and edits the notes |
| optimizer step | `w -= lr * grad` | a git commit on the notes |
| batch | many samples per step | many screenplays per step |
| epoch | one pass over the data | one pass over the screenplays |

The forward agent is closed-book. It sees the noised story and its own notes.
It never sees the human screenplay, so it cannot copy. The only thing that can
make it write better is the notes.

The loss is a document, not a number. A number would say how far off you are.
A document says what to change, which is what the optimizer needs.

The backward agent is the only one allowed to write to the pool. It gets the
loss reports plus a **read trace** for each one: the list of files the forward
agent actually opened. That is what makes credit assignment possible. A rule can
only be blamed for a screenplay it was present for.

It has four moves:

- **reinforce** a rule that helped, usually by leaving it alone
- **correct** a rule that misled: narrow where it applies, or loosen how
  strictly it is stated
- **create** a rule for something no entry covers
- **merge** two rules that have drifted into duplicates

Then it commits. That commit is the step.

With more than a few works, one agent cannot read every loss report, so a step
is split into **micro-steps**. The works are cut into groups of four
(`--group-size`). Each group's loss reports are first reduced into one
commonality report, which keeps a pattern only when it appears in more than one
work, unless it belongs to a genre. One backward pass then edits the pool from
that report and commits. The micro-steps share the pool and run in order, so
each one starts from what the last one left. Every commit is one micro-step.

## Quickstart

You need Python 3.10+, git, and the [Claude Code](https://claude.com/claude-code)
CLI, logged in. Starting from a PDF also needs `pdftotext`, from
`brew install poppler` or `apt install poppler-utils`. There are no Python
dependencies. Developed and tested on macOS and Linux, and it assumes a POSIX
shell.

```bash
git clone https://github.com/skilltraining-project/skill-training && cd skill-training
python3 -m unittest discover tests      # offline checks, no API calls
```

Get a screenplay and cut it into episodes:

```bash
bash data/get_example.sh               # a CC BY-SA licensed screenplay
python3 s0_prepare_data.py --pdf data/example/source.pdf --episodes 20
```

Destroy it into training input. This is the only step that touches all of the
data at once, and it is a one-time cost per screenplay:

```bash
python3 s1_diffuse.py --work data/example --only 1 --force   # try one, print it
python3 s1_diffuse.py --work data/example --noise heavy      # then do all of them
```

Read that first chapter before running the rest. How much you destroy here sets
the difficulty of everything downstream, and it is the one knob worth tuning by
hand. It lives in `prompts/diffuse_heavy.md`.

Train:

```bash
python3 s5_train.py --work data/example --steps 4 --episodes-per-step 5
```

Watch the pool learn:

```bash
git -C runs/<run-id>/memory log --oneline
git -C runs/<run-id>/memory show HEAD
```

Every stage also runs on its own if you want to look at one in isolation:

```bash
python3 s2_forward.py  --work data/example --pool runs/<id>/memory \
                      --out /tmp/fw --first 1 --last 5
python3 s3_loss.py     --work data/example --scripts /tmp/fw/scripts \
                      --out /tmp/loss.md --first 1 --last 5
python3 s4_backward.py --pool runs/<id>/memory --batch /tmp/batch.json --out /tmp/bw \
                      [--summary runs/<id>/loss/epoch_00/step_00/summary_g01.md]
```

`s5_train.py` writes that `batch.json` for you, one per micro-step. By hand, one
entry per work:

```json
[{"work": "example", "first": 1, "last": 5,
  "loss_report": "/abs/runs/<id>/loss/epoch_00/step_00/example.md",
  "reads": "/abs/runs/<id>/epoch_00/step_00/example/forward_reads.txt",
  "trajectory": "/abs/runs/<id>/epoch_00/step_00/example/forward_trajectory.md"}]
```

Re-run `s5_train.py` with the same arguments to resume. Each stage checks
whether its own output is already on disk, so an interrupted run picks up where
it stopped. There is no state file to fall out of sync. The single-stage
commands above have no such check and always re-run.

## What a parameter looks like

One rule, one file. This is the entire format.

```markdown
---
description: Use when two characters argue, negotiate, confess or hide something. For scenes where they talk about one thing and mean another. Not for lines that exist to deliver facts, like an address or a diagnosis.
---

## Rules
Let characters route real feeling through small concrete complaints. Instead of
"I care about you", have them pick a fight about a coat left on a chair, a cold
coffee, a missed call. The pressure sits under the line, not in it.
```

The split is doing real work. `description` is all the forward agent sees when
it decides what to open, so it has to state the boundary. The body is what it
reads after deciding, so it must not waste space restating the boundary. This is
the easiest thing to get wrong. When a description says what the rule teaches
instead of when to use it, every entry looks relevant. The agent then reads all
of them, or none of them.

The pool has three folders and only three:

```
memory/
  00_general_rules/     what the medium is, what good means. Always read.
  01_craft_elements/    how to write dialogue, hooks, action lines. Read on demand.
  02_genre_specifics/   rules that only hold inside one genre. Read when it matches.
```

A linter enforces the shape: one `description` field, one `## Rules` heading, at
most 50 lines, no episode numbers, no "the model wrote X and the human wrote Y".
It runs as a git pre-commit hook inside the pool, so the optimizer cannot commit
a malformed rule even if it wants to.

The size limits are not tidiness. The forward agent reads every description on
every pass, so a pool that grows without limit stops being routable. When an
entry outgrows its limit, the optimizer has to compress it or split it into two
entries with separate boundaries. Either way the pool gets better organized
instead of just bigger.

## What one step actually looks like

The first training step over two episodes of the example screenplay. The writer
had an empty pool, so it wrote from its own instincts. The loss report opened by
counting:

| | human | model |
|---|---|---|
| words per episode | 648 | 2,491 |
| speeches | 28 | 120 |
| median speech length | 9 words | 4 words |
| speeches of three words or fewer | 14% | 42% |
| mean action sentence length | 8.5 words | 7.4 words |

That last row is the interesting one. The model writes sentences the same length
as the professional. It just writes six times as many of them. And its dialogue
is bimodal: two-word volleys, then long speeches, with little of the ordinary
middle the human lives in.

The optimizer read that, decided the pattern was general rather than a one-off,
and committed a new entry. Part of it:

```markdown
## Rules
Live in the middle band. Most speeches want to be roughly eight to twelve words:
long enough to be a thought, short enough to be spoken in one breath. An exchange
built only of two-word volleys and long arias has no ordinary register in it, and
both extremes stop registering when they are the only two settings available.

Stop a rhythm once it has paid. When an exchange has done what it exists to do --
shown that these two are easy together, that one is needling the other, that they
disagree about a third person -- end it. A pattern you are enjoying will run five
or six turns past its point without feeling wrong from the inside.
```

Seven entries came out of that one step, spread across the three folders, all of
them within the linter's limits, all in one commit. On the next step the writer
sees their descriptions and opens the ones that fit what it is about to write.

Nobody wrote that rule. Nobody wrote the observation either. The only thing
supplied was a screenplay and a way to destroy it.

## What a run leaves behind

```
runs/<run-id>/
  config.json                       what this run was started with
  memory/                           the pool, with its own git history
  input/example.md                  the noised story, as this run saw it
  loss/epoch_00/step_00/
    example.md                      the training signal
    summary_g01.md                  a group's commonality report
  epoch_00/step_00/
    example/
      scripts/ep01.txt ...          what the agent wrote
      forward_prompt.md             exactly what it was told
      forward.jsonl                 the raw session
      forward_trajectory.md         everything it did, readable
      forward_reads.txt             which rules were open while it wrote
    backward/g01/                   one micro-step, one per group
      batch.json                    what the optimizer was given
      backward_prompt.md            exactly what it was told
      backward.jsonl                the raw session
      backward_trajectory.md        its reasoning
      memory_before/ memory_after/  the pool on both sides of the step
      memory.patch                  the gradient, as a diff
      lint_report.txt               the linter's verdict on the result
      commit.txt                    written only after every check passed
```

The loss reports and the commonality reports sit in their own directory rather
than beside the screenplays. They quote the human original, and the forward agent works inside a step
directory, so keeping the two apart is what stops a second epoch from finding
the first epoch's answer key next door. After every forward pass the read trace
is checked against that directory and against `data/<work>/human/`, and a pass
that opened either one fails instead of quietly scoring well.

Nothing here is a summary of what happened. It is what happened. If a step
produced a bad rule you can read the loss report that caused it, the trace that
justified it, and the diff that applied it.

Three checks stand between the optimizer and a finished step: the linter passes,
a commit exists, and the working tree is clean. `commit.txt` is written only after all three
pass. A resumed run looks for that file, so it never skips a step on the
strength of a partial result.

## How to tell whether it is learning

Run the same thing twice, once with the pool frozen:

```bash
python3 s5_train.py --work data/example --steps 4 --episodes-per-step 5

python3 s5_train.py --work data/example --steps 4 --episodes-per-step 5 \
    --no-backward --init-pool runs/<trained-run>/memory
```

The second run writes with the pool the first one produced, frozen at whatever
it had learned, and never updates it. Same writer, same stories, same prompts.
The only difference is whether the notes keep changing. Compare the loss reports
from the last step of each.

Dropping `--init-pool` gives you a different and blunter comparison: no notes at
all against notes that evolve. That one answers "do the notes help", not "does
the loop improve them".

This repository ships no benchmark numbers. What it ships is the machinery to
run that comparison yourself, and a complete record of every step so you can
check the answer by reading it.

Two things are worth watching during a run:

- **the read trace.** Expect the agent to open almost everything at first: the
  descriptions are vague, so everything looks relevant. If the pool is getting
  better organized, the traces should get shorter and more specific.
- **the shape of the pool.** Expect early steps to be mostly `create`, and later
  ones to shift toward `correct` and `merge`. A pool that is still only creating
  after many steps is accumulating, not learning.

## Making it write something else

The pipeline has no idea it is doing screenplays. That lives entirely in
`prompts/`, six markdown files:

```
prompts/
  diffuse_heavy.md    how to destroy an example. This defines the task.
  diffuse_light.md    a gentler setting: prose fiction, not a bare summary
  forward.md          how to write, and the format to write in
  loss.md             what counts as a difference worth reporting
  backward.md         how to turn differences into edits
  memory_policy.md    what a rule is, and the four moves
```

To train something else, replace the corruption and the format. If you can take
a good example of the thing and mechanically strip out the skill, you have a
training set. The same trick should work for legal drafting,
technical documentation, product copy, bug reports, or code review comments.
None of those have been tried here. It works less well where the skill is not
recoverable from the output, or where you cannot get good examples.

## What it costs, and what it can touch

A full pass over the 20-episode example is about 32 CLI invocations. Twenty of
them noise the screenplay, which happens once and is cached. The other twelve
are three per training step: write, compare, update. Noising and the loss are
single text calls. The forward and backward passes are agents with tools, so
each one runs many turns, and that is where the time and the money go.

The agents run with `--dangerously-skip-permissions`, which is what lets the
loop run unattended. By design they write to the run directory and the memory
pool, and the backward agent runs git inside the pool. Nothing enforces that
boundary, so run this somewhere you are comfortable giving an agent a free hand.

## Configuration

Most settings are command-line flags. Run any script with `--help` for the full
list. A few things you should not need often are environment variables:

| variable | default | what it does |
|---|---|---|
| `SKILLTRAIN_SETTING_SOURCES` | empty | which CLI setting layers the agent loads. Empty keeps your own `CLAUDE.md` out of the experiment |
| `SKILLTRAIN_API_TIMEOUT_MS` | `600000` | per-request timeout, raise it for slow models |
| `SKILLTRAIN_MAX_LINES` | `50` | line limit per rule |
| `SKILLTRAIN_MAX_BODY_CHARS` | `4800` | body limit per rule |
| `SKILLTRAIN_MAX_DESCRIPTION_CHARS` | `800` | description limit per rule |

Model selection is `--model`, passed straight through to the CLI. Leave it off
to use whatever your CLI is set to. Any Anthropic-compatible gateway works
through the CLI's own `ANTHROPIC_BASE_URL` and `ANTHROPIC_AUTH_TOKEN`. This
project never reads an API key.

## Where this came from

The experiments in the paper ran on a larger private system that trains
screenwriting agents on a proprietary corpus of short-drama screenplays. This
repository is that training loop, stripped down: the corruption step, the three
agents, the reduce step and the micro-steps, the pool and its linter. The
screenplays cannot be shared, so the paper's numbers cannot be reproduced from
here. The evaluation harness and the baselines are not included either. What is
here is the part worth reusing: the loop, the pool, and the idea that you can do
gradient descent on writing.

## Citation

```bibtex
@misc{li2026skilltraining,
  title         = {Skill Training with Corruption and Reconstruction Loop},
  author        = {Li, Mo and Yin, Zixin and Wu, Qihao and Cao, Ting and Liu, Yunxin and Shum, Heung-Yeung},
  year          = {2026},
  eprint        = {2607.27557},
  archivePrefix = {arXiv}
}
```

## License

MIT.
