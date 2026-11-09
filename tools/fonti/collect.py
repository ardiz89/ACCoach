"""Raccolta dalle fonti pubbliche via Apify, con tetto di spesa."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone

from tools.fonti import apify, db

_ACC = re.compile(r"assetto corsa competizione|\bacc\b", re.IGNORECASE)
_TS = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)")


def game_of(title: str, description: str, subreddit: str) -> str:
    if (subreddit or "").lower() == "accompetizione":
        return "acc"
    return "acc" if _ACC.search(f"{title or ''} {description or ''}") else "altro"


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


def _source(conn, platform, url, author, title, published, game, track, meta) -> tuple[int, bool]:
    cur = conn.execute(
        "INSERT OR IGNORE INTO sources(platform, url, author, title, published, game, track, meta_json)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (platform, url, author, title, published, game, track, json.dumps(meta, ensure_ascii=False)))
    conn.commit()
    sid = conn.execute("SELECT id FROM sources WHERE url=?", (url,)).fetchone()[0]
    return sid, cur.rowcount == 1


def _thread_url(url: str) -> str:
    m = re.match(r"(.*?/comments/[^/]+/[^/]*/?)", url or "")
    return m.group(1) if m else url


def _youtube(conn, item, track) -> tuple[int, int]:
    url = item.get("url")
    if not url:
        return 0, 0
    subs = item.get("subtitles") or []
    srt = next((s.get("srt") for s in subs if s.get("srt")), None)
    game = game_of(item.get("title", ""), item.get("text", ""), "")
    sid, nuova = _source(conn, "youtube", url, item.get("channelName"), item.get("title"),
                         item.get("date"), game, track, {"video_id": item.get("id")})
    nt = 0
    segs = parse_srt(srt) if srt else []
    if segs:
        corpo = " ".join(s["text"] for s in segs)
        nt = int(db.add_text(conn, sid, "transcript", item.get("channelName") or "", corpo, segs)[1])
    return int(nuova), nt


def _reddit(conn, item, track) -> tuple[int, int]:
    tipo = item.get("dataType")
    sub = item.get("parsedCommunityName") or item.get("communityName") or ""
    corpo = (item.get("body") or "").strip()
    if tipo == "post":
        game = game_of(item.get("title", ""), corpo, sub)
        sid, nuova = _source(conn, "reddit", item.get("url"), item.get("username"), item.get("title"),
                             item.get("createdAt"), game, track, {"subreddit": sub})
        nt = int(db.add_text(conn, sid, "post", item.get("username") or "",
                             f"{item.get('title', '')}\n{corpo}".strip())[1])
        return int(nuova), nt
    if tipo == "comment" and corpo:
        turl = _thread_url(item.get("url", ""))
        riga = conn.execute("SELECT id FROM sources WHERE url=?", (turl,)).fetchone()
        if riga is None:  # commento il cui post non e' nel lotto: sorgente minima
            sid, nuova = _source(conn, "reddit", turl, None, None, item.get("createdAt"),
                                 game_of("", "", sub), track, {"subreddit": sub})
        else:
            sid, nuova = riga[0], False
        nt = int(db.add_text(conn, sid, "comment", item.get("username") or "", corpo)[1])
        return int(nuova), nt
    return 0, 0


def entry_key(voce: dict) -> str:
    canon = json.dumps({"actor": voce["actor"], "input": voce["input"], "max_items": voce["max_items"]},
                       sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def collect(conn: sqlite3.Connection, client: apify.Apify, track: str, plan: list[dict],
            cap_usd: float = apify.CAP_USD, force: bool = False) -> dict:
    ns = nt = saltate = 0
    for voce in plan:
        chiave = entry_key(voce)
        if not force and conn.execute("SELECT 1 FROM collect_runs WHERE track=? AND entry_key=?",
                                      (track, chiave)).fetchone():
            saltate += 1
            continue
        resto = apify.guard(conn, client, track, cap_usd)
        items = client.run(voce["actor"], voce["input"], voce["max_items"], max_charge_usd=resto)
        for it in items:
            if voce["platform"] == "youtube":
                a, b = _youtube(conn, it, track)
            else:
                a, b = _reddit(conn, it, track)
            ns, nt = ns + a, nt + b
        prima = conn.execute("SELECT last_usd FROM spend WHERE track=?", (track,)).fetchone()[0]
        dopo = client.usage_usd()
        conn.execute("UPDATE spend SET last_usd=? WHERE track=?", (dopo, track))
        conn.execute("INSERT OR REPLACE INTO collect_runs(track, entry_key, finished_at, items, spent_usd)"
                     " VALUES (?,?,?,?,?)",
                     (track, chiave, datetime.now(timezone.utc).isoformat(timespec="seconds"),
                      len(items), round(dopo - prima, 4)))
        conn.commit()
    uso = client.usage_usd()
    riga = conn.execute("SELECT baseline_usd FROM spend WHERE track=?", (track,)).fetchone()
    base = riga[0] if riga else uso
    conn.execute("UPDATE spend SET last_usd=? WHERE track=?", (uso, track))
    conn.commit()
    return {"sources": ns, "texts": nt, "spent_usd": round(uso - base, 4), "skipped": saltate}
