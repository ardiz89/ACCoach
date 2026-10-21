# SDD ledger — plan: docs/superpowers/plans/2026-10-21-giro-coach-live.md

Spec: docs/superpowers/specs/2026-10-21-giro-coach-live-design.md (approvata). Ramo = main locale b3a7ebe + PR #104.

## Pre-flight scan
| Coppia / task | Produce → consuma | Esito |
|---|---|---|
| T1→T2 | /health remote_clients, laps_done, best → Health | coerente |
| T2→T4 | LiveTracker, parse_health, report_url, POLL_S → widget | coerente |
| T3↔T2/T4 | ?view=pagella&car&track ← report_url | coerente |
| T4↔T5 | testi live.* / wiz.* in i18n.py | coerente, file condiviso, task in serie |
| T1 self | TestClient host «testclient» → _is_remote testata a parte | ok |
| T2 self | «Resto in pista» semantica | ok |
| T3 self | ok |
| T4 self | test «no http sul thread UI» = controllo d'import: debole ma esplicito | accettato (Ruling 1) |
| T6 | prova del controllore | ok |

Ruling 1: il test di T4 «nessun urllib/requests nel modulo UI» è un controllo di forma; resta, ma la prova vera che l'hub non si blocca è T6 (hub vero con /health lento) — se sbagliato: un blocco dell'interfaccia sfugge ai test.

## Avanzamento
Task 1: dispatched (BASE 939f606, implementer aecdadcce676caa12, sonnet)
Task 1: review → Needs fixes (1 Important: resolver sincrono sul loop di /health); fix round 1 inviato (FIX_BASE c3ef995)
Task 1: fix round 1/5 (3 addressed, 0 open; commits c3ef995..5e52683)
Task 1: minor (deferred): test_two_clients_one_local_one_remote dipende dall'ordine delle chiamate allo stub (rischio flake piccolo)
Task 1: complete (commits 939f606..5e52683, review clean)
Task 2: dispatched (BASE 5e52683)
Task 2: minor (deferred): condizione `and self._seen_telemetry` morta; connected=None sul timer non testato; tablet_now resta all'ultimo valore durante silent (T4: in fase silent la riga del tablet non dice «collegato»)
Task 2: complete (commits 5e52683..f0eb827, review clean)
Task 3: dispatched (BASE f0eb827)
Task 3: l'implementatore ha usato git stash per la prova RED; la pila degli stash è intatta (solo la voce preesistente). Regola aggiunta alle istruzioni.
Task 3: minor (deferred): ramo stale di openAskedPagella non ripristina savedView (cosmetico); fetch /api/sessions duplicato con openPagellaIfNew; test solo statici → prova browser in T6
Task 3: complete (commits f0eb827..9efd58d, review clean)
Task 4: dispatched (BASE 9efd58d)
Task 4: PNG dei 5 stati visti dal controllore: idle (bottoni + anteprima 3 passi), prima di partire (QR + indirizzo + Apri su questo PC/Salta), in pista (tablet, pista·auto, giri·migliore, Stai seguendo, Ho finito) — corrispondono alla bozza approvata.
Ruling: la lettura del consiglio in corso (LapCatalog sul thread dell'interfaccia, busy_timeout fino a 3 s) viola «l'hub non si blocca mai» → va spostata fuori dal thread UI — se sbagliato: un thread in più.
Ruling: «Sessione finita» deve dire giri validi su totali e durata (spec) — si ricavano dal catalogo (giri di quella auto/pista registrati da quando è partito Coach Live), letti fuori dal thread UI — se sbagliato: una riga meno precisa.
Task 4: review → Needs fixes (3 Important: catalogo sul thread UI, Sessione finita senza validi/durata, port_open 4 Hz bloccante). Ruling: anche lo stop di «Ho finito» (5 s bloccanti, imposto dal piano) diventa non bloccante con una riga «Sto aprendo il report…» — la spec «l'hub non si blocca mai» vince sul piano — se sbagliato: un po' di codice in più. Fix round 1 inviato con minor 5-8 (FIX_BASE 21f58f7)
Ruling: «Ho finito» usa ancora _stop_live (taskkill sincrono, breve, stesso percorso del bottone Stop) — tocca widget, è già così oggi — se sbagliato: un attimo di attesa al clic.
Task 4: fix round 1/5 (8 addressed, 0 open; commits 21f58f7..ba14c99)
Task 4: minor (deferred): taskkill sincrono al clic (già ruling); emit su _Bridge distrutto alla chiusura (rumore); «nessun giro salvato» usa /health mentre il riquadro usa il catalogo (caso raro); DevicesPanel usa port_open bloccante (preesistente)
Task 4: complete (commits 9efd58d..ba14c99, review clean)
Task 5: dispatched (BASE ba14c99)
Task 5: minor (deferred): la guida riprende quasi alla lettera due frasi del pannello; «apre il report sulla Pagella» vs «apre la Pagella»; wizard non dice più «voce + overlay»
Task 5: complete (commits ba14c99..298b338, review clean)
Task 6: prova vera del controllore (in corso)
Task 6: prova vera (hub offscreen + Coach Live demo vero, porte 8797/8798, casa finta): before → driving in 5 s; pista·auto, giri, migliore; «Ho finito» ferma il coach in 0,6 s e apre /?view=pagella&car=HONE%20Demo&track=Demo%20Circuit; nessuna porta lasciata aperta. Tablet non verificabile da un solo PC (remote_clients 0 con la pagina locale: corretto).
Ruling: se la telemetria arriva prima del tablet (caso normale: il pilota avvia il gioco subito), in «Stai guidando» il passo «Collega il tablet» col QR resta visibile finché il tablet non si collega o non si salta — altrimenti il QR sparisce proprio quando serve — se sbagliato: un riquadro in più in guida.
Task 6: browser (copia archivio): /?view=pagella&car=MCLAREN_720S_GT3_EVO&track=imola con vista salvata «progress» su Monza → apre Pagella di Imola, combo salvata, parametri tolti, sessione segnata vista. OK.
Task 6: complete (controllore)
Final review: dispatched
Final review: ready after fixes — I1 web avviato dal pannello apre schede del browser; I2 QR assente in guida; I3 falso «non risponde» all'avvio; I4 QR con rete accesa a corsa iniziata; I5 test ?view= solo di forma.
Ruling I3: «il coach non risponde» solo dopo almeno una risposta buona in questa corsa; prima, fino a 30 s, «Il coach si sta avviando…»; oltre, una riga diversa «Coach Live è acceso ma non risponde» — evita il falso allarme all'avvio — se sbagliato: un guasto all'avvio si vede dopo 30 s.
Ruling I4: il pannello ricorda se la corsa è partita con la rete locale; se no, il passo 2 non mostra il QR e dice di riavviare Coach Live dopo averla attivata — un QR che non funziona è peggio di nessun QR — se sbagliato: un riavvio in più.
Ruling I5: per il link ?view= vale come prova la verifica nel browser del controllore (T6, registrata sopra); i test statici restano come guardia di forma — se sbagliato: un refactor dell'init può rompere il link senza test rosso.
Ruling M1: dopo «Resto in pista» il testo di «Sessione finita» non dice più «da un minuto» ma «Il gioco è chiuso» — se sbagliato: nessuno.
Final fix wave: dispatched (FIX_BASE 298b338)
Final fix wave: re-review clean (commit 49b326c)
