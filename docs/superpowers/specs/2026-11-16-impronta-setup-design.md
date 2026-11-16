# Ingegnere, tappa 2 — l'impronta dell'assetto caricato, e la prova finale

Stato: proposta del 16/11, approccio scelto dal pilota («ok» all'impronta dal vivo).
Le scelte segnate *[mia scelta]* sono mie: il pilota ha chiesto di procedere in
autonomia e di provare tutto alla fine, in una sessione sola.

## Perché

L'Ingegnere misura una base su un assetto e scrive la modifica su un file. Oggi non sa
se quel file è quello montato in macchina. La pagina lo chiede la prima volta
(`/api/setup/base`, `confirm`) e poi scrive sull'ultimo file scritto da HONE; il
controllo «le gomme hanno risposto?» (`core._base_moved`) se ne accorge solo a fine
prova, dopo 4 giri, e solo per le pressioni.

Misurato il 16/11 sull'archivio (sola lettura):

- **ACC non scrive da nessuna parte quale assetto è caricato.** Nessun file della
  cartella del gioco toccato durante la sessione del 14/11 lo nomina.
- **L'impronta c'è nei dati che leggiamo già.** Per giro registriamo TC, ABS, mappa,
  ripartitore e benzina (`Lap.tc_level`, `abs_level`, `engine_map`, `brake_bias`). L'08/11
  e il 14/11 i primi stint sono a **TC 6, ABS 6, ripartitore 0,75**: nessun file di
  Imola ha quei valori (tutti TC 3, ABS 4, mappa 0). Dagli stint dopo i giri dicono
  TC 3, ABS 4, mappa 0, ripartitore 0,64: corrispondono ai file. Quindi la base di quelle
  due serate era misurata su un assetto che **non era un file**, quasi certamente un
  predefinito del gioco, e la modifica è stata scritta su un altro.
- I file HONE fra loro differiscono quasi solo nelle pressioni. Per distinguerli
  servono le pressioni a freddo ai box, e nei giri salvati quei momenti non ci sono
  (il registratore non registra la corsia box).

## Obiettivi

1. Riconoscere all'uscita dai box quale file di setup è montato, o dire che non è
   nessuno dei file salvati.
2. Accorgersi quando l'assetto cambia senza che l'Ingegnere l'abbia chiesto, e rifare
   la base.
3. Dopo una modifica scritta da HONE, controllare **all'uscita dai box** (non dopo 4
   giri) che in macchina ci sia il file scritto.
4. Non scrivere mai una modifica ai box su un assetto che non è un file.
5. Arrivare al test finale in pista con quello che serve per verificare tutto dopo,
   senza fare del pilota un sensore: registro della sessione, rigioco, piano di prova,
   verifica dei campi del gioco.

## Non obiettivi

- Leggere le regolazioni che il gioco non espone (barre, molle, ala, camber). La
  documentazione ACC marca `camberRAD` e `rideHeight` come non usati.
- Assetto Corsa 1: lì l'impronta risponde «non so» e tutto resta come oggi.
- Registrare canali nuovi per campione (la vecchia «tappa 2» della proposta del
  15/11): resta per dopo.
- Caricare l'assetto nel gioco al posto del pilota.

## Anti obiettivi (se succede, è un fallimento anche se «funziona»)

- Fermare il pilota o buttare una base per un segnale **non verificato**.
- Scegliere un file in silenzio: quando l'impronta non basta, si chiede.
- Una seconda domanda «quale assetto hai caricato?» diversa da quella che c'è già.

## Vincoli

- **Due processi.** I file di setup e `last_written` stanno nell'app web (`api.py` →
  `setup/web_api.py`); il motore e l'Ingegnere stanno nel server (`server.py`,
  `engine.py`). Le pagine parlano con tutti e due: `POST /api/setup/apply` all'app web,
  poi `POST /engineer/applied` al server.
- Il motore può leggere i file di setup da solo (`setup/loader`, stesse radici
  `DEFAULT_ROOTS`), in sola lettura.
- TC, ABS e mappa della struct graphics sono corroborati per aritmetica (offset) e ora
  anche dai dati (TC 3 / ABS 4 / mappa 0 nei giri = `tC1` 3 / `abs` 4 / `eCUMap` 0 nei
  file). Il ripartitore nel file è in click, «circa 0,2 % per click», base per auto
  ignota.
- TC, ABS, mappa e ripartitore si girano anche dal volante: un valore diverso dal file
  all'uscita può essere il pilota che ha girato una manopola ai box.
- Benzina: dopo una sosta col rifornimento del menu box non è quella del file.

## Approcci considerati

1. **Impronta dal vivo** — *scelto dal pilota*. All'uscita dai box si leggono i valori
   esposti dal gioco e si confrontano con i file di quell'auto e pista.
2. Chiedere il file a ogni uscita dai box: affidabile, ma pesa a ogni sosta e in
   macchina il pilota non può rispondere.
3. Solo il controllo a posteriori di oggi (`_base_moved`): arriva dopo 4 giri e solo
   per le pressioni. Resta come ultima rete.

## Il design

### 1. Cosa si legge e quando *[mia scelta]*

Un osservatore nel motore (`engineer/fingerprint.py`, puro, alimentato dai frame)
segue la macchina ai box:

- **da fermo nella piazzola o in garage** (`in_pit`, velocità < 1 km/h) tiene l'ultimo
  valore delle quattro pressioni e le temperature aria e pista (le pressioni a
  freddo), e **riconosce dal vivo**: ogni volta che TC, ABS, mappa, ripartitore o
  pressioni cambiano, rifà il confronto coi file. È un esito provvisorio, che va nel
  frame per le pagine e scioglie subito il blocco di R3 e l'attesa di R2: il pilota
  che ha appena caricato il file giusto in garage non deve fare un giro d'uscita per
  farselo riconoscere;
- **all'uscita dalla corsia box** (fine di `in_pit_lane` dopo averla percorsa) congela
  l'impronta: TC, ABS, mappa, ripartitore e benzina di quel frame, più le pressioni a
  freddo tenute prima. Le regole che cambiano la base (R1) agiscono solo qui.

Un'impronta senza la sosta da fermo (pressioni mancanti) resta valida per gli altri
campi. Se il gioco non aggiorna quei valori in garage, l'esito provvisorio resta quello
dell'uscita prima: lo dice il test.

### 1b. Le manopole al volante *[mia scelta]*

TC, ABS, mappa e ripartitore si girano dal volante, e l'Ingegnere stesso propone
modifiche al volo (`AV`, segnate applicate da `WheelWatch`). Quindi il confronto non è
col file nudo ma con **il file più le modifiche al volo accettate in questa sessione**
(`history` dell'Ingegnere, tag `AV`). Senza, dopo un TC +1 accettato nessun file
corrisponderebbe più e R3 bloccherebbe tutto.

Due conseguenze:

- quando l'Ingegnere scrive una modifica ai box, il file nuovo porta **anche** le
  modifiche al volo accettate e non ancora in un file. `setup_apply` copia il file di
  partenza: senza questo, caricare il file nuovo annullerebbe in silenzio un TC +1 già
  tenuto. Le voci in più arrivano dal motore nel blocco della proposta (`carry`), si
  scrivono, ma non contano nel budget di click né nel registro: sono già state contate
  quando sono state accettate;
- una manopola girata dal pilota da solo, senza proposta, all'uscita dai box è un
  cambio di assetto (R1): TC e ripartitore cambiano il comportamento dell'auto, e la
  base di prima non vale più.

### 2. Il ruolo di ogni campo *[mia scelta]*

| Campo | Ruolo | Confronto col file |
|---|---|---|
| TC, ABS, mappa | **certo** | uguale a `tC1`, `abs`, `eCUMap` |
| ripartitore | **certo, fra due stint**; contro il file solo dopo averlo tarato | entro mezzo click |
| pressioni a freddo | **indizio** finché non verificate in pista | entro 0,3 psi dal valore del file (20,3 + 0,1 × click) |
| benzina | solo registro | — |

- **Taratura del ripartitore.** Si impara **solo dalla risposta del pilota** alla
  domanda «Quale assetto hai caricato?» (e mai da un file unico compatibile: alla
  prima serata su una pista nuova un predefinito del gioco può coincidere su TC, ABS e
  mappa con l'unico file della cartella). Si salva per auto lo scarto fra il valore
  letto da fermo e i click del file. Da lì il ripartitore entra nel confronto coi file.
  Se una risposta successiva dà uno scarto diverso di più di mezzo click, la taratura
  si butta e il ripartitore torna a contare solo fra due stint, finché due risposte
  di fila non concordano.
- **Pressioni.** Si registrano sempre, coppia «valore del file / valore letto da
  fermo», per verificarle dopo il test. Finché non c'è una verifica (un interruttore
  esplicito, deciso dopo il test guardando il registro) servono solo a ordinare i
  candidati e ad aggiungere un avviso, mai a fermare o a buttare una base.

### 3. L'esito del riconoscimento

- **riconosciuto**: un solo file compatibile sui campi certi, oppure più file
  compatibili e uno solo vicino anche nelle pressioni (detto «probabilmente»);
- **ambiguo**: più file compatibili che i campi certi non separano;
- **non salvato**: nessun file compatibile sui campi certi;
- **non so**: nessun file per quell'auto e pista, gioco non ACC, o campi mancanti.

### 4. Cosa fa l'Ingegnere con l'esito

Il motore passa all'Ingegnere un fatto per ogni uscita dai box: è cambiato rispetto
all'uscita prima, è un file salvato, è quello atteso. L'Ingegnere decide.

- **R1 · Cambio non chiesto.** Campi certi (o il ripartitore) diversi dall'uscita
  prima, e nessuna modifica HONE applicata nel frattempo: la finestra si svuota, le
  uscite di pista pure, e lo dice («Hai cambiato assetto rispetto allo stint di prima:
  TC da 6 a 3. Rifaccio la base.»). Se c'era una prova in corso, non si giudica: si
  tiene la richiesta della base che c'è già (`_hold_base`), con questa frase.
- **R2 · Dopo una modifica scritta da HONE.** La prima uscita deve corrispondere al
  file scritto sui campi certi (e sul ripartitore, se tarato). Se no, la prova si
  **mette in pausa** subito, all'uscita, invece di aspettare 4 giri: «All'uscita dai
  box l'assetto non è quello che ho scritto (HONE_8): TC 6 invece di 3. Ai box carica
  HONE_8.» Non è la richiesta della base di oggi (`_hold_base`), che butta la base:
  qui la base misurata prima della modifica è buona, quindi la prova resta aperta coi
  giri di prova azzerati. La pausa si scioglie da sola quando il riconoscimento (dal
  vivo ai box o all'uscita) torna a corrispondere al file scritto sui campi certi, con
  una frase che dice il limite («TC e ABS ora sono quelli di HONE_8. Le pressioni le
  controllo a fine prova.»), oppure con la risposta del pilota sulla pagina. Si
  sblocca su campi che non separano HONE_8 da HONE_7: per questo a fine prova resta
  `_base_moved`. Se i campi certi tornano ma le pressioni a freddo no, solo un avviso
  in coda al contatore.
- **R3 · Assetto non salvato.** Si misura lo stesso (la base vale per quell'assetto),
  ma una modifica `BOX` non si propone: al suo posto «L'assetto in macchina non è fra
  i file salvati per Imola: TC 6 invece di 3, ABS 6 invece di 4. Se hai girato le
  manopole, rimettile come nel file; se è un assetto nuovo, in garage salvalo con un
  nome e caricalo.» Le leve `AV` restano. Il blocco si scioglie quando il
  riconoscimento trova un file (anche dal vivo ai box, senza giro d'uscita: la base
  resta buona, perché l'assetto è lo stesso), oppure quando il pilota sceglie un file
  sulla pagina: una scelta esplicita vale come «lo so, scrivi su questo».
- **R4 · Ambiguo o non so.** Nessuna regola nuova: vale il comportamento di oggi, con
  la domanda della pagina.

Per scrivere R2 il server deve sapere quale file è stato scritto: `POST
/engineer/applied` riceve il percorso del file (le pagine lo hanno dalla risposta di
`/api/setup/apply`), e `POST /engineer/base` il file scelto dal pilota.

### 5. Le pagine *[mia scelta]*

Il blocco dell'Ingegnere nel frame porta `loaded`: esito, nome del file (o dei
candidati), valori letti. La pagina Ingegnere e il tablet mostrano una riga sola
(«In macchina: HONE_8», «Assetto non salvato», «Non riconosciuto») e:

- se la pagina non ha un file di partenza e l'impronta ne riconosce uno, nella
  tendina della domanda che c'è già quel file porta «· in macchina». Non si
  preseleziona: nella pagina di oggi scegliere una voce **è** la risposta, quindi una
  preselezione risponderebbe al posto del pilota *[mia scelta, scrivendo il piano]*;
- se il file di partenza della pagina e il file riconosciuto sono diversi, la pagina
  lo dice prima di scrivere.

### 6. Pronti per il test finale *[mia scelta]*

- **Registro della sessione** in `logs_dir()`: un file JSON Lines per giorno,
  `ingegnere-AAAAMMGG.jsonl`. Una riga per giro (decisione, messaggio, stint, giro di
  assestamento, lettura delle pressioni, giri usati), per uscita dai box (impronta,
  esito, candidati, pressioni a freddo, aria e pista), per modifica applicata e per base
  confermata. Niente dati personali; resta sul PC. Serve ad analizzare il test senza
  chiedere al pilota.
- **Rigioco come comando**: `accoach replay-engineer <pista> <data> [auto]` rigioca i
  giri di quella serata nel motore (lo script del 16/11 portato nel codice, coi suoi
  test) e, se c'è il registro della serata, mette le uscite dai box al loro posto.
- **Verifica dal vivo**: `accoach verify-setup`, come gli altri `verify-*`: in garage
  stampa i valori letti accanto a quelli di ogni file della cartella. Trenta secondi
  al test per sapere se le pressioni a freddo valgono come campo certo.
- **Piano di prova** nella pagina `/test`: una categoria nuova coi passi da guidare per
  tappa 1 e tappa 2, nell'ordine, compreso caricare apposta un file sbagliato e girare
  una manopola da solo. La sorgente è `HONE_Test_Plan_AC_ACC.xlsx`; `web/test_plan.json`
  si rigenera con `tools/gen_test_plan.py`.

## Lasciato a chi costruisce

- Il punto esatto in cui il motore intercetta uscita dai box e sosta da fermo (oggi
  `in_pit` / `in_pit_lane` sono già nello snapshot).
- Dove salvare la taratura del ripartitore (per auto; lo stato dell'Ingegnere è per
  auto e pista).
- I testi esatti in italiano e inglese, coi controlli di tono che ci sono già.
- Le frasi a voce: nessuna frase nuova registrata. Le richieste usano la chiamata ai
  box che c'è già («Rientra ai box, scegli l'assetto.»).

## Da verificare al test

- Che da fermo ai box `wheelsPressure` valga la pressione a freddo del file.
- Che in garage, caricando un file, TC, ABS, mappa e ripartitore della shared memory
  prendano subito i valori del file (serve al riconoscimento dal vivo).
- Il passo del ripartitore per click sulla 720S.
- Che l'uscita dai box si veda con `in_pit_lane` anche partendo dal garage.
