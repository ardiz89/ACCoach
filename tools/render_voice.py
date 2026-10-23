"""Genera le frasi del coach con ElevenLabs (al momento della build, non in pista).

    python tools/render_voice.py --dry-run          # il conto dei caratteri, senza chiave ne' rete
    python tools/render_voice.py                    # genera quello che manca, nelle due voci
    python tools/render_voice.py --show             # come --dry-run, piu' frase -> testo mandato
    python tools/render_voice.py --voice male       # solo la maschile (o female)
    python tools/render_voice.py --only "Gas" --only "Frena prima"   # ritocchi dopo l'ascolto
    python tools/render_voice.py --listen           # pagina d'ascolto via filtro radio

L'elenco delle frasi e' `accoach.coaching.spoken.spoken_phrases()` di QUESTO
repository (non dell'installazione da cui si guida): lo script mette `<repo>/src`
in testa a `sys.path` e dice quale `accoach` ha caricato.

Per ogni voce scrive nella sua cartella i WAV (`cue_<sha1[:10]>.wav`, vedi
`slug`), il `manifest.json` (testo detto -> file) che il
player legge, e accanto `render.json`: per ogni frase voce, modello e
impostazioni e testo mandato (`render_text`: accenti e pause) con cui e' stata resa. Una frase si rigenera solo se manca o se
quelle impostazioni sono cambiate, per non pagare due volte.

La chiave: variabile d'ambiente `ELEVENLABS_API_KEY` o il file
`%USERPROFILE%\\.elevenlabs-key`. Non viene mai stampata.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import io
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.request
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Il nostro `src` davanti a tutto: senza, `import accoach` prende l'installazione
# da cui si guida, e si genererebbe l'elenco di un altro commit.
sys.path.insert(0, str(ROOT / "src"))

API = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format={fmt}"
MODEL = "eleven_multilingual_v2"
OUTPUT_FORMAT = "pcm_22050"
SAMPLE_RATE = 22050
LANGUAGE = "it"
# «Grinta media», scelta dal pilota il 22/10 su MarcoTrox; Tiziana uguale.
VOICE_SETTINGS = {"stability": 0.30, "similarity_boost": 0.70, "style": 0.0, "speed": 1.10}

# voce -> (voice_id, cartella). La maschile e' la predefinita dal 23/10.
VOICES = {
    "male": ("W71zT1VwIFFx3mMGH2uZ", ROOT / "src" / "accoach" / "voice_cues_male"),   # MarcoTrox
    "female": ("RXoaSpLaWTEckJgPUBG3", ROOT / "src" / "accoach" / "voice_cues"),      # Tiziana
}

# Il pilota ha ascoltato le frasi (23/10): il modello sbaglia l'accento nelle
# parole sdrucciole o con dittongo e legge «qui» come «chi». Si scrive
# l'accento nel testo MANDATO; la frase originale (chiave del manifest, nome del
# file, schermo) non cambia. Per parola intera; la maiuscola iniziale si
# conserva. Le parole tronche gia' accentate (piu', meta', velocita') non si
# toccano: l'accento scritto c'e' gia'.
PRONUNCIA = {
    "antirollio": "antirollìo", "pattini": "pàttini", "scivola": "scìvola",
    "applicala": "applìcala", "tienine": "tiènine", "precarico": "precàrico",
    "margine": "màrgine", "modifica": "modìfica", "ricarica": "ricàrica",
    "pagina": "pàgina", "subito": "sùbito", "ultimo": "ùltimo",
    "fluido": "flùido", "molli": "mòlli", "rifalla": "rifàlla",
    "guadagni": "guadàgni", "veleggi": "velèggi", "qui": "quì",
    # Aggiunte dopo aver riletto le 98 frasi:
    # «molle» (le molle delle sospensioni): senza accento si confonde con
    # l'aggettivo «molle» (mòlle/mólle), e il pilota ha gia' sentito sbagliare «molli».
    "molle": "mòlle",
    # parola inglese in frase italiana: il modello la legge «cambér» all'italiana.
    "camber": "càmber",
}
# Le sigle sono maiuscole e non si confondono con una parola comune: la
# corrispondenza e' esatta. «ABS» il modello rischia di leggerlo come una parola.
SIGLE = {"TC": "ti-ci", "ABS": "a-bi-èsse"}

# Pausa dopo ogni virgola: il modello a stabilita' 0,30 le ignora.
PAUSA = ', <break time="0.3s" /> '

_WORD = re.compile(r"[^\W\d_]+")


def _respell(m: "re.Match[str]") -> str:
    w = m.group(0)
    if w in SIGLE:
        return SIGLE[w]
    low = w.lower()
    new = PRONUNCIA.get(low)
    # Solo «parola» o «Parola»: una sigla in maiuscolo (QUI) non e' la parola.
    if new is None or w not in (low, low.capitalize()):
        return w
    return new.capitalize() if w != low else new


def render_text(phrase: str) -> str:
    """Il testo che si manda all'API per una frase (la frase originale resta la
    chiave del manifest: codice e schermo non cambiano)."""
    return _WORD.sub(_respell, phrase).replace(", ", PAUSA)


KEY_ENV = "ELEVENLABS_API_KEY"
KEY_FILE_NAME = ".elevenlabs-key"
TIMEOUT_S = 120


class _Stop(Exception):
    """Un errore che ferma la generazione: il messaggio e' gia' senza chiave."""


def _die(msg: str) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(1)


def slug(text: str) -> str:
    """Il nome del WAV di una frase. E' lo stesso che dava il vecchio
    `render_cues.py` (Piper, ritirato il 23/10): i manifest di prima restano
    leggibili e una frase gia' resa si riconosce."""
    h = hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]
    return f"cue_{h}"


def load_phrases() -> list[str]:
    from accoach.coaching.spoken import spoken_phrases
    return spoken_phrases()


def _accoach_origin() -> Path:
    import accoach
    return Path(accoach.__file__).resolve().parent


def _key_file() -> Path:
    base = os.environ.get("USERPROFILE") or str(Path.home())
    return Path(base) / KEY_FILE_NAME


def _read_key() -> str:
    key = (os.environ.get(KEY_ENV) or "").strip()
    if not key:
        f = _key_file()
        if f.is_file():
            # Blocco note puo' salvare con BOM e a capo finale.
            key = f.read_text(encoding="utf-8-sig").strip()
    if not key:
        _die(f"Manca la chiave di ElevenLabs: mettila nella variabile {KEY_ENV} "
             f"o nel file {_key_file()} (una riga sola, solo la chiave).")
    return key


def _settings(voice_id: str) -> dict:
    """Quello con cui una frase e' resa: se cambia, la frase si rifa'."""
    return {"voice_id": voice_id, "model_id": MODEL,
            "voice_settings": dict(VOICE_SETTINGS),
            "output_format": OUTPUT_FORMAT, "language_code": LANGUAGE}


def _want(voice_id: str, phrase: str) -> dict:
    """Le impostazioni piu' il testo mandato: se cambia la tabella di pronuncia
    la frase si rifa', come per un'impostazione."""
    return {**_settings(voice_id), "text": render_text(phrase)}


def _load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _atomic_write(path: Path, data: bytes) -> None:
    # Scritto accanto e poi rinominato: un'interruzione lascia il file vecchio
    # intero, mai uno a meta'.
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _write_json(path: Path, data: dict) -> None:
    _atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2,
                                   sort_keys=True).encode("utf-8"))


def _to_wav(pcm: bytes) -> bytes:
    """L'API da' PCM grezzo; il player e `radioize_wav` vogliono un RIFF."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm)
    return buf.getvalue()


def _scrub(text: str, key: str) -> str:
    return text.replace(key, "***") if key else text


def _http_message(err: urllib.error.HTTPError, key: str, voice_id: str = "") -> str:
    try:
        raw = err.read().decode("utf-8", "replace")
    except Exception:  # noqa: BLE001 - il corpo e' solo un aiuto, non serve
        raw = ""
    detail = ""
    try:
        d = json.loads(raw).get("detail")
        if isinstance(d, dict):
            detail = " ".join(str(d.get(k, "")) for k in ("status", "message")).strip()
        elif d:
            detail = str(d)
    except (ValueError, AttributeError):
        detail = raw
    # Il corpo dell'errore puo' ripetere la chiave: la si toglie prima di dirlo.
    detail = _scrub(detail, key)[:300]
    low = raw.lower()
    if err.code == 400 and "language" in low:
        # Non si ritenta da soli senza `language_code`: e' una scelta da fare
        # a mano (togliere il campo dallo script), non da indovinare.
        why = ("ElevenLabs non lo accetta: il modello rifiuta `language_code` (400). "
               "Va tolto dalla richiesta nello script, poi si rilancia.")
        return why + (f" Dettaglio: {detail}" if detail else "")
    if err.code == 404 or (err.code == 400 and (
            "voice_not_found" in low or (voice_id and voice_id.lower() in low)
            or ("voice" in low and "not found" in low))):
        why = (f"ElevenLabs non trova la voce (HTTP {err.code}): aggiungi MarcoTrox "
               "(maschile) e Tiziana (femminile) a «My voices» dalla libreria "
               "di ElevenLabs (un clic ciascuna), poi rilancia.")
        return why + (f" Dettaglio: {detail}" if detail else "")
    why = {
        401: "ElevenLabs ha rifiutato la chiave (401): controlla la chiave nel file "
             f"{_key_file()} o nella variabile {KEY_ENV}.",
        402: "ElevenLabs chiede un pagamento (402): crediti finiti o piano senza "
             "questa funzione. Controlla l'abbonamento.",
        429: "ElevenLabs dice troppe richieste o crediti esauriti (429): aspetta e "
             "riprova; le frasi gia' fatte restano.",
    }.get(err.code, f"ElevenLabs ha risposto con un errore HTTP {err.code}.")
    return why + (f" Dettaglio: {detail}" if detail else "")


def _synthesize(text: str, voice_id: str, key: str) -> bytes:
    body = {"text": text, "model_id": MODEL, "voice_settings": dict(VOICE_SETTINGS),
            "language_code": LANGUAGE}
    req = urllib.request.Request(
        API.format(voice_id=voice_id, fmt=OUTPUT_FORMAT),
        data=json.dumps(body).encode("utf-8"),
        headers={"xi-api-key": key, "Content-Type": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            pcm = resp.read()
    except urllib.error.HTTPError as e:
        raise _Stop(_http_message(e, key, voice_id)) from None
    except (urllib.error.URLError, OSError) as e:
        raise _Stop(_scrub(f"Rete non raggiungibile: {e}", key)) from None
    # PCM 16 bit: un numero dispari di byte o niente audio e' una risposta rotta.
    if not pcm or len(pcm) % 2:
        raise _Stop(f"ElevenLabs ha risposto senza audio valido per «{text}».")
    return pcm


def _plan(voice: str, phrases: list[str], only: list[str] | None):
    """(da generare, da togliere) per una voce."""
    voice_id, d = VOICES[voice]
    manifest = _load_json(d / "manifest.json")
    sidecar = _load_json(d / "render.json")
    if only is not None:
        return [t for t in phrases if t in only], []
    todo = [t for t in phrases
            if t not in manifest
            or not (d / manifest[t]).is_file()
            or sidecar.get(t) != _want(voice_id, t)]
    wanted = set(phrases)
    gone = sorted(t for t in set(manifest) | set(sidecar) if t not in wanted)
    return todo, gone


def _prune(d: Path, gone: list[str], manifest: dict, sidecar: dict) -> None:
    keep_files = {f for t, f in manifest.items() if t not in gone}
    for t in gone:
        f = manifest.pop(t, None)
        sidecar.pop(t, None)
        if f and f not in keep_files:
            (d / f).unlink(missing_ok=True)
    _write_json(d / "manifest.json", manifest)
    _write_json(d / "render.json", sidecar)


def _render_voice(voice: str, todo: list[str], gone: list[str], key: str,
                  full_run: bool) -> None:
    voice_id, d = VOICES[voice]
    d.mkdir(parents=True, exist_ok=True)
    # `.tmp` lasciati da una corsa interrotta: PyInstaller copia la cartella
    # intera, e finirebbero nel pacchetto.
    for f in d.glob("*.tmp"):
        f.unlink()
    manifest = _load_json(d / "manifest.json")
    sidecar = _load_json(d / "render.json")
    if gone:
        _prune(d, gone, manifest, sidecar)
        print(f"  [{voice}] tolte {len(gone)} frasi non piu' nell'elenco")
    for text in todo:
        fname = slug(text) + ".wav"
        wav = _to_wav(_synthesize(render_text(text), voice_id, key))
        # Prima il WAV, poi il manifest, poi il sidecar: se si interrompe fra i
        # due, il sidecar vecchio fa rifare la frase alla prossima corsa.
        _atomic_write(d / fname, wav)
        manifest[text] = fname
        _write_json(d / "manifest.json", manifest)
        sidecar[text] = _want(voice_id, text)
        _write_json(d / "render.json", sidecar)
        print(f"  OK [{voice}] {text}")
    if full_run:
        # WAV rimasti senza frase (per esempio i vecchi di Piper): via.
        used = set(manifest.values())
        for f in d.glob("cue_*.wav"):
            if f.name not in used:
                f.unlink()


def _listen(voices: list[str], phrases: list[str]) -> Path:
    """Ogni frase nelle voci scelte, passata dal filtro radio, in una pagina
    fuori dal repo. Le caselle compongono il comando `--only` dei ritocchi."""
    from accoach.coaching.radio import radioize_wav
    out = Path(tempfile.mkdtemp(prefix="hone-voce-ascolto-"))
    rows = []
    for text in phrases:
        cells = []
        for voice in voices:
            d = VOICES[voice][1]
            f = _load_json(d / "manifest.json").get(text)
            if f and (d / f).is_file():
                clip = f"{voice}_{f}"
                (out / clip).write_bytes(radioize_wav((d / f).read_bytes()))
                cells.append(f'<td><audio controls preload="none" src="{clip}"></audio></td>')
            else:
                cells.append("<td>manca</td>")
        esc = html.escape(text, quote=True)
        rows.append(f'<tr><td><input type="checkbox" data-t="{esc}"></td>'
                    f"<td>{esc}</td>{''.join(cells)}</tr>")
    head = "".join(f"<th>{v}</th>" for v in voices)
    page = f"""<!doctype html>
<html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ascolto voci</title>
<style>
body{{font-family:system-ui,sans-serif;margin:16px;background:#fff;color:#111}}
table{{border-collapse:collapse;width:100%}}
td,th{{border-bottom:1px solid #ddd;padding:6px;text-align:left;vertical-align:middle}}
pre{{white-space:pre-wrap;background:#f3f3f3;padding:8px}}
</style></head><body>
<h1>Ascolto voci</h1>
<p>{len(phrases)} frasi, via filtro radio. Spunta quelle da rifare: sotto compare il comando.</p>
<table><tr><th></th><th>Frase</th>{head}</tr>
{chr(10).join(rows)}
</table>
<pre id="cmd"></pre>
<script>
document.addEventListener('change', function () {{
  var picked = Array.prototype.slice.call(document.querySelectorAll('input:checked'))
    .map(function (b) {{ return '--only "' + b.getAttribute('data-t') + '"'; }});
  document.getElementById('cmd').textContent = picked.length
    ? 'python tools/render_voice.py ' + picked.join(' ') : '';
}});
</script>
</body></html>
"""
    path = out / "voice_listen.html"
    path.write_text(page, encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Genera le frasi del coach con ElevenLabs.")
    ap.add_argument("--voice", choices=["male", "female", "both"], default="both")
    ap.add_argument("--dry-run", action="store_true",
                    help="conta frasi e caratteri da generare, senza chiave ne' rete")
    ap.add_argument("--show", action="store_true",
                    help="come --dry-run, e mostra frase -> testo mandato (solo quelle che cambiano)")
    ap.add_argument("--only", action="append", metavar="FRASE",
                    help="rigenera solo questa frase (ripetibile)")
    ap.add_argument("--listen", action="store_true",
                    help="scrive la pagina d'ascolto in una cartella temporanea")
    args = ap.parse_args(argv)

    origin = _accoach_origin()
    print(f"accoach da {origin}")
    if ROOT / "src" not in origin.parents:
        _die(f"accoach non viene da questo repository ({ROOT / 'src'}): "
             "l'elenco delle frasi sarebbe di un altro commit.")

    voices = ["male", "female"] if args.voice == "both" else [args.voice]
    phrases = load_phrases()

    if args.only is not None:
        unknown = [t for t in args.only if t not in phrases]
        if unknown:
            _die("Frase che non e' nell'elenco di spoken_phrases(): "
                 + "; ".join(f"«{t}»" for t in unknown))

    if args.listen:
        page = _listen(voices, phrases)
        print(f"pagina d'ascolto: {page}")
        return 0

    plans = {v: _plan(v, phrases, args.only) for v in voices}
    total_n = total_c = 0
    for v in voices:
        todo, gone = plans[v]
        n, c = len(todo), sum(len(render_text(t)) for t in todo)
        total_n, total_c = total_n + n, total_c + c
        line = f"{v}: {n} frasi, {c} caratteri da generare"
        if gone:
            line += f" ({len(gone)} da togliere)"
        print(line)
    all_c = sum(len(render_text(t)) for t in phrases)
    print(f"totale: {total_n} frasi, {total_c} caratteri "
          f"(elenco intero: {len(phrases)} frasi, {all_c} caratteri per voce)")
    if args.show:
        changed = [(t, render_text(t)) for t in phrases if render_text(t) != t]
        print(f"{len(changed)} frasi su {len(phrases)} cambiano nel testo mandato:")
        for t, r in changed:
            print(f"  {t}")
            print(f"    -> {r}")
    if args.dry_run or args.show:
        return 0

    # Anche senza niente da generare si passa da ogni voce: la pulizia dei
    # `.tmp` e dei WAV orfani non deve dipendere dall'avere lavoro da pagare.
    key = _read_key() if total_n else ""
    try:
        for v in voices:
            todo, gone = plans[v]
            _render_voice(v, todo, gone, key, full_run=args.only is None)
    except _Stop as e:
        _die(str(e))
    print("fatto." if total_n else "niente da generare.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
