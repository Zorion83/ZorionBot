"""Régression : les bougies en cache doivent être réécrites, pas seulement ajoutées.

IG renvoie la bougie en cours dès son ouverture. Le cycle tournant 5 s après la
demi-heure, elle arrive quasi vide (open ≈ high ≈ low ≈ close). L'ancienne version
du cache l'ajoutait puis l'ignorait à jamais (filtre sur les timestamps connus), si
bien que toutes les barres restaient figées sur leur premier instantané et que l'ATR
était sous-évalué d'environ 37 %.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from main import _merge_candles, _refetch_start


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


def test_refetch_remonte_de_plusieurs_barres():
    barres = [bougie(f"T{i}", 1, 1, 1, 1) for i in range(5)]
    assert _refetch_start(barres, back=3) == "T2"   # 3 dernières réécrites
    assert _refetch_start(barres, back=1) == "T4"


def test_refetch_tolere_un_cache_court_ou_vide():
    assert _refetch_start([], back=3) == ""
    assert _refetch_start([bougie("T0", 1, 1, 1, 1)], back=3) == "T0"
