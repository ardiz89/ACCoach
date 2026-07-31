# Spike: i bordi della pista sotto la traiettoria

> Da uno screenshot di Track Titan (2026-07-30): nella loro analisi della
> traiettoria si vede **il nastro d'asfalto con i bordi**, e la nostra vista no.
> La telemetria dice dove sta l'auto, mai dove finisce la strada — disegnarli a
> occhio sarebbe un'invenzione.
>
> Stato: **spike concluso e feature fatta.** Lo strumento di indagine resta in
> `tools/track_edges.py`, fuori dal bundle; il lato prodotto è
> `src/accoach/trackedges.py`, e disegna il nastro nella scheda Traiettoria
> quando — e solo quando — i bordi sono quelli della pista che hai guidato.
> Come sono state chiuse le tre obiezioni: in fondo a questo documento.

---

## Il formato, decodificato

`content/tracks/<pista>/ai/fast_lane.ai`, versione 7. La chiave che mancava al
tentativo precedente è **l'`int` di conteggio ripetuto subito dopo il blocco dei
punti**: senza quei 4 byte tutto il blocco dei dettagli si legge sfasato, ed è
esattamente così che erano usciti «gas = 36.79» e «sideL = 3214».

```
0    int    versione (7)
4    int    count            numero di punti
8    int    lapTime          0 in tutti i file controllati
12   int    sampleCount      0 in tutti i file controllati
16   count × 20 byte         (float x, y, z, float length, int id)
..   int    count            RIPETUTO — è l'intestazione del blocco dettagli
..   count × 72 byte         18 float per punto
..   resto non decodificato  (0.8-2.5 MB, non serve ai bordi)
```

I 18 float, coi nomi che gira la comunità: `speed, gas, brake, obsolete, radius,
**sideLeft**, **sideRight**, camber, direction, normal[3], length, forward[3],
tag, grade`. **Di questi ho verificato solo quelli che uso** — i due `side` e il
vettore avanti; gli altri li stampo come sono, senza garantirne il nome (il primo
campo, per dire, a Monza vale 27 al punto 0, che come velocità sul rettilineo non
sta in piedi).

I bordi si ottengono dalla linea, perpendicolarmente al vettore avanti **in
pianta** (la terza dimensione è l'altezza: la larghezza di una pista si misura
per terra).

## Le prove

**1. Le larghezze sono plausibili.** Mediana 10.0 m a Monza, 10.4 a Spa, 10.1 a
Suzuka, 10.5 a Imola, con massimi 15-16 m dove la pista si allarga. Sono le
larghezze vere di quei circuiti.

**2. Il giro andato fuori risulta fuori, dove è andato fuori.** A Imola il giro
1:57.235 esce di **14.6 m oltre il bordo a pos 0.978** — che è la stessa curva
in cui il coach segnala l'uscita (velocità minima 73 km/h contro 203). Due
sorgenti indipendenti — la nostra rilevazione e la geometria di Kunos —
indicano lo stesso punto. È la prova che conta.

**3. Il giro pulito resta dentro, tranne sui cordoli.** Lo stesso Imola, giro
1:46.097: sfora al massimo **2.4 m**, e lì dove passa sui cordoli.

## I limiti, misurati — e quello che è caduto

**Il sistema di coordinate è quello della pista che hai *installata*, non di
quella che hai *guidato*.** A Monza le due sono lontane **187 m in x e 154 m in
z**: i giri in archivio vengono da un Monza diverso da `content/tracks/monza`.
Imola, Spa e Suzuka combaciano entro **1.5 m**.

Questo era un limite, e il **2026-07-31 è caduto**. Confrontare le coordinate
numero per numero è una domanda sui *formati dei file*, non sui *luoghi*: la
forma guidata si può **posare** su quella del file (rotazione, traslazione e una
scala che deve venire 1), e allora l'origine non conta più. Misurato su tutti i
39 giri veri contro le quattro spline installate — 24 confronti, tutti
classificati giusti:

| giro | spline | scarto p95 | scala | esito |
|---|---|---|---|---|
| Imola | imola | 17.3 m | 0.999 | accettata — il peggiore dei veri |
| monza | monza | **4.2 m** | 1.001 | accettata — *era rifiutata a 187 m* |
| spa | spa | 4.0 m | 1.000 | accettata |
| suzuka | suzuka | 2.4 m | 1.000 | accettata |
| spa_1998 | spa | 58.3 m | 1.000 | rifiutata — altro tracciato |
| ks_nurburgring | qualunque | 12-18 m | **0.015** | rifiutata — coordinate rotte |
| pista sbagliata | — | 162-839 m | 0.68-1.23 | rifiutata |

Fra il peggiore dei veri (17.3 m) e il migliore dei falsi (58.3 m) c'è un
fattore **3.4**: la soglia sta in campo aperto, non su un confine.

Servono **tutte e due** le condizioni, e ognuna copre il buco dell'altra:

* la **sola scala** non basta — Spa 1998 combacia con Spa moderna a scala 1.000
  ed è un altro tracciato;
* il **solo scarto** non basta — un giro con le coordinate rotte combacia con
  *qualunque* circuito a 8 m, perché il fit è libero di rimpicciolirlo settanta
  volte.

Controllo indipendente dopo il fit: la linea guidata risulta a **0.7-4.4 m** dal
centro pista. La macchina è sulla strada.

E la conferma più bella è arrivata gratis: dei sette giri al Nürburgring, **sei
hanno le coordinate rotte** (167 m per un giro da 5 km) e vengono rifiutati; il
settimo ne ha di buone (5073 m contro i 5072 della spline) e passa a 6.9 m. Il
fit sceglie il giro giusto da solo, senza sapere niente di quel difetto.

**I bordi sono l'asfalto, non i limiti della pista.** Un giro pulito ci passa
sopra di 2.4 m sui cordoli — e a **La Source (Spa) la spline dice 24.5 m**,
perché la via di fuga asfaltata è asfalto. Su tutto Spa solo 2 tratti su 6934 m
superano i 16 m, e uno è esattamente quella curva. La legenda lo dice:
`l'asfalto (di norma largo 10.4 m) — le vie di fuga contano, i cordoli no`.

**E nemmeno il nome conta più.** I due giochi non chiamano le piste allo stesso
modo: Mount Panorama è `mount_panorama` su ACC e `rt_bathurst` nel mod che la
porta su AC. Cercare per stringa faceva ricomparire lo stesso difetto da un'altra
porta. Siccome il fit riconosce un circuito dalla forma, la lunghezza del giro
riduce le 65 piste installate a una manciata di candidati (misurato: da 1 a 5) e
il fit sceglie fra quelli. Provato su tutto l'archivio buttando via il nome:
**24 giri posati sulla pista giusta, nessuno su una sbagliata**, e i 15 rifiuti
sono esattamente i giri con le coordinate rotte o assenti. 0.14 s a giro.

E qui è arrivata la scoperta scomoda, misurando 24 accoppiamenti veri contro 95
falsi: **nessuna statistica assoluta separa un circuito dalla propria versione
storica.** Peggiore dei veri 26.7 m, migliore dei falsi 22.3 m (Suzuka contro
Suzuka 1998). Provati e scartati anche il massimo, il rapporto max/p95 e persino
il controllo fisico «quanta parte del giro finirebbe fuori dall'asfalto»: si
sovrappongono tutti. A separarli è solo il **confronto fra candidati** — la pista
giusta vince in tutti e 24 i casi (Suzuka 3 contro 22, Imola 17 contro 32, Spa 4
contro 51). Per questo si valutano tutti e vince il migliore, mai il primo che
passa; e la soglia resta solo come tetto.

## E infine: la geometria non viene più solo dal gioco (2026-07-31)

L'ultimo limite — *servono i file di AC installati* — è caduto cercando in rete
una sorgente aperta. Ce n'è una che ha esattamente la nostra struttura:

* **[TUMFTM/racetrack-database](https://github.com/TUMFTM/racetrack-database)**
  (LGPL-3.0): 25 circuiti, linea centrale in metri e larghezze a destra e
  sinistra, un punto ogni 5 m. Le linee vengono da punti GPS di OpenStreetMap,
  **le larghezze da immagini satellitari**;
* **[TUMRT/online_3D_racing_line_planning](https://github.com/TUMRT/online_3D_racing_line_planning)**
  (LGPL-3.0): **Mount Panorama** con le due sponde in 3D, 6001 coppie di punti.

Scartati: `bacinger/f1-circuits` (MIT, 40 circuiti) ha **solo** la linea
centrale a 125 punti e nessuna larghezza — non ci si disegna una pista;
`f1tenth_racetracks` è il TUM rimpicciolito 1:10.

Provati sui giri veri prima di impacchettarli:

| tracciato | contro | scarto p95 | scala |
|---|---|---|---|
| TUM Spa | il nostro giro Spa | **8.1 m** | 0.998 |
| TUM Suzuka | il nostro giro Suzuka | **11.3 m** | 1.002 |
| TUM Monza | il nostro giro Monza | 26.9 m | 1.005 |
| TUM Spa | il nostro giro **Spa 1998** | 63.4 m | rifiutato |
| TUM Bathurst | il **mod Kunos** installato | 16.1 m | 0.993 |

Monza è la peggiore perché la loro linea è il **centro pista** e la nostra è la
**linea IA**: due linee diverse dentro la stessa strada. Bathurst non ha giri in
archivio, quindi è stata validata contro il mod: due sorgenti indipendenti
(satellite/GPS contro modello 3D) sullo stesso circuito. Serve lo **specchio**,
perché i dati reali sono destrorsi e AC è mancino — la ricerca dello specchio nel
fit non era decorativa.

E il motivo migliore per averli non era la copertura:

| | mediana | massimo | rapporto max/mediana |
|---|---|---|---|
| TUM Spa | 9.2 m | **16.4 m** | 1.78 |
| AC spa | 10.4 m | **24.5 m** | 2.36 ← La Source |
| TUM Suzuka | 9.2 m | **15.3 m** | 1.66 |
| AC suzuka | 10.0 m | **33.5 m** | 3.35 ← il buco dei 343 m |

Le larghezze da satellite misurano **la pista**; quelle del gioco misurano ogni
metro quadro di asfalto. I 26 impacchettati stanno tutti fra 1.06 e 2.12 di
rapporto — Austin, il peggiore, ha davvero il rettilineo dei box largo 27 m.

Le due sorgenti **non** sono in gerarchia: finiscono nello stesso elenco di
candidati e vince il punteggio. Sui nostri giri vince sempre il file del gioco
(sono le sue piste, e i giri vengono da lì); togliendo AC dal quadro, i 26
impacchettati coprono da soli Monza, Spa e Suzuka. Imola no — non è fra i 25 — e
la Nürburgring del TUM viene **rifiutata a 52.4 m** perché è un'altra
configurazione da quella di AC: la stessa distanza che separa Spa 1998 da Spa.

Attribuzione e licenze: `src/accoach/tracks/NOTICE.md`.

## La feature: fatta, e come sono state chiuse le obiezioni

Il nastro si disegna nella scheda Traiettoria (`src/accoach/trackedges.py`),
scritto attorno ai modi di dire di no:

1. **Dipendenza dall'installazione del gioco.** `tracks_dir()` cerca AC nelle due
   posizioni Steam standard **e nelle librerie dichiarate in
   `libraryfolders.vdf`** — i giochi stanno sul secondo disco più spesso che no.
   Niente gioco, niente cartella, niente file: `None`, e la pagina è quella di
   sempre.
2. **È la stessa pista?** Non più un confronto di coordinate ma un fit, con le
   due soglie misurate qui sopra. Dal 31/07 **Monza rientra**.
3. **Il caso «qui non c'è».** Non è un buco da riempire: il disegno è quello di
   prima e **la voce di legenda compare solo quando il nastro c'è**.
4. **Scarto ×3/×5** — trovata disegnando: la linea mostrata non è più dove è
   passata l'auto, quindi uscirebbe dal nastro e sembrerebbe un'uscita di pista
   mai avvenuta. Con l'ingrandimento attivo **il nastro sparisce**.
5. **Buchi nel file** — trovata misurando l'archivio il 31/07: a Suzuka la spline
   ha **228 punti di fila** coi lati fuori scala. Scartarli è giusto, scartarli
   in silenzio no: i superstiti si univano e il nastro tagliava dritto per
   **343 m** attraverso il circuito. Ora un buco resta un buco.

Il ripiego dell'**inviluppo dei tuoi giri** non è stato implementato e serve
ormai solo a chi ha unicamente ACC.

## 2026-07-31, sera: la strada non era la strada

Segnalato guardando la Variante del Rettifilo accanto a una foto aerea: la
nostra si disegnava come una **esse morbida**, quella vera è un **flick secco**.

La geometria del giro era giusta (verificata contro la Monza da satellite:
−54°/−87° a destra, poi +78°/+107° a sinistra). A sbagliare era il nastro, e la
causa sta in questo documento fin dall'inizio senza che me ne accorgessi:
`sideLeft`/`sideRight` sono misurati **perpendicolarmente alla linea dell'IA**.
Dove l'IA taglia una variante il piede della perpendicolare non cade sul punto
giusto del bordo, e quello che se ne ricava è **il corridoio attorno alla
traiettoria dell'IA**, non la strada.

La strada sta altrove, e nello stesso gioco: le **mesh delle superfici**, una per
pezzo di pista, nominate con le chiavi di `surfaces.ini`.

| Monza | mesh | triangoli |
|---|---|---|
| `MONZA-ASPH` + `ROAD` | 113 | **404.824** |
| `CURB` + `KERB` | 36 | **19.755** |
| `GRASS` · `SAND` · `CONCRETE` · `WALL` | 152 | il resto |

Posate con lo stesso fit: **la linea guidata sta a 0.34 m dal vertice d'asfalto
più vicino** (p95 1.26 m). Il dato satellitare, sullo stesso giro, ne dava 7-14.

Due cose non ovvie, entrambe misurate:

* **dove stiano le mesh non è una regola.** Monza, Spa, il Nürburgring e
  Bathurst hanno un modello a parte, piccolo; Imola e Suzuka le tengono dentro
  il modello **visivo** da centinaia di MB, fra `Object112` e `bush767`. La
  prima versione cercava il file «in cui quasi tutti i nomi sono superfici» e
  falliva su metà delle piste. Ora conta: chi ne ha, ne ha 74-375; chi non ne
  ha, ne ha **zero**.
* **al browser non si mandano i triangoli.** Attorno a una sola curva ce ne sono
  ventimila, un megabyte e mezzo. Si manda il **contorno**, ricavato
  rasterizzando a mezzo metro — che risolve gratis anche le cuciture, perché due
  mesh affiancate non condividono i vertici ma coprono celle contigue. Dieci
  chilobyte a curva, un decimo di secondo.

Il nastro dalla spline resta come ripiego, per le piste senza mesh leggibili.

### E ACC?

Le sue mesh stanno dentro un `.pak` di Unreal Engine da **17 GB**: un altro
problema. Ma ACC pubblica `fastlane.ai` per tutte e 25 le piste **fuori** dal
pak, versione **8**. La decodifica della v7 non si trasporta: provate tutte le
dimensioni di record da 12 a 88 byte e tutti gli offset, nessuna dà una
polilinea vicina ai 5793 m di Monza. È uno spike a sé.

## Come rifare le misure

```
python tools/track_edges.py imola --lap "<un giro .lap.json.gz>"
python tools/track_edges.py spa --csv bordi_spa.csv
```
