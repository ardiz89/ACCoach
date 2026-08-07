# Il Confronto con la mappa accanto — piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** grafici di telemetria a sinistra e mappa del tracciato a destra sullo stesso schermo, con la mappa ferma mentre scorri i grafici. La scheda «Mappa» sparisce e il Confronto la assorbe.

**Architettura:** nessun disegno nuovo. I quattro grafici del Confronto e la mappa esistono già e funzionano: questo lavoro li mette in due colonne, sposta la scheda frenate con la mappa, toglie una scheda e ricuce i riferimenti che la nominavano.

**Tech Stack:** HTML/CSS/JS ES5-ish senza toolchain, canvas 2D.

**Spec:** `docs/superpowers/specs/2026-08-06-confronto-con-mappa-design.md`

## Global Constraints

- **Questo lavoro sposta, non ridisegna.** Cosa disegnano i grafici e la mappa non si tocca. Se qualcosa non piace di come sono fatti oggi, è un altro lavoro.
- **La pagina non deve scorrere di lato**, né a larghezza piena né stretta, e va **misurato** (`scrollWidth` contro `innerWidth`), non guardato: questa pagina ha già spedito 39 px di scroll orizzontale su telefono.
- **Niente stringhe fisse:** ogni testo che resta a schermo passa da `i18n.js` in entrambe le lingue, e le chiavi della scheda che sparisce non devono restare orfane.
- **La voce non cambia** e nessun endpoint cambia: è tutto frontend.
- **Suite:** verde su `main`. Deve restare verde.

---

### Task 1: Le due colonne, e la scheda che sparisce

**Files:**
- Modify: `src/accoach/web/index.html`, `src/accoach/web/app.js`, `src/accoach/web/style.css`, `src/accoach/web/i18n.js`
- Test: `tests/test_web_views.py`

- [ ] **Step 1: Scrivi i test che falliscono**

```python
def test_the_map_lives_in_compare_now():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert 'id="view-map"' not in html
    assert 'data-view="map"' not in html
    # la mappa, la sua legenda, il suo stato vuoto e la scheda frenate
    # sono dentro la vista Confronto
    ids = _view_of_ids()          # la helper del file: id -> vista che lo contiene
    for el in ("c-map", "map-readout", "map-missing", "brakesheet"):
        assert ids[el] == "compare"


def test_the_rail_no_longer_lists_the_map():
    js = (WEB / "app.js").read_text(encoding="utf-8")
    rail = js[js.index("RAIL_VIEWS"):js.index("\n", js.index("RAIL_VIEWS"))]
    assert '"map"' not in rail
    assert '"compare"' in rail
```

> Se `_view_of_ids()` non esiste in `tests/test_web_views.py`, guarda come il file
> risolve oggi la stessa domanda e riusa quel meccanismo.

- [ ] **Step 2: Esegui i test e verifica che falliscano**

Run: `python -m pytest tests/test_web_views.py -q -k "map or rail"`
Expected: FAIL

- [ ] **Step 3: Implementa — l'HTML**

Sposta dentro `#view-compare`, in una struttura a due colonne:

```html
  <div id="view-compare" class="hidden">
    <div class="cmp-shell">
      <div class="cmp-charts">
        <!-- i quattro grafici di oggi, nell'ordine di oggi -->
      </div>
      <aside class="cmp-map">
        <!-- il contenuto di #view-map: readout, mappa, legenda, stato vuoto -->
        <!-- e la scheda frenate, che è la stessa domanda in numeri -->
      </aside>
    </div>
  </div>
```

Elimina `#view-map` e il suo bottone. **Non buttare niente del contenuto:** riga di lettura, legenda (compresa la voce «dove il giro si è perso», che compare solo quando quel giro ce l'ha), stato vuoto «questo giro non ha coordinate» e scheda frenate si trasferiscono interi.

- [ ] **Step 4: Implementa — il CSS**

```css
.cmp-shell { display: grid; grid-template-columns: minmax(0, 1fr) minmax(320px, 38%);
  gap: 20px; align-items: start; }
/* La mappa resta ferma mentre scorri i grafici: è tutto il senso della cosa. */
.cmp-map { position: sticky; top: 12px; }

@media (max-width: 900px) {
  /* Impilate, con la mappa SOPRA: è l'orientamento, e serve prima del dettaglio. */
  .cmp-shell { grid-template-columns: 1fr; }
  .cmp-map { position: static; order: -1; }
}
```

`minmax(0, 1fr)` sulla prima colonna non è ornamentale: senza lo `0`, un canvas
largo impedisce alla colonna di restringersi ed è così che nasce lo scroll
laterale.

- [ ] **Step 5: Implementa — il JS**

Cerca ogni punto che nomina la vista `"map"` e portalo su `"compare"`: la lista
`RAIL_VIEWS`, i rami `if (VIEW === "map")` che disegnano la mappa e caricano la
scheda frenate, e il ramo che mostra il messaggio di caricamento. Il disegno
della mappa e della scheda frenate deve avvenire **quando si apre il Confronto**,
insieme ai grafici — non più su una vista sua.

**Il canvas va ridimensionato davvero.** La mappa passa da tutta larghezza a una
colonna: verifica come le altre tele prendono la loro misura in questo file e
assicurati che la mappa faccia lo stesso, anche quando la finestra cambia
dimensione con la scheda già aperta.

- [ ] **Step 6: Implementa — i18n**

`tab.map` non serve più: toglila. Le chiavi del contenuto trasferito (readout,
legenda, stato vuoto) **restano**, perché il contenuto resta.
`tests/test_web_i18n_keys.py` deve restare verde, e non devono avanzare chiavi
orfane in nessuna delle due lingue.

- [ ] **Step 7: Esegui i test e verifica che passino**

Run: `python -m pytest tests/test_web_views.py tests/test_web_i18n_keys.py tests/test_bundle_contents.py -q`
Expected: PASS

- [ ] **Step 8: Verifica a schermo — è qui che si vede se funziona**

Apri il Confronto su un giro con coordinate:

1. i grafici a sinistra, la mappa a destra, e la mappa **resta ferma** scorrendo;
2. la mappa è disegnata **alla larghezza della colonna**, non tagliata né schiacciata;
3. il **rail** (la colonna delle curve) funziona sul Confronto;
4. la scheda frenate c'è;
5. un giro **senza coordinate** mostra il suo messaggio invece di una tela vuota;
6. a larghezza stretta le colonne si impilano con la mappa sopra, e
   `document.documentElement.scrollWidth <= window.innerWidth` — **misuralo**;
7. ridimensiona la finestra con la scheda aperta: la mappa si ridisegna giusta.

- [ ] **Step 9: Commit**

```bash
git add src/accoach/web/ tests/test_web_views.py
git commit -m "Il Confronto si tiene la mappa accanto, e la scheda Mappa sparisce"
```

---

### Task 2: La guida segue le schede

**Files:** `GUIDA.md` (§5, ovunque nomini la scheda Mappa)

- [ ] **Step 1: Cerca e aggiorna**

Cerca «Mappa» in `GUIDA.md` e sistema ogni punto che manda il pilota su una
scheda che non esiste più: la mappa ora si legge **dentro il Confronto**, accanto
ai grafici, e la scheda frenate sta lì con lei.

- [ ] **Step 2: Verifica e commit**

Run: `python -m pytest tests/test_guide.py -q`

```bash
git add GUIDA.md
git commit -m "La guida: la mappa si legge nel Confronto"
```

---

## Chiusura

- [ ] `python -m pytest -q` verde
- [ ] I sette controlli a schermo del Task 1, fatti davvero
- [ ] REQUIRED SUB-SKILL: `superpowers:finishing-a-development-branch`
