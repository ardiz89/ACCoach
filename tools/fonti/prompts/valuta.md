prompt_version: 1

# Rate the speaker (kind: rate)

You receive one job file (`rate-*.job.json`) with `body`, `segments`, `meta` and
`track`. Say who is speaking and what they state about themselves. Your answer is read
by a program. Every quote is checked against `body` character for character, and
every claim you make must have its own quote. One claim without its quote and the
whole answer is thrown away.

## Output

Return ONLY this JSON object. No prose, no Markdown fences, no extra keys:

```
{"sha256": "<the job's sha256>", "kind": "rate",
 "prompt_version": "<the job's prompt_version>", "track": "<the job's track>",
 "speaker": {"name": "...", "role": "pilota|coach|anonimo"},
 "lap_time": "1:41.2" or null,
 "car": "..." or null,
 "reasons": [{"field": "name|role|lap_time|car", "claim": "...", "quote": "...", "offset": 0}]}
```

- `prompt_version` and `track`: copy them from the job, unchanged. An answer to an old
  version of the job is thrown away.
- `speaker.name`:
  - the name the speaker gives for themselves in `body`; it needs a reason with
    `"field": "name"` whose quote has the name right after "I'm", "I am",
    "my name is", "sono" or "mi chiamo";
  - or the author of this text exactly as it appears in `meta` (`author`); then no
    quote is needed;
  - never a corner name or a word of the advice (a gear, a brake marker, apex, kerb);
  - otherwise the empty string `""`.
- `speaker.role`:
  - `coach` only if the text states they coach or teach driving;
  - `pilota` only if the text states they race (a series, a team, a result);
  - `anonimo` in every other case.
  `coach` and `pilota` need a reason with `"field": "role"` quoting the speaker saying
  it about themselves, in the first person, not negated:
  - `coach`: "I'm a (driver/driving/sim racing) coach", "I am an instructor",
    "I coach" or "I teach" followed within 4 words by who or what is coached:
    drivers, driving, racing, sim racing, people to drive, students, clients,
    racecraft, guida, piloti ("I coach drivers in ACC", "I teach racecraft to
    students"; not "I teach you to brake", "I coach myself"),
    "sono/faccio il coach", "faccio l'istruttore",
    "insegno a guidare", "insegno guida", "insegno ai piloti";
  - `pilota`: "I race in/for", "I drive for", "I'm a driver for", "corro nel/per/in",
    each followed within 6 words by a series or team word: championship, campionato,
    league, lega, series, serie, GT World, GTWC, LFM, SRO, esports, endurance, team,
    scuderia ("I race in the LFM championship", "corro per il team Rossi");
    "sono (un) pilota" only if the same quote has one of those words.
  A word alone does not count: "the racing line", "the Coach Dave setup",
  "my coach told me", "in the race", "this team" say nothing about the speaker.
  Racing without a series or team is not `pilota`: "I'm a sim racer",
  "I race in public lobbies", "corro con la Ferrari", "sono un pilota della domenica".
  Reported words are not the speaker: a role quote with a quotation mark, or with
  "says", "said", "dice", "disse", "ha detto", "secondo lui", "according to" in it or in
  the 6 words before it, does not count.
- `lap_time`: a lap time the speaker states for their own lap at this track, copied as
  written, in the form `m:ss.d` (`1:41.2`, `1:41,234`); otherwise null. Not null needs a reason with `"field": "lap_time"` whose
  quote contains the lap time exactly as you wrote it.
- `car`: the car the speaker states they drive, copied as written; otherwise null. Not
  null needs a reason with `"field": "car"` whose quote contains the car exactly as you
  wrote it. A gear, a corner or a brake marker is not a car.
- Each reason:
  - `field` says which claim it supports;
  - `claim` says in a few words what the quote shows;
  - `quote` is copied character for character from `body`: the shortest clause of 4
    or more words that supports the claim;
  - `offset` is the character index in `body` where the quote starts (0-based).

## Rules

1. Never infer a role from skill, speed or confidence. Only a stated fact counts.
2. Never translate or paraphrase a quote.
3. A claim you cannot quote is left out: name `""`, role `anonimo`, `lap_time` null,
   `car` null. That is always a valid answer.
4. If the text is not about Imola in Assetto Corsa Competizione (ACC), answer name
   `""` (or the `meta` author), role `anonimo`, `lap_time` null, `car` null and
   `"reasons": []`.
