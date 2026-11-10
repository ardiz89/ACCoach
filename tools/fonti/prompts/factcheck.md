prompt_version: 2

# Fact-check one verified fact (kind: factcheck)

You receive one job file (`factcheck-*.job.json`). It has `fact` (corner, type, the
values with their authors and quotes, and `fact_key`) and `texts`: the ACC texts of the
job's `track` that name that corner, each with `body` and `meta`. The texts the fact
comes from are there too, so you can read them in context.

Each `body` is an excerpt: only the sentences that name the corner, plus one sentence
before and one after. Separate pieces of the same text are joined by a line with `[…]`.
Quote and count `offset` on `body` exactly as given.

Decide if the fact holds when you read the quotes in their full context. Look for
irony, a negation further away, a statement about another corner, another car class,
another game or an old track layout, or a later correction by the same author.

## Output

Return ONLY this JSON object. No prose, no Markdown fences, no extra keys:

```
{"fact_key": "<fact.fact_key>", "kind": "factcheck",
 "prompt_version": "<the job's prompt_version>", "track": "<the job's track>",
 "verdict": "confermato|respinto|non_confermato", "reason": "...", "quote": "...", "offset": 0}
```

- `prompt_version` and `track`: copy them from the job, unchanged. An answer to an old
  version of the job is thrown away.
- `verdict`:
  - `confermato` if an independent text supports the fact as stated;
  - `respinto` if any text contradicts it (another value for the same corner, irony, a
    correction) or the fact's own quotes do not mean what the fact says;
  - `non_confermato` if no independent text supports it and none contradicts it:
    the fact's own quotes hold, but nobody else says it.
- `reason`: one short sentence, in English, saying why.
- `quote`: the passage that supports your verdict, copied character for character from
  one `body` in `texts`, the shortest clause of 4 or more words, inside one piece. A
  quote that contains `[…]` or crosses that line is thrown away. Never translate or
  paraphrase.
  - For `confermato` it must come from a text whose `sha256` is NOT in `fact_sha256s`
    and whose author (`platform:author` in `meta`) is NOT in `fact_authors`: those are
    the texts and the authors the fact comes from, and a fact cannot confirm itself.
  - For `respinto` it may come from any text, the fact's own texts included: irony or
    a later correction by the same author is a valid reason to reject. It must be the
    passage that contradicts the fact.
  - For `non_confermato` it may come from any text: give the fact's own supporting
    passage.
- `offset`: the character index in that `body` where the quote starts.

## Rules

1. Never infer beyond what the texts say.
2. If you cannot find an independent supporting quote, answer `non_confermato`, unless
   a text contradicts the fact: then `respinto`.
3. When in doubt between `confermato` and anything else, do not confirm. A wrong
   confirmation is the serious failure. Never answer `respinto` without a quote that
   contradicts the fact.
