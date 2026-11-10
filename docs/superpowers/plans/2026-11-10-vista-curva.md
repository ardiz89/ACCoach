# Curva per curva — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** a new report tab «Curva per curva» that aggregates one session's laps per corner (loss, phases, cause, braking, line) and shows what the public sources say about that corner.

**Architecture:** a pure aggregation module (`coaching/corner_session.py`) turns per-lap debriefs, brake points and line reports into per-corner summaries; a loader (`trackfacts/__init__.py`) reads the exported source facts; a new endpoint `/api/corners` wires both; the web report gets one tab rendered by `app.js`. The fonti export gains a `disputed` list so the page can show sources that disagree.

**Tech Stack:** Python 3.14, FastAPI (`api.py`), plain JS (`web/app.js`, `web/i18n.js`), pytest.

**Spec:** `docs/superpowers/specs/2026-11-10-vista-curva-design.md`

## Global Constraints

- No AI anywhere in the report: numbers from the driver's laps and `trackfacts/*.json`, fixed rules, sentences as templates in code.
- «Una fonte dice» is never a reference: it never reaches voice, focus, training plan, and is never styled like a reference.
- Never a sentence that sets a braking board as a target («frena ai 100»). Only the gear is compared with sources («Tu: terza. Una fonte: seconda.»).
- Italian copy: «tu», short sentences, decimal comma, no colons for effect, no emoji, ≤25 words per sentence (`tests/test_tono.py`). Every new Italian string passes `tono.violations(text, "it") == []`.
- Tests always with the fake home: `USERPROFILE`/`HOME` = scratchpad `ov/casa`, `QT_QPA_PLATFORM=offscreen`, `PYTHONPATH=src`. Never `Documents\ACCoach`, never port 8778.
- Keep each file's line endings. Commit trailers: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_015rMgt45HYsP5VgTvkAVCs3`. No push, no install, no EXE.
- New behaviour documented in `GUIDA.md` and `docs/FAQ.md` (English), in the report section.

## Review Focus

1. A session with one valid lap: the tab shows that lap's numbers and says it is one lap, no medians over nothing (Task 3 test).
2. A track with no `trackfacts` file (Monza today): the sources block is absent, the rest works (Task 4 test).
3. A corner renamed by the driver: sources still match it by catalog position, not by the typed name (Task 4 test).
4. A lap whose debrief or line report raises: that lap is skipped and counted in `skipped`, the endpoint still answers (Task 4 test).
5. A `trackfacts` file with an unknown `version` or broken JSON: ignored, sources block absent, no 500 (Task 2 test).

---

### Task 1: the export carries the sources that disagree

**Files:**
- Modify: `tools/fonti/export.py`
- Modify: `src/accoach/trackfacts/imola.json`, `src/accoach/trackfacts/spa.json` (re-exported)
- Test: `tests/test_fonti_export.py`

**Interfaces:**
- Produces: `export.disputed(conn, track) -> list[dict]`; file key `"disputed"`; `VERSION = 3`.
  Each item: `{"corner", "type", "why": "conteso"|"respinto", "values": [{"value", "n", "sources": [...]}], "reason"?: str}`; `reason` is the cut (`cut()`) quote of the first `respinto` factcheck when `why == "respinto"`.

- [ ] **Step 1: test** `test_export_contesi_e_respinti_a_parte`: with `_riempi(b)` (Rivazza/gear is verified and `respinto`), the exported file has `version == 3`, an item in `disputed` with `corner == RIV`, `type == "gear"`, `why == "respinto"`, values containing `"2"`; Rivazza/gear is in neither `facts` nor `single`. Add a `conteso` case (two values with ≥2 authors each, as in the consensus tests) and assert `why == "conteso"` with both values.
- [ ] **Step 2:** run, expect FAIL (`KeyError: 'disputed'`).
- [ ] **Step 3:** implement `disputed()`: consensus entries with `state == "conteso"`, plus `verificato` entries whose `status(...) == "respinto"`. Values as in `single()` (descriptive values cut). `dumps(track, items, singles, disputed)`; bump `VERSION = 3` with comment `# 3: la lista disputed`. Update the module docstring and `tools/fonti/README.md` (one line).
- [ ] **Step 4:** tests pass: `pytest tests/test_fonti_export.py -q`.
- [ ] **Step 5:** re-export both tracks with `python tools/fonti/fonti.py --db <cartella del database delle fonti> export --track imola` and `--track spa`; check Spa has the Bus Stop gear in `disputed`.
- [ ] **Step 6:** commit «Fonti: l'esportazione porta anche le fonti in disaccordo».

### Task 2: the report reads the source facts

**Files:**
- Modify: `src/accoach/trackfacts/__init__.py` (empty today)
- Test: `tests/test_trackfacts.py` (new)

**Interfaces:**
- Produces:
  - `KNOWN_VERSIONS = (2, 3)`
  - `load(track: str, root: Path | None = None) -> dict | None` — reads `<root or package dir>/<track>.json`; `None` if missing, unreadable, not a dict, or `version` not in `KNOWN_VERSIONS`; logs one warning (module logger) on unreadable/unknown version.
  - `for_corner(facts: dict | None, catalog_name: str) -> dict` — `{"reference": [...], "single": [...], "disputed": [...], "mistakes": [...]}`; `reference` from `facts`, `single` = `single` items whose type is not `mistake` or `line`, `mistakes` = `single` items of type `mistake`, `line` items go in `single`; `disputed` from `disputed` (absent in v2 → empty). Empty lists when `facts` is None or the corner has nothing.
  - `gear_compare(you_gear: str | None, corner: dict) -> dict | None` — `{"you": "3", "source": "2", "state": "single"|"reference"}` when the driver's gear and the first `gear` value (reference first, then single) are both digits and differ; `None` otherwise.

- [ ] **Step 1: tests** (write a temp `root` with fixture JSONs):
  - `test_load_pista_assente` → `load("monza", root=tmp)` is None.
  - `test_load_versione_ignota_e_json_rotto` → version 99 → None; file `"{"` → None; no exception.
  - `test_for_corner_divide_per_gruppo` → a v3 file with one `facts` gear, one `single` brake, one `single` mistake, one `disputed` gear for «Tosa»: each lands in its group; another corner gets four empty lists.
  - `test_gear_compare` → you "3", single gear "2" → `{"you": "3", "source": "2", "state": "single"}`; same gear → None; you None → None; reference wins over single.
  - `test_file_veri_si_leggono` → `load("imola")` and `load("spa")` from the package are dicts with `version` 3.
- [ ] **Step 2:** run, expect FAIL (import error).
- [ ] **Step 3:** implement with `Path(__file__).parent` as default root, `json.loads(read_text("utf-8"))`.
- [ ] **Step 4:** `pytest tests/test_trackfacts.py -q` passes.
- [ ] **Step 5:** commit «Report: il lettore dei fatti dalle fonti».

### Task 3: the session, corner by corner

**Files:**
- Create: `src/accoach/coaching/corner_session.py`
- Test: `tests/test_corner_session.py` (new)

**Interfaces:**
- Consumes: `CornerLoss` (coaching/debrief.py:360: `index, lost_ms, category, message, phases`), `BrakePoint` (braking_points.py:53: `index, speed_kmh, distance_m, gear_min`), `CornerLine` (trajectory.py:108: `index, entry_m, apex_m, exit_m, apex_shift_m, sided, off_here`).
- Produces:
  - `NOISE_MS = 50.0` — a lap «loses» in a corner above this.
  - `@dataclass LapCorners(path: str, losses: list[CornerLoss], brakes: list[BrakePoint], lines: list[CornerLine])`
  - `@dataclass CornerSummary`: `index: int, laps: int, lost_total_ms: float, laps_losing: int, phases_ms: dict[str, float]` (median per phase over laps with phases), `cause: str | None` (CueCategory value), `cause_message: str`, `cause_laps: int`, `brake_m: float | None` (median `distance_m`, >0 only), `brake_spread_m: float | None` (max−min), `brake_kmh: float | None` (median), `gear_min: str | None` (most frequent; ties → lowest digit), `line_m: dict[str, float] | None` (median entry/apex/exit over laps not `off_here`), `apex_shift_m: float | None`, `sided: bool`, `best_path: str | None` (lap with min `lost_ms`), `typical_path: str | None` (lap whose `lost_ms` is closest to the median; ties → earlier lap).
  - `aggregate(laps: list[LapCorners]) -> list[CornerSummary]` — sorted by `lost_total_ms` desc, then `index`.
  - `cause` is set only when `cause_laps * 2 >= laps_losing` and `laps_losing > 0` («di solito»); otherwise None.
- [ ] **Step 1: tests** with hand-built dataclass instances (no laps on disk):
  - `test_ordine_per_tempo_perso` — corner 2 losing 300 ms total sorts before corner 0 losing 120 ms.
  - `test_causa_di_solito_solo_se_torna_in_meta_dei_giri` — 4 losing laps, cause A on 2 → cause A; on 1 → None.
  - `test_fasi_mediane` — phases `[("entry", 100), ("apex", 20)]`, `[("entry", 300), ...]`, `[("entry", 200), ...]` → `phases_ms["entry"] == 200`.
  - `test_frenata_mediana_e_dispersione` — distances 80, 90, 100 → `brake_m == 90`, `brake_spread_m == 20`; a 0 distance is ignored.
  - `test_marcia_piu_frequente` — "3","3","2" → "3"; "2","3" → "2".
  - `test_giro_migliore_e_tipico` — losses 50, 200, 210, 400 by path a,b,c,d → best "a", typical "b" (median 205, |200−205| = |210−205|, earlier wins).
  - `test_un_giro_solo` — one lap → `laps == 1`, medians equal that lap's values, `typical_path == best_path`.
  - `test_fuori_pista_non_conta_per_la_linea` — the `off_here` line is excluded from `line_m`.
- [ ] **Step 2:** run, expect FAIL.
- [ ] **Step 3:** implement with `statistics.median`; corners keyed by `index`.
- [ ] **Step 4:** `pytest tests/test_corner_session.py -q` passes.
- [ ] **Step 5:** commit «Report: la sessione curva per curva».

### Task 4: `/api/corners`

**Files:**
- Modify: `src/accoach/api.py` (new endpoint next to `/api/sessions`, ~line 1833)
- Test: `tests/test_api_corners.py` (new; pattern of `tests/test_api_sessions.py`, `synth.build_lap`, CAR `ferrari_488_gt3`, TRACK `monza`)

**Interfaces:**
- Consumes: Task 2 `load`, `for_corner`, `gear_compare`; Task 3 `LapCorners`, `aggregate`; existing `group_sessions`, `_own`, `_own_valid`, `_elected_path`, `_conditions_of`, `Reference`, `detect_corners`, `name_corners`, `corner_bests_for`, `build_lap_debrief`, `brake_points_of_lap`, `build_line_report`, `load_lap`.
- Produces: `GET /api/corners?car&track&index=0&lang` →
  `{"index", "laps", "skipped", "reference": {"path", "lap_time_ms"}, "corners": [ {"index", "name", "catalog_name", "apex", ...CornerSummary fields..., "sources": for_corner(...), "gear_compare": gear_compare(...)} ], "has_sources": bool}`; `{"corners": [], "laps": 0}` when there is no session or no valid lap.
- Rules: the session is `group_sessions(_own(rows))[index]` (clamped, as `/api/sessions`); laps = its valid laps; the reference is the elected lap for the session's best lap conditions (`_elected_path` with the best lap's `_conditions_of`); corners detected on the reference; `corner_refs` as `/api/analysis` does (elected and not PRO), per lap; a lap whose debrief/brakes/line raise is skipped and counted in `skipped`. `catalog_name` = `name_corners(track, corners, lg, None, None)` — the catalog name by position, ignoring typed names and the learned map — and sources match on it.
- [ ] **Step 1: tests:**
  - `test_sessione_vuota` → no laps → `corners == []`, `laps == 0`, status 200.
  - `test_curve_della_sessione` → 3 laps in one session, one with `slow_corner=1, amt=20` → status 200, `laps == 3`, the slowest corner first, each corner has `phases_ms`, `brake_m`, `line_m` keys.
  - `test_solo_la_sessione_scelta` → two sessions a week apart; `index=1` counts only the older session's laps.
  - `test_senza_fatti_niente_fonti` → Monza has no trackfacts → `has_sources is False`, each `sources` has four empty lists.
  - `test_fonti_abbinate_per_posizione` → monkeypatch `accoach.trackfacts.load` to return a v3 dict with a `single` gear for the catalog name of the first corner, and a typed name for that corner (`cornernames` like `tests/test_api_corner_name.py`); the corner's `sources["single"]` is non-empty and `name` is the typed one.
  - `test_un_giro_guasto_si_salta` → monkeypatch `build_line_report` (as imported in api) to raise for one path → `skipped == 1`, status 200.
- [ ] **Step 2:** run, expect FAIL (404).
- [ ] **Step 3:** implement.
- [ ] **Step 4:** `pytest tests/test_api_corners.py -q` passes, then the full suite.
- [ ] **Step 5:** commit «Report: /api/corners, la sessione curva per curva con le fonti».

### Task 5: the tab

**Files:**
- Modify: `src/accoach/web/index.html` (button in the «How today went» group after `data-view="session"`, panel `#view-corners`)
- Modify: `src/accoach/web/app.js` (`loadCorners`, `renderCorners`, hooked in `showView`/`redrawCurrentView` like `session`)
- Modify: `src/accoach/web/i18n.js` (keys `tab.corners` and `corners.*`, en + it)
- Modify: `GUIDA.md`, `docs/FAQ.md`
- Test: `tests/test_report_corners_tab.py` (new)

**Interfaces:**
- Consumes: Task 4 JSON.
- Produces: tab `data-view="corners"`, label it «Curva per curva», en «Corner by corner».
- Copy (Italian, exact): group headings «Quanto e dove perdi», «La tua frenata», «La tua traiettoria», «Cosa dicono le fonti»; source groups «Riferimento», «Una fonte dice», «Le fonti non concordano», «Errori che altri segnalano qui»; gear line «Tu: {you}. Una fonte: {source}.» (with «Il riferimento» instead of «Una fonte» when `state == "reference"`), gear words «prima … sesta»; one-lap note «Una sola tornata valida: sono i numeri di quel giro.»; empty «Nessun giro valido in questa sessione.».
- Rendering rules: one collapsible row per corner in API order; a source item shows the cut quote in `<q>`, author count, and a link (`url`, with `?t=Ns` when `start_s` is set, same as the review page) opening in a new tab; «Una fonte dice» items use the neutral text colour, never the reference/accent colour; numbers with decimal comma (`toLocaleString('it-IT')` as the rest of `app.js`); brake as «{m} m prima del punto più lento, ±{spread} m»; line as signed metres with «dentro»/«fuori» when `sided`. No braking board text is ever composed by the page.
- [ ] **Step 1: tests:** `index.html` has the `corners` tab button in the first group and `#view-corners`; `i18n.js` has `tab.corners` and every `corners.*` key in both `en` and `it`; every Italian `corners.*` string passes `tono.violations(text, "it") == []`; `app.js` defines `renderCorners` and never contains the substring `frena ai` / `brake at the`; GUIDA.md mentions «Curva per curva», FAQ.md mentions «Corner by corner».
- [ ] **Step 2:** run, expect FAIL.
- [ ] **Step 3:** implement.
- [ ] **Step 4:** tests pass; full suite passes.
- [ ] **Step 5:** controller check in the browser on a test port (never 8778) with the real laps copied into the fake home: Imola session of 08/11, the tab opens, Acque Minerali shows its blocks and the «Una fonte dice» items.
- [ ] **Step 6:** commit «Report: la scheda Curva per curva».
