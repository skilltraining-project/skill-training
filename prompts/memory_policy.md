## What a memory entry is

The pool has exactly three folders:

{{folder_guide}}

Every entry is one markdown file inside one of them:

```
---
description: <when to read this entry, and when not to>
---

{{body_heading}}
<how to write it>
```

The two halves do different jobs, and mixing them wastes both:

- `description` is all the writer sees when deciding what to open. It must state
  the boundary -- the situations this applies to, and the neighbouring ones it
  does not. No craft advice here.
- `{{body_heading}}` is what they read once they have decided. Explain how to
  write the thing, in plain language, as advice that transfers to the next
  story. Do not restate when it applies.

`description` is the only frontmatter field, and it has to sit on one line.
Wrapping it onto a second line is rejected. The folder and filename are the
entry's title and identity, so nothing else goes in the header.

A short example, for shape only:

```
01_craft_elements/dialogue-subtext.md

---
description: Use when two characters argue, negotiate, confess or hide something. For scenes where they talk about one thing and mean another. Not for lines that exist to deliver facts, like an address or a diagnosis.
---

## Rules
Let characters route real feeling through small concrete complaints. Instead of
"I care about you", have them pick a fight about a coat left on a chair, a cold
coffee, a missed call. The pressure in the relationship sits under the line, not
in it.
```

Hard limits, enforced by a linter on commit:

- At most {{max_lines}} lines per file, and at most {{max_body_chars}}
  characters of body. Both limits apply, so packing the body into a few very
  long lines buys you nothing. When an entry outgrows the limit, do not keep
  adding: compress it, or split it into two entries with clearly separated
  descriptions.
- `description` at most {{max_description_chars}} characters, on a single line.
- Exactly one heading in the body: `{{body_heading}}`.
- Plain language, written in English. Not a research log, not a post-mortem,
  not jargon.
- No episode numbers, no "the model wrote X, the human wrote Y". An entry is a
  rule for next time, not a record of last time.

## Attributing the difference

For each work, hold its loss report next to its read trace and work out, entry
by entry, what the entries that were open actually did:

- **It helped.** The report says something was written well, and the entry the
  writer opened is why.
- **It misled.** The report says something was written badly, and the entry
  pushed in that direction or was wrong for this situation.
- **No visible effect.** It was read, and the report says nothing either way.

This thinking is required. Acting on all of it is not, as the next section says.

## The four edits

**A -- reinforce.** An entry helped. Usually change nothing. If the rule is
stated vaguely, sharpen it. Never paste in loss-report text.

**B -- correct.** An entry misled, or should have applied and was never opened.
- Scope too wide, so it fires in the wrong scenes: narrow the `description`.
- Rule is right but stated too rigidly: loosen the body, add the exception.
- Rule was read and simply not followed: do not invent machinery around it. At
  most, make it easier to apply.

**C -- create.** The report raises something no entry in the pool covers. Check
the headers first. Then write a new file inside the
pool, at `<folder>/<short-topic-slug>.md`, with a description that states when
to read it.

**D -- merge.** Two entries have drifted into near-duplicates. Pick the one with
better coverage, fold the other's useful rules into it as one coherent passage
rather than a concatenation, adjust its description to cover the union, and
delete the other. Pools get redundant over a long run, and merging is how they
stay routable.

## How to work

1. Read each work's loss report, read trace, and -- if the report is unclear
   about what happened -- its trajectory.
2. Attribute: for each entry the writer opened, decide what it did.
3. Only when the loss suggests a missing rule, a routing failure, or redundancy,
   go to the full header list and open a few candidates.

Do not read every entry in the pool as a precaution. Not every step needs all
four edits, and not every observation in a loss report deserves one -- a change
that is not clearly an improvement is worse than no change. But steps where you
change nothing at all should be rare. If several steps in a row give you nothing
to do, suspect yourself before you conclude the pool is finished.
