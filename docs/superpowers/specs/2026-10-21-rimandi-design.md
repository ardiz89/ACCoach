# I rimandi: dalle schede del report al consiglio che segui — design

Data: 2026-10-21. Terzo dei quattro pezzi decisi col pilota (il quadro è in
`2026-10-21-pagella-e-piano-design.md`). Parte dal main locale e0002b1.

## Il perché

Dopo il pezzo 1 il pilota segue un consiglio alla volta dalla Pagella («Lo
seguo»). Le altre schede del report (Confronto, Traiettoria, Settori, Dinamica,
Andamento, e la scheda Frenate dentro il Confronto) non lo sanno: mostrano tutte
le curve allo stesso modo e il pilota deve ricordarsi da solo dove guardare.

## Deciso col pilota

1. **Una riga in cima alla scheda**, solo quando la scheda mostra qualcosa che
   riguarda il consiglio in corso. Dice dove guardare in quella scheda e porta al
   punto e al «Come si fa».
2. **Un segno sulle curve del piano** ovunque compaiano.
3. **Senza consiglio in corso le schede restano identiche** a oggi.

## Obiettivi

- Con un consiglio in corso, il pilota apre una scheda e in una riga sa cosa
  guardare lì per quel consiglio, con un clic arriva al punto e con un altro al
  «Come si fa» della curva.
- Le curve del consiglio si riconoscono a colpo d'occhio in ogni elenco, grafico
  e mappa del report, con lo stesso segno.

## Non obiettivi

- Nuove misure o nuovi grafici. I rimandi indicano quello che le schede mostrano
  già.
- Rimandi ai consigli proposti ma non seguiti, o a quelli chiusi.
- La riscrittura dei testi esistenti delle schede (pezzo 4).
- La Pagella e il «Come si fa» stessi, salvo l'ancora per curva nel «Come si fa».

## Anti-obiettivi (fallimento anche se funziona)

- Una riga su una scheda che non mostra niente di quel consiglio (la riga del
  veleggio in Traiettoria, per esempio).
- Una riga che afferma un numero o un giudizio che la scheda non mostra. La riga
  dice dove guardare, non cosa ci troverà.
- Il segno sulla curva accanto. Le schede numerano le curve ognuna sul proprio
  riferimento: una curva si ritrova per posizione, mai per indice. Meglio nessun
  segno che il segno sbagliato.
- Qualunque differenza in una scheda senza consiglio in corso: spazio vuoto,
  classi, ordine, testo.
- La stessa frase in due schede.

## Quale consiglio, quali curve

Il consiglio in corso è quello con stato `active` per l'auto e la pista che il
report sta mostrando (`coaching/advice.py`, uno solo alla volta). Le sue curve
sono `AdviceCorner` con `apex_pos`, misurate sul riferimento dello storico.

Ogni scheda ha le sue curve, con `entry`/`apex`/`exit` in frazione di giro. Una
curva della scheda è del consiglio se contiene l'`apex_pos` di una curva del
consiglio: la stessa regola di `advice.corner_at`, scritta una volta anche in
JS. Una curva del consiglio senza posizione (`apex_pos <= 0`, piano vecchio
migrato) non si segna da nessuna parte.

I difetti senza curve (`lift`, `coasting`) non hanno segni: la riga c'è dove la
scheda li mostra.

## Dove compare la riga

| Scheda | Difetti per cui c'è la riga | Dove porta «al punto» |
|---|---|---|
| Confronto | `brake_early`, `brake_late`, `over_brake`, `throttle_late`, `min_speed`, `lift` | i grafici zoomati sulla curva; per `lift`, la nota sul dritto nel debrief |
| Frenate (dentro il Confronto) | `brake_early`, `brake_late`, `over_brake` | la riga della curva nella scheda frenate (la riga del Confronto la nomina) |
| Traiettoria | `brake_early`, `brake_late`, `throttle_late`, `min_speed` | la curva aperta nella vista zoomata |
| Settori | difetti con curve | il settore che contiene la curva |
| Dinamica | `coasting`, `over_brake`, `throttle_late` | il riquadro del veleggio; per gli altri i grafici zoomati sulla curva |
| Andamento | tutti | la riga del difetto nello storico dei difetti; le schede per curva delle curve del consiglio |

Se nessuna curva del consiglio si ritrova fra le curve della scheda, la riga non
c'è (per i difetti con curve). Per Frenate vale lo stesso sulle righe della scheda
frenate.

La riga: il segno, una frase propria di quella scheda e di quel difetto, i nomi
delle curve come collegamenti (ognuno porta al suo punto), e «Come si fa» che
apre il «Come si fa» del difetto sulla figura di quella curva. Il nome del
consiglio non si ripete in ogni scheda: si capisce dal segno e dal collegamento.

## Il segno

Un solo segno, uguale ovunque, con un suggerimento al passaggio del mouse («Curva
del consiglio che segui»). Va su: le fasce delle curve nei grafici del Confronto
e della Dinamica, le etichette sulla mappa del Confronto, le righe di velocità
minima, le cascate e le schede del debrief, le righe della scheda frenate, i
bottoni curva e la tabella della Traiettoria, la riga del settore, le schede per
curva dell'Andamento. Non cambia l'ordine né la dimensione di niente.

## «Come si fa» per curva

`openHowto(defect)` accetta anche la posizione di una curva. Dopo il disegno, la
vista scorre fino alla figura che contiene quella posizione. Senza figura per
quella curva resta in cima, come oggi.

## Vincoli

- Tutto offline. Testi in italiano e inglese, col tono del pezzo 1: frasi brevi
  col tu, niente slogan, niente due punti a effetto, niente emoji, prima il fatto
  poi cosa fare.
- Il consiglio in corso si legge con una richiesta leggera, senza rigiocare le
  sessioni: la Pagella costa secondi, una scheda no.
- Una risposta in ritardo (auto/pista cambiate nel frattempo) non mette segni
  sulla pista sbagliata: si usa la guardia `EPOCH` già esistente.
- Prova nel browser sui giri del pilota, su una copia dell'archivio.
- Ogni test nuovo fallisce se si toglie la cosa che prova.

## Scelte mie

Prese da me, il pilota le può rovesciare.

1. **«Le curve del piano» sono le curve del consiglio in corso**, non quelle dei
   consigli in attesa: senza consiglio in corso le schede restano identiche, quindi
   i segni nascono e muoiono col consiglio in corso.
2. **Settori ha la riga** anche se non ha curve: indica il settore dove cade la
   curva, che è dove si vede se il guadagno arriva al cronometro.
3. **Frenate non è una scheda**, è un riquadro del Confronto: la riga del
   Confronto per i difetti di frenata lo nomina, e le sue righe hanno il segno.
4. **Il consiglio si chiede a un endpoint suo** (`/api/advice/active`), che legge
   il catalogo e basta, invece di estendere `/api/pagella`, che rigioca lo storico.
</content>
</invoke>
