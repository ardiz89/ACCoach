# La voce del coach con ElevenLabs e la radio nuova — registro (22-23/10)

Spec `docs/superpowers/specs/2026-10-23-voce-elevenlabs-design.md`, piano
`docs/superpowers/plans/2026-10-23-voce-elevenlabs.md`. Suite finale 3378.

## Cosa aveva detto il pilota

- La voce di Windows non basta: disposto a pagare un servizio una volta sola
  per avere una voce vera. Scelta MarcoTrox (Multilingual v2), «grinta media».
- «Basta generalizzare, non serve sapere il dettaglio del numero, poi quando vado
  ai box da setup visivo vedo cosa c'è da fare.»
- Due voci, maschile di default; la femminile la sceglie l'assistente (Tiziana).
- L'inglese «solo per altri piloti in futuro»: resta sulla voce di Windows.
- Dopo il primo ascolto: «in sostanza vanno bene», ma accenti sbagliati
  (antirollìo, pàttini), «qui perdi» detto «chi perdi», virgole ignorate, e
  una radio «il più realistica possibile».

## Cosa è stato fatto

- Le frasi con numeri variabili (pressioni, temperature, ABS/TC) diventano
  generali; il numero resta sullo schermo e nell'editor.
- Le leve dell'ingegnere hanno una frase detta (`engineer/voice_levers.py`, 25),
  l'annuncio è prefisso + leva.
- `coaching/spoken.py` elenca ogni frase che può essere detta in italiano (98);
  `tests/test_voice_coverage.py` fallisce se una frase nuova non ha il suo WAV.
- `tools/render_voice.py` registra con l'API (non col connettore claude.ai, che
  non regola velocità e stabilità): prova a secco, `--only`, `--listen`,
  `render.json` accanto ai WAV per sapere cosa va rifatto, pulizia degli orfani.
- Il testo mandato all'API non è la chiave: accenti scritti per le parole
  sdrucciole (tabella `PRONUNCIA`), «quì» contro il «chi», «ti-ci» per TC, e
  una pausa di 0,3 s dopo ogni virgola. Rifatte 60 frasi × 2 voci (4536
  caratteri).
- Radio nuova in Python puro (`coaching/radio.py`), una via di mezzo scelta dal
  pilota fra «team radio» e «sporca col motore»: banda 420-3000 Hz al 4° ordine,
  compressore, saturazione, codec a 8 kHz in μ-law, fruscio e motore leggeri,
  scatto del tasto e coda di squelch. Circa 130 ms la prima volta, poi in cache.

## Decisioni prese per il pilota

1. Velocità 1,10, stabilità 0,30, somiglianza 0,70, stile 0: la «grinta media»
   sentita e approvata.
2. Il livello della radio si normalizza sulla voce, non sul picco: lo scatto del
   tasto non deve decidere quanto è forte la frase.
3. ABS non ha una regola di pronuncia (tolta in `a23d7a6`).
4. Oltre 25 decimi la frase è «più di due secondi e mezzo», mai il numero.

## Difetti trovati che i test non vedevano

- L'analizzatore ricostruiva i suggerimenti perdendo la frase detta: una frase
  oltre i 2,5 s non sarebbe mai stata pronunciata.
- Il vecchio `render_cues.py` poteva sovrascrivere il rendering pagato: tolto.
- Le guide dicevano che gomme e ingegnere parlavano con la voce di Windows.
- La chiave dell'API era dentro la cartella del repo, non ignorata da git:
  spostata fuori, mai letta in chat.

## Aperti

- **Segno della convergenza**: il rimedio anteriore +1 è etichettato «toe-out» e
  il posteriore +1 «toe-in» sullo stesso parametro; sui file della 720S più click
  davanti danno meno toe-out. Da verificare nel garage di ACC, poi correggere i
  profili e registrare di nuovo le frasi della convergenza. Da controllare anche
  il camber.
- Il pilota ha `male = false` nella sua configurazione: deve scegliere «Voce
  maschile» in Impostazioni.
- L'inglese e tutto ciò che non è nel catalogo restano sulla voce di Windows.
