Rewrite the screenplay below as a plain prose summary of what happens.

This is a corruption step. The goal is not a good piece of writing -- it is to
strip out everything a screenwriter contributes, so that whoever reads your
summary later has to reinvent all of it. Take the craft away and leave the story.

Chapter number: {{episode_number}}

## Output format

First line: `# Chapter {{episode_number}}: <a short title, 3-6 words>`

Then 500-1200 words of prose, in a handful of paragraphs. Not bullet points, not
a scene list -- flowing paragraphs that merge several beats at a time.

Write everything in English, even if the screenplay below is in another language.

## Remove

- Every line of dialogue. Say what a character wanted and how they went at it,
  never what they said. No quoted speech, no memorable phrasings, no comebacks.
- Every small physical action: the clenched fist, the forced smile, the held
  glance. Say what the character felt or hid instead.
- Scene boundaries. Do not produce a scene-by-scene walkthrough. Keep events in
  the order they happen, but fold a corridor conversation, a public humiliation
  and an exit into one paragraph when they form a single causal move.
- Camera and staging: shot descriptions, cuts, angles, transitions.
- Props and details that carry no plot weight.

## Keep

- Character names, and who is what to whom.
- The causal chain: what forces what, who learns what and when.
- Identities, secrets, and the mechanism of any reversal.
- Objects that function as evidence or leverage.
- Whatever the chapter ends on. Leave the hook intact without commenting on it.

## Never write

- Screenplay vocabulary: `INT.`, `EXT.`, `V.O.`, `O.S.`, `CUT TO`, `FADE IN`,
  `(CONT'D)`, `[VFX]`, scene numbers, revision marks.
- ALL-CAPS character names. `SARAH` in the screenplay is `Sarah` here.
- Parenthetical stage directions like `(coldly)`.
- Any note about what you did, or any mention of the source being a screenplay.

Output the chapter only.

---

Screenplay, episode {{episode_number}}:

{{screenplay}}
