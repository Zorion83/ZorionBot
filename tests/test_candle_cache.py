"""Régression : les bougies en cache doivent être réécrites, pas seulement ajoutées.

IG renvoie la bougie en cours dès son ouverture. Le cycle tournant 5 s après la
demi-heure, elle arrive quasi vide (open ≈ high ≈ low ≈ close). L'ancienne version
du cache l'ajoutait puis l'ignorait à jamais (filtre sur les timestamps connus), si
bien que toutes les barres restaient figées sur leur premier instantané et que l'ATR
était sous-évalué d'environ 37 %.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import asyncio
from datetime import datetime, timedelta, timezone

import main
from config import LOOKBACK_CANDLES
from main import _bars_to_fetch, _merge_candles


def bougie(t, o, h, l, c):
    return {"time": t, "open": o, "high": h, "low": l, "close": c}


def test_la_barre_en_cours_est_reecrite_une_fois_close():
    # telle qu'enregistrée 5 s après son ouverture
    instantane = [bougie("2026-08-20T17:00:00", 4510.57, 4510.97, 4510.41, 4510.41)]
    # telle que IG la renvoie une fois la demi-heure écoulée
    complete = [bougie("2026-08-20T17:00:00", 4510.57, 4516.87, 4507.64, 4512.64)]

    (barre,) = _merge_candles(instantane, complete)

    assert barre["high"] == 4516.87
    assert barre["low"] == 4507.64
    assert barre["high"] - barre["low"] > 9   # amplitude réelle, pas 0.56


def test_pas_de_doublon_et_ordre_chronologique():
    existant = [bougie("2026-08-20T16:00:00", 1, 1, 1, 1),
                bougie("2026-08-20T16:30:00", 2, 2, 2, 2)]
    entrant = [bougie("2026-08-20T16:30:00", 2, 9, 0, 5),
               bougie("2026-08-20T17:00:00", 3, 3, 3, 3)]

    fusion = _merge_candles(existant, entrant)

    assert [b["time"] for b in fusion] == ["2026-08-20T16:00:00",
                                           "2026-08-20T16:30:00",
                                           "2026-08-20T17:00:00"]
    assert fusion[1]["high"] == 9


def test_fusion_cas_limites():
    a = [bougie("T1", 1, 1, 1, 1)]
    assert _merge_candles(a, []) == a
    assert _merge_candles([], a) == a
    assert _merge_candles([], []) == []


UTC = timezone.utc


def serie(debut: str, n: int):
    t0 = datetime.fromisoformat(debut)
    return [bougie((t0 + timedelta(minutes=30 * k)).strftime("%Y-%m-%dT%H:%M:%S"),
                   100 + k, 101 + k, 99 + k, 100 + k) for k in range(n)]


def test_cycle_normal_redemande_quelques_barres():
    # cycle 09:00:05, dernière bougie connue = 08:30 (en cours au cycle précédent)
    cache = serie("2026-10-06T07:00:00", 4)
    now = datetime(2026, 10, 6, 9, 0, 5, tzinfo=UTC)
    assert _bars_to_fetch(cache, now) == 2 + 3


def test_reprise_apres_longue_coupure_couvre_tout_le_trou():
    # dernière bougie 09:00, reprise à 14:30:05 : 11 barres manquantes, 10 ne suffisaient pas
    cache = serie("2026-10-06T07:00:00", 5)
    now = datetime(2026, 10, 6, 14, 30, 5, tzinfo=UTC)
    assert _bars_to_fetch(cache, now) >= 11 + 1


def test_week_end_et_cache_vide_plafonnes():
    cache = serie("2026-10-02T19:00:00", 4)            # vendredi 20:30 en dernier
    dimanche = datetime(2026, 10, 4, 22, 0, 5, tzinfo=UTC)
    assert 99 <= _bars_to_fetch(cache, dimanche) <= LOOKBACK_CANDLES
    assert _bars_to_fetch([], dimanche) == LOOKBACK_CANDLES
    tres_vieux = serie("2026-01-01T10:00:00", 2)
    assert _bars_to_fetch(tres_vieux, dimanche) == LOOKBACK_CANDLES


class FauxIG:
    """Comme IG avec `max` : les `count` dernières bougies jusqu'à maintenant, barre en cours incluse."""
    def __init__(self, toutes):
        self.toutes, self.appels = toutes, []

    async def get_candles(self, epic, count, start=""):
        assert not start, "le bot ne doit plus demander de plage de dates"
        self.appels.append(count)
        return self.toutes[-count:]


def test_aucun_trou_apres_cinq_heures_sans_mise_a_jour(monkeypatch):
    # IG : bougies de 07:00 à 14:30 (barre en cours) ; cache arrêté à 09:00 (figée)
    toutes = serie("2026-10-06T07:00:00", 16)
    cache = [dict(b) for b in toutes[:5]]
    cache[-1].update(high=cache[-1]["open"] + 0.1, low=cache[-1]["open"] - 0.1)
    epic = "CS.D.CFEGOLD.CEF.IP"
    monkeypatch.setattr(main, "_candle_cache", {epic: cache})
    monkeypatch.setattr(main, "_startup_done", {epic})
    monkeypatch.setattr(main, "_save_disk_cache", lambda: None)

    class Horloge(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 6, 14, 30, 5, tzinfo=UTC)
    monkeypatch.setattr(main, "datetime", Horloge)

    candles = asyncio.run(main.get_fresh_candles(FauxIG(toutes), epic))

    assert [c["time"] for c in candles] == [c["time"] for c in toutes]   # aucun trou
    assert candles[4] == toutes[4]                                         # 09:00 réécrite
