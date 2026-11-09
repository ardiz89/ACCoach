prompt_version: 1

# Extract corner facts (kind: extract)

You receive one job file (`extract-*.job.json`). It has `body` (the text), `segments`
(subtitles, or null), `meta` (where the text comes from), `track` and `corners` (the
only corner names you may use, spelled exactly as listed).

Your answer is read by a program, not a person. A deterministic verifier checks every
fact against `body`. Anything it cannot find character for character is thrown away.

## Output

Return ONLY this JSON object. No prose, no Markdown fences, no extra keys:

```
{"sha256": "<the job's sha256>", "kind": "extract",
 "prompt_version": "<the job's prompt_version>", "track": "<the job's track>",
 "facts": [{"corner": "...", "type": "...", "value": "...", "quote": "...", "offset": 0}]}
```

- `prompt_version` and `track`: copy them from the job, unchanged. An answer to an old
  version of the job is thrown away.
- `corner`: one name from `corners`, exactly as written there.
- `type`: one of `brake`, `gear`, `apex`, `kerb`, `line`, `mistake`.
- `value`:
  - `brake`: `board:50|100|150|200|250|300`, or `object:bridge|tyre_wall|kerb_start|marshal_post|apex_kerb`;
  - `gear`: a digit `1`-`6`;
  - `apex`: `early|middle|late`;
  - `kerb`: `entry|apex|exit|none`;
  - `line` and `mistake`: the quote itself, identical to `quote`.
- `quote`: copied character for character from `body`. Same spelling, same case, same
  punctuation. Never translate, never paraphrase, never fix typos.
- `offset`: the character index in `body` where `quote` starts (0-based, counted on
  `body` exactly as given).

## Rules

1. Make each quote the shortest clause of 4 or more words that supports one fact.
2. One fact per quote and type. Do not combine two facts in one entry.
3. The quote must stay inside one sentence (or one subtitle line).
4. Never infer. Report only what the text states. A brake point "a bit later than
   the 100" is not `board:100`: leave it out.
5. Leave out anything negated, hedged ("maybe", "if", "or"), or about another game,
   another track or a car-specific setup you cannot tie to the text.
6. The corner must be named in the text near the quote, before it or right after the
   value ("brake at the 100 board into Tosa").
7. If the text is not about Imola in Assetto Corsa Competizione (ACC), or states no
   such fact, return `"facts": []`.
8. When in doubt, leave the fact out. A missing fact costs nothing; an invented one is
   a defect.
