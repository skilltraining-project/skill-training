Below are {{n}} loss reports from the same training step, one per work. Each
compares a model-written screenplay against the human original. Next comes the
backward pass: an optimizer reads the signal and edits a pool of writing rules
that every work shares. It cannot read all of these reports in full, so fold
them into one summary first.

Two kinds of rule, with different bars:

- **General rules** hold for any screenplay regardless of genre: rhythm,
  dialogue, what is left unsaid. A pattern belongs here only if it shows up in
  at least two works. One work's quirk is not a law.
- **Genre rules** hold only inside one genre: thriller, romance, road movie and
  so on. These do not need to repeat. The works in this group may all be
  different genres, and a finding that only one work can show is still a
  complete signal for its genre. Do not squeeze it to one line just because it
  appears once. The question is whether it is a property of the genre, not how
  many times it came up here.

For every pattern, state which works it appears in, the genre if it is a genre
rule, what the gap actually is, and how the human wrote it against how the model
wrote it, quoting one or two of the most telling passages from the reports and
naming the work each comes from.

Things that really are specific to one story, and would not hold for another
work in the same genre, go in a short last section. One or two lines each, with
the work named, so the optimizer can decide whether to ignore them.

Do not blur specifics into slogans. "The dialogue needs polish" is useless. Keep
the reports' level of detail: the actual technique, sentence shape, rhythm, and
the craft instinct behind it. The optimizer assigns credit work by work, so every
conclusion has to be traceable to named works, not to "most of them".

{{reports_section}}

## Output

Markdown only. Choose your own headings, in this order: general rules, then
genre rules, then one-story specifics.
