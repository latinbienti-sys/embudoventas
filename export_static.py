# -*- coding: utf-8 -*-
"""Genera la version estatica del tablero para GitHub Pages (docs/).

Se ejecuta tras cada sincronizacion (sincronizar.bat) y al crear los PDFs
(pdf_mensual.bat), y se sube con:
    python export_static.py  ->  crea docs/index.html + docs/pdf/*.pdf
La pagina queda publica en https://latinbienti-sys.github.io/embudoventas/
(La version con botones +/- y consulta viva a Odoo sigue siendo el tablero
local: http://127.0.0.1:8080)
"""
import shutil
from datetime import date, datetime
from pathlib import Path

import dashboard_app
import store

BASE = Path(__file__).parent
SITE = BASE / "docs"
PDFS = SITE / "pdf"

MESES = {1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
         7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"}

CSS = """
:root { --azul:#0f3b6e; --naranja:#e07b2a; --gris:#eef1f5; --borde:#d3dae3; }
* { box-sizing: border-box; }
body { font-family: "Segoe UI", Arial, sans-serif; margin: 0; background: #f4f6f9; color: #1c2733; }
header { background: var(--azul); color: #fff; padding: 14px 22px; }
header h1 { font-size: 18px; margin: 0 0 2px; }
.sub { font-size: 12px; opacity: .85; }
main { padding: 20px; max-width: 1200px; margin: 0 auto; }
.tarjeta { background: #fff; border: 1px solid var(--borde); border-radius: 10px; padding: 16px; margin-bottom: 18px; }
.tarjeta h2 { margin: 0 0 12px; font-size: 15px; color: var(--azul); }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { border-bottom: 1px solid var(--gris); padding: 8px 10px; text-align: left; }
th { background: #f8fafc; color: #56657a; font-weight: 600; }
tr.total td { font-weight: 700; background: #f2f7ff; }
.num { text-align: center; }
.bar-fondo { background: var(--gris); border-radius: 8px; height: 16px; min-width: 80px; }
.bar-fondo > i { display:block; height: 16px; border-radius: 8px; background: var(--naranja); font-style: normal; color:#fff; font-size:10px; line-height:16px; padding-left:4px; }
a.pdf { display:inline-block; margin:0 6px 8px 0; padding:6px 12px; border:1px solid var(--borde); border-radius:6px; text-decoration:none; color:var(--azul); background:#fff; font-size:13px; }
.nota { font-size: 12px; color: #56657a; }
.aviso { color:#8a1d1d; font-weight:600; }
.foot { color:#8a939c; font-size:12px; margin-top:10px; text-align:center; }
"""


def esc(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def main():
    SITE.mkdir(exist_ok=True)
    PDFS.mkdir(exist_ok=True)

    last = store.last_snapshot_date(dashboard_app.cfg["sqlite_path"])
    if not last:
        raise SystemExit("Sin datos: primero ejecuta sincronizar.bat")
    dia = date.fromisoformat(last[:10])
    month_start = dia.replace(day=1)

    daily, daily_total = dashboard_app.build_daily_panel(dia)
    header, funnel, funnel_total = dashboard_app.build_funnel(dia)
    last_sync = store.last_sync_ok(dashboard_app.cfg["sqlite_path"])
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ---- PDFs al sitio ----
    src_pdf = Path(dashboard_app.cfg.get("pdf_output_dir", "pdf_reports"))
    for old in PDFS.glob("*.pdf"):
        old.unlink()
    if src_pdf.exists():
        for p in src_pdf.glob("*.pdf"):
            shutil.copy(p, PDFS / p.name)
    archivos_pdf = sorted(host.name for host in PDFS.glob("*.pdf"))

    # ---- filas diarias ----
    filas_diarias = "".join(
        f"<tr><td>{esc(r['nombre'])}</td><td class='num'>{r['creados']}</td>"
        f"<td class='num'>{r['atendidos']}</td><td class='num'>{r['actividades']}</td>"
        f"<td class='num'>{r['tienda']}</td><td class='num'>{r['total']}</td></tr>"
        for r in daily
    )
    filas_diarias += (
        f"<tr class='total'><td>Total</td><td class='num'>{daily_total['creados']}</td>"
        f"<td class='num'>{daily_total['atendidos']}</td>"
        f"<td class='num'>{daily_total['actividades']}</td>"
        f"<td class='num'>{daily_total['tienda']}</td>"
        f"<td class='num'>{daily_total['total']}</td></tr>"
    )

    # ---- embudo del mes con barras ----
    maxf = max([1] + [r[s] or 0 for r in funnel for s in header[1:]])
    filas_embudo = ""
    for r in funnel:
        celdas = ""
        for s in header[1:]:
            v = r[s] or 0
            ancho = round(v / maxf * 100) if v else 0
            celdas += (f"<td class='num'><div class='bar-fondo'>"
                       f"<i style='width:{ancho}%'>&nbsp;{v}</i></div></td>")
        filas_embudo += f"<tr><td>{esc(r['nombre'])}</td>{celdas}</tr>"
    filas_embudo += "<tr class='total'><td>Total</td>" + "".join(
        f"<td class='num'>{funnel_total[s] or 0}</td>" for s in header[1:]) + "</tr>"

    encabezado_embudo = "<tr>" + "".join(f"<th>{esc(h)}</th>" for h in header) + "</tr>"

    # ---- enlaces PDF ----
    pdf_html = "".join(
        f'<a class="pdf" href="pdf/{esc(a)}" target="_blank">&#128196; {esc(a)}</a>' for a in archivos_pdf
    ) if archivos_pdf else "<span class='nota'>Sin PDFs aun (usa pdf_mensual.bat).</span>"

    est = f"&uacute;ltima sincronizaci&oacute;n: {esc(last_sync['run_at'])}" if last_sync else "sin sincronizar"
    dia_txt = f"dia {dia.strftime('%d/%m/%Y')}"
    mes_txt = f"{MESES[month_start.month]} {month_start.year}"

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Embudo de Ventas - Latinbien</title>
<style>{CSS}</style>
</head>
<body>
<header>
  <h1>Embudo de Ventas &#8226; Latinbien</h1>
  <span class="sub">{est}</span> &nbsp;|&nbsp; <span class="sub">actualizado {ahora}</span>
</header>
<main>
  <section class="tarjeta">
    <h2>Clientes atendidos por ejecutivo &#8212; {esc(dia_txt)}</h2>
    <p class="nota">Columnas: nuevos en CRM, atendidos, actividades de seguimiento, contacto tienda y total del dia.</p>
    <div style="overflow-x:auto">
      <table>
        <thead><tr>
          <th>Ejecutivo</th><th class="num">Nuevos CRM</th><th class="num">Atendidos</th>
          <th class="num">Actividades</th><th class="num">Contacto Tienda</th><th class="num">Total</th>
        </tr></thead>
        <tbody>{filas_diarias}</tbody>
      </table>
    </div>
  </section>

  <section class="tarjeta">
    <h2>Embudo de ventas del mes (flujo) &#8212; {esc(mes_txt)}</h2>
    <p class="nota">Flujo del mes: movimientos de etapa por ejecutivo. Contacto Tienda y Seguimiento whatsapp se suman del seguimiento/registro local.</p>
    <div style="overflow-x:auto">
      <table>
        <thead>{encabezado_embudo}</thead>
        <tbody>{filas_embudo}</tbody>
      </table>
    </div>
  </section>

  <section class="tarjeta">
    <h2>Informes PDF del mes</h2>
    {pdf_html}
    <p class="nota" style="margin-top:10px">El tablero interactivo con botones +/− (Contacto Tienda) se abre localmente con dashboard.bat en http://127.0.0.1:8080.</p>
  </section>

  <div class="foot">Generado automaticamente desde el cache local (solo lectura, sin modificar Odoo).</div>
</main>
</body>
</html>
"""
    (SITE / "index.html").write_text(html, encoding="utf-8")
    print(f"Tablero estatico generado en docs/ ({len(daily)} ejecutivos, {len(archivos_pdf)} PDFs)")
    print("Publica con subir_web.bat (o desde sincronizar.bat / pdf_mensual.bat)")


if __name__ == "__main__":
    main()