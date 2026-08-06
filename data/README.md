# Data

Training data is not committed here. `data/get_example.sh` downloads it, and
`s0_prepare_data.py` turns it into episodes.

## Layout

```
data/<work>/
  source.pdf          the screenplay you started from (not in git)
  human/ep01.txt ...  it, split into episodes. The ground truth.
  story.md            the same story after noising. The training input.
  .cache/heavy/ch01.md  noising cache, keyed by noise level (not in git)
```

`human/` is the answer key. The forward agent never sees it, and nothing in a
run directory points at it. `story.md` is one file with `# Chapter N:` headings,
numbered to match the episodes.

## The example: Valkaama (2010)

| | |
|---|---|
| Screenplay | Tim Baumann |
| Based on a novel by | Hendrik Behnisch |
| Licence | [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/) |
| Source | <http://www.valkaama.com/media/script/Valkaama_v.2007-06-30(English-Final).pdf> |
| Mirror | Internet Archive, snapshot 2012-04-22 |
| sha256 | `53fbfff56397803cf1259ce9798da071c07dc7bf9332d8ed7051286e370c1664` |

Valkaama is an open source feature film, made the way open source software is
made: the script, the footage and the music were all released under free
licences. The licence is printed on the title page of the screenplay itself, so
it does not depend on any website staying up.

Ninety pages, fifty-seven numbered scenes, standard master-scene format with
sluglines, centred character names and parentheticals. Real text layer, so
`pdftotext -layout` gets it out cleanly. The road-movie structure splits into
three geographic acts, which makes the episode boundaries fall in sensible
places.

Two things make it a better example than a famous film would be. It is obscure
enough that a model is unlikely to have memorised it, which matters when the
whole experiment depends on the forward agent not having seen the answer. And
the English is European and slightly formal, with a few typos a human left in,
so it does not read like the default register a model falls into. That makes the
gap between the two versions easier to see.

**Licence note.** The code in this repository is MIT. The screenplay is CC
BY-SA 3.0 and is not distributed with it, which is why there is a download
script instead of a file. If you redistribute anything derived from the
screenplay, including the noised `story.md` or generated screenplays, ShareAlike
applies to that material. Training on it privately is unaffected.

## More screenplays, if you want a real batch

One work per step still trains, but a batch of four is where the loop starts
generalising instead of patching. These are the other freely licensed
feature-length screenplays that turned up while looking for the example. Each
one's licence was checked against the document itself or its host's metadata,
but none of them has been run through this pipeline, so treat the formatting
notes as a starting point rather than a promise.

| Screenplay | Pages | Licence | Where to get it |
|---|---|---|---|
| A Sad State of Affairs | 101 | CC BY-SA 3.0 US | archive.org item `ASadStateOfAffairsscreenplay`. Native text layer, no cleanup needed |
| The Pizza Joint | 108 | CC BY 3.0 | archive.org item `ThePizzaJoint`. Scanned, use the OCR derivative |
| Lizard People | ~90 | CC0 1.0 | `github.com/mklingen/LizardPeople`. Fountain, not PDF, so use `--text` |
| The Boy Who Never Slept | 82 | CC BY 2.5 | Scanned with no text layer. You will have to OCR it first |

Two traps worth knowing about if you go looking for more. Archive.org's licence
field is supplied by whoever uploaded the file and is not checked, and there is
a large cluster of famous studio screenplays mislabelled as public domain there.
And on GitHub, a repository's MIT licence covers the parser, not the screenplay
sitting in its test fixtures. Read the licence off the document when you can.

Public domain by age does not work here, in case you were about to try. US works
published before 1931 are unambiguously free, but that cutoff lands just before
sound: everything old enough to qualify is a silent continuity, with intertitles
instead of dialogue under character names.

## Using your own screenplay

```bash
python3 s0_prepare_data.py --pdf path/to/script.pdf --work data/mywork --episodes 20
python3 s1_diffuse.py --work data/mywork
```

`s0` prints how each episode came out. Read a couple of the files before
training. If the extraction mangled the layout, everything downstream inherits
the damage, and a bad ground truth is worse than no ground truth. Scans with no
text layer will not work. OCR them first.
