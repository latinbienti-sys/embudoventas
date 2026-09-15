# -*- coding: utf-8 -*-
"""Graficos del historico diario por ejecutivo (matplotlib, PNG).

grafico_historico(historico, nombre_seleccion) -> bytes PNG.
- Barras apiladas: prospectados / atendidos / cierres por dia.
- Linea: venta del dia (eje derecho).
"""
import io
from datetime import date

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.dates as mdates  # noqa: E402

COLORES = {"prospect": "#2f7cc9", "atendidos": "#1e8e5a", "cierres": "#e07b2a"}
COLOR_VENTA = "#8a1d1d"


def _serie(historico, nombre_seleccion, dias):
    """Devuelve dict {ds: {prospect, atendidos, cierres, venta}} para la seleccion."""
    if nombre_seleccion == "GLOBAL" or not nombre_seleccion:
        return {ds: historico["totales"].get(ds, {}) for ds in dias}
    e = next((x for x in historico["ejecutivos"] if x["nombre"] == nombre_seleccion), None)
    if not e:
        return {ds: {} for ds in dias}
    return {ds: (historico["rend"].get(ds, {}) or {}).get(str(e["uid"]), {}) for ds in dias}


def grafico_historico(historico, nombre_seleccion="GLOBAL"):
    dias = historico["dias"]
    serie = _serie(historico, nombre_seleccion, dias)
    fechas = [date.fromisoformat(d) for d in dias]

    prospect = [serie[ds].get("prospect", 0) or 0 for ds in dias]
    atendidos = [serie[ds].get("atendidos", 0) or 0 for ds in dias]
    cierres = [serie[ds].get("cierres", 0) or 0 for ds in dias]
    venta = [serie[ds].get("venta", 0) or 0 for ds in dias]

    fig, ax = plt.subplots(figsize=(11, 4.2), dpi=90)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    b1 = ax.bar(fechas, prospect, color=COLORES["prospect"], label="Prospectados", width=0.7)
    b2 = ax.bar(fechas, atendidos, bottom=prospect, color=COLORES["atendidos"],
                label="Atendidos", width=0.7)
    b3 = ax.bar(fechas, cierres, bottom=[p + a for p, a in zip(prospect, atendidos)],
                color=COLORES["cierres"], label="Cierres", width=0.7)

    ax2 = ax.twinx()
    if any(v for v in venta):
        ax2.plot(fechas, venta, color=COLOR_VENTA, marker="o", linewidth=2, label="Venta del día")
        ax2.set_ylabel("Venta del día (US$)")
    else:
        ax2.set_yticks([])
    ax2.tick_params(axis="y")

    ax.set_title(f"Histórico diario de gestión — {nombre_seleccion or 'GLOBAL'}", fontsize=13)
    ax.set_ylabel("Gestión del día")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
    ax.grid(axis="y", alpha=0.3)
    ax.legend(loc="upper left", fontsize=9)
    if any(v for v in venta):
        ax2.legend(loc="upper right", fontsize=9)

    for bars in (b1, b2, b3):
        ax.bar_label(bars, fontsize=7, color="#333", padding=1)

    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()