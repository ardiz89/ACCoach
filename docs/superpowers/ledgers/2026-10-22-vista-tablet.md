# Vista tablet — registro (22/10)

Spec `docs/superpowers/specs/2026-10-22-vista-tablet-design.md`, piano
`docs/superpowers/plans/2026-10-22-vista-tablet.md`. Ramo `feat/vista-tablet`
da `9ceeb6a`. Suite finale 3083.

## Perché

L'iPad del pilota è un iPad 3 con iOS 9.3.6 (Safari 9). La pagina Ingegnere non
può girarci: Safari 9 si ferma alla prima riga di JavaScript moderno. Il firewall
di Norton 360 blocca le richieste del tablet verso il PC (il ping passa, le
pagine no) e il pilota non può cambiarlo senza pagare: la prova sull'iPad vero
resta aperta.

## Decisioni prese per il pilota

1. `i18n.js` `set()` usa `XMLHttpRequest` invece di `fetch`: su Safari 9 il
   selettore della lingua altrimenti non funziona.
2. I test di `tablet.js` in node danno a `i18n.js` un `document` minimo.
3. Anche il distintivo dal vivo della pagina Ingegnere legge `at_box`: su ACC
   diceva «in pista» con l'auto ferma nel box.
4. `tablet.js` non usa `.forEach` in nessuna forma; il controllo Safari 9 lo
   vieta su quel file.
5. Nei passi 4 e 5 alcuni difetti minori sono stati corretti subito invece di
   aspettare: la stessa frase in due avvisi, errori inghiottiti, il bottone
   «Fatto» che ricompariva, l'altezza `100vh`, un secondo formato dei numeri, il
   doppio tocco provato solo sulla forma del codice.
6. Nella revisione finale anche cifre a larghezza fissa, link «Pagina completa»
   nascosto sui browser vecchi, banner demo, a capo della guida.

## Difetti trovati che i test non vedevano

- In `i18n.js` `querySelectorAll(...).forEach` sta in un `try`: su Safari 9 i
  testi fissi di **tutte** le pagine non si traducevano mai, in silenzio.
- Su ACC `in_pit` non si accende con l'auto ferma: il promemoria ai box della
  pagina completa non compariva mai (corretto con `at_box`).
- La schermata «spento» diceva «il coach non è acceso» anche col coach acceso e
  il gioco chiuso. Poi la guida diceva «nei menu»: falso, nei menu il gioco
  manda già dati.
- Il rimando di `/engineer` provava solo `async`; la pagina usa anche `??`.
- La misura a 1024 × 768 era ottimista: Safari 9 lascia circa 1024 × 680.
- La guida prometteva il bottone «L'ho cambiato» anche su ACC, dove non c'è.

## Incidenti

- Uno script di schermate di un subagente ha chiamato `config.set_language("it")`
  sul `config.toml` vero. Verificato: contenuto identico alla copia presa in
  mattinata (lingua «it», `lan = true`, porta 8778). Nessun danno.
- Lo stesso ha ridotto il config della casa finta a una riga: HONE di prova è
  partito sulla 8778 della casa finta. Ricostruito.
- Un rapporto interno era finito nel ramo; tolto, e `.superpowers/` è ora in
  `info/exclude`.

## Rimasti aperti (minori)

- `/api/setup/base`: ordine `.json` poi `.ini`; un `stat()` su un file sparito
  dà 500; due radici con la stessa cartella.
- Il controllo Safari 9 è una lista di divieti: non vede parametri di default,
  `**`, `Array.includes`.
- Se `POST /engineer/applied` fallisce, la stessa modifica si può scrivere due
  volte (best-effort per spec).
- Nei menu di ACC la vista mostra la telemetria a zero invece di un'attesa.
- Prova su WebKit e sull'iPad vero: mai fatta.
