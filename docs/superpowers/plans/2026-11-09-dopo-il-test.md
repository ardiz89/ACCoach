# Dopo il test dell'08/11 — piano

**Goal:** correggere tre cose viste nel test del pilota (ACC, 720S, Imola,
08/11): l'Ingegnere che calcola sul setup sbagliato, il coach che si ripete, il
carburante che il tablet non mostra.

**Spec:** la chat del 08-09/11, approvata dal pilota con «ok procedi». I fatti
misurati sono nella memoria `test-da-zero-2026-11-08`.

## Global Constraints

- Testi in italiano col tu, frasi brevi, virgola decimale, niente due punti a
  effetto, niente emoji; massimo 25 parole per frase nelle pagine e nella guida
  (`tests/test_tono.py`). Le frasi della voce massimo 8 parole.
- `tablet.js` gira su Safari 9 (iPad iOS 9.3.6): solo ES5 (`var`, niente
  arrow, niente template string, niente `fetch`), come il resto del file.
- Test sempre con la casa finta (`USERPROFILE`/`HOME` =
  una cartella finta nello scratchpad della sessione,
  `QT_QPA_PLATFORM=offscreen`, `PYTHONPATH=src`). Mai `Documents\ACCoach`
  vero, mai i setup veri di ACC, mai la porta 8778.
- I file del repo: si mantiene lo stile di fine riga di ciascun file.
- Commit con `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` e
  `Claude-Session: https://claude.ai/code/session_015rMgt45HYsP5VgTvkAVCs3`.
  Niente push. Mai il nome dell'account Windows nei file del repo.
- Ogni comportamento nuovo va in `GUIDA.md` e `docs/FAQ.md` (inglese), nella
  sezione che parla di quella cosa.

## A. L'Ingegnere non indovina il setup di partenza

Fatto misurato: a inizio sessione `/api/setup/base`
(`src/accoach/setup/web_api.py:306`) non ha ancora un `last_written` e propone il
file più recente per data (`HONE_2`, 65/60 sugli anteriori). Il pilota guidava
quasi certamente `720sEVO_Imola_0` (57/52). `HONE_3` ha alzato gli anteriori di
13 click invece di 5: a caldo 25,8 → 28,0 psi, contro +0,5 previsti.

1. **Il primo file si sceglie, non si propone.** Senza `last_written` per quella
   auto e pista, `/api/setup/base` risponde `"base": null` e `"confirm": true`,
   con l'elenco dei setup dal più recente. La schermata dei box del tablet
   (`tablet.js`, `bx`, `fillSelect`, `basePath`) e la pagina Ingegnere
   (`engineer.js`, la stessa scelta) mostrano la domanda «Quale assetto hai
   caricato in ACC?». La tendina parte vuota, e il tasto per scrivere resta
   spento finché il pilota non sceglie. Con `last_written` presente tutto
   resta come oggi.
2. **La risposta delle gomme si controlla.** Quando si chiude la prova di una
   modifica di pressione (`engineer/core.py`), per ogni asse cambiato si
   confronta lo spostamento misurato a caldo (mediana dei giri dopo meno quella
   dei giri prima, `LapStats.pressures_hot`) con quello previsto (click ×
   psi per click). Se `|misurato − previsto| > max(0,8 psi, |previsto|)`, la
   decisione porta `confirm_base: true` e un messaggio. Il messaggio dice di
   quanto si sono mosse le gomme e quanto valeva la modifica, e chiede di
   scegliere ai box l'assetto davvero caricato. Il tablet e la pagina Ingegnere,
   letto `confirm_base`, rifanno la domanda del punto 1. I numeri vanno fissati
   in un test con quelli dell'08/11:
   - previsto +0,5, misurato +2,2: scatta;
   - previsto −0,8, misurato −0,5: non scatta;
   - previsto −0,8, misurato −0,6: non scatta.
3. Test, guida, FAQ. Commit «L'Ingegnere chiede su quale assetto lavora».

## B. Il coach non si ripete

Fatti misurati l'08/11 (153 frasi in un'ora, 11 in 60 s):
- «Pattini in uscita» due volte a 1,5 e 1,6 s di distanza. Il limite
  anti-ripetizione è per tratto di pista (`scheduler.py`,
  `repeat_suppress_s`), e in uscita di curva l'auto cambia tratto;
- «Pattini in uscita» a ogni uscita dai box, con le gomme fredde;
- con un focus attivo la voce dice solo «qui perdi», perché `TIME_LOSS` sta in
  `TRIGGER` (`coaching/cue.py:227`). Eppure le frasi registrate «Qui perdi N
  decimi» esistono (`voice_cues/manifest.json`).

1. La stessa categoria non si ridice entro `SAME_CATEGORY_S = 5.0` secondi,
   qualunque sia il tratto. Vale per tutte le categorie, anche le urgenti.
2. Niente pattinamento (`WHEELSPIN`) nel giro di uscita dai box, cioè finché
   non si passa la linea la prima volta dopo l'uscita. Le gomme sono fredde e
   pattinare è normale.
3. `TIME_LOSS` esce da `TRIGGER`: la voce dice la frase intera col numero, che è
   già registrata.
4. Nel log del focus (`engine.py`, `_focus_log_line`) «perdi N ms» diventa
   «base N ms»: è il valore di partenza, non la perdita di quel giro.
5. Test, guida e FAQ dove parlano di quando il coach parla. Commit «Il coach non
   ripete la stessa frase e lascia stare il giro di uscita».

## C. Il carburante sul tablet

1. Lo stato dal vivo che arriva al tablet ha un blocco carburante:
   - `"fuel": {"litres": l, "pct": p, "laps": n}`;
   - `pct` = 100 × litri / capacità (`max_fuel`), oppure `null` se la
     capacità è 0;
   - `laps` = litri / consumo medio di `FuelEngineer` (giri interi, per
     difetto), oppure `null` finché non c'è un consumo misurato.
2. Sul tablet, nella vista Telemetria, una terza cifra grande accanto a velocità
   e marcia, con lo stesso stile:
   - la percentuale, con sotto «≈ N giri»;
   - «–» quando il dato non c'è.
   Solo ES5.
3. Test, guida, FAQ. Commit «Il tablet mostra la benzina e i giri che restano».
