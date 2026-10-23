/* La prova «questo browser regge la pagina completa?».
 *
 * Scritto apposta con `async function` e `??`, le due forme di engineer.js che
 * i browser vecchi non leggono (Safari 9 nessuna delle due, Safari 10-13 solo
 * la prima). Dove il file non si analizza non gira niente e window.HONE_MODERN
 * resta assente: modern-gate.js manda alla vista tablet, e tablet.js spegne il
 * link «Pagina completa». Prima la prova compilava una stringa in uno script
 * inline, e la CSP delle pagine non lo lascia piu' passare.
 *
 * NON va nella lista di tests/safari9.py: li' «fallisce» per costruzione.
 */
async function honeModernProbe() { return null ?? true; }
window.HONE_MODERN = true;
