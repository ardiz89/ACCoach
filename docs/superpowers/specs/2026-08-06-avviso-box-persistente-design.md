# L'avviso di rientro ai box che non se ne va

**Data:** 2026-08-06 · **Stato:** approvato, da pianificare

## Da dove nasce

Parole del pilota: *«quando mi viene suggerito di tornare ai box, deve rimanere
sempre attivo l'avviso del ritorno ai box finché non entro nella corsia»*.

Oggi il richiamo ai box è un **cue**: viene pronunciato, la pastiglia
sull'overlay lo mostra e **sfuma dopo 1,8 secondi** come qualunque altro
consiglio. Se in quel momento stavi guardando la curva davanti, il richiamo è
passato e non torna fino al giro dopo.

## La decisione

**Un rientro non è un evento, è una condizione.** Un cue è la cosa giusta per
«frena più tardi», che vale in un punto e poi non vale più; è la cosa sbagliata
per «devi rientrare», che vale finché non sei rientrato.

Quindi il rientro smette di essere *solo* un cue e diventa anche uno **stato**
esposto dal motore — la stessa mossa fatta il 06/08 per la carta della curva, e
per la stessa ragione: un evento sfuma, una condizione dura.

## Cosa si spedisce

**Quando compare:** dal momento in cui il coach chiama il rientro.

**Quando sparisce:** quando entri in **corsia box**. E anche quando il rientro
smette di essere necessario — un avviso che sopravvive alla sua ragione è peggio
di nessun avviso.

**Come:** finché è attivo, la banda della pastiglia diventa un avviso fisso in
ambra:

```
┌─ HONE ────────────────────── PB 1:53.712 ─┐
│            ██████▌   +0.42                │
│  ▶ RIENTRA AI BOX                         │   ← fisso, ambra
│  FOCUS · FRENATA · Lesmo 1                │
│  ● Variante Ascari              −0.31     │
└───────────────────────────────────────────┘
```

I consigli di guida **cedono quella riga** finché l'avviso è su, e la riprendono
quando sei in corsia. La gerarchia è quella giusta: un consiglio su come prendere
la Lesmo che copre il rientro ti fa fare un giro in più col serbatoio vuoto.

**La voce non cambia.** I cue continuano a essere pronunciati esattamente come
oggi, negli stessi momenti: cambia solo **chi occupa quella riga a schermo**.
Questo è un vincolo, non un dettaglio — è la stessa regola con cui è stato
spedito il KPI per curva.

## Dove sta lo stato

`pitcall.py` sa già tutto quello che serve: che una sosta è **pendente**
(`set_pending`, alimentato dal cambio d'assetto proposto dall'ingegnere), che il
**richiamo è stato fatto** per quel giro, e vede `in_pit_lane` e `in_pit`. Non
serve inventare niente: serve **esporlo** come stato invece che solo come cue.

Viaggia in `EngineState` come blocco opzionale accanto a `engineer`, `focus` e
`corner`, il server lo serializza, l'overlay lo legge. **Assente quando non c'è
nulla in sospeso** — mai un avviso spento che occupa spazio.

## Test

- compare **dopo il richiamo**, non prima;
- **sopravvive al giro successivo** — è esattamente il difetto che si sta
  correggendo, e un test che guarda solo i primi 1,8 secondi lo mancherebbe;
- **sparisce entrando in corsia box**;
- sparisce se il rientro non è più necessario;
- **non compare** quando non c'è niente in sospeso;
- i cue pronunciati sono **gli stessi di prima**, negli stessi istanti: test di
  non-regressione sul comportamento della voce.

## Fuori perimetro

Cambiare **quando** il coach chiama il rientro: quella logica è misurata e
tarata altrove (`pitcall.py`, con la corsia box imparata dai tuoi giri) e questo
lavoro non la tocca. Qui cambia solo per quanto tempo l'avviso resta a schermo.
