# Geometria dei circuiti — da dove viene

I file `.csv` in questa cartella **non sono nostri**. Descrivono i circuiti veri —
linea centrale in metri e larghezza a destra e a sinistra — e stanno qui perché
la geometria della pista non deve dipendere da quale simulatore hai avviato né
da quali piste hai installato.

Formato, uguale per tutti: `x_m, y_m, w_tr_right_m, w_tr_left_m`.

## Fonti e licenze

**25 circuiti** (Austin, Brands Hatch, Budapest, Catalunya, Hockenheim, IMS,
Melbourne, Mexico City, Montreal, Monza, Moscow Raceway, Norisring,
Nürburgring, Oschersleben, Sakhir, São Paulo, Sepang, Shanghai, Silverstone,
Sochi, Spa, Spielberg, Suzuka, Yas Marina, Zandvoort) — copiati **senza
modifiche** da:

> **TUMFTM/racetrack-database** — Institute of Automotive Technology,
> Technical University of Munich. <https://github.com/TUMFTM/racetrack-database>
> Licenza **LGPL-3.0**.
>
> Le linee centrali vengono da punti GPS di OpenStreetMap, lisciate; le
> larghezze sono estratte da immagini satellitari.

**Mount Panorama** (`MountPanorama.csv`) — **derivato** da:

> **TUMRT/online_3D_racing_line_planning**,
> `data/raw_track_data/mount_panorama_bounds_3d.csv`.
> <https://github.com/TUMRT/online_3D_racing_line_planning> — Licenza
> **LGPL-3.0**.
>
> L'originale dà le due sponde in 3D, 6001 coppie di punti. Qui sono state
> convertite nello stesso formato a quattro colonne degli altri: centro = punto
> medio della coppia, semilarghezze = metà della loro distanza, e un punto ogni
> 5 m invece che ogni metro. La quota è stata scartata: la larghezza di una
> pista si misura per terra.

I file restano **separati e sostituibili**: chi vuole può metterci la propria
versione, o toglierli del tutto — senza di essi HONE funziona come prima, solo
senza il nastro d'asfalto sulle piste che non ha installate.

## Perché non bastavano i file del gioco

Ci sono anche quelli, e vengono usati: Assetto Corsa pubblica la propria linea IA
con le larghezze (`ai/fast_lane.ai`, vedi `SPIKE-BORDI.md`). Ma coprono solo le
piste che hai **installate**, e solo se hai AC. Queste 26 valgono per tutti.

Misurato il 2026-07-31, e c'è un motivo in più per tenerle: **le larghezze da
satellite misurano la pista, quelle del gioco misurano tutto l'asfalto.**

| | mediana | massimo |
|---|---|---|
| Spa, da qui | 9.2 m | **16.4 m** |
| Spa, dai file di AC | 10.4 m | **24.5 m** (la via di fuga di La Source) |
| Suzuka, da qui | 9.2 m | **15.3 m** |
| Suzuka, dai file di AC | 10.0 m | **33.5 m** |
