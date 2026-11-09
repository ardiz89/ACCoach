prompt_version: 1

# Rate the speaker (kind: rate)

You receive one job file (`rate-*.job.json`) with `body`, `segments`, `meta` and
`track`. Say who is speaking and what they state about themselves. Your answer is read
by a program, and every quote is checked against `body` character for character.

## Output

Return ONLY this JSON object. No prose, no Markdown fences, no extra keys:

```
{"sha256": "<the job's sha256>", "kind": "rate",
 "speaker": {"name": "...", "role": "pilota|coach|anonimo"},
 "lap_time": "1:41.2" or null,
 "car": "..." or null,
 "reasons": [{"claim": "...", "quote": "...", "offset": 0}]}
```

- `speaker.name`: the name the speaker gives for themselves in `body`, or the channel
  or user name in `meta` if the body names no one. Empty string if unknown.
- `speaker.role`:
  - `coach` only if the text states they coach or teach driving;
  - `pilota` only if the text states they race (a series, a team, a result);
  - `anonimo` in every other case.
- `lap_time`: a lap time the speaker states for their own lap at this track, copied as
  written; otherwise null.
- `car`: the car the speaker states they drive, copied as written; otherwise null.
- `reasons`: one entry for each claim above that is not empty or `anonimo` (name from
  the body, role, lap time, car). `claim` says in a few words what the quote supports.
  `quote` is copied character for character from `body`, the shortest clause of 4 or
  more words that supports that claim. `offset` is the character index in `body` where
  the quote starts.

## Rules

1. Never infer a role from skill, speed or confidence. Only a stated fact counts.
2. Never translate or paraphrase a quote.
3. A claim without a supporting quote in `body` is left out: role `anonimo`,
   `lap_time` null, `car` null.
4. If the text is not about Imola in Assetto Corsa Competizione (ACC), still answer,
   with role `anonimo`, `lap_time` null, `car` null and `"reasons": []`, unless the
   speaker's identity is stated.
