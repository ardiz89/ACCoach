# Riprendere i test dell'Ingegnere (tappe 1 e 2)

Scritto il 16/11/2026 per la conversazione che seguirà il test in pista. Chi riprende
legga questo file per primo, poi la memoria del progetto
(`ingegnere-riprogetto-2026-11-15`).

## Cosa è installato

La cartella da cui si guida (`%USERPROFILE%\progetti\ACCoach`, HEAD staccato) è al
commit in cima a `main` locale del 16/11. `main` locale non è pubblicato: niente push
finché il pilota non dice che è tutto finito. Prima di qualunque analisi, controllare
che la cartella da cui si è guidato sia davvero a quel commit
(`git -C %USERPROFILE%\progetti\ACCoach log --oneline -1`).

Dentro ci sono:

- **Tappa 1, pressioni.** Si decidono sulla mediana dei giri a regime dello stesso
  stint, senza il primo dopo la sosta. Due assi in una sosta. Il verdetto si dà sulla
  pressione raggiunta. Il contatore dice quanti giri mancano davvero.
- **Tappa 2, l'assetto ai box.** Riconosce quale file è in macchina (TC, ABS, mappa,
  ripartitore, pressioni a freddo). R1: assetto cambiato senza che l'Ingegnere l'abbia
  chiesto, rifà la base. R2: dopo una scrittura c'è il file sbagliato, la prova va in
  pausa e la base resta. R3: assetto non salvato, niente modifiche ai box. Design in
  `docs/superpowers/specs/2026-11-16-impronta-setup-design.md`.
- La mappa decisionale per il pilota: https://claude.ai/artifact/7GprcPbwG7Gb7jKQ2kmd7A

## Il giorno del test

1. Avvio come sempre, con `HONE.bat`.
2. Il foglio da seguire è sul tablet, pagina `/test`, categoria **Ingegnere** (10
   passi, nell'ordine). Ogni passo dice cosa fare e cosa deve succedere.
3. Il passo 1 va fatto in garage prima di uscire, da una console nella cartella
   d'installazione:
   `.venv\Scripts\python.exe accoach_main.py verify-setup`
   Lasciarlo andare circa 30 secondi, poi caricare un altro assetto e guardare le
   righe cambiare. Uscire con Ctrl+C. È l'unico modo di sapere se le pressioni lette
   da fermo sono quelle del file.
4. Durante la sessione non serve annotare i numeri: li scrive il registro.

## Dopo il test: cosa guardare

Il registro della serata è in `%USERPROFILE%\Documents\ACCoach\logs\ingegnere-AAAAMMGG.jsonl`.
Ha una riga per giro (`lap`), una per ogni lettura ai box (`setup`), una per ogni
modifica applicata (`applied`, `source` = `page` o `wheel`) e una per ogni risposta
sulla pagina (`base`). I percorsi sono relativi alla cartella dei setup.

Rigiocare la serata nell'Ingegnere (sola lettura, con casa finta):

```
set USERPROFILE=<cartella temporanea>
.venv\Scripts\python.exe -m accoach replay-engineer imola AAAAMMGG --laps "<cartella vera dei giri>" --log "<registro della serata>"
```

Le domande a cui il test deve rispondere:

1. **Pressioni a freddo.** Nelle righe `setup`, `box_psi` (lette da fermo) e i click
   del file (20,3 + 0,1 × click) coincidono entro 0,3 psi? Se sì, si accende
   `COLD_PSI_VERIFIED` in `src/accoach/engineer/fingerprint.py` e le pressioni
   diventano un campo certo. Guardare anche `box_core_c` contro l'aria per tarare
   `COLD_TYRE_MARGIN_C` (oggi 15 °C, non misurato).
2. **Il garage.** Caricando un file, TC, ABS, mappa e ripartitore cambiano subito
   nelle righe `setup` con `at` = `live`? L'uscita dal garage produce una riga
   `exit`?
3. **Il ripartitore.** Lo scarto imparato (`bias_learned` nelle righe `base`) e il
   passo di 0,2 % per click tornano sulla 720S?
4. **Le regole.** R1, R2 e R3 sono scattate quando il foglio lo aspettava, e mai
   altrove? Confrontare con il foglio compilato sul tablet.

## Casi lasciati aperti

Vanno cercati nel registro:

- Dopo una scrittura il file nuovo non viene caricato, la prova va in pausa, e lo
  si carica solo alla sosta dopo: la prova riparte su una base misurata con un'altra
  elettronica. Per chiuderlo l'Ingegnere deve ricordare le manopole della base.
- Una manopola girata in pista durante lo stint di base fa fermare la prova quando si
  carica il file scritto. Il motore fa bene; il foglio non lo dice.
- Scegliere un file salvato che contiene già una modifica al volo fa scrivere quella
  modifica due volte.
- `box_psi` lo sovrascrive una fermata in corsia box (coda, semaforo d'uscita).
- Un'uscita non riconosciuta non lascia la sua riga nel registro.

## Le tappe dopo

- La costanza del pilota prima del verdetto (dispersione degli stacchi e delle
  traiettorie). Il pilota l'ha chiesta il 16/11. Mattoni già nel codice:
  `braking_points.py`, `trajectory.py`.
- Dalla proposta del 15/11: il sintomo dichiarato dal pilota a fine run, il passo da
  2 click, i run da 4 + 3 + 3 + 3 giri, le pressioni per ruota, il comando
  «ricomincia».

## Per aprire la nuova conversazione

> Riprendiamo i test dell'Ingegnere: leggi `HANDOFF-test-ingegnere-2026-11-16.md`
> nel main locale e la memoria `ingegnere-riprogetto-2026-11-15`, poi analizza il
> registro e i giri della serata del <data>.
