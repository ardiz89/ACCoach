# Integrazione della PR #114 nel main locale — 22/10

La #114 (pagina Ingegnere a schede sotto i 1440 px, grafico «Pedali e sterzo», sterzo nella striscia dei pedali dell'overlay, `steer` nello stato dal vivo) era fuori dal main e scritta prima della riscrittura dei testi. Fusa con un merge (`d22ae7e`) più un giro di correzioni (`47f27bf`).

- Conflitti: solo `eng.hint` (html e catalogo). Tenuto il testo vero del main (Coach Live alimenta la pagina); la #114 riportava la frase vecchia, falsa, con un'emoji.
- La fusione ha fatto emergere: la lingua dell'app non iniettata nella pagina Ingegnere (l'espressione aspettava `>` dopo `lang`, la #114 mette `data-tab` su `<html>`); il tour che sui telefoni/tablet saltava il passo dell'editor; 420 px con scorrimento laterale nella scheda Setup.
- Portata agli standard: testi nuovi col tono, numeri con `fmtN`/`fmt_num`, CSS in rem, frecce sostituite da parole («34 % a sinistra», «STERZO 34 % SX»).
- Revisione: le letture dell'overlay erano tagliate («STERZO 100 % S», il verso perso) — ora le caselle si misurano col carattere vero, con un test che rende i casi peggiori; pizzico per zoomare riattivato sul tablet; scala dello sterzo azzerata alla disconnessione; «COAST 1,2 s»; i commenti dicevano «radianti» ma il valore è la frazione −1..1 dello sterzo a fondo.
- Da provare in pista: lo scorrimento col dito vero sul tablet, la scala dello sterzo, la striscia dell'overlay con la traccia dei pedali accesa.
