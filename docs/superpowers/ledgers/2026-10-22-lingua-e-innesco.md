# Lingua delle pagine e parola d'innesco del trail braking — 22/10

Chiesto dal pilota dopo il pezzo 4.

1. **Parola d'innesco del TRAIL_BRAKE**: «rilascia»/«release» → «accompagna»/«trail it». Il richiamo scatta quando molli il freno troppo presto; «rilascia» diceva il contrario della correzione. Consiglio del coach approvato dal pilota. WAV rigenerati (59 per voce).
2. **Le pagine seguono la lingua dell'app** (`config.language`, scelta nell'hub): report e pagina Ingegnere la ricevono dal server a ogni apertura (`<html lang>` + `window.HONE_LANG`, `Cache-Control: no-cache`); niente più `localStorage`. Il selettore nelle pagine cambia la lingua di tutta l'app con `POST /api/language` (solo it/en).

Difetti trovati dalla revisione e curati:
- un clic sul selettore dal tablet, con `config.toml` illeggibile, riscriveva tutta la configurazione coi valori di base (laps_dir, lan): riprodotto. Ora `write_language` cambia solo la riga `language` in testa al file, verifica rileggendo, e se non può risponde 503 senza scrivere; scritture atomiche con tentativi su Windows.
- un salvataggio dell'hub riportava la lingua vecchia: `save_config` ora scrive solo i campi cambiati da quel processo sopra il file attuale, e restituisce False se non può (l'hub lo dice con `set.save_failed`, non mostra più «Salvato»).
- l'hub dopo un proprio salvataggio segue la lingua del file (`follow_language`).

Rimasto: l'hub aperto non si accorge da solo di un cambio di lingua fatto da una pagina finché non salva o riparte; `/api/language` non ha autenticazione, come gli altri POST (un dispositivo in rete può cambiare la lingua dell'app).
