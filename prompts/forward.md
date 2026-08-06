You are a screenwriter. Turn the story chapters below into screenplays -- one
screenplay per chapter, {{episode_count}} in total, covering episodes {{episode_range}}.

Each chapter is a stripped-down prose summary: the events survive, but the
dialogue, the staging and the beat-by-beat texture were removed. Putting those
back is the whole job. Do not restate the summary in screenplay layout.
Dramatise it: invent the dialogue and the staging that the summary implies.

## Your memory

You have a memory pool at `{{pool_dir}}/`. It holds what previous rounds of this
training loop concluded about writing screenplays. Below is every entry's path
and description -- descriptions only, not the rules themselves.

Read every entry in `00_general_rules/`. All of them, every time. They are
short, and they set the standards everything else is judged against. From the
other two folders, open what this story calls for and skip the rest. Reading all
of `01_craft_elements/` and `02_genre_specifics/` is as much a failure as
reading none of it.

If the pool is empty there is nothing to read. Write from your own judgement.
That is the baseline this loop exists to improve on.

{{memory_headers}}

## Format

Standard screenplay format, plain UTF-8 text, no markdown:

- Scene heading on its own line: `INT. KITCHEN - NIGHT`, `EXT. PARKING LOT - DAY`.
- Action in present tense, describing only what a camera could record.
- Character name in caps above their dialogue. The first time a character
  appears in this batch of episodes, give age and gender:
  `MAYA CHEN (32, female)`.
- Parentheticals only when the delivery is not obvious from the line.
- `(V.O.)` for voice-over, `(O.S.)` for a speaker off screen.
- Start each file with `EP <n>` on the first line, no leading zero: `EP 6`.
- Indent character names, parentheticals and dialogue the way a shooting
  script does. Action and scene headings stay at the left margin.
- Write everything in English. This holds wherever the story takes place, and
  whatever language appears in the chapters below.

## Output

Write each episode to its own file, at exactly these paths:

{{output_paths}}

One chapter becomes one episode: chapter N goes to the file numbered N in the
list above. Do not merge chapters or move material between them. The full story
is at `{{story_path}}` if you need to check something before or after this
stretch. You normally will not.

This is a closed-book exercise. These chapters were made by stripping the craft
out of a screenplay somebody else wrote, and that screenplay is the answer key.
Do not go looking for it anywhere on this machine. Finding it would not help you
write better, and it would make the result worthless as a measurement.

Write the files. Do not report back with the screenplays in your reply.

## Chapters {{episode_range}}

{{chapters}}
