"""Score « Qualité de l'exploitation » (0-100).

Score raisonné (pas une réplication de la référence). Calibré pour un classement sensé
sur 6 valeurs : Renault ~16 (Médiocre), Pernod/Danone/Total/STMicro/BNP ~67-71 (Bon).
Voir PRD §5.8. Fonctions pures.
"""

from __future__ import annotations

from obole import config
from obole.models import CompanyKind


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def quality_score(
    roe_mean: float | None,
    roe_last: float | None,
    ca_decline_years: int | None,
    equity_to_assets_pct: float | None,
    kind: CompanyKind = CompanyKind.INDUSTRIAL,
) -> float | None:
    """Calcule le score 0-100. Renvoie None si données insuffisantes.

    roe_mean / roe_last en % ; ca_decline_years = nb d'années de baisse du CA ;
    equity_to_assets_pct = capitaux propres / total bilan en %.
    """
    if roe_mean is None and roe_last is None:
        return None

    w = config.QUALITY_WEIGHTS
    cap = config.QUALITY_ROE_CAP

    s_roe = _clamp(roe_mean or 0.0, 0, cap) / cap * w["roe_mean"]
    s_roe_last = _clamp(roe_last or 0.0, 0, cap) / cap * w["roe_last"]

    declines = ca_decline_years if ca_decline_years is not None else 0
    s_reg = _clamp(w["regularity"] - declines * 2, 0, w["regularity"])

    if kind is CompanyKind.FINANCIAL:
        # Banque : actif net/actif ~4-6 % est normal -> on neutralise.
        s_balance = float(w["balance"])
    else:
        eq = equity_to_assets_pct if equity_to_assets_pct is not None else 30.0
        s_balance = _clamp((eq - 10) / 30 * w["balance"], 0, w["balance"])

    return s_roe + s_roe_last + s_reg + s_balance
