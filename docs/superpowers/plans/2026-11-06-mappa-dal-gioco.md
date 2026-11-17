# La pista vista dall'alto con la grafica del gioco — piano

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** in reportistica la mappa del giro intero e la vista della curva hanno
come sfondo il modello grafico di Assetto Corsa visto dall'alto, attenuato e
ingrandibile, con sopra le stesse linee e frenate di oggi.

**Architecture:**
- `kn5visual.py` legge i kn5 grafici e di collisione in array numpy, applicando
  le matrici dei nodi.
- `trackart.py` disegna tasselli 512×512 in coordinate del modello, a sei
  livelli da 0,1 a 3,2 m per pixel, e li tiene in una cache su disco.
- L'API dice alla pagina se lo sfondo c'è e con quale fit si posa, e serve i
  tasselli solo al PC stesso.
- `app.js` disegna i tasselli sotto le linee con una trasformazione affine
  giro→schermo, attenuati con `ctx.filter`, e aggiunge zoom e trascinamento
  alla mappa grande.

**Tech Stack:** Python 3.14, numpy 2.4, Pillow 12.1, FastAPI già in uso,
canvas 2D. Nessuna dipendenza nuova.

**Spec:** `docs/superpowers/specs/2026-11-06-mappa-dal-gioco-design.md`
(leggerla tutta: le lezioni dello spike sul formato kn5 sono lì).

## Global Constraints

- Sola lettura dei file di AC; mai scrivere nella cartella del gioco.
- Le immagini si generano in locale e restano in locale. Mai nel repo, nel
  bundle, nei log, nell'export. Si servono solo a un client locale
  (`guard.is_local_client`).
- Cache sotto `paths.base_dir() / "cache" / "mapbg"`: cancellabile e
  ricostruibile, senza dati del pilota.
- Se qualcosa non si legge o non si posa, lo sfondo manca e la mappa resta
  quella di oggi. Mai uno sfondo inventato o posato a caso.
- Le linee si leggono prima dello sfondo. Lo sfondo è attenuato a saturazione
  0,55 e luminosità 0,62.
- Nessuna dipendenza nuova.
- Conteggi letti dal file sempre controllati prima di allocare (come
  `trackmesh._Reader.need`).
- Test senza i file veri del gioco, con kn5 sintetici (vedi
  `tests/test_trackmesh.py::_kn5`).
- Test sempre con la casa finta. Misure solo in sola lettura sui file di AC
  installati e sulla **copia** dell'archivio. Mai `Documents\ACCoach`, mai la
  porta 8778.
- Testi in italiano col tu, frasi brevi, virgola decimale, niente due punti a
  effetto, niente emoji, massimo 25 parole per frase nelle pagine e nella guida
  (`tests/test_tono.py`).
- I file del repo sono CRLF: modificarli preservando i fine riga.
- Commit con `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` e
  `Claude-Session: https://claude.ai/code/session_015rMgt45HYsP5VgTvkAVCs3`.
  Niente push.

## Decisioni

1. **Chi posa lo sfondo.** `trackedges.ac_fit(points)` sceglie, fra le sole
   piste di AC installate (`all_splines()`), quella col fit migliore, con le
   stesse soglie di `fit`. Restituisce la linea dell'IA vincitrice e il suo
   `Fit`. Un circuito del bundle non posa mai lo sfondo.
2. **Quali file.**
   - La cartella della configurazione è `spline.parent.parent`. Se è dentro la
     pista (`<pista>/<layout>/ai/...`), il file è
     `<pista>/models_<layout>.ini`, altrimenti `<pista>/models.ini`.
   - Ogni `[MODEL_n]` dà `FILE`, `POSITION` e `ROTATION`, quest'ultima in gradi
     intorno a Y, X e Z in quest'ordine, come AC.
   - Senza ini si prendono tutti i `*.kn5` della cartella della pista.
   - Il modello di collisione (`trackmesh.physics_model`) serve solo per l'altezza
     della strada (Decisione 5).
3. **Tasselli.**
   - `LEVELS_M = (0.1, 0.2, 0.4, 0.8, 1.6, 3.2)` metri per pixel e `TILE_PX = 512`,
     quindi il lato di un tassello è `TILE_PX * LEVELS_M[L]` metri.
   - Il tassello `(L, tx, tz)` copre x ∈ [tx·lato, (tx+1)·lato) e
     z ∈ [tz·lato, (tz+1)·lato), in coordinate del **modello**.
   - Il pixel (0, 0) è in alto a sinistra e corrisponde a x minima, z massima.
     Niente specchio nei tasselli: lo specchio lo fa la trasformazione della
     pagina.
   - JPEG qualità 85. Un tassello senza niente disegnato non si salva come
     immagine: si salva un segnaposto vuoto `<tz>.none`, e l'API risponde 204.
4. **Disegno.**
   - Vista ortografica dall'alto, z-buffer sulla quota (vince la più alta).
   - Colore = txDiffuse con campionamento bilineare, guadagno 1,0.
   - Texel con alpha < 100 scartati per gli shader con alpha test o blend 1.
   - Triangoli con area in pianta < 1e-4 m² scartati alla lettura.
   - Triangoli il cui ingombro sullo schermo è sotto 1,5 px di lato si disegnano
     come un punto al baricentro, vettorizzato. Lì va il tempo dei livelli
     grossi.
   - Texture ridotte per livello. Lato massimo 4096 per L0-1, 2048 per L2-3,
     1024 per L4-5. Cache delle texture decodificate entro 512 MB.
   - Una texture che Pillow non apre (BC7) fa disegnare quel triangolo grigio
     (128, 128, 128), e la pista non fallisce.
5. **Sopra la strada.**
   - Dove il modello di collisione ha strada o cordolo
     (`trackmesh._class_of(nome) in {"road", "kerb"}`), un frammento più alto
     della strada di oltre `OVERHEAD_M = 2.0` m non si disegna.
   - Il 2,0 è di partenza. Il Task 3 lo misura a Monza e lo scrive.
6. **API.**
   - `GET /api/mapbg?car&track&lap` (giro risolto come `/api/analysis`)
     risponde:
     `{"ok": true, "key": <16 hex>, "fit": {scale, cos, sin, dx, dz, mirror}, "levels": LEVELS_M, "tile_px": 512}`.
     Altrimenti risponde `{"ok": false, "reason": r}` con r fra `"remote"`,
     `"no_ac"`, `"no_fit"`, `"no_model"`.
   - `GET /api/mapbg/tile/{key}/{level}/{tx}/{tz}` risponde 200 con
     image/jpeg, 204 se vuoto, 403 se il client non è locale, 404 se la chiave
     non è nota.
   - Il `fit` porta le coordinate del modello in quelle del giro, cioè è
     `Fit.apply`.
7. **Chiave di cache.** I primi 16 hex dello sha1 di: percorsi dei kn5 usati,
   più dimensione e mtime di ciascuno, più `ART_VERSION = 1`. Se cambia un file
   della pista, i tasselli si rifanno.
8. **Pagina.**
   - Lo sfondo si disegna con `ctx.filter = "saturate(0.55) brightness(0.62)"`
     sotto tutto il resto, attraverso una trasformazione affine
     `[a, b, c, d, e, f]` (convenzione `setTransform`) da coordinate del giro a
     pixel CSS, composta con il `fit`.
   - Il livello è il più fine il cui metro per pixel non scende sotto quello
     dello schermo diviso `devicePixelRatio`.
   - I tasselli si caricano come `Image`. Quando uno arriva, la vista si
     ridisegna, al massimo una volta per frame. Finché non arrivano si vede la
     mappa di oggi.
9. **Zoom della mappa grande** (`#c-map`, non il rail).
   - Rotella ×1,25 per scatto intorno al cursore, trascinamento per spostare,
     doppio clic per tornare al giro intero.
   - Si riparte dal giro intero a ogni giro nuovo.
   - Da k = 1 (giro intero) fino a 10 px per metro.
   - Hover, croce del giro perso, segni del consiglio e frenate passano dalle
     stesse X/Y, quindi seguono lo zoom.
10. **Larghezza della linea sopra lo sfondo.** Con lo sfondo disegnato, la tua
    linea è larga `clamp(2 + 5·tt, 1.5, 3·s)` px, con `s` in pixel per metro.
    Così la mezza larghezza non supera 1,5 m alla scala del giro intero.
    Senza sfondo resta `2 + 5·tt` come oggi. Ogni linea e segno ha un bordo
    scuro `rgba(0,0,0,0.65)` largo 2 px in più.
11. **Vista della curva.** Con lo sfondo e `LINE_MAG == 1`, lo sfondo prende il
    posto di `drawSurfaces` / `drawRoad`, sotto la stessa rotazione `turn`.
    Con `LINE_MAG > 1` niente sfondo, come oggi niente strada. La legenda usa
    `line.leg.photo`.

## Review Focus

1. Un giro con una pista solo nel bundle (AC installato ma pista assente)
   rischia di ricevere uno sfondo posato col fit del bundle. Deve dare
   `no_fit`. → Task 1.
2. Un kn5 bloccato mentre AC lo carica (OSError) rischia di finire nella
   cache come «pista senza sfondo». Non deve: si riprova alla richiesta dopo.
   → Task 4.
3. Una richiesta di tassello da un altro dispositivo in rete, anche con la
   chiave giusta, deve ricevere 403. → Task 5.
4. Parametri del tassello costruiti a mano (`key` non esadecimale, livello 9,
   `tx` non intero, `..`) non devono toccare il disco fuori dalla cache. Devono
   dare 404 o 422. → Task 5.
5. Un giro senza coordinate (`has_map` falso) non deve chiedere lo sfondo,
   oppure deve ricevere `no_fit`. La pagina resta quella di oggi. → Task 5 e 6.

---

### Task 1: chi posa lo sfondo, e con quali file

**Files:**
- Modify: `src/accoach/trackedges.py` (accanto a `_by_shape`)
- Create: `src/accoach/trackart.py` (solo `art_files` in questo task)
- Test: `tests/test_trackart.py`

**Interfaces — Produces:**
- `trackedges.ac_fit(points) -> tuple[Path, Fit] | None`
- `trackart.ArtFile(path: Path, position: tuple[float, float, float], rotation_deg: tuple[float, float, float])`
  (dataclass frozen)
- `trackart.art_files(spline: Path) -> list[ArtFile]`

- [ ] **Step 1: test.**
  - `test_the_background_is_never_placed_with_a_bundled_circuit`: con
    `bundled_tracks` che restituisce un circuito identico al giro e
    `all_splines` vuoto, `ac_fit(points) is None`, mentre `edges_and_fit`
    trova il bundle.
  - `test_the_ac_track_that_fits_best_wins`: due linee IA sintetiche, una
    giusta e una spostata di 30 m in forma, scritte col formato di
    `fast_lane.ai`; il risultato restituisce il percorso di quella giusta. Gli
    aiuti per scrivere una linea stanno in `tests/test_trackedges.py`.
  - `test_models_ini_is_read_with_its_layout`: `<pista>/gp/ai/fast_lane.ai`
    con `models_gp.ini`, che elenca `a.kn5` con `POSITION=1,2,3` e
    `ROTATION=90,0,0`; il risultato è
    `[ArtFile(<pista>/a.kn5, (1,2,3), (90,0,0))]`, e il `models.ini` della
    stessa pista è ignorato.
  - `test_without_an_ini_every_kn5_of_the_track_is_used`.
  - `test_a_file_named_outside_the_track_folder_is_ignored`: `FILE=..\x.kn5`
    non entra.
- [ ] **Step 2:** → FAIL.
- [ ] **Step 3:** implementa.
  - `ac_fit` è `_by_shape` ristretto a `all_splines()`, con la stessa
    tolleranza di lunghezza e lo stesso «vince il migliore».
  - `art_files` legge l'ini con `configparser`. Tollera chiavi mancanti
    (posizione e rotazione a zero) e salta i file che non esistono.
- [ ] **Step 4:** → PASS. **Step 5:** commit «Lo sfondo si posa solo su una pista di AC, coi suoi file».

### Task 2: leggere un kn5 grafico

**Files:**
- Create: `src/accoach/kn5visual.py`
- Test: `tests/test_kn5visual.py`

**Interfaces — Produces:**
- `Material(name: str, shader: str, blend: int, alpha_test: bool, diffuse: str | None)`
- `Model`, con i campi:
  - `path: Path`
  - `tris: np.ndarray`, float32 (N, 3, 3) xyz nel mondo
  - `uv: np.ndarray`, float32 (N, 3, 2)
  - `mat: np.ndarray`, int32 (N,)
  - `mesh: np.ndarray`, int32 (N,), indice in `mesh_names`
  - `mesh_names: list[str]`
  - `materials: list[Material]`
  - `textures: dict[str, tuple[int, int]]`, nome → (offset, lunghezza) nel file
- `read(path: Path, position=(0,0,0), rotation_deg=(0,0,0)) -> Model`, che
  solleva `ValueError` / `OSError` su file non valido.
- `texture_bytes(model: Model, name: str) -> bytes | None`

- [ ] **Step 1: test.** Estendi l'aiuto `_kn5` dei test con texture,
  materiali, uv e matrici dei nodi (versione locale nel nuovo file di test).
  - `test_a_node_matrix_moves_its_children`: una mesh sotto un nodo con
    traslazione (10, 0, 5) esce spostata di (10, 0, 5); due nodi annidati
    compongono, prima il figlio poi il padre (vettore riga).
  - `test_models_ini_position_and_rotation_are_applied`: `rotation_deg=(90,0,0)`
    porta (1, 0, 0) in (0, 0, -1) secondo la convenzione di AC. Se la misura
    sul Monza vero dice il contrario, vince la misura e si scrive nel commit.
  - `test_the_diffuse_texture_is_found_by_its_slot`: il materiale con mappe
    `txMask` e `txDiffuse` ha `diffuse` uguale al nome di `txDiffuse`, e
    `texture_bytes` restituisce quei byte.
  - `test_vertical_triangles_are_dropped`: un muro verticale non entra in
    `tris`.
  - `test_a_lying_count_is_refused`: un conteggio di vertici da due miliardi
    in un file piccolo dà `ValueError`, senza allocare.
  - `test_skinned_meshes_are_skipped`: un nodo di tipo 3 non entra.
- [ ] **Step 2:** → FAIL.
- [ ] **Step 3:** implementa seguendo le «Lezioni dello spike» della spec, con
  i controlli di `trackmesh._Reader.need`. Le texture si indicizzano, non si
  leggono.
- [ ] **Step 4:** → PASS.
- [ ] **Step 5: misura sola lettura** sul Monza installato: tempo di `read` di
  ogni file di `art_files`, triangoli tenuti e scartati, e memoria degli array.
  Numeri nel commit.
- [ ] **Step 6:** commit «Il modello grafico di una pista si legge in array».

### Task 3: disegnare un tassello

**Files:**
- Modify: `src/accoach/trackart.py`
- Test: `tests/test_trackart.py`

**Interfaces — Consumes:** Task 2 (`Model`, `texture_bytes`).
**Produces:**
- `LEVELS_M`, `TILE_PX`, `OVERHEAD_M`, `ALPHA_CUT = 100`
- `Scene(models: list[Model], road: Model | None)`, dove `road` è il modello di
  collisione
- `render_tile(scene: Scene, level: int, tx: int, tz: int) -> PIL.Image.Image | None`
  (None se niente è stato disegnato)

- [ ] **Step 1: test** con modelli sintetici e texture PNG fatte in memoria.
  - `test_a_quad_fills_the_tile_with_its_texture`: un quadrato con texture
    rossa che copre il tassello `(0, 0, 0)` lo rende tutto rosso entro ±2 per
    canale.
  - `test_the_tile_corner_is_x_min_z_max`: un quadratino blu in
    x ∈ [0, 1], z ∈ [lato-1, lato] colora l'angolo in alto a sinistra.
  - `test_the_highest_surface_wins`: due quadrati sovrapposti a quota 0 e 1 →
    vince quello a 1.
  - `test_something_above_the_road_is_not_drawn`: strada (nome `1ROAD_x` nel
    modello di collisione) a quota 0 sotto un ponte a quota 6 → il colore è
    quello della strada. Un tetto a quota 6 senza strada sotto resta.
  - `test_transparent_texels_are_dropped`: con alpha test e texel alpha 0
    resta visibile la superficie sotto.
  - `test_bilinear_blends_two_texels`: una texture 2×1 nero/bianco stesa su
    2 m a 0,1 m per pixel dà al centro un grigio fra 100 e 155, non un
    gradino.
  - `test_tiny_triangles_are_splatted_with_the_same_colour`: una griglia di
    triangoli da 0,5 m al livello 5 dà lo stesso colore uniforme della
    texture, ±3.
  - `test_an_unreadable_texture_draws_grey`.
  - `test_an_empty_tile_is_none`.
- [ ] **Step 2:** → FAIL.
- [ ] **Step 3:** implementa (Decisioni 4-5). Indice spaziale a caselle per
  trovare i triangoli di un tassello senza scorrerli tutti.
- [ ] **Step 4:** → PASS.
- [ ] **Step 5: misura sola lettura** sul Monza installato, script nello
  scratchpad e non nel repo. I risultati entrano nel commit.
  - Tempo di tutti i tasselli del livello 5 sul circuito, e mediana e massimo
    di 20 tasselli del livello 0 lungo la linea del giro.
  - Obiettivo: livello 5 intero ≤ 20 s, livello 0 mediana ≤ 2 s.
  - Se il tempo è oltre il doppio dell'obiettivo, fermati e riferisci senza
    cambiare motore.
  - Controlla `OVERHEAD_M` sul portale del traguardo e sulle passerelle di
    Monza. Il tassello si vede con il Read di un PNG.
- [ ] **Step 6:** commit «Un tassello della pista vista dall'alto».

### Task 4: la cache dei tasselli

**Files:**
- Modify: `src/accoach/trackart.py`
- Test: `tests/test_trackart.py`

**Interfaces — Consumes:** Task 1 (`art_files`), Task 2 (`read`), Task 3
(`render_tile`, `Scene`).
**Produces:**
- `ART_VERSION = 1`
- `cache_dir() -> Path`
- `art_key(spline: Path) -> str | None`, con 16 hex (Decisione 7), None senza
  file
- `scene_for(key: str) -> Scene | None`, con al massimo una scena in memoria e
  un lock per la lettura
- `tile(key: str, level: int, tx: int, tz: int) -> bytes | None`, che dà i
  byte JPEG e None se vuoto, e solleva `KeyError` se la chiave non è nota

- [ ] **Step 1: test** (casa finta).
  - `test_a_tile_is_rendered_once_then_read_from_disk`: `render_tile`
    sostituito da un contatore → due chiamate a `tile`, un disegno.
  - `test_an_empty_tile_is_remembered_as_empty`.
  - `test_touching_a_track_file_changes_the_key`.
  - `test_a_locked_file_is_not_remembered_as_missing`: `read` che solleva
    `OSError` la prima volta e riesce la seconda → la seconda chiamata a
    `scene_for` dà una scena.
  - `test_the_cache_lives_under_the_hone_folder`: `cache_dir()` sta dentro
    `paths.base_dir()`.
- [ ] **Step 2:** → FAIL. **Step 3:** implementa. La chiave si registra in memoria
  con la sua linea IA quando `art_key` la calcola, ed è così che `scene_for`
  la ritrova. **Step 4:** → PASS. **Step 5:** commit «I tasselli si fanno una volta e si tengono».

### Task 5: l'API

**Files:**
- Modify: `src/accoach/api.py` (accanto a `/api/trajectory`)
- Test: `tests/test_api_mapbg.py`

**Interfaces — Consumes:** Task 1 (`ac_fit`), Task 4 (`art_key`, `tile`).
**Produces:** le due rotte della Decisione 6.

- [ ] **Step 1: test** con `TestClient`, client locale `("127.0.0.1", 5000)`
  e client remoto `("192.168.1.20", 5000)`.
  - `test_a_remote_client_gets_no_background`: `/api/mapbg` dà
    `{"ok": false, "reason": "remote"}`, e il tassello dà 403 anche con una
    chiave valida.
  - `test_without_ac_the_reason_is_no_ac`, `test_a_bundled_only_track_is_no_fit`
    e `test_a_lap_without_coordinates_is_no_fit`.
  - `test_a_placed_lap_gets_key_fit_and_levels`: con `ac_fit` e `art_key`
    sostituiti, la risposta ha `fit` con i sei campi e `levels == list(LEVELS_M)`.
  - `test_tile_params_are_checked`: `key="../../x"`, `level=9` e `tx="a"` danno
    404 o 422, e `tile` non viene chiamato.
  - `test_an_empty_tile_is_204` e `test_a_tile_is_jpeg`.
- [ ] **Step 2:** → FAIL. **Step 3:** implementa. Il locale si decide con
  `guard.is_local_client(request.client.host)`, la chiave con il regex
  `^[0-9a-f]{16}$` e il livello con `0 <= level < len(LEVELS_M)`. **Step 4:** → PASS.
  **Step 5:** commit «La pagina chiede lo sfondo e i tasselli, solo dal PC».

### Task 6: lo sfondo nella pagina

**Files:**
- Modify: `src/accoach/web/app.js` (`drawMapTo`, `drawMap`, `drawCornerZoom`,
  il caricamento del giro), `src/accoach/web/i18n.js`, `GUIDA.md`, `docs/FAQ.md`
- Test: `tests/test_mapbg_page.py` (node, come
  `tests/test_engineer_record_panel.py`), `tests/test_guide.py`

**Interfaces — Consumes:** Task 5 (JSON di `/api/mapbg`, URL dei tasselli).
**Produces, in app.js:**
- `MAPBG`: la risposta di `/api/mapbg` del giro corrente, o null
- `mapBgAffine(fit, A) -> number[6]`, che compone modello → giro → schermo
- `mapBgLevel(pxPerM, dpr) -> int`
- `mapBgDraw(ctx, bg, A, w, h)`
- `lineWidthOnPhoto(tt, s) -> number`
- `MAP_VIEW = {k, cx, cz}`

- [ ] **Step 1: test** in node.
  - `test_the_affine_puts_a_model_point_where_the_lap_point_is`:
    `mapBgAffine` con un fit noto (rotazione, scala, specchio) porta un punto
    del modello dove la `X/Y` della mappa porta `Fit.apply` dello stesso punto,
    entro 0,01 px.
  - `test_the_level_follows_the_zoom`: `mapBgLevel(0.3, 1) == 5`,
    `mapBgLevel(10, 1) == 0` e `mapBgLevel(5, 2) == 0`.
  - `test_the_line_stays_inside_the_road_at_full_lap_scale`:
    `lineWidthOnPhoto(1, 0.87) <= 2.61` e `lineWidthOnPhoto(1, 3) == 7`.
  - `test_without_a_background_the_line_is_as_today`.
  - `test_the_background_is_dimmed_as_chosen`: il testo di app.js contiene
    `saturate(0.55) brightness(0.62)`.
  - `test_the_rail_has_no_background`: `drawRail` non chiama `mapBgDraw`.
- [ ] **Step 2:** → FAIL.
- [ ] **Step 3:** implementa (Decisioni 8-11).
  - `/api/mapbg` si chiede solo se `has_map`, dopo l'analisi, con gli stessi
    car, track e lap. Una risposta `ok: false` lascia tutto come oggi.
  - Chiave i18n `line.leg.photo`:
    - it: «Lo sfondo è la pista vista dall'alto, presa dai file di Assetto Corsa.»
    - en: «The background is the track seen from above, taken from Assetto Corsa's files.»
  - Testo di GUIDA.md e FAQ.md nella sezione della mappa. Deve dire:
    - da dove viene lo sfondo;
    - che serve AC con quella pista e vale anche per i giri di ACC;
    - che la prima volta si prepara e poi resta;
    - che il paesaggio da vicino è sfocato perché il gioco lo tiene così;
    - come si ingrandisce e si torna al giro intero;
    - che sugli altri dispositivi la mappa resta senza sfondo.
  - Un test in `tests/test_guide.py` cerca «vista dall'alto» in entrambe le
    lingue.
- [ ] **Step 4:** → PASS e suite intera.
- [ ] **Step 5: verifica nel browser.** Avvia la reportistica su una porta di
  prova, non la 8778, con la casa finta, e con la copia dell'archivio come
  cartella giri. Apri il giro di Monza
  `monza__mclaren-720s-gt3-evo__1m53s202__20260814T212454z0000.lap.json.gz`
  contro `1m53s090`. Controlla con gli screenshot:
  - lo sfondo sotto la mappa intera, attenuato;
  - zoom fino alla prima variante con linee e frenate leggibili;
  - doppio clic che torna al giro intero;
  - la vista della curva con lo sfondo;
  - un giro di una pista non installata in AC (Red Bull Ring) identico a oggi.
  Mai `localStorage.clear()`.
- [ ] **Step 6:** commit «La mappa del report ha sotto la pista vista dall'alto».
