# Spike: la linea IA di ACC (`fastlane.ai`, versione 8)

> **Stato: a metà, e la metà che manca è netta.** I punti sono decodificati e
> validati su **tutte e 25** le piste; le larghezze reggono su **9**. Lo
> strumento è `tools/acc_fastlane.py`, fuori dal bundle come lo spike dei bordi.
>
> Nessuna riga di questo spike è entrata nel prodotto: finché le larghezze non
> reggono ovunque, non c'è niente da disegnare.

---

## Perché

Il 31/07 la strada ha smesso di venire dalla linea dell'IA e ha cominciato a
venire dal **modello delle superfici** di Assetto Corsa (`SPIKE-BORDI.md`):
asfalto, cordoli, erba, ghiaia. Su ACC quel modello **non è raggiungibile** —
sta dentro `AC2/Content/Paks/AC2-WindowsNoEditor.pak`, **17 GB** di Unreal
Engine.

Ma ACC lascia **fuori dal pak** una `fastlane.ai` per ogni pista, in
`AC2/Content/Cache/<pista>/`. Venticinque file, 61 MB in tutto, Mount Panorama
compresa. Se si leggono, ACC smette di dipendere dal fatto che tu abbia
*anche* Assetto Corsa installato.

## Il motivo per cui la v7 non si trasportava

Provate **tutte** le dimensioni di record da 12 a 88 byte e tutti gli offset
possibili: nessuna combinazione dava una polilinea vicina ai 5793 m di Monza.

La risposta era nei byte, e cercarla alla cieca era il modo sbagliato:

```
0010  00 00 00 20 dc 4f 78 c0    <- 00 00 00 XX .. c0 : la firma di un DOUBLE
```

Le coordinate di ACC sono a **64 bit**, non a 32. Su AC erano float.

## Il formato, per la parte che regge

```
0    int      versione (8)
4    int      conteggio  — e' il DOPPIO dei punti (rapporto 2.00 su tutte e 25)
8    int      0
12   int      0
16   N × 72   un punto: 9 double, di cui i primi quattro sono
              x, y, z, distanza cumulata
..   int      il conteggio RIPETUTO — come nella v7, e' l'intestazione dei
              dettagli
..   N × 80   dettagli: 20 float, con sideLeft/sideRight agli indici 5 e 6
..   resto    non decodificato
```

Quanti siano i punti **non si chiede all'header**: si cammina finché restano
sensati. Il conteggio dichiarato è esattamente il doppio su ogni pista, ma
cosa conti davvero resta ignoto, e costruirci sopra sarebbe fidarsi di un
numero che non si è capito.

## Le prove sui punti (tutte e 25)

Due, indipendenti fra loro.

**1. La lunghezza contro quella pubblicata.** Scarto medio **1.6%**, che è
l'ordine di grandezza della polilinea contro la misura vera:

| | punti | cumulata | pubblicata | scarto |
|---|---|---|---|---|
| monza | 576 | 5744 m | 5793 | −0.8% |
| spa | 695 | 6933 m | 7004 | −1.0% |
| mount_panorama | 618 | 6164 m | 6213 | −0.8% |
| nurburgring_24h | 2523 | 25195 m | 25378 | −0.7% |
| watkins_glen | 542 | 5405 m | 5552 | −2.7% |

**2. Il file che conferma sé stesso.** La distanza cumulata *dichiarata*
all'ultimo punto e la polilinea *calcolata* dalle coordinate coincidono entro
pochi metri su ogni pista — 5744 contro 5758 a Monza, 6933 contro 6935 a Spa.
Sono due numeri che vengono da parti diverse dello stesso file: se la
decodifica fosse sbagliata non avrebbero motivo di accordarsi.

## Dove si ferma: le larghezze

Il record di dettaglio da 80 byte, letto come float, è chiarissimo su Monza:

```
0.000 0.000 0.000 0.000  9000.000  7.573 4.240 7.573 4.240 0.010 -1.000 ...
                                    ^^^^^ ^^^^^ ripetuti
```

7.573 + 4.240 = **11.81 m**, la larghezza di Monza. L'indice 14 vale ~5.0 su
ogni record: è il passo fra i punti. Gli indici 5 e 6 sono i due lati, **gli
stessi della v7** — e le colonne 7 e 8 li ripetono, il che è esattamente ciò che
mi aveva sviato in un primo tentativo (due colonne identiche a 8 byte di
distanza sembrano una coppia sinistra/destra, e non lo sono).

Ma il passo da 80 byte **regge solo su 9 piste su 25**:

| reggono (95-100% dei lati) | non reggono (15-62%) |
|---|---|
| monza 9.8 m · imola 10.4 · suzuka 10.5 · nurburgring 12.7 · nurburgring_24h 8.4 · paul_ricard 13.2 · zolder 13.7 · donington 10.7 · oulton_park 8.8 | spa · silverstone · mount_panorama · barcelona · red_bull_ring · zandvoort · misano · laguna_seca · e altre |

Sulle sedici che non reggono il valore esce **costante attorno a 5.7-6.0 m**,
che ha tutta l'aria di un campo diverso letto per sbaglio — un default, non una
misura. Il record di dettaglio quindi **non è lungo 80 byte su tutte le piste**,
o i lati non stanno sempre allo stesso posto.

## Cosa servirebbe per finirlo

Trovare il passo del blocco dettagli **pista per pista** invece che assumerlo,
allo stesso modo in cui il numero di punti si conta invece di leggerlo. Il
segnale c'è: dove il passo è giusto la frazione di lati plausibili è del 100%,
dove è sbagliato crolla sotto il 60%. È un criterio misurabile, quindi la
ricerca si può automatizzare — ma è un'altra sessione, non una regolazione.

## Come rifare le misure

```
python tools/acc_fastlane.py
python tools/acc_fastlane.py monza --dump 4
```
