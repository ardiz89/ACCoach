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

# ACC si riconosce dal titolo o dal sottoreddit: un hashtag nella descrizione no.
_ACC = re.compile(r"assetto corsa competizione|\bacc\b", re.IGNORECASE)
# Nella descrizione conta solo una frase che dice il gioco: il nome intero, o «in ACC»
# («each circuit in ACC»). «ACC version soon» o «#acc» non bastano.
_DESC_ACC = re.compile(r"(?<!#)\bassetto corsa competizione\b"
                       r"|\b(?:in|on|for|using|with)\s+(?:the\s+)?acc\b", re.IGNORECASE)
# Un titolo che nomina anche un altro gioco parla di tutti e due: non è una fonte su ACC.
_MIXED = re.compile(
    r"\bac\s+vs\.?\s+acc\b|\bacc\s+vs\.?\s+ac\b|\bac1\b|\bassetto corsa 1\b"
    r"|\biracing\b|\blmu\b|\ble mans ultimate\b|\bams\s?2\b|\bautomobilista\b"
    r"|\brf2\b|\brfactor\b|\bgran turismo\b|\bgt7\b|\bf1\b",
    re.IGNORECASE)


def _w(*words: str) -> re.Pattern:
    """Parole intere, nel testo già in minuscolo."""
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(words) + r")(?![a-z0-9])")


_GT3 = _w("gt3")
# Classi che in ACC non sono GT3, con i modelli che le nominano senza dirlo.
_NOT_GT3 = {
    "gt4": _w("gt4", "ginetta", "g55", "alpine", "a110", "ktm", "x-bow", "xbow", "camaro",
              "570s", "cayman", "718", "maserati"),
    "altra": _w("gt3 cup", "cup", "trofeo", "super trofeo", "gt2", "m2", "tcx",
                "488 challenge", "challenge evo"),
}
_GT3_CUP = _w("gt3 cup")
_TS = re.compile(r"(?:(\d+):)?(\d+):(\d+)[,.](\d+)")
_TAG = re.compile(r"<[^>]*>")
_POST_ID = re.compile(r"/comments/([A-Za-z0-9]+)")
# `gt3_presunta`: la fonte non nomina nessuna classe, e in ACC la classe di base è la GT3
# (deciso dal pilota il 10/11).
GT3_PRESUNTA = "gt3_presunta"
CLASSES = ("gt3", GT3_PRESUNTA, "gt4", "altra", "ignota")
# I campi dei sottotitoli dell'attore YouTube, in ordine di preferenza: con i tempi prima.
SUBTITLE_FIELDS = ("srt", "vtt", "plaintext", "text")


def game_of(title: str, description: str, subreddit: str) -> str:
    """`acc` o `altro`.

    Il titolo basta se nomina ACC. Se non lo nomina, vale la descrizione con una frase
    di `_DESC_ACC`, purché non nomini un altro gioco, nemmeno con un hashtag.
    """
    title = title or ""
    if _MIXED.search(title):
        return "altro"
    if (subreddit or "").lower() == "accompetizione":
        return "acc"
    if _ACC.search(title):
        return "acc"
    desc = description or ""
    return "acc" if _DESC_ACC.search(desc) and not _MIXED.search(desc) else "altro"


def _classes_named(text) -> set[str]:
    """Le classi che il testo nomina: gt3, gt4, altra. «GT3 Cup» non è una GT3."""
    t = str(text or "").lower()
    out = {k for k, rx in _NOT_GT3.items() if rx.search(t)}
    if _GT3.search(_GT3_CUP.sub(" ", t)):
        out.add("gt3")
    return out


def car_class_of(title, description, extra) -> str:
    """La classe della fonte. Solo il titolo la assegna, se nomina una classe sola.

    La descrizione e `extra` (flair, sottoreddit) non assegnano mai: se nominano un'altra
    classe la tolgono, e la fonte resta `ignota`. Se nessuno dei tre nomina una classe
    diversa dalla GT3, la fonte è `gt3_presunta`: in ACC la classe di base è la GT3.
    """
    named = _classes_named(title)
    if not named:
        return GT3_PRESUNTA if not _classes_named(f"{description or ''} {extra or ''}") - {"gt3"} \
            else "ignota"
    if len(named) != 1:
        return "ignota"
    klass = next(iter(named))
    if _classes_named(f"{description or ''} {extra or ''}") - {klass}:
        return "ignota"
    return klass


def text_class_of(body) -> str | None:
    """La classe che un testo dice per sé, se diversa dalla GT3; None se non ne dice.

    Un testo che nomina la GT3 e un'altra classe è `ignota`. Un testo che nomina solo la
    GT3 non assegna niente: vale la classe della fonte.
    """
    named = _classes_named(body)
    if not named - {"gt3"}:
        return None
    return next(iter(named)) if len(named) == 1 else "ignota"


def parse_srt(srt: str) -> list[dict]:
    """Sottotitoli SRT o WebVTT: un segmento per blocco, con l'inizio in secondi."""
    segs = []
    for blocco in re.split(r"\n\s*\n", (srt or "").replace("\r\n", "\n").strip()):
        righe = [r for r in blocco.splitlines() if r.strip()]
        for i, r in enumerate(righe):
            if "-->" in r:
                m = _TS.search(r)
                testo = " ".join(_TAG.sub("", x).strip() for x in righe[i + 1:]).strip()
                if m and testo:
                    h, mi, s, ms = (int(x or 0) for x in m.groups())
                    segs.append({"start_s": round(h * 3600 + mi * 60 + s + ms / 1000, 3), "text": testo})
                break
    return segs


def subtitles_of(item: dict) -> tuple[str, str | None, list[dict] | None, list[str]]:
    """`(campo, corpo, segmenti, chiavi viste)` dai sottotitoli dell'elemento.

    Il campo è quello trovato fra SUBTITLE_FIELDS, oppure `nessuno`. Le chiavi viste
    servono a capire la forma vera dell'uscita quando nessun campo torna.
    """
    subs = item.get("subtitles") or []
    subs = [x for x in subs if isinstance(x, dict)] if isinstance(subs, list) else []
    keys = sorted({k for x in subs for k in x})
    for campo in SUBTITLE_FIELDS:
        raw = next((x[campo] for x in subs if isinstance(x.get(campo), str) and x[campo].strip()), None)
        if raw is None:
            continue
        if campo in ("srt", "vtt"):
            segs = parse_srt(raw)
            if segs:
                return campo, " ".join(sg["text"] for sg in segs), segs, keys
            continue
        return campo, " ".join(raw.split()), None, keys
    return "nessuno", None, None, keys


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
    tipo = _kind(item)
    if tipo != "post" and isinstance(item.get("postId"), str) \
            and re.fullmatch(r"[A-Za-z0-9]+", item["postId"]):
        return item["postId"]   # automation-lab: l'id del post senza «t3_»
    for campo in (("id",) if tipo == "post" else ("postId", "parentId")):
        v = item.get(campo)
        if isinstance(v, str) and (tipo == "post" or v.startswith("t3_")):
            v = v[3:] if v.startswith("t3_") else v
            if re.fullmatch(r"[A-Za-z0-9]+", v):
                return v
    m = _POST_ID.search(item.get("url") or item.get("permalink") or "")
    return m.group(1) if m else None


# Due attori, due forme: trudax (dataType, username, body, parsedCommunityName) e
# automation-lab (type, author, selfText per il post, subreddit solo nel post).
_SUB_IN_URL = re.compile(r"reddit\.com/r/([A-Za-z0-9_]+)/")


def _kind(item: dict):
    return item.get("dataType") or item.get("type")


def _subreddit(item: dict) -> str:
    sub = item.get("parsedCommunityName") or item.get("communityName") or item.get("subreddit")
    if sub:
        return str(sub)
    m = _SUB_IN_URL.search(item.get("permalink") or item.get("url") or "")
    return m.group(1) if m else ""


def _user(item: dict):
    return item.get("username") or item.get("author")


def thread_url(post_id: str) -> str:
    return f"https://www.reddit.com/comments/{post_id}/"


def _youtube(conn, item, track, seen: dict | None = None) -> tuple[int, int, bool]:
    """`(fonte nuova, testo nuovo, c'è un testo)` per un video."""
    title, desc = item.get("title"), item.get("text")
    sid, nuova = _source(conn, "youtube", item.get("url"), item.get("channelName"), title,
                         item.get("date"), game_of(title, desc, ""), track,
                         {"video_id": item.get("id")}, car_class_of(title, desc, ""))
    campo, corpo, segs, keys = subtitles_of(item)
    if seen is not None:
        seen["fields"][campo] = seen["fields"].get(campo, 0) + 1
        if campo == "nessuno":
            seen["keys"].update(keys)
    if not corpo:
        return int(nuova), 0, False
    nt = int(db.add_text(conn, sid, "transcript", item.get("channelName") or "", corpo, segs,
                         car_class=text_class_of(corpo))[1])
    return int(nuova), nt, True


def _reddit(conn, item, track, seen: dict | None = None) -> tuple[int, int, bool]:
    """`(fonte nuova, testo nuovo, c'è un testo)` per un post o un commento."""
    tipo = _kind(item)
    if tipo not in ("post", "comment"):
        return 0, 0, False
    sub = _subreddit(item)
    corpo = (item.get("body") or item.get("selfText") or "").strip()
    pid = _post_id(item)
    if pid is None:
        raise ValueError("post senza id")
    if tipo == "post":
        title = item.get("title")
        flair = item.get("flair") or item.get("linkFlairText")
        sid, nuova = _source(conn, "reddit", thread_url(pid), _user(item), title,
                             item.get("createdAt"), game_of(title, corpo, sub), track,
                             {"subreddit": sub, "post_id": pid, "flair": flair},
                             car_class_of(title, corpo, f"{flair or ''} {sub}"))
        testo = f"{title or ''}\n{corpo}".strip()
        if not testo:
            return int(nuova), 0, False
        return int(nuova), int(db.add_text(conn, sid, "post", _user(item) or "", testo,
                                           car_class=text_class_of(corpo))[1]), True
    if not corpo:
        return 0, 0, False
    # Il post del thread può arrivare dopo: intanto una fonte minima, che il post completerà.
    sid, nuova = _source(conn, "reddit", thread_url(pid), None, None, item.get("createdAt"),
                         game_of("", "", sub), track, {"subreddit": sub, "post_id": pid},
                         "ignota", full=False)
    return int(nuova), int(db.add_text(conn, sid, "comment", _user(item) or "", corpo,
                                       car_class=text_class_of(corpo))[1]), True


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
    fallite: list[tuple[int, str]] = []
    seen: dict = {"fields": {}, "keys": set()}
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
                a, b, c = leggi(conn, it, track, seen)
            except Exception as e:  # un elemento guasto non ferma il lotto
                conn.rollback()
                guasti += 1
                _log(f"Voce {i}, elemento {n}: illeggibile ({type(e).__name__}), lo salto. "
                     "Resta in raw_items.")
                continue
            ns, nt, con_testo = ns + a, nt + b, con_testo + int(c)
        stato = run.get("status")
        if stato != "SUCCEEDED":
            fallite.append((i, str(stato)))   # i dati pagati restano, la voce no
            continue
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
            "skipped": saltate, "bad_items": guasti, "empty": vuote, "failed": fallite,
            "subtitle_fields": seen["fields"], "subtitle_keys": sorted(seen["keys"])}


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
        try:
            schema = client.input_schema(actor)
        except apify.ApifyError as e:
            if getattr(e, "status", None) in (401, 403):
                problemi.append(f"voce {i} ({actor}): token non valido o senza permesso.")
            elif getattr(e, "status", None) == 404:
                problemi.append(f"voce {i} ({actor}): attore non trovato. Controlla il nome.")
            else:
                problemi.append(f"voce {i} ({actor}): Apify ha risposto {getattr(e, 'status', '?')}.")
            continue
        if schema is None:
            problemi.append(f"voce {i} ({actor}): schema non trovato nella build dell'attore.")
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
