# Guide scritte al setup GT3 su ACC (1.9 / 1.10) — rapporto di ricerca

Data della ricerca: 15/11/2026. Scopo: materiale operativo per un algoritmo che suggerisce modifiche di setup in sessione.

**Come leggere i numeri.** Ogni numero porta una sigla fra parentesi quadre (es. `[ARIS19]`): l'URL corrispondente è nell'elenco fonti al §8. Dove un numero non è stato trovato in nessuna fonte c'è scritto «non trovato». Le date e gli autori sono quelli letti sulle pagine; non sono stati verificati altrove.

**Limiti di questa ricerca (da sapere prima di usarla).**

- **Il forum Kunos (assettocorsa.net) non è stato raggiunto**: i motori di ricerca non hanno restituito nessun post originale di Aristotelis Vasilakos. Di suo ho letto per intero solo il PDF «Version 1.9 – Physics notes» `[ARIS19]`. Le altre sue posizioni arrivano di seconda mano (riassunti di terzi) e sono segnate come tali.
- **La serie di Aris sul setup è in video** («7 steps to a custom setup», «Talk & Drive» sugli ammortizzatori). Le trascrizioni non sono state lette (manca la chiave del servizio trascrizioni). Ho usato il riassunto scritto di Trinacria Simracing `[TRIN-7]`.
- **Non accessibili**: simracingsetup.com (verifica anti-bot: usati solo gli estratti dei risultati di ricerca, segnati `[SRS]`), acc-wiki.info (dominio non risolto), overtake.gg (403, compreso il blog Kunos «Suspension and Setups»), support.gosetups.gg (403).
- **Ohne Speed, LFM, SimGrid**: nessuna guida scritta al setup trovata (Ohne Speed pubblica in video).
- **Versione 1.10**: nessuna fonte trovata descrive cambi di fisica o di finestra pressioni rispetto alla 1.9. Tutte le guide «attuali» ripetono i valori 1.9. Non è una conferma che nulla sia cambiato: è assenza di fonti.
- **Passo in click**: quasi nessuna guida dà un passo numerico. È la lacuna più grossa per l'algoritmo; vedi §6.

---

## 1. Fonti e peso

| Sigla | Fonte | Autore | Data letta | Peso | Nota |
|---|---|---|---|---|---|
| `[ARIS19]` | «Version 1.9 – Physics notes» (PDF Kunos) | Aristotelis Vasilakos, responsabile fisica Kunos | aprile 2023 | **Massimo** (fonte primaria) | Unica fonte dell'autore della fisica letta per intero. Copre pressioni, temperature, toe/camber, bumpstop, molle, ammortizzatori, TC. |
| `[CDA-FAQ19]` | «V1.9 Coach Dave Academy ACC FAQ» | James Parker (capo setup CDA) | 19/04/2023 | Alto | Coerente con `[ARIS19]`, aggiunge indicazioni pratiche. CDA vende setup. |
| `[CDA-GUIDE]` | «The ultimate ACC car setup guide» | Simon Baggus | pagina datata 2026 | Medio-alto | Completa ma qualitativa; contiene **contraddizioni interne** (vedi §5). |
| `[CDA-PSI]` | «How to set the correct tyre pressures in ACC» | Rudra Mehta, ed. Grant Campbell | 18/01/2021, aggiornata | Medio | Contraddizioni interne sulla finestra. |
| `[CDA-OSUS]` | «How to fix oversteer and understeer in ACC» | Coach Dave (David Perel, pilota GT) | 19/10/2020, aggiornata | Medio-alto per le liste; **pre-1.9** | La lista ammortizzatori contraddice il testo dello stesso articolo. |
| `[CDA-FAQ18]` | «Coach Dave Academy FAQ – V1.8» | Coach Dave | 02/12/2021 | Medio (pre-1.9) | Unica con finestre freni per pastiglia. |
| `[CDA-PADS]` | «Brake pads in ACC» | Simon Baggus | 12/02/2021, aggiornata | Medio | |
| `[CDA-WET]` | «ACC wet tyre pressures: myth or meta» | James Parker | 08/12/2023 | Medio-alto (dati MoTeC, campione piccolo) | Contraddice la finestra bagnato «ufficiale». |
| `[CDA-720EVO]` | «ACC McLaren 720S GT3 Evo guide» | Vitaly Mikhalchuk | 17/08/2023 | Medio-alto | Unica guida scritta specifica sulla Evo. |
| `[CDA-720]` `[CDA-M4]` `[CDA-AMG]` `[CDA-296]` `[CDA-991]` `[CDA-FAST]` | Guide per auto CDA | Cav Budd, Grant Campbell, Vinodh Moodley, Sean Greene, Simon Baggus | 2021–2026 | Medio | Usate per il confronto fra architetture. |
| `[D61]` `[D61-PDF]` | Driver61 «ACC setup guide» + cheat sheet PDF V1 | Scott Mansell (pilota e coach) | 17/03/2021 (agg. 22/04/2025) | Medio per le tabelle; **numeri di pressione superati (pre-1.9)** | La tabella sintomo→rimedio più completa trovata. |
| `[TROPHI]` | «Why tyre pressures are crucial in ACC» | team trophi.ai + Driver61 | 18/10/2025 | Medio | Aggiornata alla 1.9. |
| `[SOLOX]` | «ACC tyre pressure guide» | Alessio Lorandi (ex pilota) | agg. 05/10/2026 | Medio | Recente, con esempio numerico freddo→caldo. |
| `[TRAX-PSI]` `[TRAX-BASE]` | Traxion | Ross McGregor | marzo–aprile 2021 | Basso-medio (pre-1.9) | Utile solo per la regola temperatura pista. |
| `[TRIN-7]` | «ACC: how to customize the car setup in seven steps» | Trinacria Simracing (riassunto della serie video di Aris) | ~2022 | Medio-alto come contenuto (è Aris di seconda mano) | Pre-1.9. |
| `[TRIN-BEG]` | «ACC beginner setup guide» | Trinacria Simracing, da Skaven Zverov | versione 1.9 | Medio | Aggregatore; ha numeri che altri non danno. |
| `[DRS-IT]` | «Guida al Setup» (italiano) | forum DRS Team Italia, da Skaven Zverov / simracingsetup | 11/09/2020 | Basso-medio (pre-1.9) | Unica guida italiana trovata; è una traduzione. |
| `[FGM]` | «Damper settings guide» | Full Grip Motorsport (autore non indicato) | n.d. | Basso | Unica con passi in click per gli ammortizzatori; autorevolezza non verificabile. |
| `[BDR]` | «All about the tires in ACC» | Blue Dragon Racing | 17/07/2026 | Basso | Usa ancora 27.3–27.8 (finestra pre-1.9) e si contraddice. |
| `[HOEK]` | «Front engine car preset explained» | Arnout Hoekstra | n.d. | Basso (dichiara di «imparare in pubblico») | |
| `[STEAM]` | discussione Steam «Ideal tyre temps for 1.9?» | utenti | 03/05/2023 | Basso | Nessuno sviluppatore. |
| `[SRS]` | simracingsetup.com (solo estratti di ricerca) | Rich (autore del sito) | n.d. | Basso finché non letta per intero | |

---

## 2. Tabella per regolazione

Legenda fasi: **F** = ingresso in frenata, **R** = rilascio/inserimento, **C** = centro curva, **U** = uscita in trazione. «Sotto» = sottosterzo, «sovra» = sovrasterzo.

### 2.1 Pressioni gomme

| Voce | Valore | Fonte |
|---|---|---|
| Finestra a caldo, asciutto (1.9+) | 26–27 psi, «indicativa»: non c'è più un picco netto a 26.5 come prima | `[ARIS19]` |
| idem | 26.0–27.0 per tutte le classi | `[CDA-FAQ19]` `[CDA-GUIDE]` `[TROPHI]` `[SOLOX]` `[TRIN-BEG]` |
| idem (valori discordanti) | 26–27.2 in tabella e 26.5–27.5 nelle FAQ della stessa pagina | `[CDA-PSI]` |
| idem (discordante) | 26.5–27.5 nelle FAQ, contro 26.0–27.0 nella tabella della stessa pagina | `[CDA-GUIDE]` |
| idem (discordante) | 26.4–27.0 (solo estratto di ricerca, pagina non letta) | `[GOSET]` |
| Finestre **superate** (pre-1.9) ancora in giro | 27.3–27.8 (DHE 2020) `[TROPHI]`; 27.3–28 `[D61]`; 27.3–27.9 `[CDA-FAQ18]` `[TRAX-BASE]`; 27.3–27.8 riproposta nel 2026 da `[BDR]` | |
| Obiettivo pratico | circa 26.5 | `[SOLOX]`; «26.5 buon compromesso» `[STEAM]` |
| Finestra a caldo, bagnato | 30.0–31.0 `[CDA-GUIDE]` `[SOLOX]`; 29.5–31.0 `[TROPHI]` `[TRAX-PSI]` `[TRIN-BEG]` e tabella di `[CDA-PSI]`; 29.5–30.5 nelle FAQ di `[CDA-PSI]`; «30 psi» `[CDA-FAQ18]` | |
| Bagnato, posizione contraria | 35 psi (il massimo) sempre: più veloce di 30 psi in tutti gli stati di pista provati, da −0.31 s a −1.72 s al giro | `[CDA-WET]` |
| Bagnato, limite basso | le gomme da bagnato lavorano «da circa 28.5 psi» (attribuito a un post di uno sviluppatore Kunos, non letto in originale) | `[TRIN-BEG]` |
| Effetto del verso | Pressione più bassa: più flessione, trazione, movimento, più calore, meno precisione, **più rotazione**. Più alta: più sostegno laterale, precisione, meno calore | `[ARIS19]` |
| Per velocità | Curva veloce ad alto carico → pressione più alta. Curva lenta → pressione più bassa (rotazione e trazione) | `[ARIS19]` |
| Differenza fra assi | Si può usare per stabilizzare o far ruotare: meno pressione dietro = più imbardata. «Bastano 0.5° di rotazione in più per cambiare del tutto la curva» | `[ARIS19]` |
| idem (posizione diversa) | Tenere anteriore e posteriore il più vicini possibile, altrimenti l'auto è meno prevedibile | `[CDA-FAQ19]` `[CDA-296]` |
| Con aria più calda | −0.1 psi a freddo per ogni +1 °C di aria | `[CDA-PSI]` `[TROPHI]` `[SOLOX]` `[TRIN-BEG]` |
| Con pista più calda | 0.1–0.2 psi per 1 °C di pista; la tabella dell'autore mostra circa 0.1 psi ogni 2 °C | `[TRAX-PSI]` (pre-1.9; formulazione ambigua sul verso) |
| idem (fonte debole, incoerente) | pista <20 °C: +0.2–0.3 a freddo; >30 °C: −0.2–0.3; e altrove «0.25 psi per 10 °C» contro «+0.7 psi per +10 °C» | `[BDR]` |
| Un click di condotto freni | 0.2 psi di pressione a caldo (0.3 fra 2 e 3) | `[TRIN-BEG]` — ma `[CDA-FAQ18]` dice che dalla 1.8 i condotti hanno «effetto minimo» sulle gomme. Da misurare. |
| Quanti psi a caldo vale un click a freddo | **non trovato** come regola. `[SOLOX]`: una variazione a freddo produce «quasi la stessa» variazione a caldo. `[BDR]`: muoversi a passi di 0.1–0.2 psi | |
| Salita freddo→caldo (esempio) | AS 25.0→27.4 (+2.4), AD 25.0→26.9 (+1.9), PS 24.8→26.6 (+1.8), PD 24.8→26.1 (+1.3) | `[SOLOX]` (un solo esempio) |
| Temperatura di partenza | circa 65 °C all'uscita box | `[CDA-GUIDE]` |
| Giri per stabilizzarsi | 2–3 (GT3, termocoperte) `[TROPHI]`; minimo 3 `[CDA-PSI]`; 3–4 `[TRAX-BASE]`; 4–5 `[SOLOX]`; fino a 5 `[CDA-FAQ18]`; in qualifica leggere dopo il giro 2 `[SOLOX]` | |
| Costo dell'errore | 1 psi fuori = 5–6 decimi al giro | `[CDA-PSI]` |
| Effetti collaterali | Bassa: più usura `[STEAM]`, più sterzo necessario, feedback diverso `[ARIS19]`. Alta: meno consumo carburante `[D61-PDF]` | |

### 2.2 Temperature gomme

| Voce | Valore | Fonte |
|---|---|---|
| Finestra (nucleo) | 70–100 °C | `[ARIS19]` `[CDA-FAQ19]` |
| Punto ideale | nucleo stabile a 80–90 °C | `[ARIS19]` `[CDA-GUIDE]` `[SOLOX]` |
| Superficie | da 50 °C in rettilineo a 120 °C e oltre in curva: normale | `[ARIS19]` |
| Sotto 70 / sopra 100 | graining / blistering | `[CDA-GUIDE]` |
| Lettura O-M-I | Dalla 1.9 i valori OMI della schermata setup sono vicini alla superficie; si possono leggere ai box o premendo ESC a metà curva | `[ARIS19]` |
| Scarto massimo esterno–interno | 15 °C | `[ARIS19]` `[CDA-FAQ19]` `[CDA-PSI]` |
| idem (discordante) | 9 °C davanti e 5 °C dietro (o 9 e 9) | `[CDA-GUIDE]` `[TRIN-BEG]` — verosimilmente residuo pre-1.9 |
| idem | 10–15 °C `[TROPHI]`; 5–8 °C `[BDR]` | |
| Esempi di Aris, in rettilineo | 0° camber e 0 toe: 90-90-90; −3.5° con toe positivo: 88-95-100; −3.5° con toe negativo: 60-90-105 | `[ARIS19]` |
| Esempi di Aris, in curva | 110-100-98; 95-98-100; 67-100-105 (stesse tre configurazioni) | `[ARIS19]` |
| Interno surriscaldato | meno pressione, toe verso 0 `[D61-PDF]`; camber meno negativo `[D61]` | |
| Esterno surriscaldato | più pressione, toe verso 0, più camber negativo | `[D61-PDF]` `[D61]` |
| Centro surriscaldato | meno pressione | `[D61]` |
| Tutto surriscaldato | più pressione, meno toe, meno caster, più TC, più condotti freni | `[D61-PDF]` |
| Tutto freddo | meno pressione, più toe, meno TC, meno condotti | `[D61-PDF]` |

Nota: `[CDA-FAQ19]` avverte che dopo la 1.9 il bordo esterno può apparire blu per il nuovo modello di camber: non è per forza un difetto.

### 2.3 Camber

| Voce | Contenuto | Fonte |
|---|---|---|
| Verso → effetto | Più negativo: più appoggio nelle curve ad alto carico; temperatura meno uniforme (interno caldo) | `[CDA-GUIDE]` |
| Fase | Più negativo davanti riduce il sotto in ingresso e a centro curva | `[TRIN-7]` `[D61-PDF]` |
| Dietro | Più negativo dietro riduce il sovra (ingresso, centro, uscita) `[D61-PDF]`; ma **meno** camber dietro aiuta la trazione sulle piste con molte zone di trazione `[CDA-FAQ19]` e il pattinamento a bassa velocità `[D61-PDF]` | |
| 1.9 | Il massimo camber ovunque non è più la scelta migliore; valori estremi con toe negativo surriscaldano l'interno e lasciano freddo l'esterno, peggiorando frenata e primo inserimento | `[ARIS19]` `[CDA-FAQ19]` |
| Effetti collaterali | Troppo: instabilità posteriore in frenata, tramlining, spalla interna calda | `[CDA-FAQ18]` |
| Passo | Per la gara 0.3–0.6° in meno rispetto alla qualifica | `[CDA-FAQ18]` (pre-1.9) |
| Passo in click | non trovato | |

### 2.4 Toe

| Voce | Contenuto | Fonte |
|---|---|---|
| Anteriore positivo (toe-in) | Più stabilità in ingresso, più sotto in percorrenza | `[CDA-GUIDE]` `[DRS-IT]` |
| Anteriore negativo (toe-out) | Più reattivo, più sovra; in eccesso sterzo vago al centro | `[CDA-GUIDE]` `[ARIS19]` |
| Posteriore positivo | Stabilità, meno sovra in inserimento e centro; costa resistenza e velocità di punta | `[CDA-OSUS]` |
| Posteriore meno positivo | Più rotazione, più velocità; rischio pattinamento e surriscaldamento posteriori | `[CDA-OSUS]` |
| Posteriore negativo | Sconsigliato; può far scodare in frenata | `[CDA-GUIDE]` `[ARIS19]` |
| 1.9 | La nuova fisica ruota di più, soprattutto in accelerazione: il toe negativo «non è più necessario» | `[ARIS19]` |
| Campo consigliato | provare fra 0 e −0.2 davanti e dietro; alcune auto vogliono valori più vicini a 0 | `[CDA-FAQ19]` |
| Effetti collaterali | Toe eccessivo: più usura su stint lungo `[CDA-FAQ19]`, più calore `[D61-PDF]`, meno velocità di punta `[D61-PDF]` | |

### 2.5 Caster

| Voce | Contenuto | Fonte |
|---|---|---|
| Più caster | Più camber dinamico in sterzata, sterzo più pesante, più stabilità; buono in inserimento | `[CDA-GUIDE]` |
| Limite | Troppo: sotto a centro curva nelle curve veloci. Regola: tenerlo alto finché non compare sotto in una curva veloce, poi ridurre | `[CDA-GUIDE]` `[DRS-IT]` |
| Tabella Driver61 | «Più caster» è rimedio per il sotto in tutte e tre le fasi e per l'auto instabile; «meno caster» per gomme surriscaldate e degrado | `[D61-PDF]` |
| Passo | non trovato | |

### 2.6 Barre antirollio

| Voce | Contenuto | Fonte |
|---|---|---|
| Principio | Non creano grip: spostano la ripartizione del carico. Effetto massimo a regime, a centro curva | `[CDA-OSUS]` |
| Anteriore più rigida | Più sotto / meno sovra; l'anteriore rolla meno | `[CDA-OSUS]` |
| Anteriore più morbida | Meno sotto in ingresso | `[CDA-GUIDE]` `[DRS-IT]` |
| Posteriore più rigida | Più sovra, più nervosa; protegge l'altezza del diffusore e stabilizza l'aerodinamica | `[CDA-OSUS]` `[TRIN-7]` |
| Posteriore più morbida | Meno sovra in uscita, meno pattinamento | `[CDA-GUIDE]` `[D61-PDF]` |
| Effetti collaterali | Posteriore rigida: meno grip meccanico dietro e gomme posteriori più calde `[TRIN-7]`. Barre morbide: meglio sui cordoli `[CDA-AMG]` | |
| 1.9 | Le barre rigide hanno un effetto più marcato; provare barre molto rigide per vedere come l'auto regge i carichi prolungati | `[CDA-FAQ19]` |
| Passo | non trovato | |

### 2.7 Wheel rate (molle)

| Voce | Contenuto | Fonte |
|---|---|---|
| Anteriore più rigida | Meno beccheggio in frenata → meno sovra in frenata; meno sovra nel veloce | `[CDA-OSUS]` |
| Anteriore più morbida | Meno sotto nel lento e in frenata | `[CDA-OSUS]` |
| Posteriore più rigida | Meno sotto nel veloce; troppo: nervosa in trazione e sui cordoli d'uscita del lento | `[CDA-OSUS]` |
| Posteriore più morbida | Meno sovra nel lento, più trazione; troppo: pigra nel veloce | `[CDA-OSUS]` |
| Tutto più morbido | Più trazione dal lento, ma meno risposta nei cambi di direzione, sovra in ingresso a media-alta velocità, auto nervosa | `[TRIN-7]` |
| 1.9 | Molle troppo morbide portano il tampone a fine corsa: l'energia passa al telaio, che flette senza smorzamento, e si perde grip meccanico. Molle più rigide: meno beccheggio e rollio, aerodinamica più stabile, meno stress termico sulle gomme | `[ARIS19]` |
| Eccezione | Monza: può ancora convenire morbido per stare bassi. Sintomi di troppo morbido: saltellamento laterale in curva, comportamento imprevedibile sui cordoli | `[ARIS19]` |
| Passo | «uno o due click» per la trazione nel lento | `[TRIN-7]` |

### 2.8 Bumpstop (rate e range)

| Voce | Contenuto | Fonte |
|---|---|---|
| Corsa massima | 20–30 mm, poi la sospensione si ferma | `[ARIS19]` |
| Range anteriore più corto | Limita il beccheggio in frenata: più stabilità, piattaforma aerodinamica ferma | `[CDA-OSUS]` `[TRIN-7]` |
| Range anteriore più lungo | Più beccheggio: meno sotto in frenata e nel veloce (con rate più rigido) | `[CDA-OSUS]` |
| Range posteriore | Di norma alto: toccare spesso il tampone in accelerazione dà porpoising e sovra. Ridurlo aiuta il sotto in uscita | `[CDA-OSUS]` |
| Range posteriore più lungo (1.9) | Può ridurre il comportamento brusco in trazione, ritardando il passaggio di energia al telaio | `[CDA-FAQ19]` |
| Range più lungo + altezza anteriore ritoccata | Migliora il comportamento sui cordoli | `[CDA-FAQ19]` |
| Rate più morbido | Reazione più dolce a fine corsa; rimedio per sovra a centro curva e in uscita e per auto instabile | `[CDA-GUIDE]` `[D61-PDF]` |
| Due filosofie (1.8) | (a) poco rake, range alto, rate rigido; (b) rate morbido, range basso, un po' più di rake | `[CDA-FAQ18]` |
| Lettura | Nel widget: gialla = posizione, rossa = contatto col tampone, verde = estensione massima | `[CDA-GUIDE]` `[TRIN-7]` |
| Per auto | AMG: range posteriore quasi a zero per ruotare nel lento e medio `[CDA-AMG]`. 720S Evo: ridurre i range per togliere sovra nei cambi di direzione `[CDA-720EVO]` | |
| Passo | non trovato | |

### 2.9 Ammortizzatori

| Voce | Contenuto | Fonte |
|---|---|---|
| Lento vs veloce | Lento = trasferimenti di carico (frenata, rollio, accelerazione). Veloce = cordoli, dossi, ondulazioni | `[CDA-GUIDE]` `[ARIS19]` |
| 1.9 | Lo smorzamento lento ora cambia sensibilmente la guida. Valori **minimi o massimi** di bump/rebound lento possono provocare jacking ed effetti indesiderati | `[ARIS19]` |
| Regola generale | Rebound sempre più alto del bump | `[TRIN-BEG]` `[DRS-IT]`; rebound = 1.3–1.5 × bump `[FGM]` |
| Troppo bump | Compressione dura, resiste al rollio | `[CDA-OSUS]` |
| Poco bump | Troppo affondamento e rollio | `[CDA-OSUS]` |
| Troppo rebound | Le ruote interne perdono contatto | `[CDA-OSUS]` |
| Poco rebound | L'auto oscilla a lungo dopo i dossi, fatica in trazione | `[CDA-OSUS]` |
| Inserimento (R) | Bump lento anteriore più morbido + rebound lento anteriore più rigido = più grip in inserimento | `[CDA-720EVO]` (post-1.9); `[FGM]` concorda sul bump |
| Frenata (F) | Bump anteriore e rebound posteriore più rigidi = più stabilità | `[CDA-AMG]` (via estratto) |
| Uscita (U) | Rebound lento posteriore più rigido contro il sovra in uscita | `[FGM]` |
| Cordoli | Meno fast bump e meno fast rebound `[D61-PDF]`; oppure meno fast bump e **più** fast rebound `[DRS-IT]` (contraddizione) | |
| Per auto | AMG instabile sui cordoli: +3–4 click di smorzamento posteriore | `[CDA-AMG]` |
| Passo | 1 click alla volta `[FGM]`; 3–4 click `[CDA-AMG]` | |
| Soglia lento/veloce | circa 50 mm/s | `[FGM]` (fonte debole) |
| Valori di partenza | bump lento 6–10, fast bump 3–5, rebound lento 8–12, fast rebound 4–6 (pista liscia) | `[FGM]` (fonte debole, non per auto) |
| Bagnato | ridurre tutto del 20–30% | `[FGM]` (fonte debole) |

**Attenzione:** sul verso degli ammortizzatori le fonti si contraddicono apertamente (§5.4). È l'area meno affidabile di tutto il rapporto.

### 2.10 Altezze da terra e rake

| Voce | Contenuto | Fonte |
|---|---|---|
| Posteriore più alto (più rake) | Centro di pressione in avanti → più sovra / meno sotto; migliora inserimento e rotazione | `[CDA-OSUS]` `[TRAX-BASE]` |
| Posteriore più basso | Più stabilità, meno sovra in ingresso | `[CDA-OSUS]` |
| Anteriore più basso | Meno sotto: effetto aerodinamico grande. Il posteriore è la regolazione fine | `[TRIN-7]` |
| Per velocità | Sotto nel lento → alzare il posteriore. Sotto nel veloce → meno ala | `[CDA-OSUS]` |
| Tutto più basso | Più carico dal fondo; rischio di toccare su piste sconnesse | `[CDA-GUIDE]` `[TRAX-BASE]` |
| 1.9 | Il guadagno di grip meccanico con corsa utile supera di solito il guadagno di resistenza dello stare bassissimi (salvo Monza) | `[ARIS19]` |
| Eccezione BMW M4 | Oltre una certa differenza di rake il bilanciamento torna indietro: più rake rende l'auto più sicura | `[CDA-M4]` |
| Ferrari 296 | Rake sotto 20 mm contro il sovra improvviso | `[CDA-296]` |
| Passo in mm | non trovato | |

### 2.11 Splitter

| Voce | Contenuto | Fonte |
|---|---|---|
| Più splitter | Più carico davanti: meno sotto, più sovra; va regolato insieme all'ala | `[CDA-GUIDE]` |
| Effetti collaterali | Meno stabilità posteriore e più resistenza | `[CDA-720EVO]` `[CDA-296]` |
| Indicatore | «Front aero variation» nella schermata: alzarlo finché la stabilità posteriore comincia a calare | `[TRIN-BEG]` `[DRS-IT]` |
| Passo | non trovato | |

### 2.12 Ala posteriore

| Voce | Contenuto | Fonte |
|---|---|---|
| Più ala | Più carico dietro: meno sovra, più sotto, soprattutto nel veloce; più resistenza | `[CDA-GUIDE]` `[CDA-OSUS]` |
| Meno ala | Rimedio per sotto nel veloce; più velocità di punta | `[CDA-OSUS]` |
| Trazione | Più ala aiuta dove si accelera sterzando a media-alta velocità | `[TRAX-BASE]` |
| Costo per click | Dipende dall'auto: sulla M4 costa poco `[CDA-M4]`; km/h per click **non trovato** | |
| Metodo | Per capire l'effetto, fare un salto grande (es. da 3 a 8) e poi tornare indietro | `[D61]` |

### 2.13 Condotti freni e temperature freni

| Voce | Valore | Fonte |
|---|---|---|
| Scala | 0 (chiusi) – 6 (aperti) | `[CDA-PADS]` |
| Chiusi | I freni arrivano a 1000 °C in fretta: mai in gara | `[CDA-PADS]` `[TRIN-BEG]` |
| Obiettivo dischi | davanti 600–650 °C, dietro 450 °C | `[CDA-GUIDE]` |
| idem | picco davanti ≤600 °C, dietro ≤450 °C; fading se l'anteriore supera regolarmente 600 o il posteriore arriva a 520 | `[CDA-FAQ18]` |
| Finestra pastiglia 1 | davanti 300–600 °C, dietro 260–450 °C | `[CDA-FAQ18]` |
| Finestra pastiglia 2 | davanti 300–600 °C, dietro 200–450 °C | `[CDA-FAQ18]` |
| idem (discordante) | davanti 300–700 °C, dietro 300–600 °C | `[TRIN-BEG]` |
| Effetto sulle gomme | «minimo» dalla 1.8 `[CDA-FAQ18]`; ma `[CDA-FAQ19]` dice di usarli per tenere in finestra il nucleo, e `[TRIN-BEG]` dà 0.2 psi per click | |
| Effetti collaterali | Più aperti: più resistenza, meno velocità di punta; cambiano un po' il bilanciamento aerodinamico | `[CDA-GUIDE]` `[CDA-PADS]` |
| Regola | Pista veloce: più chiusi. Pista tecnica o caldo: più aperti. Pioggia: più chiusi | `[CDA-GUIDE]` `[DRS-IT]` |
| Pastiglie | 1: sprint, durata realistica 90–120 min. 2: endurance, fino a 12 ore. 3: bagnato. 4: solo dimostrativa | `[CDA-PADS]` |

### 2.14 Ripartizione di frenata

| Voce | Contenuto | Fonte |
|---|---|---|
| Più avanti | Più stabilità in frenata, più sotto in ingresso | `[CDA-GUIDE]` |
| Più indietro | Più rotazione in ingresso, meno stabilità, sovra in ingresso | `[CDA-GUIDE]` `[CDA-AMG]` |
| In gara | Si ritocca mentre benzina e gomme cambiano il bilanciamento | `[CDA-GUIDE]` |
| Bloccaggi / freni caldi | Spostare la ripartizione lontano dalle ruote che bloccano o scaldano | `[D61-PDF]` |
| Ordini di grandezza (generici, non ACC) | motore anteriore fino a 60-40; motore centrale circa 56-44 … 59-41 | `[CDA-PADS]` |
| Esempio | Bentley: sopra 64% davanti come partenza | `[TRAX-BASE]` |
| Passo | «variazioni piccole»; numero non trovato | `[TRIN-BEG]` |

### 2.15 Precarico del differenziale

| Voce | Contenuto | Fonte |
|---|---|---|
| Cosa si regola | Solo il precarico (le rampe sono fisse per omologazione) | `[CDA-GUIDE]` `[TRIN-7]` |
| Più basso | Più agile in ingresso, più sotto in uscita, erogazione più lineare | `[CDA-GUIDE]` `[TRIN-7]` |
| Più alto | Più stabile in ingresso, più sovra in uscita, meno trazione, erogazione meno lineare | `[CDA-GUIDE]` `[TRIN-7]` |
| Curve lente (da Aris, seconda mano) | Basso: agile e stabile in frenata, meno trazione. Alto: sotto al rilascio, più trazione ma sovra in potenza | `[TRIN-7]` |
| Curve veloci (da Aris, seconda mano) | Basso: agile e stabile. Alto: sotto sia al rilascio sia in potenza | `[TRIN-7]` |
| Per marcia | Alto: più sovra a centro curva nelle marce basse, più sotto in uscita nelle marce alte | `[TRIN-BEG]` |
| Esempio numerico | 170 Nm contro 100 Nm (Ferrari 488) | `[TRIN-7]` |
| Passo | non trovato | |

### 2.16 TC1, TC2, ABS, mappa motore, rapporto di sterzo

| Regolazione | Contenuto | Fonte |
|---|---|---|
| TC1 | Soglia di slittamento prima del taglio | `[CDA-GUIDE]` `[CDA-720EVO]` |
| TC2 | Quanta potenza viene tolta quando TC1 interviene; utile contro il sovra in curve specifiche | `[CDA-GUIDE]` `[CDA-720EVO]` |
| TC1/TC2 (definizione opposta) | Sulla Porsche 991: TC1 = «taglio», TC2 = «slittamento» | `[CDA-991]` |
| Regola | Tenere TC1 e TC2 entro ±1 l'uno dall'altro | `[CDA-GUIDE]` `[TRIN-BEG]` |
| Con la pista | Più TC su pista verde, scendere mentre si gomma | `[CDA-296]` |
| 1.9 | La nuova logica TC su varie auto moderne permette più controllo dello slittamento; arma a doppio taglio: rischio di perdere l'auto in accelerazione e usura eccessiva | `[ARIS19]` |
| Effetti | Più TC: meno sovra in uscita, gomme più calde secondo `[D61-PDF]` (lo mette anche fra i rimedi per gomme fredde: «meno TC» raffredda); meno TC: più accelerazione | `[D61-PDF]` |
| Esempio | AMG: TC fra 1 e 3, ABS partire da 2 | `[CDA-AMG]` |
| ABS | Più alto: più stabilità, si frena più tardi ma lo spazio si allunga. Più basso: spazio più corto, meno stabilità. Partire alto e scendere | `[CDA-GUIDE]` |
| ABS su pista sconosciuta | portarlo da 3 a 6 | `[TRIN-7]` |
| Mappa motore | Numero più basso = più potenza e più consumo (con eccezioni, es. Porsche); mappe da asciutto, da bagnato e pace car | `[CDA-GUIDE]` `[TRIN-BEG]` |
| Rapporto di sterzo | Esempio 15:1; numero più alto = sterzo meno reattivo; raramente da toccare | `[CDA-GUIDE]` `[DRS-IT]` |
| Sterzo troppo sensibile | meno toe, meno camber davanti, più caster | `[D61-PDF]` |

---

## 3. Tabelle «sintomo → rimedi»

### 3.1 Driver61 — cheat sheet PDF `[D61-PDF]` (2021, pre-1.9)

Ricostruita dall'estrazione testuale del PDF; l'ordine è quello di stampa dall'alto in basso. **Due righe sembrano refusi dell'originale** e sono segnate con (?): compaiono identiche sotto «sottosterzo» e «sovrasterzo».

| Fase | Sottosterzo | Sovrasterzo | Instabile |
|---|---|---|---|
| **Ingresso** | 1. meno pressione anteriore · 2. più toe-out · 3. più camber anteriore · 4. più caster · 5. meno barra ant. o più barra post. · 6. ripartizione più indietro · 7. meno wheel rate ant. · 8. **più** precarico · 9. più bump ant. · 10. più rebound ant. · 11. meno altezza ant. o più altezza post. | 1. meno pressione posteriore · 2. meno toe-out ant. · 3. più camber post. · 4. meno barra ant. o più barra post. (?) · 5. più TC · 6. meno wheel rate post. o più ant. · 7. ripartizione più avanti · 8. meno precarico · 9. meno bump post. · 10. meno rebound post. · 11. meno altezza ant. o più post. (?) | meno pressione post. · meno toe · più camber · più caster · ripartizione più avanti · più range bumpstop · meno wheel rate · meno altezza |
| **Centro** | 1. meno pressione ant. · 2. più toe-out · 3. più camber ant. · 4. più caster · 5. meno barra ant. o più post. · 6. meno wheel rate ant. · 7. più bump ant. · 8. più rebound ant. · 9. meno altezza ant. o più post. · 10. più splitter | 1. meno pressione post. · 2. meno toe-out ant. · 3. più camber post. · 4. (?) · 5. più TC · 6. meno wheel rate post. o più ant. · 7. meno barra post. · 8. meno rate bumpstop · 9. più range bumpstop post. · 10. meno precarico · 11. meno bump post. · 12. meno rebound post. · 13. (?) · 14. più ala | meno pressione post. · meno toe · più camber · più caster · meno rate bumpstop · più range bumpstop · meno wheel rate · meno altezza · più ala · più splitter |
| **Uscita** | 1. meno pressione ant. · 2. più caster · 3. meno barra ant. o più post. · 4. più bump ant. · 5. più rebound ant. · 6. meno altezza ant. o più post. · 7. più splitter | 1. meno pressione post. · 2. più camber post. · 3. (?) · 4. più TC · 5. meno wheel rate post. o più ant. · 6. meno barra post. · 7. meno rate bumpstop · 8. meno precarico · 9. (?) · 10. più ala | meno pressione post. · meno toe · più camber · più caster · più TC · più range bumpstop · meno wheel rate · meno altezza · più ala e più splitter |

Altre voci dello stesso foglio:

| Sintomo | Rimedi nell'ordine di stampa |
|---|---|
| Accelerazione lenta | meno TC · mappa motore più alta · meno precarico · più bump post. · meno ala · meno splitter · meno condotti |
| Velocità di punta bassa | più pressione · toe verso 0 · camber meno negativo · mappa più alta · meno ala · meno splitter · meno condotti |
| Pattinamento a bassa velocità | meno pressione post. · camber post. verso 0 · più TC · meno barra post. · meno precarico |
| Sterzo troppo sensibile | meno toe davanti e dietro · camber ant. verso 0 · più caster · «ridurre il rapporto di sterzo» (così nell'originale) |
| Instabile in generale | meno pressione · più TC · meno rate bumpstop · più range bumpstop · meno fast bump · meno fast rebound · meno altezza · più ala · più splitter |
| Striscia / tocca il fondo | più wheel rate · più rate bumpstop · più range bumpstop · più altezza |
| A disagio sui cordoli | meno wheel rate · meno rate bumpstop · più range bumpstop · meno fast bump · meno fast rebound |
| Bloccaggi | più ABS · meno pressione freni (sconsigliato) · ripartizione lontano dalle ruote che bloccano |
| Instabile in frenata | toe verso 0 · più ABS · meno pressione freni (sconsigliato) · ripartizione più avanti · meno bump · più ala · più splitter |
| Frenata più potente | meno ABS · pastiglie 4 · pressione freni al massimo · più ala · più splitter |
| Usura freni eccessiva | più ABS · pastiglie 2 o 3 · meno condotti · meno pressione freni · ripartizione lontano dalle ruote che bloccano |
| Freni troppo caldi | più ABS · pastiglie 2 o 3 · più condotti · meno pressione freni · ripartizione lontano dalle ruote calde |
| Gomme surriscaldate | più pressione · toe verso 0 · meno caster · spostare la ripartizione · più TC · più condotti |
| Gomme fredde | meno pressione · più toe · meno TC · spostare la ripartizione · meno condotti |
| Bordo interno caldo | meno pressione · toe verso 0 |
| Bordo esterno caldo | più pressione · toe verso 0 · più camber |
| Temperature gomme in salita (gara) | più pressione · più TC |
| Temperature gomme in discesa | meno pressione · meno TC |
| Degrado gomme eccessivo | toe verso 0 · meno caster · meno pressione · meno TC |
| Consumo carburante alto | più pressione · mappa motore più bassa · meno ala |

### 3.2 Coach Dave Academy `[CDA-OSUS]` (2020, aggiornata; pre-1.9)

Organizzata per leva, non per fase. Nessun ordine di priorità dichiarato: l'ordine è quello delle sezioni dell'articolo (aerodinamica → molle → bumpstop → toe → differenziale → ammortizzatori).

| Sintomo | Altezza e ala | Molle | Bumpstop | Toe post. | Precarico |
|---|---|---|---|---|---|
| Sovra in ingresso / frenata | più ala e/o posteriore più basso | ant. più rigida | range più corto, rate più morbido | più toe-in | più alto |
| Sotto in frenata | — | ant. più morbida e/o post. più rigida | range ant. più lungo, rate più rigido | meno toe-in | più basso |
| Sovra nel lento | — | post. più morbida | range post. più lungo | più toe-in | — |
| Sotto nel lento | posteriore più alto | ant. più morbida | range post. più corto | meno toe-in | — |
| Sovra nel veloce | — | ant. più rigida | range più corto, rate più morbido | più toe-in | — |
| Sotto nel veloce | meno ala | post. più rigida | range ant. più lungo, rate più rigido | meno toe-in | — |
| Sotto su tutto il giro | posteriore più alto e meno ala | — | — | — | — |
| Sovra a centro curva | — | — | — | più toe-in | più alto |
| Sotto a centro curva | — | — | — | meno toe-in | più basso |
| Sovra in potenza in uscita | — | — | — | — | più basso |
| Sotto in potenza in uscita | — | — | range post. più corto | — | più alto |

Ammortizzatori, lista riassuntiva dello stesso articolo: più bump ant. → più sotto; meno bump post. → più sotto; più rebound ant. → più sovra; meno rebound post. → più sovra; meno bump ant. → più sovra; più bump post. → più sovra; meno rebound ant. → più sotto; più rebound post. → più sotto.

### 3.3 Barre antirollio, versione breve `[CDA-GUIDE]` `[DRS-IT]`

| Sintomo | Rimedio |
|---|---|
| Sotto in ingresso | barra ant. più morbida (oppure ripartizione più indietro) |
| Sovra in ingresso | barra ant. più rigida |
| Sovra in uscita | barra post. più morbida |
| Sotto in uscita | barra post. più rigida — `[CDA-GUIDE]` scrive invece che la post. rigida riduce il sotto **in ingresso** |

### 3.4 Ammortizzatori `[FGM]` (fonte debole)

| Sintomo | Rimedio |
|---|---|
| Sotto in ingresso | bump lento ant. più morbido; controllare che il rebound lento ant. non sia troppo rigido |
| Sovra in uscita | rebound lento post. più rigido; controllare il bump lento post. |
| Poco grip a centro curva | rigidezza complessiva eccessiva: guardare prima le molle |
| Auto «galleggiante» | rebound lento troppo morbido |
| Auto nervosa, «impaccata» | rebound lento troppo rigido |
| Ruote che saltano | ammorbidire i veloci |
| Si schiaccia sui dossi in serie | fast rebound troppo rigido |

Ordine di prova consigliato: rebound lento → bump lento → veloci.

### 3.5 Leve mancanti nelle tabelle

- **Usura o surriscaldamento di un solo asse**: nessuna tabella dedicata trovata. Indicazioni sparse: barra posteriore rigida scalda le posteriori `[TRIN-7]`; poco toe-in posteriore le surriscalda `[CDA-OSUS]`; pressione bassa scalda `[ARIS19]`; le posteriori si consumano prima e questo dà sovra per qualche giro `[TRIN-7]`.
- **Ordine di lavoro generale** secondo Aris (seconda mano, `[TRIN-7]`): 1 pressioni e aerodinamica → 2 verifica (molle, precarico) → 3 assetto più morbido → 4 barra posteriore → 5 wheel rate e bumpstop → 6 camber, toe, ritocco pressioni → 7 prova finale con gomme nuove. Secondo `[D61]`: prima le modifiche «universali» (ali, altezze, pressioni, ripartizione, TC/ABS), poi ammortizzatori e grip meccanico. Secondo `[TRIN-BEG]`: pressioni → camber e toe con la telemetria → condotti.

---

## 4. Dove due guide mettono leve diverse al primo posto

| Sintomo | Driver61 `[D61-PDF]` | Coach Dave `[CDA-OSUS]` / `[CDA-GUIDE]` | Aris `[ARIS19]` / `[TRIN-7]` |
|---|---|---|---|
| Sotto in ingresso | pressione anteriore più bassa | barra anteriore più morbida; molla ant. più morbida | altezza anteriore più bassa (effetto aerodinamico) |
| Sovra in ingresso | pressione posteriore più bassa | più ala e/o posteriore più basso | — |
| Sotto nel lento | (non distingue per velocità) | posteriore più alto | pressione più bassa per far flettere e ruotare |
| Sotto nel veloce | (non distingue) | meno ala | pressione più alta per sostegno e precisione |
| Sovra in uscita | pressione posteriore più bassa | precarico più basso; barra post. più morbida | attenzione: **meno** pressione dietro per Aris dà **più** rotazione |
| Cordoli | meno wheel rate | altezza ant. + range bumpstop più lungo | molle più rigide con corsa utile sufficiente (1.9) |

Il punto più delicato è l'ultima colonna della riga «sovra in uscita»: Driver61 (2021) usa «meno pressione dietro» come primo rimedio per il sovrasterzo in ogni fase, mentre Aris (1.9) scrive che meno pressione dietro = più flessione = **più imbardata**. Le due cose si possono conciliare (più impronta e trazione contro meno precisione laterale), ma per un algoritmo il verso va deciso con una misura, non preso da una tabella.

---

## 5. Punti controversi

### 5.1 Finestra pressioni a caldo, asciutto

- **26.0–27.0** è la posizione di Kunos `[ARIS19]` e di quasi tutte le guide aggiornate. Aris la chiama «indicativa»: la finestra è più larga e non c'è più un punto magico.
- **26.5–27.5** compare solo nelle FAQ in fondo a due pagine Coach Dave `[CDA-GUIDE]` `[CDA-PSI]`, le stesse che in tabella danno 26.0–27.0 (o 26–27.2). Nessuna fonte la argomenta: ha l'aspetto di un residuo di redazione, non di una tesi.
- **27.3–27.8/28** è la finestra del modello DHE 2020, superata dalla 1.9, ma ancora pubblicata nel 2025–2026 da `[D61]` e `[BDR]`.
- Conclusione operativa: bersaglio 26.0–27.0, con il lato della finestra scelto per tipo di curva secondo Aris (alto per il veloce, basso per il lento).

### 5.2 Pressioni da bagnato

- Tre finestre: 30.0–31.0, 29.5–31.0, 29.5–30.5. Differenze piccole.
- La contestazione vera è `[CDA-WET]`: con dati MoTeC, 35 psi batte 30 psi in ogni stato di pista provato, con calo sui 10 giri dimezzato su pista umida (es. Ferrari 2.0 s → 0.9 s). Campione piccolo (due piloti, tre o quattro auto, due piste), e l'autore consiglia di ignorare il widget.
- `[TROPHI]` afferma che la 1.9 non ha cambiato il comportamento delle gomme da bagnato.

### 5.3 Scarto termico interno–esterno

15 °C per Aris; 9 °C davanti e 5 °C dietro in `[CDA-GUIDE]` (che in un altro punto scrive 9 e 9). Il valore di Aris è quello 1.9; gli altri precedono il cambio delle letture OMI.

### 5.4 Verso degli ammortizzatori

- `[CDA-OSUS]`, lista riassuntiva: più bump ant. → più sotto; più rebound ant. → più sovra.
- `[D61-PDF]`: per **togliere** sotto (in tutte le fasi) aumentare bump ant. e rebound ant. Sul bump è l'opposto di Coach Dave.
- `[CDA-720EVO]` (post-1.9): per più grip in inserimento, bump lento ant. più **morbido** e rebound lento ant. più **rigido**. Coerente con la lista Coach Dave, opposto a Driver61 sul bump.
- `[CDA-OSUS]` si contraddice da solo: nel testo dice che più bump ant. aiuta il sovra in inserimento, nella lista che dà sotto (le due frasi sono compatibili), ma sul rebound anteriore testo e lista divergono.
- Cordoli: fast rebound da ridurre `[D61-PDF]` o da aumentare `[DRS-IT]`.
- Aris `[ARIS19]` non dà versi, solo l'avviso sugli estremi.

### 5.5 Precarico in ingresso

- Maggioranza (`[CDA-GUIDE]`, `[TRIN-7]` da Aris, `[DRS-IT]`): precarico alto = più stabile in ingresso, quindi per il sotto in ingresso si **abbassa**.
- `[D61-PDF]`: per il sotto in ingresso «aumentare il precarico». Opposto.
- `[CDA-OSUS]` nel testo scrive prima che il precarico alto dà più rotazione in ingresso, poi che dà sotto.
- In uscita c'è un secondo disaccordo: precarico alto = più sovra in uscita (`[CDA-GUIDE]`, `[TRIN-7]`), ma `[TRIN-BEG]` precisa «sovra nelle marce basse, sotto nelle alte», e `[TRIN-7]` «sotto in potenza nelle curve veloci».

### 5.6 Condotti freni e gomme

`[CDA-FAQ18]`: effetto minimo sulle gomme. `[CDA-FAQ19]`: regolarli per tenere il nucleo in finestra. `[TRIN-BEG]`: 0.2 psi per click. `[D61-PDF]`: li usa come rimedio per gomme calde o fredde.

### 5.7 Temperature freni

Davanti 600–650 °C come obiettivo `[CDA-GUIDE]` contro «600 e non oltre, altrimenti fading» `[CDA-FAQ18]` contro finestra fino a 700 °C `[TRIN-BEG]`. Nessun dato di Kunos trovato.

### 5.8 Pressioni uguali o diverse fra gli assi

Aris: la differenza fra assi è uno strumento di bilanciamento. Coach Dave: tenerle più vicine possibile.

### 5.9 Molle morbide o rigide

Aris 1.9: più rigide, con corsa utile. Coach Dave 1.9: funzionano entrambi gli estremi, compensando con lo smorzamento.

---

## 6. Cosa manca per l'algoritmo

| Dato richiesto | Esito |
|---|---|
| Passo in click per barre, molle, bumpstop, ala, splitter, precarico, caster, camber | non trovato in nessuna fonte (solo «uno o due click» per le molle `[TRIN-7]`, «1 click» e «3–4 click» per gli ammortizzatori) |
| Psi a caldo per click a freddo | non trovato come regola (circa 1:1 secondo `[SOLOX]`) |
| Sensibilità dell'ala in km/h o in % di bilanciamento per click | non trovato |
| Sensibilità dell'altezza in % di bilanciamento per mm | non trovato |
| Effetto della temperatura pista (distinta dall'aria) sulle pressioni, post-1.9 | non trovato |
| Finestra freni dichiarata da Kunos | non trovato |
| Tabella per usura/surriscaldamento di un asse | non trovato |
| Novità della 1.10 | non trovato |
| Range di regolazione della 720S Evo | trovati solo caster, ala, splitter, serbatoio (§7) |

Questi valori si leggono dalla schermata setup del gioco o si misurano; nelle guide non ci sono.

---

## 7. Architettura dell'auto e McLaren 720S GT3 Evo

### 7.1 Motore anteriore, centrale, posteriore

| Architettura | Tratti dichiarati | Fonte |
|---|---|---|
| **Anteriore** (AMG, BMW M4, Mustang, Bentley) | Stabilità e prevedibilità; buon uso dei cordoli (M4 fra le migliori); ripartizione di frenata arretrabile (M4); servono molle anteriori più rigide per il peso davanti | `[CDA-FAST]` `[CDA-M4]` `[CDA-GUIDE]` |
| idem, rimedi tipici | AMG: bumpstop posteriori quasi a zero per ruotare nel lento; ala alta per trazione; TC 1–3 | `[CDA-AMG]` |
| idem, preset (fonte debole) | altezze 50 mm ant. / 75 mm post., barra ant. al 60%, barra post. al 25% | `[HOEK]` |
| **Centrale** (720S, 296, Huracán, R8) | Bilanciamento neutro, forti nel medio-veloce; più sensibili a rake e cordoli; 296: rake sotto 20 mm, barre rigide davanti e morbide dietro, splitter il meno possibile | `[CDA-296]` `[CDA-720EVO]` |
| **Posteriore** (Porsche 991/992) | Trazione eccezionale dal lento; dipende molto da ala e rake; pressioni posteriori critiche; il serbatoio davanti all'asse anteriore fa cambiare il bilanciamento nello stint; dura con le gomme se guidata aggressiva | `[CDA-FAST]` `[CDA-991]` |
| Ripartizione di frenata | anteriore fino a 60-40, centrale 56-44 … 59-41 (ordini di grandezza generici) | `[CDA-PADS]` |

Nessuna guida trovata confronta in modo sistematico le tre architetture leva per leva: il confronto qui sopra è composto da guide per singola auto.

### 7.2 McLaren 720S GT3 Evo

| Voce | Contenuto | Fonte |
|---|---|---|
| Base | Motore centrale, V8 4.0 biturbo; lunghezza 4.664 mm; passo 2.696 mm | `[CDA-720EVO]` `[CDA-720]` |
| Novità Evo | Più carico, bilanciamento aerodinamico spostato in avanti, sospensioni riviste | `[CDA-720EVO]` `[CDA-FAST]` |
| Range | Caster fino a 16.3° (prima 8.0°); ala 0–12, cioè 13 posizioni (prima 0–8); splitter con 4 posizioni; serbatoio 120 l (prima 109) | `[CDA-720EVO]` |
| Punti forti | Curve medie e veloci, erogazione dolce, cordoli meglio della vecchia 720S | `[CDA-720EVO]` |
| Punti deboli | Anteriore «pigro» in inserimento nel lento; rolla troppo nei cambi di direzione rapidi e tende al sovra; sospensione rigida, male sui cordoli alti; più resistenza e meno velocità di punta delle auto a motore anteriore | `[CDA-720EVO]` |
| Barre e molle | Più rigide che su molte altre auto | `[CDA-720EVO]` |
| Bumpstop | L'auto ci si appoggia molto; ridurre i range per togliere sovra nei cambi di direzione | `[CDA-720EVO]` |
| Ammortizzatori | Dopo la base: bump lento ant. più morbido e rebound lento ant. più rigido per il grip in inserimento | `[CDA-720EVO]` |
| Rake | Preferisce poco rake per efficienza; più rake per stabilità o condizioni variabili, compensando con un po' meno ala | `[CDA-720EVO]` `[CDA-720]` |
| Splitter | Per più mordente davanti, pagando stabilità posteriore e resistenza | `[CDA-720EVO]` |
| TC | TC1 soglia, TC2 entità del taglio; TC2 per limitare il sovra in curve specifiche | `[CDA-720EVO]` |
| Guida | Precisa e dolce; cambiare marcia prima (più coppia) | `[CDA-720EVO]` |
| Sterzo | La 720S GT3 usa 480° di rotazione volante | `[CDA-296]` (citazione indiretta) |
| Pressioni | Una pagina prodotto Coach Dave per la 720S Evo riporta 27.5–28 psi: è la finestra pre-1.9, testo non aggiornato | estratto di ricerca, pagina non letta |
| Range di barre, wheel rate, precarico, ripartizione, livelli TC/ABS | non trovato | |

Implicazione per l'algoritmo: sulla 720S Evo il sintomo tipico dichiarato è **sotto in inserimento nel lento + sovra nei cambi di direzione**, e le leve indicate dalla guida specifica sono, nell'ordine in cui le presenta, barre e molle rigide → range bumpstop → ammortizzatori lenti anteriori → rake → splitter.

---

## 8. Elenco fonti (URL)

**Fonte primaria Kunos**
- `[ARIS19]` https://assettocorsa.gg/wp-content/uploads/ACCv19-physics_notes.pdf — copia: https://coachdaveacademy.com/wp-content/uploads/2023/04/ACCv19-physics_notes-3.pdf

**Coach Dave Academy**
- `[CDA-FAQ19]` https://coachdaveacademy.com/announcements/1-9-acc-faq-coach-dave/
- `[CDA-GUIDE]` https://coachdaveacademy.com/tutorials/the-ultimate-acc-car-setup-guide/
- `[CDA-PSI]` https://coachdaveacademy.com/tutorials/how-to-set-the-correct-tyre-pressures-in-acc/
- `[CDA-OSUS]` https://coachdaveacademy.com/tutorials/how-to-fix-oversteer-and-understeer-in-acc/ — stesso contenuto: https://coachdaveacademy.com/tutorials/how-to-fix-understeer-in-acc/ e https://coachdaveacademy.com/tutorials/how-to-fix-oversteer-in-acc/
- `[CDA-FAQ18]` https://coachdaveacademy.com/release-notes/v1-8-acc-update-faq-coach-dave-academy/
- `[CDA-PADS]` https://coachdaveacademy.com/tutorials/brake-pads-in-acc/
- `[CDA-WET]` https://coachdaveacademy.com/tutorials/acc-wet-tyre-pressures-myth-or-meta/
- `[CDA-720EVO]` https://coachdaveacademy.com/tutorials/tips-and-tricks-to-driving-the-mclaren-720s-gt3-evo/
- `[CDA-720]` https://coachdaveacademy.com/tutorials/tips-and-tricks-to-driving-the-mclaren-720s-gt3
- `[CDA-M4]` https://coachdaveacademy.com/tutorials/under-the-hood-tips-and-tricks-to-driving-the-new-bmw-m4-gt3/
- `[CDA-AMG]` https://coachdaveacademy.com/tutorials/under-the-hood-tips-and-tricks-to-driving-the-mercedes-amg-gt3-evo/
- `[CDA-296]` https://coachdaveacademy.com/tutorials/tips-and-tricks-to-driving-the-ferrari-296-gt3/
- `[CDA-991]` https://coachdaveacademy.com/tutorials/tips-and-tricks-on-how-to-drive-porsche-991-gt3-r/
- `[CDA-FAST]` https://coachdaveacademy.com/tutorials/what-is-the-fastest-gt3-car-in-acc/

**Driver61 / trophi**
- `[D61]` https://driver61.com/sim-racing/assetto-corsa-competizione-setup-guide/
- `[D61-PDF]` https://driver61.com/wp-content/uploads/2021/04/Driver61-Assetto-Corsa-Competizione-Setup-Guide-V1.pdf
- `[TROPHI]` https://www.trophi.ai/post/why-tyre-pressures-are-crucial-in-acc

**Altre**
- `[SOLOX]` https://solox.gg/acc-tyre-pressure/
- `[TRAX-PSI]` https://traxion.gg/why-tyre-pressures-are-key-to-winning-in-asetto-corsa-competizione/
- `[TRAX-BASE]` https://traxion.gg/assetto-corsa-competizione-basic-setup-guide/
- `[TRIN-7]` https://trinacriasimracing.wordpress.com/acc-how-to-customize-the-car-setup-in-seven-steps/
- `[TRIN-BEG]` https://trinacriasimracing.wordpress.com/acc-beginner-setup-guide/
- `[DRS-IT]` https://drsteamitalia.altervista.org/forum/topic/guida-al-setup/
- `[FGM]` https://www.fullgripmotorsport.com/academy/tutorial/6610c60d-4e3a-454f-af85-b791a1dede46
- `[BDR]` https://bluedragonracing.eu/protips/all-about-the-tires-in-acc-first-part-what-the-hell-is-psi/
- `[HOEK]` https://arnouthoekstra.substack.com/p/front-engine-car-preset-explained
- `[STEAM]` https://steamcommunity.com/app/805550/discussions/0/3820784984083192442/

**Trovate ma non lette (solo estratti di ricerca, o inaccessibili)**
- `[GOSET]` https://support.gosetups.gg/hc/en-gb/articles/23218772165906-What-Are-the-Optimal-Tyre-Pressures-for-GT3-Cars-in-ACC (403)
- `[SRS]` https://simracingsetup.com/assetto-corsa/acc-beginners-setup-guide/ e https://simracingsetup.com/assetto-corsa/acc-tyre-pressure-guide/ (verifica anti-bot)
- https://www.acc-wiki.info/wiki/Car_Setups_and_Pitstop/en e https://www.acc-wiki.info/wiki/Setup_Guide_for_Beginners (dominio non risolto)
- https://www.overtake.gg/threads/assetto-corsa-competizione-blog-suspension-and-setups.159375/ (blog Kunos su sospensioni e setup, 403)
- https://bsimracing.com/?p=79604 (annuncio del video di Aris sugli ammortizzatori, 18/01/2020: nessun testo)
- Guide analizzate e scartate perché senza contenuto utile: https://traxion.gg/assetto-corsa-competizione-setup-troubleshooting-guide/ (solo video), https://www.tracktitan.io/post/how-to-setup-tyre-pressures e https://www.tracktitan.io/post/how-to-set-up-gt3-aerodynamics (nessun numero), https://gosetups.gg/blog/hybrid-setups-release-mclaren-720s-gt3-evo-and-aston-martin-v8-vantage-gt3/ (promozionale)
