"""Raccolta dalle fonti pubbliche via Apify, con tetto di spesa.

Ogni voce del piano è una corsa di un attore Apify:

- prima di pagare si salva l'id della corsa in `collect_runs`; se l'attesa finisce
  prima della corsa, il prossimo `collect` la riprende e non la paga di nuovo;
- gli elementi grezzi del dataset si salvano in `raw_items` prima di leggerli;
- ogni elemento si legge per conto suo: uno guasto si salta e gli altri restano;
- una voce che non dà nemmeno un testo non si segna finita;
- ogni voce ha una quota fissa del tetto: quanto resta diviso le voci ancora da fare.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone

from tools.fonti import apify, db

# ACC si riconosce solo dal titolo o dal sottoreddit: un hashtag nella descrizione no.
_ACC = re.compile(r"assetto corsa competizione|\bacc\b", re.IGNORECASE)
# Un titolo che nomina anche l'altro gioco parla di tutti e due: non è una fonte su ACC.
_MIXED = re.compile(r"\bac\s+vs\.?\s+acc\b|\bacc\s+vs\.?\s+ac\b|\bac1\b|\bassetto corsa 1\b",
                    re.IGNORECASE)
_GT3 = re.compile(r"(?<![a-z0-9])gt3(?![a-z0-9])")
_GT4 = re.compile(r"(?<![a-z0-9])gt4(?![a-z0-9])")
_TS = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)")
_POST_ID = re.compile(r"/comments/([A-Za-z0-9]+)")
CLASSES = ("gt3", "gt4", "ignota")


def game_of(title: str, description: str, subreddit: str) -> str:
    """`acc` o `altro`. La descrizione non conta mai: lì stanno gli hashtag di tutti i giochi."""
    title = title or ""
    if _MIXED.search(title):
        return "altro"
    if (subreddit or "").lower() == "accompetizione":
        return "acc"
    return "acc" if _ACC.search(title) else "altro"


def car_class_of(title, description, extra) -> str:
    """`gt3` o `gt4` se la fonte ne nomina una sola, a parola intera; altrimenti `ignota`."""
    text = " ".join(str(x or "") for x in (title, description, extra)).lower()
    gt3, gt4 = bool(_GT3.search(text)), bool(_GT4.search(text))
    if gt3 != gt4:
        return "gt3" if gt3 else "gt4"
    return "ignota"


def parse_srt(srt: str) -> list[dict]:
    segs = []
    for blocco in re.split(r"\n\s*\n", (srt or "").strip()):
        righe = [r for r in blocco.splitlines() if r.strip()]
        for i, r in enumerate(righe):
            if "-->" in r:
                m = _TS.search(r)
                testo = " ".join(x.strip() for x in righe[i + 1:])
                if m and testo:
                    h, mi, s, ms = (int(x) for x in m.groups())
                    segs.append({"start_s": round(h * 3600 + mi * 60 + s + ms / 1000, 3), "text": testo})
                break
    return segs


def _source(conn, platform, url, author, title, published, game, track, meta, car_class,
            full: bool = True) -> tuple[int, bool]:
    """La fonte con quell'URL; `(id, nuova)`.

    `full` dice che l'elemento porta i dati veri della fonte (il post, il video): se la
    fonte c'era già, minima perché creata da un commento arrivato prima, si aggiorna.
    """
    if not url:
        raise ValueError("url mancante")
    riga = conn.execute("SELECT id FROM sources WHERE url=?", (url,)).fetchone()
    dati = (author, title, published, game, track, json.dumps(meta, ensure_ascii=False, sort_keys=True),
            car_class)
    if riga is None:
        cur = conn.execute(
            "INSERT INTO sources(platform, url, author, title, published, game, track, meta_json,"
            " car_class) VALUES (?,?,?,?,?,?,?,?,?)", (platform, url, *dati))
        conn.commit()
        return cur.lastrowid, True
    if full:
        conn.execute("UPDATE sources SET author=?, title=?, published=?, game=?, track=?, meta_json=?,"
                     " car_class=? WHERE id=?", (*dati, riga[0]))
        conn.commit()
    return riga[0], False


def _post_id(item: dict) -> str | None:
    """L'id del post del thread: dal campo dell'elemento, o dal suo permalink."""
    tipo = item.get("dataType")
    for campo in (("id",) if tipo == "post" else ("postId", "parentId")):
        v = item.get(campo)
        if isinstance(v, str) and (tipo == "post" or v.startswith("t3_")):
            v = v[3:] if v.startswith("t3_") else v
            if re.fullmatch(r"[A-Za-z0-9]+", v):
                return v
    m = _POST_ID.search(item.get("url") or "")
    return m.group(1) if m else None


def thread_url(post_id: str) -> str:
    return f"https://www.reddit.com/comments/{post_id}/"


def _youtube(conn, item, track) -> tuple[int, int, bool]:
    """`(fonte nuova, testo nuovo, c'è un testo)` per un video."""
    subs = item.get("subtitles") or []
    srt = next((s.get("srt") for s in subs if isinstance(s, dict) and s.get("srt")), None)
    title, desc = item.get("title"), item.get("text")
    sid, nuova = _source(conn, "youtube", item.get("url"), item.get("channelName"), title,
                         item.get("date"), game_of(title, desc, ""), track,
                         {"video_id": item.get("id")}, car_class_of(title, desc, ""))
    segs = parse_srt(srt) if srt else []
    if not segs:
        return int(nuova), 0, False
    corpo = " ".join(s["text"] for s in segs)
    nt = int(db.add_text(conn, sid, "transcript", item.get("channelName") or "", corpo, segs)[1])
    return int(nuova), nt, True


def _reddit(conn, item, track) -> tuple[int, int, bool]:
    """`(fonte nuova, testo nuovo, c'è un testo)` per un post o un commento."""
    tipo = item.get("dataType")
    if tipo not in ("post", "comment"):
        return 0, 0, False
    sub = item.get("parsedCommunityName") or item.get("communityName") or ""
    corpo = (item.get("body") or "").strip()
    pid = _post_id(item)
    if pid is None:
        raise ValueError("post senza id")
    if tipo == "post":
        title = item.get("title")
        flair = item.get("flair") or item.get("linkFlairText")
        sid, nuova = _source(conn, "reddit", thread_url(pid), item.get("username"), title,
                             item.get("createdAt"), game_of(title, corpo, sub), track,
                             {"subreddit": sub, "post_id": pid, "flair": flair},
                             car_class_of(title, corpo, f"{flair or ''} {sub}"))
        testo = f"{title or ''}\n{corpo}".strip()
        if not testo:
            return int(nuova), 0, False
        return int(nuova), int(db.add_text(conn, sid, "post", item.get("username") or "", testo)[1]), True
    if not corpo:
        return 0, 0, False
    # Il post del thread può arrivare dopo: intanto una fonte minima, che il post completerà.
    sid, nuova = _source(conn, "reddit", thread_url(pid), None, None, item.get("createdAt"),
                         game_of("", "", sub), track, {"subreddit": sub, "post_id": pid},
                         car_class_of("", "", sub), full=False)
    return int(nuova), int(db.add_text(conn, sid, "comment", item.get("username") or "", corpo)[1]), True


def entry_key(voce: dict) -> str:
    canon = json.dumps({"actor": voce["actor"], "input": voce["input"], "max_items": voce["max_items"]},
                       sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def finished(conn: sqlite3.Connection, track: str) -> set[str]:
    return {k for (k,) in conn.execute(
        "SELECT entry_key FROM collect_runs WHERE track=? AND finished_at IS NOT NULL", (track,))}


def _log(msg: str) -> None:
    print(msg, file=sys.stderr)


def collect(conn: sqlite3.Connection, client: apify.Apify, track: str, plan: list[dict],
            cap_usd: float = apify.CAP_USD, force: bool = False, only: int | None = None,
            polls: int = apify.POLLS) -> dict:
    """Raccoglie le voci del piano (`only`: solo la voce con quel numero, da 1)."""
    if only is not None and not 1 <= only <= len(plan):
        raise ValueError(f"Il piano ha {len(plan)} voci: --only va da 1 a {len(plan)}.")
    ns = nt = saltate = guasti = 0
    vuote: list[int] = []
    for i, voce in enumerate(plan, 1):
        if only is not None and i != only:
            continue
        chiave = entry_key(voce)
        riga = conn.execute("SELECT run_id, finished_at FROM collect_runs WHERE track=? AND entry_key=?",
                            (track, chiave)).fetchone()
        if riga and riga[1] and not force:
            saltate += 1
            continue
        if riga and riga[0] and not riga[1] and not force:
            run_id = riga[0]   # una corsa già pagata: si riprende
        else:
            resto = apify.guard(conn, client, track, cap_usd)
            da_fare = {entry_key(v) for v in plan} - finished(conn, track) | {chiave}
            run = client.start_run(voce["actor"], voce["input"], voce["max_items"],
                                   max_charge_usd=resto / len(da_fare))
            run_id = run["id"]
            conn.execute("INSERT OR REPLACE INTO collect_runs(track, entry_key, finished_at, items,"
                         " spent_usd, run_id) VALUES (?,?,NULL,NULL,NULL,?)", (track, chiave, run_id))
            conn.commit()
        run = client.wait_run(run_id, polls)
        if conn.execute("SELECT spent_usd IS NULL FROM collect_runs WHERE track=? AND entry_key=?",
                        (track, chiave)).fetchone()[0]:
            costo = float(run.get("usageTotalUsd") or 0.0)
            conn.execute("UPDATE collect_runs SET spent_usd=? WHERE track=? AND entry_key=?",
                         (round(costo, 4), track, chiave))
            conn.execute("UPDATE spend SET runs_usd = COALESCE(runs_usd, 0) + ?, last_usd=? WHERE track=?",
                         (costo, client.usage_usd(), track))
            conn.commit()

        items = client.dataset_items(run_id, voce["max_items"])
        quando = _now()
        conn.executemany(
            "INSERT OR IGNORE INTO raw_items(track, entry_key, item_json, fetched_at) VALUES (?,?,?,?)",
            [(track, chiave, json.dumps(it, sort_keys=True, ensure_ascii=False), quando) for it in items])
        conn.commit()
        leggi = _youtube if voce["platform"] == "youtube" else _reddit
        con_testo = 0
        for n, it in enumerate(items, 1):
            try:
                if not isinstance(it, dict):
                    raise TypeError("non è un oggetto")
                a, b, c = leggi(conn, it, track)
            except Exception as e:  # un elemento guasto non ferma il lotto
                conn.rollback()
                guasti += 1
                _log(f"Voce {i}, elemento {n}: illeggibile ({type(e).__name__}), lo salto. "
                     "Resta in raw_items.")
                continue
            ns, nt, con_testo = ns + a, nt + b, con_testo + int(c)
        if not con_testo:
            vuote.append(i)
            continue
        conn.execute("UPDATE collect_runs SET finished_at=?, items=? WHERE track=? AND entry_key=?",
                     (quando, len(items), track, chiave))
        conn.commit()
    if conn.execute("SELECT 1 FROM spend WHERE track=?", (track,)).fetchone():
        conn.execute("UPDATE spend SET last_usd=? WHERE track=?", (client.usage_usd(), track))
        conn.commit()
    return {"sources": ns, "texts": nt, "spent_usd": round(apify.spent(conn, track), 4),
            "skipped": saltate, "bad_items": guasti, "empty": vuote}


def _type_ok(kind, value) -> bool:
    checks = {
        "string": lambda v: isinstance(v, str),
        "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
        "boolean": lambda v: isinstance(v, bool),
        "array": lambda v: isinstance(v, list),
        "object": lambda v: isinstance(v, dict),
    }
    return kind not in checks or checks[kind](value)


def check_actors(client: apify.Apify, plan: list[dict]) -> list[str]:
    """Le chiavi del piano che lo schema dell'attore non conosce, e i valori non ammessi."""
    problemi = []
    for i, voce in enumerate(plan, 1):
        actor = voce["actor"]
        schema = client.input_schema(actor)
        if schema is None:
            problemi.append(f"voce {i} ({actor}): schema non trovato. Controlla il nome dell'attore.")
            continue
        props = schema.get("properties") or {}
        for k, v in sorted((voce.get("input") or {}).items()):
            p = props.get(k)
            if not isinstance(p, dict):
                problemi.append(f"voce {i} ({actor}): chiave sconosciuta «{k}».")
                continue
            if not _type_ok(p.get("type"), v):
                problemi.append(f"voce {i} ({actor}): «{k}» vuole un {p.get('type')}, "
                                f"nel piano c'è un {type(v).__name__}.")
                continue
            enum = p.get("enum") or (p.get("items") or {}).get("enum")
            if enum:
                for x in (v if isinstance(v, list) else [v]):
                    if x not in enum:
                        ammessi = ", ".join(str(e) for e in enum)
                        problemi.append(f"voce {i} ({actor}): valore «{x}» non ammesso per «{k}»"
                                        f" (ammessi {ammessi}).")
    return problemi
