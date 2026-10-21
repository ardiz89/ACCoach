# SDD ledger — plan: docs/superpowers/plans/2026-10-21-pagella-e-piano.md

Spec: docs/superpowers/specs/2026-10-21-pagella-e-piano-design.md (approvata dal pilota).

## Pre-flight scan

| Coppia / task | Produce → consuma | Esito |
|---|---|---|
| T1→T4 | COAST_MAIN_S, DefectSummary.corners | coerente |
| T1→T3 | LapDefects, lap_defects | coerente |
| T2→T3 | lap_errors(lap, corners) | coerente: replay ha le curve del riferimento |
| T1,T5 | verdict(top: DefectSummary) | coerente |
| T3,T4→T6 | replay, propose_advice(summaries, stored, names, apex), measure_advice, rebase | coerente: names/apex dalle curve del riferimento |
| T6→T7 | payload /api/pagella | coerente |
| T7↔T8 | T7 «Produces: openHowto(defect)», ma #view-howto e rendering stanno in T8 | CONFLITTO → Ruling 1 |
| T4→T9 | load_advice: corners con apex_pos in data_json | coerente se Advice serializzato intero → Ruling 2 |
| T7 vs test esistenti | rimuove view-recap/view-training; test_web_views, tour e i18n li citano | non un conflitto del piano; va detto all'implementatore → Ruling 3 |
| T1 self | test 4-cap «...» non scritto per intero | lasciato all'implementatore (Step 1 dice di costruirlo col ciclo) |
| T2 self | profilo di bloccaggio preso dai test esistenti | ok |
| T3 self | cache modulo-livello: test deve poterla svuotare | Ruling 4 |
| T5 self | test regex «^[^:]{1,30}:\s» su ogni testo | ok; si applica per frase |
| T6 self | GET con effetti (migrazione, reached) | accettato dalla spec |
| T9 self | ok |
| T10 self | ok |

Ruling 1: T7 crea anche il guscio vuoto `<section id="view-howto">` fuori dalla nav e una `openHowto(defect)` che salva il difetto e fa `showView("howto")`; T8 riempie il rendering — perché T7 deve poter collegare i bottoni senza dipendere da T8 — se sbagliato: un guscio da spostare, costo minimo.
Ruling 2: `save_advice` salva in `data_json` l'intero `Advice` (asdict), corners con `apex_pos` compresi, più `reference_path` — T9 e il rebase di T6 ne hanno bisogno — se sbagliato: migrazione dello schema JSON, costo basso.
Ruling 3: in T7 l'implementatore aggiorna i test esistenti che citano recap/training (test_web_views, test_web_i18n_keys, tour) invece di lasciarli rossi, e rimuove le chiavi i18n non più usate solo se un test lo richiede — perché la spec fonde quelle schede — se sbagliato: chiavi orfane innocue.
Ruling 4: la cache di T3 ha una funzione `clear_cache()` usata dai test — perché una cache di modulo rende i test dipendenti dall'ordine — se sbagliato: nessuno.

## Avanzamento
Task 1: dispatched (BASE 06b677d, implementer a9515297b2eee019d, sonnet)
Ruling: COAST_MAIN_S = 0,4 s, 75° percentile dei soli giri che veleggiano (14 su 145), non di tutti — il percentile su tutti vale 0 e renderebbe principale qualunque veleggio; la spec chiede solo che sia misurata — se sbagliato: il veleggio entra in pagella troppo o troppo poco, si ritocca una costante.
Ruling: coast_s si misura solo sulle curve che hanno una perdita (limite di GripState) — accettato per ora: è dove il veleggio costa; da dire nella vista Come si fa se serve — se sbagliato: il veleggio è sottostimato.
Ruling: i commit dei subagenti portano il Co-Authored-By del loro modello reale (es. Sonnet 5.5) invece della riga Opus del piano — è l'attribuzione vera; la riga del piano vale per i commit del controllore — se sbagliato: riscrittura dei trailer prima del merge.
Task 1: review → Approved con 1 Important (mutazioni scarse) + minor; fix round 1 inviato (FIX_BASE ca855d2)
Task 1: fix round 1/5 (5 addressed, 0 open; commits ca855d2..0b6ebdb)
Task 1: minor (deferred): `if mean <= 0` scarta un difetto netto negativo (impossibile oggi); test sulla dispersione delle curve parziale
Task 1: complete (commits 06b677d..0b6ebdb, review clean)
Task 2: dispatched (BASE 0b6ebdb)
Task 2: ⚠️ «1 warning» della suite: già presente su main prima del ramo (2400 passed, 1 warning il 21/10) — non introdotto qui.
Task 2: minor (deferred): test sotto/sovrasterzo con asserzioni deboli (>=1, <=len) e nessun caso curva con entrambi i sintomi
Task 2: complete (commits 0b6ebdb..660fcb1, review clean)
Task 3: dispatched (BASE 660fcb1)
Ruling: SessionReplay.wet = maggioranza dei giri con mescola nota; senza mescola nota = asciutto — coerente con history_reference (mescola mancante = asciutto) — se sbagliato: una sessione mista finisce nella classe sbagliata.
Task 3: review → Needs fixes (1 Important: wet senza test); fix round 1 inviato (FIX_BASE 8f852f5)
Task 3: fix round 1/5 (3 addressed, 0 open; commits 8f852f5..34397cf)
Task 3: minor (deferred): docstring _wet_vote dice «un'ora prima», sono due; LapDefects in cache è mutabile (solo convenzione read-only)
Task 3: complete (commits 660fcb1..34397cf, review clean)
Task 4: dispatched (BASE 34397cf)
Ruling: data_json di advice = asdict(Advice) + reference_path opzionale — serve al rebase (T6) e al focus (T9) — se sbagliato: schema JSON da migrare.
Ruling: migrazione del piano vecchio: apex_pos sconosciuto = 0.0, created_utc → accepted_utc — il vecchio Goal non porta la posizione — se sbagliato: T9 non trova la curva di un consiglio migrato e il focus sceglie da solo (degrado innocuo).
Task 4: review → Needs fixes (1 Important: migrazione crea un secondo active); fix round 1 inviato (FIX_BASE 783aee1)
Ruling: migrazione — categoria senza difetto (es. TIME_LOSS) → piano cancellato senza consiglio — non era un'abitudine — se sbagliato: il pilota perde un obiettivo su una curva senza causa.
Ruling: migrazione — un consiglio declined/dropped già esistente per lo stesso difetto vince sul piano vecchio — scelta esplicita più recente — se sbagliato: un piano accettato sparisce.
Ruling: migrazione con un altro consiglio già active → il migrato diventa proposed — uno alla volta — se sbagliato: il pilota deve ri-seguirlo a mano.
Task 4: fix round 1/5 (2 addressed, 1 open Minor — fallback nome curva non bilingue; commits 783aee1..2bb78ef)
Task 4: minor (deferred): advice.py fallback "Corner N" fisso invece di trackdata.corner_name (bilingue) — T6 passa sempre i nomi; da sistemare se un nome vuoto arriva in UI
Task 4: minor (deferred): migrazione — goal non-dict solleva fuori dal try; goal senza nome → curva senza nome
Task 4: complete (commits 34397cf..2bb78ef, 0 Important open)
Task 5: dispatched (BASE 2bb78ef)
Ruling: la frase del piano «È la tua prima sessione qui: il confronto arriva dalla prossima.» viola la regola dei due punti scritta nello stesso piano → diventa «È la tua prima sessione qui. Il confronto arriva dalla prossima.» — la spec (tono) vince sul piano — se sbagliato: nessuno.
Ruling: il problema non usa «In <nome curva>» (preposizione sbagliata per molti nomi: «In Variante Alta», «In Rivazza»); il nome curva apre la frase come etichetta, sul modello approvato «Villeneuve · …»: «Variante Alta. Qui stacchi…» — se sbagliato: ritocco di testo.
Task 5: review → Needs fixes (2 Important: rulings a/b non applicati); fix round 1 inviato con anche i minor di tono (FIX_BASE fb872ac)
Ruling: il verdetto può avere fino a 3 frasi (la frase della prima sessione diventa due) — la regola dei due punti vince sul limite di frasi del piano — se sbagliato: verdetto un po' più lungo.
Task 5: fix round 1/5 (4 addressed, 0 open; commits fb872ac..9406e83)
Task 5: minor (deferred): EN coasting.what comma splice «that time is simply wasted, …»; riga lunga in lift.drill EN
Task 5: complete (commits 2bb78ef..9406e83, review clean)
Task 6: dispatched (BASE 9406e83)
Ruling: in /api/howto «typical_path» = giro valido della sessione col valore del difetto in quella curva più vicino alla mediana; «best_path» = riferimento dello storico — la spec dice «il suo solito e il suo migliore» — se sbagliato: figura meno rappresentativa.
Task 6: report trascritto dal controllore (lo strumento dell'implementatore non poteva creare il file)
Ruling: i giri il cui cronometro non copre il giro (trends.clock_covers_lap, la regola già usata dal riepilogo) escono dallo storico, e un riferimento così non si elegge — spiega l'anomalia 22,6 s a Monza; una regola esistente, non nuova — se sbagliato: qualche giro sano in meno nella media.
Ruling: confermate le scelte 1-8 del report di T6 (classe gomma per maggioranza, riferimento per classe su tutto l'archivio, rebase sulla sessione d'accettazione, reached sul primo giro che lo raggiunge, follow ricalcolato dal server) — coerenti con la spec — se sbagliato: comportamenti di bordo da ritoccare.
Ruling: avanti-indietro del consiglio fra classi di gomma (concern 2 di T6) parcheggiato — raro, serve due sessioni bagnate — se sbagliato: un rebase inutile per lettura.
Task 6: review → Needs fixes (3 Important: clock_covers_lap, metri «in media» da un giro, mappatura errori API; + 4 minor da fare); fix round 1 inviato (FIX_BASE b7eb209)
Ruling: la sessione lentissima di Monza (10/08, 25 s a giro) è vera e resta nei dati; il mini-andamento di T7 usa una scala tagliata a 2× la mediana della serie e marca la barra tagliata — non si nascondono dati veri, ma una barra non deve schiacciare le altre — se sbagliato: lettura visiva da ritoccare.
Ruling: `excluded` ammette anche `reference_session` (T7 lo gestisce) — frase vera per quel caso — se sbagliato: nessuno.
Task 6: fix round 1/5 (7 addressed, 0 open; commits b7eb209..4c0bcfd)
Task 6: minor (deferred): _REFS cache un file illeggibile come None per tutto il processo; _mean_brake_offset_m rilegge i giri senza cache; sessione con tutti i giri scartati dal clock → testo reference_session/no_reference non lo dice; branch brake_late del segno senza test
Task 6: complete (commits 9406e83..4c0bcfd, review clean)
Task 7: dispatched (BASE 4c0bcfd)
Ruling: la prova nel browser di T7 (Step 5) e di T8 la fa il controllore con Chrome, non l'implementatore — un subagente non deve pilotare il browser del pilota — se sbagliato: nessuno.
Task 7: prova browser del controllore (copia archivio, Imola 720S, 2560 px): Pagella si apre per prima, schede nei 3 gruppi, verdetto/difetti/dove/errori/piano popolati e in italiano corretto; «Lo seguo» → «In corso» + «Lascio stare»; cambio lingua ok; nessun errore in console. DIFETTO: a 1920×1080 il piano finisce a 1129 px (sotto la piega, la spec chiede verdetto+difetti+piano senza scorrere); i riquadri «dove sbagli»/«errori» sono alti e semivuoti (righe da ~45 px). Minor: mini-barre molto piccole (~10 px); la striscia del giro (GIRO/CONFRONTO/GAP) sopra la Pagella non serve lì.
Task 7: review → Approved (8 minor); controllore: 1 Important dalla prova browser (piano sotto la piega a 1920×1080); fix round 1 inviato con l'Important + minor 1,3,4(undecline),5,6,7 + barre più alte (FIX_BASE 147972e)
Task 7: fix round 1/5 (6 addressed, 1 open — undecline serve un campo backend; commits 147972e..08c3163). Misura controllore: lapbar nascosta, righe del piano a y=882..1007 → dentro a viewport 1080.
Ruling: «1920×1080» della spec = viewport di 1080 px; con la cornice del browser (~950) il secondo consiglio è tagliato di poco — accettato: il pilota legge su un 32" — se sbagliato: su un portatile 1080p si scorre un po'.
Ruling: aggiungere `declined` al payload di build_pagella e la riga «Riprendi» — la spec dice che «non lo seguo» si ricorda, ma un rifiuto senza ritorno è irreversibile per il pilota — se sbagliato: una riga in più.
Task 7: fix round 2 inviato (declined + Riprendi; ses.none doppio) (FIX_BASE 08c3163)
Task 7: fix round 2/5 (7 addressed, 0 open; commits 08c3163..8e7df49)
Task 7: minor (deferred): due richieste /api/sessions all'avvio in serie; regole CSS .pag-tag spezzate da .pag-declined; openPagellaIfNew ritorna undefined su risposta vecchia
Task 7: complete (commits 4c0bcfd..8e7df49, review clean)
Task 8: dispatched (BASE 8e7df49)
Task 8: prova browser del controllore (Imola, min_speed): problema con i numeri del pilota, «misurato sul tuo giro migliore 1:45.870», tre figure (mappa curva + velocità, solito vs migliore) per Variante Alta/Tosa/Rivazza, testi come si fa, esercizio 6 giri, come sta andando; nessun errore in console. DIFETTI: l'obiettivo in numeri non compare nell'esercizio («meno dell'obiettivo» senza il valore; spec: «obiettivo in numeri»); «← Torna alla Pagella» solo in fondo e piccolo.
Task 8: review → Approved (6 minor); controllore: 1 Important (obiettivo in numeri assente nell'esercizio) + torna in alto; fix round 1 inviato (FIX_BASE d5f8115)
Task 8: minor (deferred): resize durante il caricamento riparte la richiesta; finestra figura = cornerWindow (+25%) non entry..exit stretto (accettato, è il comportamento del Confronto); regex del test di escape copre solo interpolazioni dirette; «giro di riferimento» (Pagella) vs «giro migliore» (Come si fa) sono lo stesso giro (il più veloce pulito della classe) — accettato
Task 8: controllore ha verificato nel browser (server riavviato): «Obiettivo: sotto 0,38 s a giro» e due «Torna alla Pagella».
Task 8: fix round 1/5 (3 addressed, 0 open; commits d5f8115..151e844) — verifica browser già fatta dal controllore
Task 8: minor (deferred): loadHowto carica /api/analysis anche quando non disegnerà la figura (!trace)
Task 8: complete (commits 8e7df49..151e844, review clean)
Task 9: dispatched (BASE 151e844)
Ruling: curve del consiglio già «acquisite»/«parcheggiate» dal focus non guidano più il coach; il consiglio resta in corso finché il report non lo chiude — la spec: il verdetto del focus non chiude il consiglio — se sbagliato: il pilota sente il coach su altre curve mentre il report dice «in corso»; da rivedere coi rimandi (pezzo 3).
Ruling: il consiglio accettato a metà di un focus subentra alla scelta successiva — non si butta una misura aperta — se sbagliato: qualche giro di ritardo.
Ruling: una lettura del catalogo per giro completato nel motore — è già il momento in cui il motore salva il giro; best-effort — se sbagliato: un ritardo minimo a fine giro.
Task 9: review → Approved (4 minor). Ruling: il minor «catalogo letto a ogni giro anche a drill aperto» promosso a Important — nel loop di guida un busy_timeout di 3 s può fermare il coach a fine giro — se sbagliato: un giro di correzione in più. Fix round 1 inviato (+ test fcorners) (FIX_BASE bfa9d1f)
Task 9: minor (deferred): mappatura iniziale su self._corners alla creazione (innocua); concern di prodotto «consiglio con tutte le curve parcheggiate non guida più il coach» → per il pilota, vedi ruling sopra
Task 9: fix round 1/5 (2 addressed, 0 open; commits bfa9d1f..8c2cbc5)
Task 9: minor (deferred): a focus chiuso (ASSESS/CLEAN) il catalogo si apre ancora sul thread del tick a fine giro
Task 9: complete (commits 151e844..8c2cbc5, review clean)
Task 10: dispatched (BASE 8c2cbc5)
Ruling: buco del piano — la spec vuole «Andamento (con i difetti sessione per sessione)» e nessun task lo implementa. Aggiungo un Task 11 piccolo: nella scheda Andamento un riquadro con i difetti per sessione (stesse misure della Pagella, riferimento dello storico) — la spec è vincolante — se sbagliato: un riquadro in più.
Task 10: complete (commits 8c2cbc5..e4fa141, review clean) — minor (TESTING.md con schede vecchie; «tre bottoni»; due punti; «a ogni apertura») spostati nel Task 11
Task 11: brief scritto dal controllore (task-11-brief.md); dispatched (BASE e4fa141)
Task 11: prova browser controllore (Monza 720S, 10 sessioni): riquadro in cima ad Andamento, 4 difetti, date sotto le barre, nessun errore. DIFETTI: (a) il taglio a 2× mediana taglia 5 barre su 10 di «Gas tardi in uscita» — nasconde proprio il miglioramento che il pilota vuole vedere; (b) difetti oggi a zero mostrati con «0,00 s» nella pillola rossa; (c) date ripetute (12 ago ×3) senza distinguere le sessioni.
Ruling: il taglio delle barre vale solo per un valore isolato fuori scala: se il massimo supera 3× il secondo valore più alto, la scala è il secondo × 1,2 e si taglia solo quello; altrimenti nessun taglio. Stessa funzione per Pagella e Andamento — l'andamento deve mostrare il calo vero; il taglio esiste solo per la sessione anomala — se sbagliato: un'altra soglia da ritoccare.
Task 11: review → Approved (8 minor). Ruling: accettate le deviazioni (trend nel payload; valori mai None = zero misurato; sessione bagnata isolata → storico asciutto ma la pagina lo dice). Fix round 1 inviato: Important = nuova regola del taglio (controllore) + minor 2-8 (FIX_BASE 1fa5ae6)
Task 11: verifica browser controllore dopo il fix: nessuna barra tagliata a torto, il calo è leggibile, zeri in verde, orari sotto le date dello stesso giorno.
Task 11: fix round 1/5 (8 addressed, 0 open; commits 1fa5ae6..66177c3)
Task 11: minor (deferred): resize durante il primo caricamento rifà la richiesta; _trend_at ricalcola le medie
Task 11: complete (commits e4fa141..66177c3, review clean)
Final review: dispatched
Final review: With fixes — Important: (1) uscite di pista sempre 0 (replay vede solo giri puliti); (2) curve del consiglio non rimappate per apex al cambio di riferimento; (3) glossario sparito contro la spec.
Ruling: glossario → si mostra nella vista Come si fa (la spec lo dice: «glossario compreso»), usando glossary_for esistente — se sbagliato: un riquadro in più.
Ruling: l'azione «reached» manuale senza bottone si rimuove (backend + testi) — la spec ha tre scelte, codice morto — se sbagliato: nessuno, non era raggiungibile.
Ruling: dead backend di /api/training, /api/plan, recap in /api/sessions rimandato a un PR di pulizia — non tocca il pilota, e togliere endpoint ha più rischio — se sbagliato: una doppia richiesta lenta all'avvio resta.
Ruling: curva a cavallo del traguardo (minor 7) parcheggiata — track.py dice che le curve non scavalcano la linea — se sbagliato: un consiglio su quella curva non guida il coach.
Final fix wave: dispatched (FIX_BASE 66177c3)
Final fix wave: 8 commit (66177c3..b3a7ebe), suite 2588.
Ruling: consiglio le cui curve non trovano più posto nel riferimento nuovo → resta senza curve e si misura sul giro intero — parcheggiato: raro (serve un riferimento con geometria diversa ovunque), e non mente sul nome — se sbagliato: una misura più larga del consiglio.
Ruling: closed_by rimasto da chiusure a mano via API — ignorabile: la funzione non è mai stata rilasciata, nessun dato del pilota ce l'ha — se sbagliato: nessuno.
Final fix wave: re-review clean; verifica browser controllore: «Uscite di pista 2×» in Pagella, glossario nel Come si fa. Final review clean.
