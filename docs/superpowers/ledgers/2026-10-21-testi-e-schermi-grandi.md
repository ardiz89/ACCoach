# SDD ledger — plan: docs/superpowers/plans/2026-10-21-testi-e-schermi-grandi.md

Spec: docs/superpowers/specs/2026-10-21-testi-e-schermi-grandi-design.md (decisioni del pilota del 21/10: voce compresa, guida per ultima, testo che cresce da solo, inglese con le stesse regole; scelte mie elencate nella spec). Ramo feat/testi da main locale e18cdc7.

## Pre-flight scan
| Coppia / task | Produce → consuma | Esito |
|---|---|---|
| T1→T2..T11 | tono.SURFACES/PENDING/violations/placeholders, fmtNum, textfmt.fmt_num | coerente |
| T1→T3,T4 | T3 divide `report` in report_a/report_b dentro tono.py | coerente (T3 modifica il registro di T1) |
| T3/T4↔T6 | chiavi della pagina Ingegnere: T1 le esclude da `report`, T6 le possiede | coerente |
| T2↔T9 | app.js in entrambi | in serie: ok |
| T5↔T1 | howto.py: fmt_s delega a textfmt in T1, testi in T5 | in serie: ok |
| T3..T8→T10,T11 | la guida cita i testi nuovi | ordine giusto |
| T8 | Piper fuori dal repo, copiato dal worktree del main | ok |
| T1 self | regole + eccezioni (orari, tempi sul giro, rapporti) | ok |
| T2 self | toFixed vietato fuori dagli helper; attributi/CSV/JSON col punto | ok |
| T3,T4,T5,T6,T7 self | togli dal PENDING → rosso → riscrivi → verde | ok |
| T9 self | clamp 14→20 px fra 1600 e 2880 px | ok |
| T10,T11 self | ancore della guida da preservare | ok |
| T12 | controllore | ok |

Ruling 1: chi riscrive testi (T3-T8, T10-T11) lavora su opus — la qualità della prosa è il requisito del pilota («AI slop») — se sbagliato: costo più alto.
Ruling 2: la regola `long` (25 parole) non si applica alle righe di elenco della guida che sono comandi o percorsi — sono dati, non frasi — se sbagliato: qualche riga lunga resta.

## Avanzamento
Task 1: dispatched (BASE 0393c1b, implementer a1d1322421b692f56, sonnet)
Ruling: accettate le scelte di T1 (8 parole per la voce, duplicati da 4 parole in su, % e {x}s senza spazio come errore di unità, URL e percorsi ammessi, ▶ ● come emoji, superfici più larghe del piano) — coerenti con la spec — se sbagliato: soglie da ritoccare in tono.py.
Task 1: review → Needs fixes (3 Important: collettore coach incompleto; segnaposti al plurale {n|a|b}; rami if lang dell'Ingegnere invisibili)
Ruling: per i duplicati, la guida può ripetere i titoli e le etichette dell'interfaccia che cita (titoli e testo fra virgolette) — la guida nomina le schede — se sbagliato: una frase ripetuta nella guida sfugge.
Ruling: ordinali «2° giro» esenti dalla regola delle unità; migliaia «1.000» ammesse in italiano; i tempi di settore si scrivono come i tempi sul giro («34.512») e sono ammessi col punto dei millesimi — è il formato dei cronometri del gioco — se sbagliato: qualche tempo da riscrivere.
Task 1: fix round 1 inviato: Important 1-3 + minor 4-8 (FIX_BASE a33904d)
Task 1: fix round 1/5 (8 addressed, 0 open; commits a33904d..7dd0ece), suite 2831
Task 1: minor (deferred): placeholder_mismatches salta le coppie di rami (chiavi con @); alcuni cue f-string senza inglese; «4.512» passa come migliaia; riga con spazi in tono.py:449
Task 1: complete (commits 0393c1b..7dd0ece, review clean)
Task 2: dispatched (BASE 7dd0ece, implementer a2cf4ee5c42ab9a5d, sonnet)
Task 2: minor (noted): rec.gain «{gain}s» e ses.sub_temp «{from}°» unità attaccate nel catalogo → Task 3/4
Task 2: review → Needs fixes (3 Important: asse offset con fixz; allow-list troppo larga; temperatura asfalto grezza); fix round 1 inviato con minor 4,5 (FIX_BASE 72cad29)
Ruling: il segno meno nei numeri mostrati è «−» (U+2212) sia in JS (fmtNum) sia in Python (textfmt.fmt_num, da allineare nel Task 5); il trattino ASCII resta nei dati — le perdite usano già «−» — se sbagliato: un carattere da cambiare in due funzioni.
Task 2: fix round 1/5 (5 addressed, 0 open; commits 72cad29..8ddf676), suite 2847
Task 2: minor (deferred): fallback di fmtDec senza i18n.js stampa punto e «-»; c.road_temp null in conditionsNote non verificato
Task 2: complete (commits 7dd0ece..8ddf676, review clean)
Task 3: dispatched (BASE 8ddf676, implementer a1600d0f1b469aad4, opus)
Ruling: recur.none/trends.none dicono «Nei tuoi ultimi giri…» invece della frase d'esempio della spec — il riquadro legge gli ultimi 15 giri fra sessioni, la frase della spec sarebbe falsa — se sbagliato: nessuno.
Task 3: review → Needs fixes (2 Important: flow.map «X, col Y»; pag.declined che si fonde coi bottoni)
Ruling: demo.banner diventa «Questi sono giri di esempio generati da HONE, non i tuoi.» / «These are sample laps made by HONE, not yours.» — «giri di prova» per un pilota sono i suoi giri di prova — se sbagliato: ritocco.
Task 3: fix round 1 inviato: Important 1-2 + minor 3-14 + demo.banner (FIX_BASE a1a16f6)
Task 3: fix round 1/5 (15 addressed, 0 open; commits a1a16f6..0514e29), suite 2850
Task 3: minor (deferred): ses.none e st.none frase uguale (→ T4); trends.none en senza virgola dopo l'apertura
Task 3: complete (commits 8ddf676..0514e29, review clean)
Task 4: dispatched (BASE 0514e29, implementer a7f0bc76f7dd5988c, opus); scritta writer-guide.md con gli errori trovati nella revisione del T3
Ruling: da T4 in poi la revisione legge TUTTE le chiavi della superficie, non solo il diff — il controllo automatico vede la forma, il pilota ha chiesto tutto il tono; report_a (T3) avrà la stessa lettura completa nella revisione finale — se sbagliato: revisioni più lunghe.
Task 4: review → Needs fixes (5 Important: «Nello stint:» scritto in app.js; brk.note; didascalie a sei coppie; ideal.from senza verbo; «Settore il giro diviso in tre»); fix round 1 inviato con tutti i minor (FIX_BASE 9741afa)
Task 4: note per i Task 10/11: GUIDA.md:573 e FAQ.md:325 descrivono ancora il «nastro del bilanciamento»; bottoni icona ✎ ✕ in app.js restano (da decidere nella revisione finale)
Task 4: fix round 1/5 (13 addressed, 0 open; commits 9741afa..48265d0), suite 2853
Task 4: minor (deferred, da vedere nel browser al T12): «Settori (settori della pista)» forse ridondante; «Ingresso» in colonna stretta; line.name.hint it con virgola giuntiva
Task 4: complete (commits 0514e29..48265d0, review clean)
Task 5: dispatched (BASE 48265d0, implementer a08e5aa5c290d4827, opus)
Task 5: review → Needs fixes (6 Important: lift «compreso il rettilineo» falso; landmark «il riferimento frena» falso; «il 80 %»; frenata detta due volte; «arco» per un raggio; «Di questi» senza antecedente); fix round 1 inviato con i minor (FIX_BASE 3d57fb5)
Task 5: fix round 1/5 (14 addressed, 0 open; commits 3d57fb5..78f0192), suite 2866
Task 5: minor (deferred): esercizi di Allenamento serviti solo da /api/training (nessuna pagina li mostra, endpoint morto dal pezzo 1); fallback «Corner N» in debrief.py:215 (raro)
Task 5: complete (commits 48265d0..78f0192, review clean)
Task 6: dispatched (BASE 78f0192, implementer af3f397af0c9f7948, opus)
Task 6: note per T7/T10/T11: la voce dell'Ingegnere legge la frase intera del rimedio (oltre 8 parole); «Al volo» → «Dal volante» nell'interfaccia, GUIDA.md:154 ancora «Al volo» (test che lo cerca)
Task 6: review → Needs fixes (4 Important: rec.gain capovolge il segno; chiavi grezze aRBFront nel registro con la mappa già disponibile; eng.oc.side fusa con la lista; ordine delle parole dei sintomi in inglese); fix round 1 inviato con i minor 5-14 (15 al Task 8) (FIX_BASE fec2930)
Task 6: fix round 1/5 (16 addressed, 0 open; commits fec2930..30f320d), suite 2880
Task 6: complete (commits 78f0192..30f320d, review clean)
Task 7: dispatched (BASE 30f320d, implementer a0b09a7096af236c2, opus)
Ruling: il «✓» dei passi fatti nel pannello In pista resta come segno di stato in una colonna a sé (non dentro una frase) — i passi «che si spuntano da soli» li ha approvati il pilota — se sbagliato: un simbolo da togliere.
Ruling: i numeri grandi dell'HUD dell'overlay (delta, decimi) restano nel formato del cronometro col punto, come i tempi sul giro — il pilota li legge in movimento come nel gioco — se sbagliato: virgola da mettere nell'overlay.
Ruling: il motto del marchio «Know why you're slow.» resta in inglese anche in italiano — è il marchio (memoria del rebrand) — se sbagliato: una riga da tradurre.
Task 7: review → Needs fixes (1 Important: set.engineer_voice imperativo che sembra un ordine al pilota); fix round 1 inviato con i minor 2-18 (19 preesistente, al T12) (FIX_BASE 29baa95)
PAUSA 21/10 sera: il pilota ha chiesto di riprendere domani. T7 fix round 1 in volo (implementer a0b09a7096af236c2).
Task 7: fix round 1 committato e74a72e (suite 2889). DA FARE DOMANI: ri-revisione mirata 29baa95..e74a72e, poi Task 7: complete.
Task 7: fix round 1/5 (18 addressed, 0 open; commits 29baa95..e74a72e), suite 2889
Task 7: minor (deferred): set.pedals_hint/scale_hint in italiano aprono ancora quasi uguali; «All'inizio è spenta» ambiguo (meglio «Di base»); rientro di una riga in test_tono.py
Task 7: complete (commits 30f320d..e74a72e, review clean)
Task 8: dispatched (BASE e74a72e, opus); Piper copiato in tools/piper (ignorato da git)
Task 8: commit 379f674 (WAV 54→59 per voce, suite 2895); review dispatched
Task 8: review → Needs fixes (3 Important: «Sovrasterzo in uscita» afferma una fase che il rilevatore non misura; «bilanciamento» senza «freni»; «Dal prossimo giro scelgo» non sempre vero)
Ruling: nei messaggi del focus il nome della curva apre la frase come etichetta («{name}, …»), senza preposizione — come nella Pagella («In Variante Alta» è italiano sbagliato) — se sbagliato: ritocco.
Ruling: web/test_plan.json resta fuori dalla riscrittura del tono, ma le frasi del coach che cita fra virgolette si allineano a quelle nuove — sono fatti che il pilota verifica in pista — se sbagliato: nessuno.
Ruling: la leva della pressione detta a voce diventa un imperativo («Aggiungi 2 click alla pressione anteriore») anche se è della superficie engineer — la voce la legge dopo «rientra ai box» — se sbagliato: nessuno.
Da chiedere al pilota: la parola-innesco «rilascia» (patto del focus sulla frenata) suona opposta al consiglio «tienine un filo all'inserimento».
Task 8: fix round 1 inviato: Important 1-3 + minor 4-9, 11, 12 (FIX_BASE 379f674)
Task 8: fix round 1/5 (11 addressed, 0 open; commits 379f674..becb871), suite 2897
Task 8: minor (deferred): consiglio del bilanciamento freni ~5 s detto in rettilineo; leve dell'Ingegnere a voce fino a 9-10 parole
Task 8: complete (commits e74a72e..becb871, review clean)
Task 9: dispatched (BASE becb871, implementer a81f21381d136baa2, sonnet)
Ruling: la colonna di «Il giro spiegato» (.flow-shell, ~100 caratteri) resta com'è invece di scendere sotto 75 — la spec vuole anche il portatile identico, e i 75 caratteri erano una scelta mia — se sbagliato: righe lunghe da accorciare.
Task 9: review → Needs fixes (2 Important: tempi a destra dei grafici tagliati sui 32" per margini fissi; <small> sotto 12 px a 1600 px). Ruling: 18,5 px a 2560 (formula del piano) al posto dei 18 della spec — differenza di mezzo pixel, la formula è quella misurata — se sbagliato: nessuno. Fix round 1 inviato con i minor 3-8 (FIX_BASE 82f3f28)
Task 9: fix round 1/5 (8 addressed, 0 open; commits 82f3f28..97cc75e), suite 2924
Task 9: minor (deferred): offset fissi non al bordo (etichette anelli g-g, barra di scala, S/F); il test nel browser legge solo il DOM, il testo dei canvas misurato a mano
Task 9: complete (commits becb871..97cc75e, review clean)
Task 10: dispatched (BASE 97cc75e, implementer a4c28600afa52db2d, opus)
Task 10: review → Needs fixes (5 Important falsi: focus conta anche i giri sporchi; focus non restringe sempre la voce; pressioni solo GT3; tre scelte della Pagella; guadagno ciano non verde + 6 Important di prosa). Ruling: nello stesso giro si correggono anche eng.hint, tour.e1.x (Coach Live alimenta la pagina Ingegnere), focus.warmup (giri completi, anche sporchi), wiz.s3 (giro pulito) — sono affermazioni false in superfici già chiuse — se sbagliato: nessuno. Fix round 1 inviato (FIX_BASE dafdf6e)
Task 10: fix round 1/5 (tutti addressed; nuova incoerenza: GUIDA L108 «due giri puliti» contro «ti basta un giro pulito»; commento stantio sopra eng.hint) → fix round 2 inviato (FIX_BASE f02eb7f)
Task 10: fix round 2/5 (L108 un giro pulito, commento eng.hint; 70ff434) e 3/5 (riferimento che insegue il giro migliore; e593066) — verificati dal controllore sul diff (una frase ciascuno)
Task 10: minor (deferred): coach.warming del coach da terminale «Fai qualche giro pulito» (riguarda il riferimento, corretto)
Task 10: complete (commits 97cc75e..e593066, review clean)
Task 11: dispatched (BASE e593066, implementer a1ec895951ea544c5, opus)
Task 11: review → Needs fixes (GUIDA §1 falso su HONE.bat; «Track record»; «piece of advice» ×16; frasi rigide). Ruling: rec.title en diventa «Test log» (e FAQ L244/246) — «Track record» in un'app di corse è il record della pista — se sbagliato: un'etichetta. Ruling: GUIDA §1 si corregge in questo giro (HONE.exe senza Python, HONE.bat dal sorgente prepara Python) e --interactive si allinea fra le due guide. Fix round 1 inviato (FIX_BASE 2b7b44d)
Task 11: fix round 1/5 (tutti addressed). Nuovo: le guide dicono «python -m accoach <comando>» ma HONE.bat non installa il pacchetto (verificato: HONE.bat e help usano accoach_main.py) → fix round 2 inviato: dal sorgente «python accoach_main.py <comando>» (FIX_BASE dd9f276)
Task 11: fix round 2/5 (comandi dal sorgente con accoach_main.py; 8a119f5) — verificato dal controllore con grep (nessun «-m accoach» rimasto)
Task 11: complete (commits e593066..8a119f5, review clean); PENDING vuoto
Task 12: prova del controllore con Playwright (Chrome dava timeout) sulla copia dell'archivio, Imola 720S, 9 schede × 1366/1920/2560, it ed en: nessun errore di pagina, nessuno sbordo, nessun {segnaposto}/undefined/NaN, minimo 12 px a 1366, base 14/15,5/18,5. DIFETTI: (1) etichette «left/right» del grafico sterzo scritte a mano in inglese anche in italiano (axisLabel, app.js:3976, 4285) e «left» sopra l'etichetta T9 a 2560; (2) Andamento: le date sotto le barre dei difetti si accavallano a 2560 (barre in px, testo in rem); (3) temperatura «37,9 °» nella fascia del giro e nei menu contro «°C» altrove; didascalia «Livelli (migliore → ideale → PRO · gap = …)» con frecce decorative.
Task 12: fix dispatch (FIX_BASE 8a119f5)
Task 12: fix 8a119f5..6bfffdf (suite 2930); verifica controllore a 2560 su Imola: date di Andamento leggibili, «°C» ovunque, didascalia Livelli riscritta
Task 12: minor (deferred): con più di 12 sessioni a 1366 px gli spazi delle barre potrebbero restringersi di nuovo
Task 12: complete
Final review: dispatched
Final review: With fixes — Important: (1) stato vuoto con «python -m accoach live» e «launcher»; (2) «No steering data for this lap.» scritto a mano in inglese; (3) «tip» nella guida inglese ma «advice» nell'interfaccia.
Ruling: si fanno nell'unica ondata anche i minor di coerenza (virgolette inglesi “ ”, brake_early, «validi», lap.offTrack.why, coach.warming, testi di report_a, «dal volante», maiuscole di Report card, line.name.hint, «°C» nella pagina Ingegnere, test_plan.json monitor, riga di tono.py) e si tolgono le emoji dal coach da terminale (lo apre un bottone dell'hub, è interfaccia) — se sbagliato: nessuno.
Ruling: la lingua della pagina Ingegnere sul tablet (predefinita inglese senza preferenza salvata) resta com'è — è precedente al ramo e cambia comportamento — da dire al pilota.
Final fix wave: dispatched (FIX_BASE 6bfffdf)
Final fix wave: 6bfffdf..2e8e774 (suite 2940); re-review: 11 addressed, nessuna rottura; il sospetto inquinamento dei test di test_web_rimandi era l'ordine delle modifiche dell'implementatore (riprodotto)
Final review: minor (parked): docs/FAQ.md:119 e :499 dicono ancora «advice» per un consiglio del piano; empty.hint mostra un comando dal sorgente; il file XLSX del piano di prova è indietro rispetto a test_plan.json (precedente)
Final review: clean
