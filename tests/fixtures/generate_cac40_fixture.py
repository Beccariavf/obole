"""Génère la série CAC 40 figée de la calibration Clara Vallis.

Réseau requis, exécution MANUELLE et rare : la fixture est commitée pour que le
test de calibration tourne hors ligne et ne dérive pas avec les séances.

    .venv/bin/python tests/fixtures/generate_cac40_fixture.py

La série s'arrête au 2023-12-31 : régénérer la fixture est un acte explicite
(mettre à jour les fenêtres de calibration et les bornes si les mesures bougent).
"""

from __future__ import annotations

from pathlib import Path

START = "2000-01-01"
END = "2023-12-31"
OUT = Path(__file__).with_name("cac40_daily.csv")


def main() -> None:
    import pandas as pd
    import yfinance as yf

    hist = yf.Ticker("^FCHI").history(start=START, end="2024-01-01", auto_adjust=False)
    close = hist["Close"].dropna()
    close = close[close > 0].loc[:END]
    if close.empty:
        raise SystemExit("yfinance indisponible : aucune donnée ^FCHI")

    generated = pd.Timestamp.today().date().isoformat()
    lines = [
        "# CAC 40 (^FCHI) — clôtures quotidiennes, source Yahoo Finance.",
        f"# Généré le {generated} par generate_cac40_fixture.py — ne pas éditer à la main.",
        "date,close",
    ]
    lines += [f"{d.date().isoformat()},{v:.2f}" for d, v in close.items()]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(close)} lignes -> {OUT}")


if __name__ == "__main__":
    main()
