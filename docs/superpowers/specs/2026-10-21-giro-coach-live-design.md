# Il giro di Coach Live: avvio, guida, chiusura — design

Data: 2026-10-21. Secondo dei quattro pezzi decisi col pilota (il primo, la
Pagella, è in `2026-10-21-pagella-e-piano-design.md`).

## Il perché

Il pilota, parole sue:
- «all'avvio del coach live il sistema dovrebbe suggerire l'utente di agganciare
  il proprio device o schermo all'ingegnere di pista»;
- «dobbiamo aggiungere una procedura step by step per aiutare il pilota ad
  avviare, seguire, chiudere il coaching»;
- «alla chiusura del coaching, l'utente dovrebbe essere guidato con la minima
  fatica alla relativa pagina di reportistica».

Come va in pista oggi (parole sue): apre HONE, avvia Coach Live, poi ACC, e mette
il tablet sul supporto. Il tablet guarda la pagina Ingegnere in rete locale
(`lan = true` nella sua configurazione). Quando chiude Coach Live non succede
niente: il report va aperto a mano, sulla scheda che era aperta l'ultima volta.

## Cosa è stato approvato

La bozza «Coach Live: avvio, guida, chiusura» del brainstorming (tre momenti
dello **stesso** pannello «In pista» dell'hub), approvata con «al momento va bene
così»:

1. **Appena premi «Avvia Coach Live» — «Prima di partire».** Una lista di passi:
   1. ✓ Coach Live acceso (voce e overlay pronti).
   2. **Collega il tablet all'ingegnere.** Un QR da inquadrare col tablet e
      l'indirizzo scritto in chiaro (`192.168.x.y:8778/engineer`); «Apri su questo
      PC»; «Salta, guido senza».
   3. Avvia ACC ed esci dai box — si spunta da solo quando arriva la telemetria.
2. **Mentre guidi — «In pista».** Tablet collegato ✓; pista · auto, giro N e
   miglior tempo; «Stai seguendo: <consiglio>» con una riga su cosa fa il coach;
   un solo bottone grande **«Ho finito, mostrami com'è andata»**, che ferma il
   coach e apre il report sulla Pagella.
3. **Hai chiuso ACC senza premere niente — «Sessione finita».** Giri salvati
   (validi su totali), durata; il coach resta acceso finché non lo fermi tu (stai
   magari solo cambiando pista); «Mostrami com'è andata» e «Resto in pista».

Ipotesi mia, confermata dal pilota insieme alla bozza: il passo del tablet si
spunta da solo quando la pagina Ingegnere si collega dal tablet.

## Obiettivi

- Chi avvia Coach Live vede subito cosa fare dopo, in ordine, e ogni passo si
  spunta da solo quando è fatto.
- Il tablet si collega alla pagina Ingegnere inquadrando un codice, senza
  scrivere indirizzi.
- A fine sessione un clic porta alla Pagella della sessione appena guidata.
- Se il pilota chiude ACC e basta, l'hub lo nota e offre lo stesso clic.

## Non obiettivi

- Nessuna modifica al motore del coach o a cosa dice.
- Coach Live non si ferma da solo quando ACC si chiude.
- Niente nuove pagine web: il report e la pagina Ingegnere esistono già.
- Il resto dell'hub (Analisi, Assetto, Dispositivi, Impostazioni) non cambia,
  salvo i rimandi descritti qui.

## Anti-obiettivi

- Un passo che si spunta senza che sia vero (es. «tablet collegato» perché la
  pagina è aperta sul PC stesso).
- Un hub che si blocca o rallenta mentre interroga Coach Live: il pilota è in
  macchina e l'hub è dietro al gioco.
- Testi da macchina (vedi «Tono»).
- Un pannello che dice «telemetria in arrivo» quando Coach Live è morto.

## Vincoli e appoggi

- **Dipende dalla PR #104** («Ingegnere vivo durante Coach Live»): con #104 Coach
  Live serve il backend dal vivo in modalità spettatore sulla porta
  `cfg.server.port` (8777), in LAN quando `cfg.lan`; la pagina Ingegnere stessa la
  serve il processo `web` sulla porta `cfg.web.port` (8778). Questo ramo parte da
  `main` + #104 fusa dentro (`feat/giro-coach-live`); #104 resta da provare in
  pista prima di arrivare in `main`.
- **Lo stato di Coach Live si legge da `/health`** del backend (`server.py`):
  `connected`, `game`, `car`, `track`, `saved_laps`, `clients`. Serve in più
  **quanti client della pagina sono collegati da un indirizzo che non è il PC
  stesso** (es. `remote_clients`): è il segno del tablet. Il QR e gli indirizzi
  esistono già (`netinfo.device_urls`, `netinfo.qr_png`, pagina «Dispositivi»).
- **Il consiglio in corso** si legge dal catalogo (`LapCatalog.load_advice(car,
  track)`, stato `active`) con auto e pista prese da `/health`.
- **Il report** si apre già sulla Pagella quando c'è una sessione nuova per quella
  combo (`hone_seen_session:<car>|<track>` in `app.js`). Per «Ho finito» non basta
  fidarsi di quella regola: l'indirizzo che l'hub apre deve chiedere
  esplicitamente la Pagella e la combo guidata (es. `?view=pagella&car=…&track=…`),
  e il report deve onorarlo.
- Il processo `web` può non essere acceso: avviando Coach Live con `cfg.lan`
  attivo, l'hub lo accende se non c'è (serve al QR); «Ho finito» lo accende se non
  c'è prima di aprire il browser. Il processo `web` non registra giri, quindi
  `hubgate` non lo blocca durante Coach Live (verificare).
- L'hub non deve mai bloccarsi: le richieste a `/health` hanno un timeout breve e
  non girano sul thread dell'interfaccia (o usano la rete asincrona di Qt). Si
  interroga solo mentre Coach Live è acceso, ogni ~2 s.
- **ACC chiuso** = `/health` dice `connected` falso per almeno 60 s dopo essere
  stato vero in questa corsa di Coach Live. Un Coach Live che non risponde a
  `/health` non è «ACC chiuso»: il pannello dice che il coach non risponde.
- Con `cfg.lan` spento, il passo 2 non mostra un QR che non funzionerebbe: dice
  che il tablet si collega solo con la rete locale attiva e porta alla pagina
  «Dispositivi» dove si attiva (un clic); «Apri su questo PC» resta.
- La procedura «passo passo» richiesta dal pilota **è** questo pannello; in più il
  passo «Coach Live» del wizard del primo avvio (`GettingStarted`) e la guida
  (`GUIDA.md` / `docs/FAQ.md`) lo descrivono.
- Italiano e inglese per ogni testo.

## Tono (deciso col pilota il 21/10)

Frasi brevi col tu; numeri con la virgola e l'unità; niente slogan, niente due
punti a effetto, niente emoji (i segni ✓ ▶ dei passi sono icone di stato, non
emoji decorative); mai la stessa frase in due posti; prima il fatto, poi cosa
fare.

## Come si verifica

- La logica dei passi (da una serie di risposte di `/health` e dallo stato del
  processo allo stato del pannello) sta in funzioni pure, testate senza Qt.
- Il pannello si prova renderizzandolo in PNG nei tre momenti (memoria del
  12/09: un dialogo Qt si verifica rendendolo, non chiedendo al pilota).
- Prova vera: Coach Live in demo con una casa finta, `/health` vero; il tablet
  si simula con un client websocket da un indirizzo che non è 127.0.0.1 (o si
  prova col tablet del pilota quando è al PC).
- Mai scrivere in `Documents\ACCoach`.

## Scelte mie, dopo la rilettura del revisore

Prese da me, non dal pilota; il pilota le può rovesciare.

1. **Cosa vuol dire «tablet collegato».** Un client websocket del backend il cui
   indirizzo non è 127.0.0.1 **né uno degli indirizzi di questo PC**
   (`netinfo` li conosce): la pagina aperta sul PC via indirizzo di rete non
   conta. Il passo 2 resta spuntato per tutta la corsa di Coach Live una volta
   avvenuto; nella vista «In pista» la riga del tablet dice lo stato di adesso
   («collegato» / «il tablet si è scollegato»), perché un tablet che spegne lo
   schermo chiude il websocket e il pilota deve saperlo senza che il pannello
   torni indietro.
2. **«Ho finito» senza auto/pista.** Se `/health` non ha mai dato auto e pista
   (il gioco non è mai partito) o non risponde, il bottone apre il report senza
   parametri (l'ultima combo vista) e la riga sopra il bottone dice che di
   questa corsa non ci sono giri. Con zero giri salvati vale lo stesso. Con giri
   salvati ma nessuno valido, si apre la Pagella: è lei che lo spiega.
3. **Auto e pista.** I valori di `/health` sono quelli del gioco; il catalogo e il
   report li confrontano con la loro normalizzazione (`LapCatalog._slug`, il
   confronto senza maiuscole di `app.js`). Il costruttore verifica sul codice e,
   se serve, normalizza nello stesso modo prima di cercare il consiglio e di
   costruire l'indirizzo. Nessuna mappa nuova.
4. **Fermare il coach.** «Ho finito» usa l'arresto che esiste
   (`_stop_live_and_wait`, attesa fino a 5 s), poi apre il report. Un giro si
   salva quando si passa la linea, quindi non c'è un giro a metà da salvare; il
   giro in corso si perde come oggi. Se l'arresto non riesce entro il tempo, il
   report si apre lo stesso e la riga lo dice.
5. **L'indirizzo con la vista.** `?view=pagella&car=…&track=…` vince sulla
   scheda e sulla combo ricordate; la combo diventa quella ricordata e la sessione
   più recente diventa «già vista», così la prossima apertura normale non riapre
   la Pagella senza motivo.
6. **Il processo `web`.** Se la porta del report risponde già, l'hub lo usa
   com'è. Se va acceso, l'hub lo accende; se non parte entro qualche secondo, il
   passo 2 dice che la pagina Ingegnere non è raggiungibile e «Apri su questo PC»
   resta. Il QR mostra l'indirizzo di rete solo con `cfg.lan` attivo.
7. **Demo e coach muto.** In demo i passi si spuntano con la telemetria finta,
   come in pista. Tre risposte mancate di fila a `/health` (circa 6 s) e il
   pannello dice che il coach non risponde, finché non risponde di nuovo. Se la
   telemetria non è mai arrivata, il pannello resta al passo 3 e «Sessione
   finita» non compare.
8. **La pagina «In pista».** Con Coach Live spento mostra i bottoni di oggi e,
   sotto, i tre passi in anteprima (cosa succederà). Con Coach Live acceso il
   pannello prende il posto della pagina. Il vecchio «Ferma Coach Live» resta,
   piccolo, come «Ferma senza aprire il report». Lo stato del pannello si ricava
   ogni volta dal processo e da `/health`: uscire e rientrare nella pagina non lo
   azzera.
9. **Nessun consiglio in corso.** La riga «Stai seguendo» non compare.

## Lasciato al costruttore

Dove vive la logica (modulo nuovo accanto a `hubgate.py` è il candidato), come
fare le richieste senza bloccare l'interfaccia, il disegno esatto del pannello
dentro lo stile dell'hub, il nome del campo nuovo di `/health`.
