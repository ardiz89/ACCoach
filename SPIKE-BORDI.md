# Spike: i bordi della pista sotto la traiettoria

> Da uno screenshot di Track Titan (2026-07-30): nella loro analisi della
> traiettoria si vede **il nastro d'asfalto con i bordi**, e la nostra vista no.
> La telemetria dice dove sta l'auto, mai dove finisce la strada — disegnarli a
> occhio sarebbe un'invenzione.
>
> Stato: **spike concluso, feature non ancora decisa.** Vive in
> `tools/track_edges.py`, fuori dal bundle (`HONE.spec` non lo include,
> `requirements.txt` non cambia). Il seguito è una decisione di prodotto, e sta
> in fondo a questo documento.

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

## I due limiti, misurati

**Il sistema di coordinate è quello della pista che hai *installata*, non di
quella che hai *guidato*.** A Monza le due sono lontane **187 m in x e 154 m in
z**: i giri in archivio vengono da un Monza diverso da
`content/tracks/monza`. Imola, Spa e Suzuka combaciano entro **1.5 m**. Quindi
l'allineamento è **un controllo da fare pista per pista**, mai un'assunzione — e
il controllo costa niente: stessa forma, stesso centro. Il tool si ferma da solo
quando lo scarto supera i 5 m.

**I bordi sono l'asfalto, non i limiti della pista.** Un giro pulito ci passa
sopra di 2.4 m sui cordoli. Qualunque cosa ci disegnamo sopra deve dire
**«asfalto»**, altrimenti chiama escursione un cordolo preso bene.

E i due limiti che si sapevano già: vale **solo per AC** (i dati pista di ACC
sono impacchettati) e **solo per le piste installate**.

## Cosa resta da decidere (non l'ho fatto)

Disegnare il nastro nella scheda Traiettoria è una **feature**, non il seguito
automatico dello spike, perché porta in casa tre cose nuove:

1. **una dipendenza dall'installazione del gioco** — trovare `assettocorsa` su
   disco, gestire chi ce l'ha altrove, chi gioca solo ad ACC, chi ha spostato la
   libreria Steam. Oggi HONE legge solo la memoria condivisa e la sua cartella
   giri: non ha mai aperto un file del gioco;
2. **un controllo di allineamento per pista**, col suo modo di dire di no. A
   Monza — cioè su una delle piste su cui l'utente guida davvero — la risposta
   oggi è no;
3. **una linea da disegnare che a volte non c'è**: metà delle viste avrebbero i
   bordi e metà no, a seconda della pista e del gioco. Va progettato quel caso,
   non aggiunto dopo.

Il ripiego onesto per ACC e per le piste disallineate resta quello di prima:
**l'inviluppo dei tuoi giri** su quella pista — «dove sei passato» — dichiarato
così, mai chiamato bordo pista.

## Come rifare le misure

```
python tools/track_edges.py imola --lap "<un giro .lap.json.gz>"
python tools/track_edges.py spa --csv bordi_spa.csv
```
