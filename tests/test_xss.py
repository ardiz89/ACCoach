"""Niente codice che entra nelle pagine: la guida e i nomi scritti dal pilota.

La revisione di sicurezza del 23/10 ne ha trovate due:

* ``/guida?lang=`` metteva la lingua così com'era dentro ``<html lang="…">``:
  un link con ``lang="><script>…`` eseguiva il suo script sulla 8778, che è la
  pagina da cui partono le scritture degli assetti;
* i nomi curva e i riferimenti di frenata, scritti dal pilota (o da chiunque
  raggiunga la 8778), finivano in ``innerHTML`` senza escape nel report e nella
  pagina Ingegnere. Un nome è salvato su disco: lo script restava lì e girava a
  ogni apertura.

Le difese sono due e servono entrambe: il server rifiuta ``<`` e ``>`` nei
nomi (Decisione 10; apostrofi, virgolette e ``&`` restano ammessi, «Curva
dell'Ascari» è un nome vero), e le pagine escapano comunque ogni dato, perché
sul disco ci possono già essere nomi scritti prima di questa regola.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from accoach import cornernames, guide
from accoach.api import create_api
from accoach.recording.storage import save_lap

import synth

WEB = Path(__file__).resolve().parent.parent / "src" / "accoach" / "web"
CAR, TRACK = "ferrari_488_gt3", "monza"
APEX = 0.31
EVIL = "<img src=x onerror=alert(1)>"


@pytest.fixture
def store(tmp_path, monkeypatch):
    """Il file dei nomi in una cartella del test, mai in quella del pilota."""
    p = tmp_path / "corner-names.json"
    monkeypatch.setattr(cornernames, "path", lambda: p)
    return p


@pytest.fixture
def client(tmp_path, store):
    laps = tmp_path / "laps"
    laps.mkdir()
    for i in range(3):
        lap = synth.build_lap()
        lap.recorded_utc = f"2026-08-04T18:0{i}:00+00:00"
        save_lap(lap, laps)
    return TestClient(create_api(laps))


# --- la guida ---------------------------------------------------------------

def test_a_script_in_the_language_does_not_reach_the_page(client):
    r = client.get("/guida", params={"lang": '"><script>alert(1)</script>'})
    assert r.status_code == 200
    assert "<script>alert(1)" not in r.text
    assert "alert(1)" not in r.text


def test_an_unknown_language_falls_back_to_a_real_one(client):
    r = client.get("/guida", params={"lang": "xx"})
    assert r.status_code == 200
    lang = re.search(r'<html lang="([^"]*)">', r.text).group(1)
    assert lang in ("it", "en")


def test_render_page_never_writes_an_unknown_language():
    page = guide.render_page("# T\n\ntesto", lang='it"><b>x</b>')
    assert '<html lang="en">' in page
    assert "<b>x</b>" not in page


def test_a_javascript_link_in_the_markdown_is_not_a_link():
    body, _ = guide.render_markdown("[x](javascript:alert(1))")
    assert 'href="javascript:' not in body
    assert "<a " not in body
    # Anche con le maiuscole e con gli spazi che il browser perdona.
    for href in ("JavaScript:alert(1)", "data:text/html,x", "vbscript:x"):
        body, _ = guide.render_markdown(f"[x]({href})")
        assert "<a " not in body, href


@pytest.mark.parametrize("href", ["https://a.b", "http://a.b", "#s", "FAQ.md",
                                  "docs/FAQ.md#voce", "mailto:a@b.c"])
def test_ordinary_links_stay_links(href):
    body, _ = guide.render_markdown(f"[x]({href})")
    assert f'<a href="{href}">x</a>' in body


# --- il server rifiuta i caratteri che aprono codice -------------------------

def _name(c, name):
    return c.post("/api/corner-name", json={"track": TRACK, "pos": APEX, "name": name})


def _mark(c, text):
    return c.post("/api/braking-reference",
                  json={"track": TRACK, "pos": APEX, "text": text})


@pytest.mark.parametrize("bad", [EVIL, "a>b", "<b>Tosa", "Curva <"])
def test_a_corner_name_with_markup_characters_is_refused(client, store, bad):
    r = _name(client, bad)
    assert r.status_code == 400
    assert not store.exists() or bad not in store.read_text(encoding="utf-8")
    assert len(cornernames.for_track(TRACK, store)) == 0


def test_the_refusal_says_why_in_the_drivers_language(client):
    it = client.post("/api/corner-name?lang=it",
                     json={"track": TRACK, "pos": APEX, "name": EVIL})
    en = client.post("/api/corner-name?lang=en",
                     json={"track": TRACK, "pos": APEX, "name": EVIL})
    assert it.status_code == en.status_code == 400
    assert it.json()["detail"] == "Il nome non può contenere < o >."
    assert en.json()["detail"] == "The name can't contain < or >."


def test_the_reference_refusal_has_its_own_sentence(client):
    """Un riferimento non è un nome: la frase lo dice."""
    it = client.post("/api/braking-reference?lang=it",
                     json={"track": TRACK, "pos": APEX, "text": EVIL})
    en = client.post("/api/braking-reference?lang=en",
                     json={"track": TRACK, "pos": APEX, "text": EVIL})
    assert it.status_code == en.status_code == 400
    assert it.json()["detail"] == "Il riferimento non può contenere < o >."
    assert en.json()["detail"] == "The reference can't contain < or >."


@pytest.mark.parametrize("good", ["Tamburello", 'Curva "Villeneuve"',
                                  "Raidillon de l'Eau Rouge", "Curva dell'Ospedale",
                                  "Tosa & Rivazza"])
def test_a_real_name_is_accepted_quotes_and_apostrophes_included(client, store, good):
    """Gli apostrofi stanno nei nomi veri («Raidillon de l'Eau Rouge»), e ogni
    pagina li escapa con `esc`: si vietano solo `<` e `>`, che aprono un tag."""
    assert _name(client, good).status_code == 200
    assert cornernames.for_track(TRACK, store).of(APEX) == good


@pytest.mark.parametrize("bad", [EVIL, "Il cartello <100>"])
def test_a_braking_reference_with_markup_characters_is_refused(client, store, bad):
    r = _mark(client, bad)
    assert r.status_code == 400
    assert r.json()["detail"]
    assert len(cornernames.marks_for(TRACK, store)) == 0


@pytest.mark.parametrize("good", ["Cartello dei 100", 'Il cartello "100"',
                                  "Ponte & cordolo", "All'inizio del cordolo"])
def test_an_ordinary_braking_reference_is_still_accepted(client, store, good):
    assert _mark(client, good).status_code == 200
    assert len(cornernames.marks_for(TRACK, store)) == 1


def test_the_store_itself_refuses_them_too(store):
    """Il server non è l'unica strada per `put`: la regola sta nel negozio."""
    assert cornernames.FORBIDDEN == set("<>")
    with pytest.raises(ValueError):
        cornernames.put(TRACK, APEX, EVIL, store)
    with pytest.raises(ValueError):
        cornernames.put_mark(TRACK, APEX, EVIL, store)
    # Togliere un nome (testo vuoto) resta possibile.
    cornernames.put(TRACK, APEX, "", store)


def test_a_dirty_names_file_from_before_does_not_break_the_report(client, store):
    """Review Focus 4: nomi già salvati con i caratteri ora vietati. Il report
    non deve cadere, e il nome arriva com'è (sarà la pagina a escaparlo)."""
    store.write_text(json.dumps({
        TRACK: {"corners": [{"pos": APEX, "name": EVIL}],
                "marks": [{"pos": APEX, "text": 'Il "cartello" & <b>'}]},
    }), encoding="utf-8")
    r = client.get("/api/analysis", params={"car": CAR, "track": TRACK, "lang": "it"})
    assert r.status_code == 200
    assert EVIL in json.dumps(r.json(), ensure_ascii=False)
    assert client.get("/api/braking",
                      params={"car": CAR, "track": TRACK, "lang": "it"}).status_code == 200
    # E lo si può ancora togliere: il vuoto è l'annulla.
    assert _name(client, "").status_code == 200


# --- le pagine escapano ogni dato --------------------------------------------

_NODE = shutil.which("node")
needs_node = pytest.mark.skipif(_NODE is None, reason="serve node per eseguire esc")


@needs_node
@pytest.mark.parametrize("page", ["app.js", "engineer.js"])
def test_esc_escapes_all_five_characters(page, tmp_path):
    src = (WEB / page).read_text(encoding="utf-8")
    i = src.index("function esc(")
    fn = src[i:src.index("\n}", i) + 2]
    script = tmp_path / "esc.js"
    script.write_text(fn + "\nprocess.stdout.write(JSON.stringify(["
                      "esc(`<img src=x onerror=\"a\">'&`), esc(null), esc(0), esc(undefined)]));",
                      encoding="utf-8")
    out = json.loads(subprocess.run([_NODE, str(script)], capture_output=True,
                                    text=True, check=True).stdout)
    assert out[0] == "&lt;img src=x onerror=&quot;a&quot;&gt;&#39;&amp;"
    assert out[1] == "" and out[2] == "0" and out[3] == ""


#: Le parole che, in fondo a un nome di variabile, vogliono dire «testo che
#: viene dal server o dal pilota». Un locale che contiene HTML già costruito si
#: chiama `…HTML`, e così si distingue da un dato da escapare.
_DATA = re.compile(r"(?:^|\.)(name|where|message|label|theme|detail|fix|headline|"
                   r"title|note|words|symptom|physical|slot|slotLabel|"
                   r"setupName|lastWritten|errors|corners)$")
_CHAIN = re.compile(r"^[A-Za-z_$][\w$]*(?:\.[\w$]+)*$")
#: Un template che finisce in testo semplice (textContent, un attributo messo
#: col DOM, un toast) non va escapato: lì `esc` farebbe vedere `&amp;`.
_TEXT_SINK = re.compile(r"textContent|setAttribute\(|showToast\(|\.title\s*=|"
                        r"\.value\s*=|\.label\s*=|console\.|fillText|showModalError\(|"
                        r"per il canvas")


def _statement_before(lines, n):
    """Le righe della frase che contiene la riga ``n`` (0-based), fin lì."""
    k = n
    while k > 0:
        prev = lines[k - 1].rstrip()
        if prev.endswith((";", "{", "}")) or not prev.strip():
            break
        k -= 1
    return "\n".join(lines[k:n + 1])


def _unescaped(src):
    lines = src.split("\n")
    bad = []
    for m in re.finditer(r"\$\{([^{}`]*)\}", src):
        expr = m.group(1).strip()
        if not (_CHAIN.match(expr) and _DATA.search(expr)):
            continue
        n = src.count("\n", 0, m.start())
        if _TEXT_SINK.search(_statement_before(lines, n)):
            continue
        bad.append(f"{n + 1}: ${{{expr}}}")
    # Lo stesso dato attaccato con `+` fuori da un template («… + c.name»): era
    # la forma di `lineNameHTML`, che il controllo sui `${…}` non vedeva.
    for m in re.finditer(r"\+\s*([A-Za-z_$][\w$]*(?:\.[\w$]+)+)\s*(?=[;+)\n,])", src):
        expr = m.group(1)
        if not _DATA.search(expr):
            continue
        n = src.count("\n", 0, m.start())
        if _TEXT_SINK.search(_statement_before(lines, n)):
            continue
        bad.append(f"{n + 1}: + {expr}")
    return bad


@pytest.mark.parametrize("page", ["app.js", "engineer.js"])
def test_every_data_string_in_a_template_goes_through_esc(page):
    """Ogni nome, `where`, `message`, `label`, `theme` (e i loro cugini) che entra
    in un template passa da `esc(`. Il controllo guarda la FORMA, e una forma si
    aggira: per questo c'è anche la prova sotto, che muta il sorgente."""
    src = (WEB / page).read_text(encoding="utf-8")
    assert _unescaped(src) == []


def test_the_check_above_does_see_an_unescaped_name():
    """La mutazione: togliere `esc` da uno dei punti della revisione deve far
    fallire il controllo, se no il controllo non controlla niente."""
    src = (WEB / "app.js").read_text(encoding="utf-8")
    eng = (WEB / "engineer.js").read_text(encoding="utf-8")
    for src, expr in ((src, "r.message"), (src, "w.name"), (src, "s.where"),
                      (src, "l.label"), (src, "corner.name"), (eng, "fc.theme"),
                      (eng, "fc.name"), (eng, "c.label")):
        good = "${esc(" + expr + ")}"
        assert good in src, good
        assert _unescaped(src.replace(good, "${" + expr + "}", 1)), expr


def test_the_review_points_are_escaped():
    """I punti esatti della revisione, per nome: un controllo generico che un
    giorno smettesse di vederli non deve portarseli via in silenzio."""
    app = (WEB / "app.js").read_text(encoding="utf-8")
    for s in ("esc(r.message)", 'r.corners.map(esc).join(", ")', "esc(w.name)",
              "esc(r.name)", "esc(l.label)", "esc(c.name)", "esc(n.message)",
              "esc(l.message)", "esc(s.where)", "esc(corner.name)",
              "esc(lap.max_off_where)", "esc(e.message)"):
        assert s in app, s
    eng = (WEB / "engineer.js").read_text(encoding="utf-8")
    for s in ("esc(fc.name)", "esc(fc.theme)", "esc(c.label)",
              "res.errors.map(esc).join", "esc(state.lastWritten)",
              "esc(p.label)", "esc(p.note)"):
        assert s in eng, s
