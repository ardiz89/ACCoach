"""Lo script che genera le voci con ElevenLabs (`tools/render_voice.py`).

Nessun test tocca la rete ne' la chiave vera: la chiave e' una stringa finta
riconoscibile, la cartella utente punta a una cartella temporanea (cosi' il file
`.elevenlabs-key` vero non e' raggiungibile), `urllib.request.urlopen` e'
sostituito e le connessioni dei socket falliscono comunque.
"""

from __future__ import annotations

import io
import json
import math
import socket
import struct
import sys
import urllib.error
import urllib.request
import wave
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "tools"))
import render_voice  # noqa: E402 - script di build, provato qui

FAKE_KEY = "sk_FINTA_chiave_di_prova_7f3a9c"

PHRASES = ["Frena prima", "Gas", "Qui perdi 3 decimi"]


def _pcm(n: int = 2205) -> bytes:
    """Un decimo di secondo di sinusoide, PCM 16 bit mono come `pcm_22050`."""
    return b"".join(struct.pack("<h", int(8000 * math.sin(i / 5.0))) for i in range(n))


class _Resp:
    def __init__(self, body: bytes):
        self._b = body

    def read(self) -> bytes:
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeAPI:
    """Al posto di `urlopen`: registra le richieste e risponde con PCM, o con
    l'errore HTTP che il test chiede per una frase."""

    def __init__(self):
        self.calls: list[dict] = []
        self.fail: dict[str, int] = {}

    def __call__(self, req, timeout=None):
        body = json.loads(req.data.decode("utf-8"))
        headers = {k.lower(): v for k, v in req.header_items()}
        self.calls.append({"url": req.full_url, "body": body, "headers": headers})
        code = self.fail.get(body["text"])
        if code:
            # Il corpo d'errore contiene la chiave: lo script non deve ripeterlo.
            detail = json.dumps({"detail": {"status": "invalid_api_key",
                                            "message": f"key {FAKE_KEY} rejected"}})
            raise urllib.error.HTTPError(req.full_url, code, "errore", {},
                                         io.BytesIO(detail.encode()))
        return _Resp(_pcm())

    def texts(self) -> list[str]:
        return [c["body"]["text"] for c in self.calls]


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Cartelle temporanee per le due voci, elenco piccolo, rete finta."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("ELEVENLABS_API_KEY", FAKE_KEY)

    dirs = {"male": tmp_path / "voice_cues_male", "female": tmp_path / "voice_cues"}
    monkeypatch.setattr(render_voice, "VOICES", {
        "male": (render_voice.VOICES["male"][0], dirs["male"]),
        "female": (render_voice.VOICES["female"][0], dirs["female"]),
    })
    phrases = list(PHRASES)
    monkeypatch.setattr(render_voice, "load_phrases", lambda: list(phrases))

    api = FakeAPI()
    monkeypatch.setattr(urllib.request, "urlopen", api)

    def _no_net(*a, **k):
        raise AssertionError("un test ha provato ad aprire una connessione vera")
    monkeypatch.setattr(socket, "create_connection", _no_net)
    monkeypatch.setattr(socket.socket, "connect", _no_net)

    class E:
        pass
    e = E()
    e.dirs, e.phrases, e.api, e.home, e.tmp = dirs, phrases, api, home, tmp_path
    return e


def _manifest(d: Path) -> dict:
    return json.loads((d / "manifest.json").read_text(encoding="utf-8"))


def _sidecar(d: Path) -> dict:
    return json.loads((d / "render.json").read_text(encoding="utf-8"))


def _all_written_bytes(root: Path) -> bytes:
    return b"".join(p.read_bytes() for p in root.rglob("*") if p.is_file())


# --- il conto, prima di pagare ------------------------------------------------

def test_dry_run_counts_characters_without_key_or_network(env, monkeypatch, capsys):
    monkeypatch.delenv("ELEVENLABS_API_KEY")
    assert render_voice.main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    chars = sum(len(p) for p in PHRASES)  # 11 + 3 + 18 = 32
    assert chars == 32
    assert f"male: 3 frasi, {chars} caratteri" in out
    assert f"female: 3 frasi, {chars} caratteri" in out
    assert f"totale: 6 frasi, {2 * chars} caratteri" in out
    assert env.api.calls == []
    assert not env.dirs["male"].exists() and not env.dirs["female"].exists()


def test_dry_run_counts_only_what_is_missing(env, capsys):
    render_voice.main(["--voice", "male"])
    env.phrases.append("Scala prima")
    capsys.readouterr()
    render_voice.main(["--dry-run", "--voice", "male"])
    out = capsys.readouterr().out
    assert "male: 1 frasi, 11 caratteri" in out
    assert "female:" not in out


# --- la generazione -------------------------------------------------------------

def test_generation_writes_valid_wavs_and_manifest(env):
    assert render_voice.main(["--voice", "both"]) == 0
    from accoach.coaching.radio import radioize_wav
    for voice, d in env.dirs.items():
        man = _manifest(d)
        assert set(man) == set(PHRASES)
        for text, fname in man.items():
            assert fname == render_voice.slug(text) + ".wav"
            raw = (d / fname).read_bytes()
            assert raw[:4] == b"RIFF" and raw[8:12] == b"WAVE"
            with wave.open(io.BytesIO(raw)) as w:
                assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (22050, 1, 2)
                assert w.getnframes() == 2205
            radio = radioize_wav(raw)
            assert radio != raw and radio[:4] == b"RIFF"
        assert not list(d.glob("*.tmp"))
    assert len(env.api.calls) == 6


def test_request_carries_the_chosen_voice_model_and_settings(env):
    render_voice.main(["--voice", "male", "--only", "Gas"])
    (call,) = env.api.calls
    assert call["url"] == ("https://api.elevenlabs.io/v1/text-to-speech/"
                           "W71zT1VwIFFx3mMGH2uZ?output_format=pcm_22050")
    assert call["body"] == {
        "text": "Gas",
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.30, "similarity_boost": 0.70,
                           "style": 0.0, "speed": 1.10},
        "language_code": "it",
    }
    assert call["headers"]["xi-api-key"] == FAKE_KEY


def test_female_uses_tiziana(env):
    render_voice.main(["--voice", "female", "--only", "Gas"])
    assert "/RXoaSpLaWTEckJgPUBG3?" in env.api.calls[0]["url"]


def test_second_run_does_not_call_the_api(env):
    render_voice.main([])
    n = len(env.api.calls)
    render_voice.main([])
    assert len(env.api.calls) == n


def test_changed_setting_in_sidecar_regenerates_that_phrase(env):
    render_voice.main(["--voice", "male"])
    d = env.dirs["male"]
    side = _sidecar(d)
    side["Gas"]["voice_settings"]["speed"] = 1.0  # resa con un'altra velocita'
    (d / "render.json").write_text(json.dumps(side), encoding="utf-8")
    env.api.calls.clear()
    render_voice.main(["--voice", "male"])
    assert env.api.texts() == ["Gas"]
    assert _sidecar(d)["Gas"]["voice_settings"]["speed"] == 1.10


def test_wav_without_sidecar_entry_is_regenerated(env):
    """I WAV di Piper di oggi hanno il manifest ma nessun sidecar: si rifanno."""
    render_voice.main(["--voice", "male"])
    d = env.dirs["male"]
    side = _sidecar(d)
    del side["Frena prima"]
    (d / "render.json").write_text(json.dumps(side), encoding="utf-8")
    env.api.calls.clear()
    render_voice.main(["--voice", "male"])
    assert env.api.texts() == ["Frena prima"]


def test_missing_wav_file_is_regenerated(env):
    render_voice.main(["--voice", "male"])
    d = env.dirs["male"]
    (d / _manifest(d)["Gas"]).unlink()
    env.api.calls.clear()
    render_voice.main(["--voice", "male"])
    assert env.api.texts() == ["Gas"]


def test_phrase_removed_from_list_disappears(env):
    render_voice.main([])
    gone = render_voice.slug("Gas") + ".wav"
    env.phrases.remove("Gas")
    env.api.calls.clear()
    render_voice.main([])
    assert env.api.calls == []
    for d in env.dirs.values():
        assert "Gas" not in _manifest(d)
        assert "Gas" not in _sidecar(d)
        assert not (d / gone).exists()
        assert set(_manifest(d)) == {"Frena prima", "Qui perdi 3 decimi"}


def test_only_calls_only_those_even_if_up_to_date(env):
    render_voice.main([])
    env.api.calls.clear()
    render_voice.main(["--only", "Gas"])
    assert env.api.texts() == ["Gas", "Gas"]  # una per voce


def test_only_with_unknown_phrase_stops(env, capsys):
    with pytest.raises(SystemExit):
        render_voice.main(["--only", "Frase che non esiste"])
    assert env.api.calls == []
    assert "non e' nell'elenco" in capsys.readouterr().err


# --- la chiave ------------------------------------------------------------------

def test_key_read_from_file_in_user_profile(env, monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY")
    # Blocco note salva con BOM e a capo: la chiave va ripulita.
    (env.home / ".elevenlabs-key").write_text("﻿" + FAKE_KEY + "\r\n", encoding="utf-8")
    render_voice.main(["--voice", "male", "--only", "Gas"])
    assert env.api.calls[0]["headers"]["xi-api-key"] == FAKE_KEY


def test_missing_key_stops_before_any_call(env, monkeypatch, capsys):
    monkeypatch.delenv("ELEVENLABS_API_KEY")
    with pytest.raises(SystemExit):
        render_voice.main([])
    assert env.api.calls == []
    assert "ELEVENLABS_API_KEY" in capsys.readouterr().err


@pytest.mark.parametrize("code", [401, 402, 429])
def test_auth_quota_rate_errors_stop_without_the_key(env, capsys, code):
    render_voice.main(["--voice", "male", "--only", "Gas"])  # una frase gia' fatta
    d = env.dirs["male"]
    before = (d / "manifest.json").read_bytes()
    env.api.fail["Frena prima"] = code
    with pytest.raises(SystemExit) as exc:
        render_voice.main(["--voice", "male"])
    out, err = capsys.readouterr()
    assert str(code) in err
    for text in (out, err, str(exc.value)):
        assert FAKE_KEY not in text
        assert "FINTA" not in text
    assert FAKE_KEY.encode() not in _all_written_bytes(env.tmp)
    # nessun WAV rotto, nessun manifest a meta'
    assert not (d / (render_voice.slug("Frena prima") + ".wav")).exists()
    assert not list(d.glob("*.tmp"))
    assert (d / "manifest.json").read_bytes() == before


def test_error_midway_keeps_what_was_already_paid(env):
    """Si ferma alla frase che fallisce, ma le frasi prima restano salvate."""
    env.api.fail["Gas"] = 500
    with pytest.raises(SystemExit):
        render_voice.main(["--voice", "male"])
    d = env.dirs["male"]
    man = _manifest(d)
    assert "Frena prima" in man and "Gas" not in man
    assert (d / man["Frena prima"]).exists()
    assert not list(d.glob("*.tmp"))
    assert "Frena prima" in _sidecar(d) and "Gas" not in _sidecar(d)


def test_empty_audio_is_an_error_not_a_wav(env, monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: _Resp(b""))
    with pytest.raises(SystemExit):
        render_voice.main(["--voice", "male", "--only", "Gas"])
    assert not (env.dirs["male"] / (render_voice.slug("Gas") + ".wav")).exists()


# --- l'ascolto ------------------------------------------------------------------

def test_listen_writes_a_page_outside_the_repo(env, monkeypatch, capsys):
    render_voice.main([])
    listen_root = env.tmp / "listen"
    listen_root.mkdir()
    monkeypatch.setattr(render_voice.tempfile, "tempdir", str(listen_root))
    env.api.calls.clear()
    monkeypatch.delenv("ELEVENLABS_API_KEY")  # l'ascolto non chiede la chiave
    assert render_voice.main(["--listen"]) == 0
    assert env.api.calls == []
    (page,) = listen_root.rglob("voice_listen.html")
    assert _ROOT not in page.parents
    html = page.read_text(encoding="utf-8")
    for p in PHRASES:
        assert p in html
    clips = list(page.parent.glob("*.wav"))
    assert len(clips) == 2 * len(PHRASES)  # ogni frase in entrambe le voci
    for c in clips:
        assert c.name in html
    assert str(page) in capsys.readouterr().out


# --- quale accoach ----------------------------------------------------------------

def test_reports_which_accoach_it_loaded(env, capsys):
    render_voice.main(["--dry-run"])
    out = capsys.readouterr().out
    assert "accoach da " in out
    assert str(_ROOT / "src") in out


# --- la pulizia della cartella ---------------------------------------------------

STRAY = "cue_deadbeef00.wav"


def test_full_run_removes_stray_wav_even_with_nothing_to_render(env):
    render_voice.main(["--voice", "male"])
    d = env.dirs["male"]
    (d / STRAY).write_bytes(b"RIFF")
    env.api.calls.clear()
    render_voice.main(["--voice", "male"])  # niente da generare
    assert env.api.calls == []
    assert not (d / STRAY).exists()
    assert set(_manifest(d)) == set(PHRASES)


def test_full_run_with_work_removes_stray_wav(env):
    d = env.dirs["male"]
    d.mkdir(parents=True)
    (d / STRAY).write_bytes(b"RIFF")
    render_voice.main(["--voice", "male"])
    assert not (d / STRAY).exists()


def test_only_keeps_stray_wav(env):
    render_voice.main(["--voice", "male"])
    d = env.dirs["male"]
    (d / STRAY).write_bytes(b"RIFF")
    render_voice.main(["--voice", "male", "--only", "Gas"])
    assert (d / STRAY).exists()


@pytest.mark.parametrize("args", [["--voice", "male"], ["--voice", "male", "--only", "Gas"]])
def test_stale_tmp_files_are_removed(env, args):
    """Un'interruzione puo' lasciare `.tmp` che PyInstaller impacchetterebbe."""
    render_voice.main(["--voice", "male"])
    d = env.dirs["male"]
    (d / "manifest.json.tmp").write_text("{", encoding="utf-8")
    (d / "cue_0123456789.wav.tmp").write_bytes(b"RI")
    render_voice.main(args)
    assert not list(d.glob("*.tmp"))


# --- errori che hanno una causa precisa -------------------------------------------

def _fail_with(env, monkeypatch, code, body):
    def boom(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, code, "errore", {},
                                     io.BytesIO(json.dumps(body).encode()))
    monkeypatch.setattr(urllib.request, "urlopen", boom)


@pytest.mark.parametrize("code,body", [
    (404, {"detail": {"status": "voice_not_found",
                      "message": f"A voice with voice_id W71zT1VwIFFx3mMGH2uZ was not found. {FAKE_KEY}"}}),
    (400, {"detail": {"status": "voice_not_found", "message": "voice missing"}}),
    (404, {"detail": "Not Found"}),
])
def test_missing_voice_says_to_add_it_from_the_library(env, monkeypatch, capsys, code, body):
    _fail_with(env, monkeypatch, code, body)
    with pytest.raises(SystemExit):
        render_voice.main(["--voice", "male", "--only", "Gas"])
    out, err = capsys.readouterr()
    assert "My voices" in err and "MarcoTrox" in err and "Tiziana" in err
    assert FAKE_KEY not in out + err


def test_language_code_unsupported_is_said_clearly(env, monkeypatch, capsys):
    _fail_with(env, monkeypatch, 400, {"detail": {
        "status": "unsupported_language",
        "message": f"Model eleven_multilingual_v2 does not support language_code. {FAKE_KEY}"}})
    with pytest.raises(SystemExit):
        render_voice.main(["--voice", "male", "--only", "Gas"])
    out, err = capsys.readouterr()
    assert "language_code" in err and "non lo accetta" in err
    assert FAKE_KEY not in out + err


# --- pronuncia e pause nel testo mandato -------------------------------------

BRK = ', <break time="0.3s" /> '


def test_render_text_respells_whole_words_keeping_the_capital():
    assert render_voice.render_text("Ammorbidisci la barra antirollio anteriore.") == \
        "Ammorbidisci la barra antirollìo anteriore."
    assert render_voice.render_text("Pattini in uscita") == "Pàttini in uscita"
    assert render_voice.render_text("Ultimo giro") == "Ùltimo giro"
    # parola intera: «pattinio» o «subitodopo» non contengono una parola da toccare
    assert render_voice.render_text("margineggia") == "margineggia"


def test_render_text_leaves_accented_tronche_alone():
    assert render_voice.render_text("più metà velocità così com'era") ==         "più metà velocità così com'era"


def test_render_text_qui_in_the_middle_and_at_the_start():
    assert render_voice.render_text("Qui perdi 3 decimi") == "Quì perdi 3 decimi"
    assert render_voice.render_text("Dai più gas qui") == "Dai più gas quì"
    assert render_voice.render_text("qui perdi") == "quì perdi"
    # una parola che contiene «qui» non si tocca
    assert render_voice.render_text("quindi equilibrio") == "quindi equilibrio"


def test_render_text_spells_out_the_acronyms():
    assert render_voice.render_text("Alza il TC di uno.") == "Alza il ti-ci di uno."
    # esatta: «tc» minuscolo o dentro un'altra parola non e' la sigla
    assert render_voice.render_text("tcx") == "tcx"


def test_render_text_pause_after_every_comma():
    assert render_voice.render_text("Arrivi lungo, frena prima") == \
        f"Arrivi lungo{BRK}frena prima"
    assert render_voice.render_text("Qui hai margine, frena, poi molli") == \
        f"Quì hai màrgine{BRK}frena{BRK}poi mòlli"
    # una virgola senza spazio (un numero) non e' una pausa
    assert render_voice.render_text("1,5 secondi") == "1,5 secondi"


def test_request_body_uses_render_text_but_manifest_uses_the_original(env):
    env.phrases[:] = ["Qui hai margine, frena più tardi"]
    render_voice.main(["--voice", "male"])
    (call,) = env.api.calls
    assert call["body"]["text"] == f"Quì hai màrgine{BRK}frena più tardi"
    d = env.dirs["male"]
    assert list(_manifest(d)) == ["Qui hai margine, frena più tardi"]
    assert _manifest(d)["Qui hai margine, frena più tardi"] == \
        render_voice.slug("Qui hai margine, frena più tardi") + ".wav"


def test_sidecar_records_the_text_sent_and_pronunciation_change_regenerates(env, monkeypatch):
    env.phrases[:] = ["Pattini in uscita"]
    render_voice.main(["--voice", "male"])
    d = env.dirs["male"]
    assert _sidecar(d)["Pattini in uscita"]["text"] == "Pàttini in uscita"
    env.api.calls.clear()
    render_voice.main(["--voice", "male"])
    assert env.api.calls == []  # stessa tabella: niente da pagare
    monkeypatch.setattr(render_voice, "PRONUNCIA",
                        {**render_voice.PRONUNCIA, "pattini": "pattìni"})
    render_voice.main(["--voice", "male"])
    assert env.api.texts() == ["Pattìni in uscita"]
    assert _sidecar(d)["Pattini in uscita"]["text"] == "Pattìni in uscita"


def test_dry_run_counts_the_characters_actually_sent(env, capsys):
    env.phrases[:] = ["Qui, ora"]
    render_voice.main(["--dry-run", "--voice", "male"])
    out = capsys.readouterr().out
    sent = f"Quì{BRK}ora"
    assert f"male: 1 frasi, {len(sent)} caratteri" in out
    assert env.api.calls == []


def test_show_lists_pairs_and_never_calls_the_api(env, capsys):
    env.phrases[:] = ["Gas", "Qui, ora"]
    assert render_voice.main(["--show"]) == 0
    out = capsys.readouterr().out
    assert "Qui, ora" in out and f"Quì{BRK}ora" in out
    assert "1 frasi su 2 cambiano" in out
    assert env.api.calls == []
    assert not env.dirs["male"].exists()


def test_old_sidecar_without_text_counts_as_phrase_sent_plain(env):
    env.phrases[:] = ["Gas", "Pattini in uscita"]
    render_voice.main(["--voice", "male"])
    d = env.dirs["male"]
    side = _sidecar(d)
    for e in side.values():
        del e["text"]  # come lo scriveva lo script di prima
    (d / "render.json").write_text(json.dumps(side), encoding="utf-8")
    env.api.calls.clear()
    render_voice.main(["--voice", "male"])
    # «Gas» e' uguale: gia' approvata, non si rifa'. «Pattini...» cambia: si rifa'.
    assert env.api.texts() == ["Pàttini in uscita"]


def test_abs_is_not_respelled(env):
    assert render_voice.render_text("Alza l'ABS di uno") == "Alza l'ABS di uno"


def test_prune_non_esce_dalla_cartella(tmp_path):
    d = tmp_path / "voce"
    d.mkdir()
    fuori = tmp_path / "x.wav"
    fuori.write_bytes(b"non toccare")
    dentro = d / "x.wav"
    dentro.write_bytes(b"mio")
    manifest = {"frase": "../x.wav"}
    render_voice._prune(d, ["frase"], manifest, {"frase": {}})
    assert fuori.read_bytes() == b"non toccare"
    assert not dentro.exists()          # solo il nome, dentro d
    assert manifest == {}
