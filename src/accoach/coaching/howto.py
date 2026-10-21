"""Le parole della Pagella e del «Come si fa»: nomi, verdetto, problema, esercizi.

Il tono è deciso col pilota, che aveva bocciato i testi «da macchina» della
scheda Allenamento (la stessa frase su ogni scheda, gli slogan, i due punti a
effetto). Le regole, che `tests/test_howto_tono.py` controlla:

* frasi brevi col tu, prima il fatto e poi cosa fare;
* mai la stessa frase in due posti: ogni difetto ha il suo testo, e una regola
  che vale per tutti (si segue un consiglio alla volta) non sta qui ma una volta
  sola sopra il piano;
* nessuna cifra dentro gli esercizi: i numeri del pilota arrivano come
  parametri (`problem`, `verdict`) e li formatta `fmt_s`, con la virgola in
  italiano.

Gli esercizi partono da quelli della scheda Allenamento (`training._T`) e dalla
ricerca sui coach professionisti (`COACHING-PRO.md`). Per alzate, veleggio e
frenata tardiva un esercizio non c'era ed è scritto qui.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..textfmt import fmt_num
from .defects import DefectSummary
from .training import GlossaryEntry, glossary_of


@dataclass(frozen=True)
class HowTo:
    what: str         # il fatto e cosa cambiare
    watch: str        # cosa guardare in pista
    ignore: str       # cosa lasciare stare
    drill: str        # l'esercizio
    laps: int         # quanti giri dura l'esercizio
    done_when: str    # quando è fatto


def _lang(lang: str) -> str:
    return lang if lang in ("it", "en") else "en"


# --- i nomi -----------------------------------------------------------------

_DEFECT_NAMES = {
    "it": {
        "brake_early": "Freni troppo presto",
        "brake_late": "Freni troppo tardi",
        "over_brake": "Troppo freno",
        "throttle_late": "Gas tardi in uscita",
        "min_speed": "Poca velocità in curva",
        "lift": "Alzi il gas sul dritto",
        "coasting": "Veleggi prima di frenare",
    },
    "en": {
        "brake_early": "Braking too early",
        "brake_late": "Braking too late",
        "over_brake": "Too much brake",
        "throttle_late": "Late on the throttle",
        "min_speed": "Too slow mid-corner",
        "lift": "Lifting on the straight",
        "coasting": "Coasting before the brake",
    },
}

_ERROR_NAMES = {
    "it": {"lock": "Bloccaggi", "spin": "Pattinamenti", "understeer": "Sottosterzo",
           "oversteer": "Sovrasterzo", "off": "Uscite di pista"},
    "en": {"lock": "Lock-ups", "spin": "Wheelspin", "understeer": "Understeer",
           "oversteer": "Oversteer", "off": "Off track"},
}


def defect_name(key: str, lang: str) -> str:
    return _DEFECT_NAMES[_lang(lang)][key]


def error_name(key: str, lang: str) -> str:
    return _ERROR_NAMES[_lang(lang)][key]


# --- i numeri ---------------------------------------------------------------

def fmt_s(v: float, lang: str) -> str:
    """Secondi con due decimali e l'unità: «0,18 s» in italiano, «0.18 s» in inglese."""
    return fmt_num(v, 2, _lang(lang), "s")


def _seconds(value: float, unit: str) -> float:
    return value / 1000.0 if unit == "ms" else value


# --- il «come si fa» --------------------------------------------------------

# Giri per esercizio: Ross Bentley lavora su un tema per 5-6 giri
# (COACHING-PRO.md, §2.1). Sei dove l'esercizio ha tre passi da due giri,
# cinque dove il gesto è uno solo (alzate, veleggio).
_LAPS = {"brake_early": 6, "brake_late": 6, "over_brake": 6, "throttle_late": 6,
         "min_speed": 6, "lift": 5, "coasting": 5}

_HOWTO = {
    "it": {
        "brake_early": dict(
            what="Cominci a frenare prima del necessario, e quel tratto lo fai "
                 "già lento. Prima impari a staccare sempre nello stesso punto, poi "
                 "lo sposti più tardi a piccoli passi.",
            watch="In pista guarda la velocità minima della curva, la più bassa "
                  "che tocchi. Se scende mentre freni più tardi, quello che "
                  "prendi in staccata lo ridai in curva.",
            ignore="Il tempo sul giro, per questi giri, non conta.",
            drill="Scegli un punto che vedi, un cartello o l'inizio di un "
                  "cordolo, e stacca lì per i primi due giri. Poi frena una "
                  "lunghezza d'auto più tardi a ogni giro. Il colpo di freno va "
                  "dato forte subito, e si scarica man mano che rallenti. Quando "
                  "una ruota blocca, o con l'ABS senti il pedale vibrare e l'auto "
                  "allarga, torna al punto di prima e restaci fino alla fine.",
            done_when="L'esercizio è riuscito se almeno un giro su due chiudi queste "
                      "staccate sotto l'obiettivo.",
        ),
        "brake_late": dict(
            what="Stacchi dopo il tuo giro migliore, ma all'apex sei più lento. "
                 "Arrivi troppo forte, resti sul freno mentre giri e l'auto non "
                 "gira. Frena un po' prima, quanto basta per arrivare "
                 "all'apex col freno quasi finito.",
            watch="Guarda dove togli del tutto il piede dal freno. Deve succedere "
                  "prima dell'apex, non sopra.",
            ignore="Il metro che sembri perdere in staccata non conta, conta "
                   "quanto esci forte.",
            drill="Per i primi due giri frena una lunghezza d'auto prima del "
                  "solito, e senti l'auto che si inserisce senza tirare dritta. "
                  "Poi torna a frenare più tardi, mezza lunghezza a ogni "
                  "giro. Fermati quando l'anteriore torna a scivolare in ingresso, "
                  "e resta sull'ultimo punto in cui l'auto girava pulita.",
            done_when="Basta che la staccata lunga resti sotto l'obiettivo in metà "
                      "dei giri, e questo difetto è chiuso.",
        ),
        "over_brake": dict(
            what="Usi più freno del tuo giro migliore, o lo tieni premuto troppo "
                 "a lungo, e arrivi in curva più piano del necessario. Il punto "
                 "in cui stacchi va bene così. Quello che devi cambiare è come "
                 "lasci il pedale.",
            watch="Mentre giri il volante, senti quanto stai ancora premendo. Più "
                  "sterzo metti, meno freno deve restare.",
            ignore="Il punto di frenata resta dov'è, in questi giri non si tocca.",
            drill="Per due giri lascia il freno appena giri il volante. Uscirai "
                  "largo e lento, ed è voluto, perché ti serve sentire un estremo. "
                  "Per altri due tieni un filo di freno fino all'apex, che è "
                  "l'altro estremo, e sentirai l'auto girare di più ma "
                  "anche rallentare troppo. Negli ultimi due cerca il punto in "
                  "mezzo, dove l'auto gira senza fermarsi. Se il posteriore "
                  "scappa, non staccare il piede di colpo. Molla il freno piano e "
                  "raddrizza.",
            done_when="Quando il freno in più scende sotto l'obiettivo in almeno "
                      "metà dei giri, passi oltre.",
        ),
        "throttle_late": dict(
            what="In uscita apri il gas più tardi del tuo giro migliore, oppure "
                 "lo apri e poi lo richiudi. Di solito il motivo sta prima, in "
                 "ingresso. Se all'apex hai ancora il volante girato, il gas non "
                 "lo puoi dare.",
            watch="Guarda il punto d'uscita che hai scelto. Da lì il piede sul gas "
                  "va solo giù, senza mai tornare indietro.",
            ignore="Nella prima parte della curva accetta di perdere qualcosa.",
            drill="Scegli un riferimento all'uscita, un cordolo o una riga, e da "
                  "lì in poi il gas sale e non torna indietro. Per riuscirci entra "
                  "un filo più piano e più largo, così all'apex l'auto è già quasi "
                  "dritta. Apri il gas poco alla volta e continua ad aprire. Se le "
                  "ruote dietro pattinano, o senti il controllo di trazione "
                  "strozzare il motore, prova la stessa uscita con una marcia in "
                  "più.",
            done_when="Ti fermi quando l'uscita da queste curve resta sotto "
                      "l'obiettivo in un giro su due.",
        ),
        "min_speed": dict(
            what="Nel punto più lento della curva vai più piano del tuo giro "
                 "migliore. Di solito l'ingresso è troppo stretto, o l'ultima "
                 "parte della frenata ti toglie più velocità di quella che serve. "
                 "Quello che perdi lì lo paghi fino alla curva dopo.",
            watch="Guarda la velocità più bassa che tocchi in questa curva, e "
                  "nient'altro.",
            ignore="Non guardare il cronometro, questi sono giri di misura.",
            drill="Prendi la velocità minima che ti viene naturale e prova a "
                  "portarne un po' di più ogni giro. Stesso punto di frenata, e a "
                  "ogni giro premi un filo meno, un decimo di pedale e non metà. "
                  "Allarga l'ingresso di un paio di metri, perché un arco più "
                  "largo si fa più veloce. Quando l'auto comincia ad allargare o "
                  "il posteriore si alleggerisce, quella è la velocità che regge. "
                  "Se arrivi troppo forte, tieni il gas fermo e apri il volante, "
                  "senza alzare il piede di colpo.",
            done_when="Il traguardo è perdere a centro curva meno dell'obiettivo, in "
                      "almeno metà dei giri.",
        ),
        # Nuovo: l'alzata è misurata dove il riferimento resta in pieno
        # (debrief._lift_notes), quindi curvoni e pieghe veloci. COACHING-PRO
        # mette la vista al primo posto della gerarchia: l'alzata istintiva
        # nasce dall'occhio più che dall'auto.
        "lift": dict(
            what="Alzi il piede dal gas dove il tuo giro migliore resta in pieno, "
                 "di solito in un curvone veloce o in una piega del rettilineo. Il "
                 "tempo perso lì si moltiplica su tutto il dritto che segue.",
            watch="Guarda dove alzi e di quanto. Spesso è un'alzata breve e "
                  "istintiva, non una decisione.",
            ignore="Le curve lente lasciale come sono, l'esercizio riguarda solo i "
                   "tratti in pieno.",
            drill="Al primo giro alza nello stesso punto, ma meno, lasciando "
                  "giù quasi tutto il pedale invece di mollarne metà. A ogni giro alza meno "
                  "del giro prima, finché passi in pieno. Guarda lontano, verso "
                  "l'uscita del curvone. Quasi sempre l'alzata nasce da quello che "
                  "vedi, non da quello che fa l'auto. Se l'auto si muove sotto di "
                  "te, torna all'alzata del giro prima e restaci per altri due giri.",
            done_when="Le alzate sono sistemate quando, in metà dei giri, costano "
                      "meno dell'obiettivo.",
        ),
        # Nuovo: il veleggio misurato è quello *prima* del freno (GripState.
        # coast_s). Quello in inserimento, dopo la frenata, alcuni coach lo
        # usano apposta per far girare l'auto (COACHING-PRO §5.4): non va
        # condannato, e il testo lo dice.
        "coasting": dict(
            what="Fra il gas e il freno passi del tempo senza nessuno dei due "
                 "pedali, e l'auto rallenta da sola senza che tu ne approfitti. Il "
                 "piede deve passare dal gas al freno in un colpo solo.",
            watch="Guarda il punto di frenata. Il gas resta giù fino a lì.",
            ignore="Un attimo senza pedali in inserimento, dopo la frenata, a "
                   "volte serve a far girare l'auto. Quello lascialo com'è.",
            drill="Scegli il punto di frenata e tieni il gas a fondo fino a quel "
                  "punto, non un metro prima. Poi il piede va dritto sul freno, "
                  "senza pause. Se ti accorgi che alzi prima per prepararti, quel "
                  "punto di frenata per ora è troppo tardi per te. Frena dove alzi, "
                  "senza il vuoto in mezzo, e torna a frenare più tardi solo "
                  "quando il passaggio fra i pedali è pulito.",
            done_when="Il veleggio è a posto se in almeno un giro su due resta sotto "
                      "l'obiettivo.",
        ),
    },
    "en": {
        "brake_early": dict(
            what="You start braking earlier than you need to, and you drive that "
                 "stretch already slow. First learn to brake at the same spot every "
                 "lap, then move it later in small steps.",
            watch="On track, watch the minimum speed in the corner, the lowest you "
                  "reach. If it drops as you brake later, what you gain on the "
                  "brakes you give back in the corner.",
            ignore="Lap time doesn't count on these laps.",
            drill="Pick something you can see, a board or the start of a kerb, "
                  "and brake there for the first two laps. Then brake one car "
                  "length later every lap. Hit the brake hard straight away and "
                  "ease off as the car slows. When a wheel locks, or with ABS you "
                  "feel the pedal buzz and the car runs wide, go back to the "
                  "previous point and stay there to the end.",
            done_when="The drill has worked once at least one lap in two gets "
                      "through these braking zones under the target.",
        ),
        "brake_late": dict(
            what="You brake later than your best lap, but you're slower at the "
                 "apex. You arrive too fast, stay on the brake while turning, and "
                 "the car won't turn in. Brake a little earlier, just "
                 "enough to reach the apex with the brake almost off.",
            watch="Watch where your foot comes fully off the brake. It should "
                  "happen before the apex, not on it.",
            ignore="The metre you seem to lose on the brakes doesn't matter, what "
                   "matters is how fast you leave the corner.",
            drill="For the first two laps brake one car length earlier than "
                  "usual, and feel the car turn in without pushing straight. Then "
                  "brake later again, half a car length each lap. Stop "
                  "when the front starts to slide on entry again, and stay on the "
                  "last point where the car turned cleanly.",
            done_when="Keep the late braking under the target on half your laps, and "
                      "this one is closed.",
        ),
        "over_brake": dict(
            what="You use more brake than your best lap, or hold it too long, and "
                 "you reach the corner slower than you need to. Where you start "
                 "braking is fine as it is. What you need to change is how you "
                 "come off the pedal.",
            watch="As you turn the wheel, feel how hard you're still pressing. The "
                  "more steering you add, the less brake should be left.",
            ignore="Leave the braking point where it is, it doesn't move on these "
                   "laps.",
            drill="For two laps come off the brake as soon as you turn the wheel. "
                  "You'll run wide and slow, on purpose, because you need to feel one "
                  "extreme. For two more keep a touch of brake all the way to the "
                  "apex, the other extreme, and "
                  "you'll feel the car turn more but also slow down too much. On "
                  "the last two find the point in between, where the car turns "
                  "without stopping. If the rear steps out, don't jump off the "
                  "pedal. Ease off the brake and straighten up.",
            done_when="When the extra brake drops under the target on at least half "
                      "your laps, you move on.",
        ),
        "throttle_late": dict(
            what="On exit you open the throttle later than your best lap, or open "
                 "it and then close it again. The reason is usually earlier, on "
                 "entry. If the wheel is still turned at the apex, you can't use "
                 "the throttle.",
            watch="Watch the exit point you picked. From there your throttle foot "
                  "only goes down and never comes back.",
            ignore="In the first part of the corner, accept losing a little.",
            drill="Pick a reference on exit, a kerb or a line, and from there on "
                  "the throttle only goes up. To make it work, turn in a touch "
                  "slower and wider, so the car is almost straight at the apex. "
                  "Open the throttle a little at a time and keep opening. If the "
                  "rear wheels spin, or you hear traction control choke the "
                  "engine, try the same exit one gear higher.",
            done_when="You stop when the exit from these corners stays under the "
                      "target on one lap in two.",
        ),
        "min_speed": dict(
            what="At the slowest point of the corner you're slower than your best "
                 "lap. Usually the entry is too tight, or the end of your braking "
                 "takes away more speed than needed. What you lose there you pay "
                 "for all the way to the next corner.",
            watch="Watch the lowest speed you reach in this corner, and nothing "
                  "else.",
            ignore="Don't look at the clock, these are measuring laps.",
            drill="Take the minimum speed that comes naturally and try to carry a "
                  "bit more every lap. Keep the same braking point and press a "
                  "touch less each lap, a tenth of the pedal, not half. Widen the "
                  "entry by a couple of metres, because a wider arc is a faster "
                  "one. When the car starts to run wide or the rear goes light, "
                  "that is the speed it can hold. If you arrive too fast, hold the "
                  "throttle where it is and open the wheel, without lifting "
                  "sharply.",
            done_when="The goal is to lose less than the target mid-corner, on at "
                      "least half your laps.",
        ),
        "lift": dict(
            what="You lift off the throttle where your best lap stays flat, "
                 "usually in a fast sweeper or a kink on the straight. The time "
                 "lost there multiplies along the whole straight that follows.",
            watch="Watch where you lift and how much. It's often a short, "
                  "instinctive lift, not a decision.",
            ignore="Leave the slow corners as they are, this drill is only about "
                   "the flat-out sections.",
            drill="On the first lap lift at the same spot, but less, keeping "
                  "most of the pedal down instead of dropping half of it. Every lap lift less "
                  "than the one before, until you go through flat. Look far ahead, "
                  "towards the exit of the sweeper. The lift almost always comes "
                  "from what you see, not from what the car does. If the car moves "
                  "under you, go back to the previous lap's lift and stay there "
                  "for two more laps.",
            done_when="The lifts are sorted when they cost less than the target on "
                      "half your laps.",
        ),
        "coasting": dict(
            what="Between throttle and brake you spend time on neither pedal, and "
                 "that time is simply wasted. The car slows down without you "
                 "doing anything with it. Your foot should "
                 "go from throttle to brake in one move.",
            watch="Watch your braking point. The throttle stays down until you "
                  "get there.",
            ignore="A moment off both pedals while turning in, after the braking, "
                   "sometimes helps the car rotate. Leave that one as it is.",
            drill="Pick your braking point and keep the throttle flat right up to "
                  "it, not a metre before. Then your foot goes straight onto the "
                  "brake, with no pause. If you catch yourself lifting early to "
                  "get ready, that braking point is too deep for you for now. "
                  "Brake where you lift, with no gap in between, and only move the "
                  "braking later once the switch between pedals is clean.",
            done_when="The coasting is fixed if it stays under the target on at "
                      "least one lap in two.",
        ),
    },
}


def howto(key: str, lang: str) -> HowTo:
    return HowTo(laps=_LAPS[key], **_HOWTO[_lang(lang)][key])


# --- il glossario -------------------------------------------------------------

# Il glossario della vecchia scheda Allenamento (`training._GLOSSARY`), con le
# sue regole: solo le parole che la pagina usa, nell'ordine della pagina, ed e'
# sempre la *seconda* spiegazione. Qui la pagina e' il «Come si fa» di un
# difetto: le parole sono quelle del suo testo e del suo problema, piu' il giro
# di riferimento, che ogni vista nomina («Misurato contro…»).
_GLOSSARY_TERMS = {
    "brake_early": ("brake_point", "min_speed", "reference", "lockup"),
    "brake_late": ("brake_point", "apex", "reference"),
    "over_brake": ("brake_point", "apex", "reference", "trail_braking"),
    "throttle_late": ("apex", "reference", "wheelspin"),
    "min_speed": ("brake_point", "min_speed", "reference"),
    "lift": ("reference",),
    "coasting": ("brake_point", "reference"),
}


def glossary(key: str, lang: str) -> list[GlossaryEntry]:
    """Le parole del «Come si fa» di `key`, spiegate."""
    return glossary_of(_GLOSSARY_TERMS.get(key, ("reference",)), _lang(lang))


# --- il problema in una frase -----------------------------------------------

# Il corpo comincia minuscolo. Con una curva il nome apre come etichetta, «Ascari.
# Qui stacchi…», come nel modello approvato dal pilota: «In <nome>» sbaglia
# l'articolo con metà dei nomi. Senza curva (alzate e veleggio non hanno curve
# nel consiglio) niente «Qui»: la frase parla del giro intero, con la maiuscola.
_PROBLEM = {
    "it": {
        "brake_early": "stacchi prima del tuo giro migliore, e ci perdi {s} a giro.",
        "brake_early_m": "stacchi in media {m} prima del tuo giro migliore, e ci "
                         "perdi {s} a giro.",
        "brake_late": "stacchi dopo il tuo giro migliore ma all'apex sei più "
                      "lento, e ci perdi {s} a giro.",
        "brake_late_m": "stacchi in media {m} dopo il tuo giro migliore ma "
                        "all'apex sei più lento, e ci perdi {s} a giro.",
        "over_brake": "usi più freno del tuo giro migliore, e ci perdi {s} a giro.",
        "throttle_late": "apri il gas più tardi del tuo giro migliore, e ci perdi "
                         "{s} a giro.",
        "min_speed": "a centro curva vai più piano del tuo giro migliore, e ci "
                     "perdi {s} a giro.",
        "lift": "alzi il gas dove il tuo giro migliore resta in pieno, e ci perdi "
                "{s} a giro.",
        "coasting": "prima di frenare passi in media {s} a giro senza gas né freno.",
        "where": "{c}. Qui {body}",
        "metre": "{n} metro",
        "metres": "{n} metri",
    },
    "en": {
        "brake_early": "you brake earlier than your best lap, and it costs you {s} "
                       "a lap.",
        "brake_early_m": "you brake {m} earlier than your best lap on average, "
                         "and it costs you {s} a lap.",
        "brake_late": "you brake later than your best lap but you're slower at "
                      "the apex, and it costs you {s} a lap.",
        "brake_late_m": "you brake {m} later than your best lap on average but "
                        "you're slower at the apex, and it costs you {s} a lap.",
        "over_brake": "you use more brake than your best lap, and it costs you {s} "
                      "a lap.",
        "throttle_late": "you open the throttle later than your best lap, and it "
                         "costs you {s} a lap.",
        "min_speed": "you're slower than your best lap mid-corner, and it costs "
                     "you {s} a lap.",
        "lift": "you lift where your best lap stays flat, and it costs you {s} a "
                "lap.",
        "coasting": "before braking you spend {s} a lap on average off both "
                    "pedals.",
        "where": "{c}. Here {body}",
        "metre": "{n} m",
        "metres": "{n} m",
    },
}


def problem(key: str, corner_name: str, value: float, unit: str, lang: str,
            metres: float | None = None) -> str:
    """Il problema in una frase, coi numeri del pilota.

    ``value`` è nell'unità del difetto (ms per tutti, secondi di veleggio per
    il coasting). ``metres`` è lo scarto del punto di frenata dal giro migliore:
    si dice solo per i due difetti di staccata, dove è il numero che il pilota
    può andare a cercare in pista.
    """
    t = _PROBLEM[_lang(lang)]
    s = fmt_s(_seconds(value, unit), lang)
    n = round(abs(metres)) if metres is not None else 0
    if key in ("brake_early", "brake_late") and n >= 1:
        m = t["metre" if n == 1 else "metres"].format(n=n)
        body = t[key + "_m"].format(s=s, m=m)
    else:
        body = t[key].format(s=s)
    if corner_name:
        return t["where"].format(c=corner_name, body=body)
    return body[0].upper() + body[1:]


# --- il verdetto ------------------------------------------------------------

_VERDICT = {
    "it": {
        "gap": "In media perdi {s} a giro rispetto al tuo giro di riferimento",
        "even": "In media sei sul tempo del tuo giro di riferimento",
        "share": ", e il {p} % viene da {name}.",
        "top": ", e l'abitudine che pesa di più è {name}.",
        "end": ".",
        "first": "È la tua prima sessione qui. Il confronto arriva dalla prossima.",
        "less": "Rispetto alla sessione prima perdi {s} in meno a giro",
        "more": "Rispetto alla sessione prima perdi {s} in più a giro",
        "same": "Rispetto alla sessione prima perdi lo stesso tempo a giro",
        "down": "{names} in calo",
        "up": "{names} in crescita",
        "with": ", con {parts}.",
        "and": " e ",
        "q": "«{}»",
    },
    "en": {
        "gap": "On average you lose {s} a lap to your reference lap",
        "even": "On average you're level with your reference lap",
        "share": ", and {p} % of it comes from {name}.",
        "top": ", and the habit that weighs most is {name}.",
        "end": ".",
        "first": "This is your first session here. The comparison starts with "
                 "the next one.",
        "less": "Compared with the previous session you lose {s} less a lap",
        "more": "Compared with the previous session you lose {s} more a lap",
        "same": "Compared with the previous session you lose the same time a lap",
        "down": "{names} going down",
        "up": "{names} going up",
        "with": ", with {parts}.",
        "and": " and ",
        "q": "“{}”",
    },
}

# Sotto il mezzo centesimo, `fmt_s` stamperebbe «0,00 s in più»: è «uguale».
_SAME_S = 0.005


def verdict(mean_gap_s: float, top: DefectSummary | None, share: float,
            prev: dict | None, lang: str) -> str:
    """Com'è andata, in una o due frasi.

    ``share`` è la quota della perdita che viene da ``top``; il coasting non ne
    ha una (è in secondi di veleggio, non di perdita) e viene solo nominato.
    ``prev["gap_delta_s"]`` è la perdita di oggi meno quella della sessione
    prima: negativa vuol dire che perdi meno.
    """
    lg = _lang(lang)
    t = _VERDICT[lg]
    out = (t["gap"].format(s=fmt_s(mean_gap_s, lg)) if mean_gap_s >= _SAME_S
           else t["even"])
    if top is None:
        out += t["end"]
    else:
        name = t["q"].format(defect_name(top.key, lg))
        pct = min(100, round(share * 100))
        if top.unit == "ms" and pct >= 1:
            out += t["share"].format(p=pct, name=name)
        else:
            out += t["top"].format(name=name)
    if prev is None:
        return f"{out} {t['first']}"

    delta = prev.get("gap_delta_s", 0.0)
    if delta <= -_SAME_S:
        cmp_ = t["less"].format(s=fmt_s(-delta, lg))
    elif delta >= _SAME_S:
        cmp_ = t["more"].format(s=fmt_s(delta, lg))
    else:
        cmp_ = t["same"]
    parts = []
    for key, tpl in (("better", "down"), ("worse", "up")):
        keys = prev.get(key) or []
        if keys:
            names = t["and"].join(t["q"].format(defect_name(k, lg)) for k in keys)
            parts.append(t[tpl].format(names=names))
    cmp_ += t["with"].format(parts=t["and"].join(parts)) if parts else t["end"]
    return f"{out} {cmp_}"


# --- quando la Pagella non giudica, e quando un consiglio è raggiunto -------

# Al posto dei blocchi della Pagella: il motivo, detto una volta.
_EXCLUDED = {
    "it": {
        "wet": "Questa sessione è sul bagnato e il tuo storico è sull'asciutto. "
               "Resta fuori dall'andamento, perché le due cose non si confrontano.",
        "dry": "Questa sessione è sull'asciutto e il tuo storico è sul bagnato. "
               "Non entra nell'andamento finché non ne guidi un'altra così.",
        "no_reference": "Non c'è ancora un altro giro valido con cui confrontare "
                        "questa sessione. Il confronto parte dal prossimo giro pulito.",
        "reference_session": "In questa sessione c'è il tuo giro di riferimento "
                             "e nessun altro giro da misurare. Gli altri giri si "
                             "misurano contro di lui, lui contro sé stesso no.",
        "no_laps": "In questa sessione non c'è nessun giro valido da giudicare.",
    },
    "en": {
        "wet": "This session is on wet tyres and your history is on dry ones. It "
               "stays out of the trend, because the two don't compare.",
        "dry": "This session is on dry tyres and your history is on wet ones. It "
               "joins the trend once you drive another one like it.",
        "no_reference": "There's no other valid lap yet to compare this session "
                        "with. The comparison starts with your next clean lap.",
        "reference_session": "This session holds your reference lap and no other "
                             "lap to measure. Other laps are measured against it, "
                             "but it can't be measured against itself.",
        "no_laps": "This session has no valid lap to judge.",
    },
}

_REACHED = {
    "it": "Il consiglio su «{name}» è raggiunto, sotto l'obiettivo in {hits} giri "
          "su {laps}. Nel piano trovi il prossimo.",
    "en": "The advice on “{name}” is done, under the target on {hits} laps out of "
          "{laps}. The plan shows the next one.",
}


def excluded(reason: str, lang: str) -> str:
    """Perché questa sessione non ha pagella: bagnato, asciutto, niente metro o giri."""
    return _EXCLUDED[_lang(lang)][reason]


def reached(key: str, hits: int, laps: int, lang: str) -> str:
    """La frase che si aggiunge al verdetto quando la misura chiude un consiglio.

    ``hits`` è sempre almeno 2 (`measure_advice` chiede almeno due giri sotto
    obiettivo), quindi «giri» resta plurale.
    """
    lg = _lang(lang)
    return _REACHED[lg].format(name=defect_name(key, lg), hits=hits, laps=laps)

