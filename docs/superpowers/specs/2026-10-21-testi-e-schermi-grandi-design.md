# I testi col tono nuovo e la lettura sugli schermi grandi — design

Data: 2026-10-21. Quarto e ultimo dei pezzi decisi col pilota (il quadro è in
`2026-10-21-pagella-e-piano-design.md`). Parte dal main locale e18cdc7.

## Il perché

Il pilota trova i testi dell'app «da macchina»: frasi lunghe, slogan, due punti
a effetto, emoji, la stessa frase in più posti, numeri col punto. E su un 32" «si
perde a leggere»: il testo è fisso fra 10 e 14 px e non cresce con lo schermo.
I testi dei pezzi 1-3 sono già nati col tono nuovo; questo pezzo porta allo
stesso tono tutto il resto e rende la lettura comoda sugli schermi grandi.

## Deciso col pilota

- Il tono (dal pezzo 1): frasi brevi e dirette, col tu. Numeri con la virgola in
  italiano e con l'unità («0,18 s»). Niente slogan, niente due punti a effetto,
  niente emoji. Mai la stessa frase in due posti. Prima il fatto, poi cosa fare.
- Il 21/10, su questo pezzo:
  1. **Anche la voce** in pista: le frasi del coach si riscrivono e i WAV si
     rigenerano.
  2. **La guida si riscrive per ultima**, così racconta i testi nuovi.
  3. **Il testo cresce da solo con lo schermo**, senza un comando.
  4. **L'inglese segue le stesse regole** dell'italiano.

## Cosa entra

| Superficie | Dove stanno i testi |
|---|---|
| Report (tutte le schede, Pagella compresa) | `web/i18n.js`, `web/index.html`, testi scritti dal backend (`api.py`, `pagella.py`, `coaching/debrief.py`, `trajectory.py`, `trends`, `training.py`, `howto.py`) |
| Pagina Ingegnere | `web/engineer.html`, `engineer.js`, `engineer/core.py`, `engineer/steps.py`, `engineer/profiles` |
| Hub, avvio, pannello In pista, overlay | `i18n.py` (`_UI`), `launcher.py`, `hub_home.py`, `livepanel_ui.py`, `overlay.py` |
| Voce e testi del coach a schermo | `coaching/cue.py`, `focus.py`, `pitcall.py`, `voice.py`, `i18n._CUE_EN`, i WAV in `voice_cues/` e `voice_cues_male/` |
| Guida | `GUIDA.md`, `docs/FAQ.md` |

## Cosa non entra

- Il contenuto del protocollo di prova (`web/test_plan.json`): è uno strumento di
  prova, non l'interfaccia. Entrano invece i testi fissi della pagina di prova e
  del riquadro di prova (`test.js`, `testpanel.py`).
- L'aiuto della riga di comando (`__main__.py`): è per chi sviluppa.
- I nomi delle curve e dei circuiti (sono dati, non testi).
- Il significato. Un testo riscritto dice la stessa cosa di prima, coi numeri di
  prima: niente affermazioni nuove, niente consigli nuovi. Dove un testo vecchio
  afferma qualcosa che la schermata non mostra, si corregge e si annota nel
  registro.

## Le regole, come si controllano

Le regole del pilota diventano un controllo automatico su ogni catalogo di testi,
sul modello di `tests/test_howto_tono.py`, che oggi le applica solo a «Come si
fa» e alla Pagella.

| Regola | Controllo |
|---|---|
| Niente emoji | nessun carattere nei blocchi emoji e simboli pittografici (✓ ⚡ 📊 🔧 📡 📈 ▶ compresi) |
| Niente due punti a effetto | nessuna frase che apre con un'etichetta seguita da due punti («Obiettivo: …», «Nota: …», «Curve: »). Restano ammessi gli orari («22:58»), i tempi sul giro («1:47.427») e le didascalie di una tabella o di un campo che non sono frasi |
| Niente lineetta a effetto | nessuna frase costruita «X — Y» per dare enfasi; la lineetta resta solo fra due valori («22 °C — 30 °C») |
| Niente punti esclamativi | nessun «!» |
| Frasi brevi | nessuna frase oltre 25 parole |
| Virgola decimale in italiano | nessun numero con il punto decimale nei testi italiani, compresi quelli composti a runtime (i numeri passano da una funzione di formato unica per lingua, in JS e in Python) |
| Unità | numero e unità separati da uno spazio («0,18 s», «14 m», «165 km/h») |
| Mai la stessa frase in due posti | nessuna frase identica in due chiavi diverse dello stesso catalogo né fra cataloghi, per lingua |
| Niente slogan | nessuna delle formule della lista sotto |

Formule da slogan, vietate (italiano e inglese): «bella costanza», «ottimo
lavoro», «continua così», «sei pronto», «scopri», «al volo», «a colpo d'occhio»,
«nice consistency», «great job», «keep it up», «you're all set», «discover»,
«at a glance». La lista vive nel controllo e si allunga quando il pilota ne trova
un'altra.

I tempi sul giro restano nel formato dei cronometri («1:47.427»): è il formato
del gioco e il pilota lo legge così. La regola della virgola vale per gli altri
numeri.

## Prima e dopo (il metro per chi riscrive)

| Prima | Dopo |
|---|---|
| Nessun errore ricorrente — bella costanza! | In questa sessione nessun errore si ripete. |
| Obiettivo: sotto {v} a giro | L'obiettivo è stare sotto {v} a giro. |
| Curve: | (sparisce; l'elenco ha già il suo titolo) |
| 📊  Analisi & Report (browser) | Analisi e report |
| Tenuta: '{sym}' risolto ({a}→{b}). | Il problema di tenuta «{sym}» è risolto. Era {a}, ora è {b}. |
| Gas giù al {thr}% per {secs}s{where}: ~{tenths} decimi | Tieni il gas al {thr} % per {secs} s{where}. Ti costa circa {tenths} decimi. |
| Qui perdi {s} s — più che in qualunque altro punto | Qui perdi {s} s, più che in ogni altro punto. |
| DEMO — giri sintetici, non i tuoi dati reali | Questi sono giri di prova, non i tuoi. |

Le frasi del coach in pista (voce) seguono le stesse regole e in più si capiscono
al primo ascolto a 200 km/h: al massimo otto parole, un verbo all'imperativo,
nessun numero dove non serve.

## La lettura sugli schermi grandi

- Il report e la pagina Ingegnere misurano il testo a partire da una dimensione
  di base che cresce con la larghezza della finestra: 14 px fino a 1600 px di
  larghezza, poi in proporzione fino a 20 px. Su un 32" (2560 px di larghezza in
  CSS) il testo normale arriva a 18 px.
- Nessun testo sotto 12 px a 1600 px di larghezza, e tutti i testi crescono con la
  stessa proporzione (didascalie, etichette dei grafici, tabelle).
- Le etichette dentro i grafici (canvas) crescono con la stessa base.
- La larghezza della pagina cresce con la base, così le righe restano della stessa
  lunghezza in caratteri. Le colonne di lettura restano sotto i 75 caratteri.
- Su un portatile (fino a 1600 px) la pagina resta quella di oggi.
- L'hub (Qt) segue già la scala di Windows. Lì nessun testo sotto 12 px.

## Vincoli

- Tutto offline. Le voci si rigenerano con Piper in locale (le voci sono in
  `tools/piper/` del worktree col main, la cartella non è nel repo).
- Mai scrivere in `%USERPROFILE%\Documents\ACCoach`; le prove si fanno su una
  copia.
- I test che fissano il testo esatto si aggiornano al testo nuovo; un test che
  controlla un significato (un numero, un nome di curva) resta e deve continuare
  a fallire se il significato cambia.
- Prova finale nel browser sui giri del pilota, a 1366, 1920 e 2560 px di
  larghezza, e l'hub reso in PNG.

## Scelte mie

Prese da me, il pilota le può rovesciare.

1. **Il protocollo di prova e l'aiuto della riga di comando restano fuori**: non
   sono testi che il pilota legge mentre usa l'app.
2. **I tempi sul giro restano «1:47.427»**, col punto dei millesimi, come nel gioco.
3. **La lineetta a effetto conta come i due punti a effetto**: è lo stesso modo di
   dare enfasi.
4. **Il limite di 25 parole per frase** e **di otto parole per la voce** sono
   misure mie per «frasi brevi».
5. **La base cresce da 14 a 20 px** fra 1600 e 2880 px di larghezza; 18 px su
   2560 è la misura che mi aspetto comoda a un metro da un 32".
</content>
</invoke>
