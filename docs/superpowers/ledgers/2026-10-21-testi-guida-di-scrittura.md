# Guida per chi riscrive i testi (vale per i Task 3-8, 10, 11)

## Chi legge
Un pilota italiano di simulatori. Legge dopo la sessione, spesso su un 32", e in pista sente la voce. Odia il testo «da macchina» («AI slop»): frasi lunghe, slogan, «Etichetta: valore» a effetto, lineette a effetto, emoji, punti esclamativi, la stessa frase in più posti, riempitivi vaghi. Vuole frasi brevi e dirette col tu, prima il fatto e poi cosa fare, numeri con la virgola e l'unità («0,18 s»).

Scrivi l'italiano come lo direbbe un coach di guida italiano a un pilota: naturale, non tradotto. L'inglese è una traduzione naturale con le stesse regole, non parola per parola.

Modello approvato dal pilota:
> **Villeneuve** · dopo la Variante Alta
> Qui perdi 0,18 s a giro, e succede quasi sempre (10 giri su 14). L'obiettivo è scendere sotto 0,12.

## Cosa non cambia
Il significato: stessi fatti, stessi numeri, stessi segnaposti (`{v}`, plurali `{n|giro|giri}`, tag HTML). Nessuna affermazione nuova. Se un testo vecchio afferma qualcosa che la schermata non mostra, correggilo e scrivilo nel report. Prima di riscrivere una frase guarda dove compare (titolo accanto, bottoni, lista che segue), così non ripete il titolo e si legge al suo posto.

## Errori già trovati dalla revisione (non rifarli)
- Il trattino a effetto travestito: «X, col Y» («Dove stai perdendo, col tratto in evidenza»), le parentesi usate al posto della lineetta in una frase, «X: Y» trasformato in «X Y» senza verbo.
- Frammenti senza verbo nelle frasi descrittive («Per esempio un'alzata dove…»). Le etichette brevi (titoli, bottoni, intestazioni) restano invece sostantivi o verbi, senza due punti.
- Troppe frasi brevissime di fila: diventa uno staccato meccanico. Breve non vuol dire telegrafico.
- Parole da ufficio: «in modo significativo», «coppia» per auto e pista, «procedere», «effettuare».
- Una frase che, tolti i due punti, si fonde con la lista o coi bottoni che seguono: va chiusa col punto («Hai messo da parte questi consigli.»).
- Affermazioni assolute dove il programma ha solo cercato: «non ho trovato errori», non «non ci sono errori».
- In inglese: costruzioni assolute penzolanti («…, this stretch highlighted»), «a significant amount of».

## Come si verifica
`tests/tono.py` + `tests/test_tono.py`: togli la tua superficie da `PENDING` e lavora finché è verde. I test che fissano il testo esatto si aggiornano; quelli che controllano un significato restano.
Nel report: una tabella prima → dopo delle frasi più lette (italiano e inglese).
