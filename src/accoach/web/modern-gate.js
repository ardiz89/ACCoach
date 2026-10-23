/* Il cancello di engineer.html: senza la bandierina di modern.js questo
 * browser non legge la pagina completa (resterebbe bianca), quindi si va alla
 * vista tablet. ES3 apposta: deve partire anche dove modern.js non parte.
 * Caricato subito dopo modern.js, prima di tutto il resto. */
if (window.HONE_MODERN !== true) { location.replace("/tablet"); }
