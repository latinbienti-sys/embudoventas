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
.pestanas { display:flex; flex-wrap:wrap; gap:6px; margin-bottom:14px; }
.pestanas button { border:1px solid var(--borde); background:#fff; border-radius:6px; padding:7px 13px; font-size:13px; cursor:pointer; color:#3a4a5c; }
.pestanas button.activa { background:var(--azul); color:#fff; border-color:var(--azul); font-weight:600; }
.graf-dia { display:flex; align-items:flex-end; gap:2px; height:120px; margin-top:8px; }
.graf-dia .col { flex:1; display:flex; flex-direction:column; align-items:center; gap:4px; min-width:0; }
.graf-dia .col i { display:block; width:100%; background:var(--naranja); border-radius:3px 3px 0 0; position:relative; }
.graf-dia .col span { font-size:10px; color:#56657a; }
.graf-dia .col b { font-size:10px; }
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
    gestion = dashboard_app.build_gestion(dia)
    cierre = dashboard_app.build_cierre(dia)
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

    # ---- gestion diaria ----
    gs = gestion["stages"]
    mg = {s: (gestion["totals"][s]["meta"] if gestion["totals"].get(s) else 0) for s in gs}
    filas_gestion = ""
    for r in gestion["rows"]:
        celdas = ""
        for s in gs:
            lo = r["logrado"].get(s, 0)
            pe = r["pendiente"].get(s, 0)
            color = "#1e8e5a" if r["ok"].get(s) else "#0f3b6e"
            celdas += (f"<td class='num' style='border-bottom:1px solid var(--gris)'><b style='color:{color}'>{lo}</b>"
                       f"<div class='nota' style='font-size:10px'>pend {pe}</div></td>")
        filas_gestion += f"<tr><td>{esc(r['nombre'])}</td>{celdas}</tr>"
    tot_log = "".join(f"<td class='num'>{gestion['totals'][s]['logrado']}</td>" for s in gs)
    v = gestion["ventas"]
    venta_txt = (f"Venta del mes (Cierre): <b>US${v['logrado']:,.0f}</b> &middot; "
                 f"Meta: US${v['meta']:,.0f} &middot; Pendiente: US${v['pendiente']:,.0f}")

    t = cierre["total"]
    cierre_txt = (f"Resultado de la jornada del {dia.strftime('%d/%m/%Y')}: "
                  f"prospectaron <b>{t['prospect']}</b>, atendieron <b>{t['atendidos']}</b>, "
                  f"cerraron <b>{t['cierres']}</b>.")
    filas_cierre = ""
    for r in cierre["rows"]:
        filas_cierre += (
            f"<tr><td>{esc(r['nombre'])}</td><td class='num'>{r['prospect']}</td>"
            f"<td class='num'>{r['atendidos']}</td><td class='num'>{r['tienda']}</td>"
            f"<td class='num'><b style='color:{'#1e8e5a' if r['cierres'] else '#0f3b6e'}'>{r['cierres']}</b></td>"
            f"<td class='num'>US${r['venta']:,.2f}</td></tr>"
        )
    filas_cierre += (
        f"<tr class='total'><td>Total</td><td class='num'>{t['prospect']}</td>"
        f"<td class='num'>{t['atendidos']}</td><td class='num'>{t['tienda']}</td>"
        f"<td class='num'>{t['cierres']}</td><td class='num'>US${t['venta']:,.2f}</td></tr>"
    )

    # ---- enlaces PDF ----
    pdf_html = "".join(
        f'<a class="pdf" href="pdf/{esc(a)}" target="_blank">&#128196; {esc(a)}</a>' for a in archivos_pdf
    ) if archivos_pdf else "<span class='nota'>Sin PDFs aun (usa pdf_mensual.bat).</span>"

    est = f"&uacute;ltima sincronizaci&oacute;n: {esc(last_sync['run_at'])}" if last_sync else "sin sincronizar"
    dia_txt = f"dia {dia.strftime('%d/%m/%Y')}"
    mes_txt = f"{MESES[month_start.month]} {month_start.year}"

    # ---- vista por ejecutivo (info como el PDF, en pestanas) ----
    vista = dashboard_app.build_vista(dia)
    v_items = [vista["global"]] + vista["rows"]
    maxf = max([1] + [v for row in v_items for v in row["funnel"].values()])
    maxd = max([1] + [v for row in v_items for v in row["serie"]])

    vista_pest = "".join(
        f"<button data-i='{i}' class='{('activa' if not i else '')}'>{esc(row['nombre'])}</button>"
        for i, row in enumerate(v_items)
    )
    th_hdr = ['<th class="num">' + esc(s) + "</th>" for s in vista["stages"]]
    vista_pan = []
    for i, x in enumerate(v_items):
        celdas = ""
        for st in vista["stages"]:
            v = x["funnel"].get(st, 0) or 0
            an = round(v / maxf * 100) if v else 0
            celdas += (f"<td class='num'><div class='bar-fondo'>"
                       f"<i style='width:{an}%'>&nbsp;{v}</i></div></td>")
        cols = "".join(
            f"<div class='col'><b>{v}</b><i style='height:{max(3, round(v / maxd * 95))}px'></i>"
            f"<span>{di + 1}</span></div>"
            for di, v in enumerate(x["serie"])
        )
        meta_v = vista["sales_meta"] or 0
        pend_v = max(0, meta_v - x["venta_mes"])
        vista_pan.append(
            f"<div class='vista-panel' data-i='{i}' {'hidden' if i else ''}>"
            f"<p class='nota'><b>Informe del mes {esc(vista['mes'])}</b> &mdash; {esc(x['nombre'])}</p>"
            f"<div style='overflow-x:auto'><table>"
            f"<thead><tr><th>Flujo (embudo del mes)</th>{''.join(th_hdr)}</tr></thead>"
            f"<tbody><tr><td>{esc(x['nombre'])}</td>{celdas}</tr></tbody></table></div>"
            f"<p class='nota'>Venta mensual: <b>US${x['venta_mes']:,.0f}</b> &middot; "
            f"Meta: US${meta_v:,.0f} &middot; Pendiente: US${pend_v:,.0f}</p>"
            f"<p class='nota'>Atenci&oacute;n diaria del mes (creados + atendidos + contacto tienda)</p>"
            f"<div class='graf-dia'>{cols}</div></div>"
        )
    vista_html = (
        f"<div class='pestanas'>{vista_pest}</div>"
        f"<div class='panel-vista'>{''.join(vista_pan)}</div>"
        "<script>"
        "(function(){var p=document.querySelector('.panel-vista');"
        "var bts=document.querySelectorAll('.pestanas button');"
        "bts.forEach(function(b){b.onclick=function(){"
        "bts.forEach(function(z){z.classList.remove('activa');});"
        "b.classList.add('activa');"
        "Array.prototype.forEach.call(p.children,function(pl){"
        "pl.hidden = String(pl.getAttribute('data-i')) !== b.getAttribute('data-i');});};});})();"
        "</script>"
    )

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="3600">
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
    <h2>Gesti&oacute;n diaria (meta vs logrado hoy vs pendiente) &#8212; {esc(dia_txt)}</h2>
    <p class="nota">{venta_txt}</p>
    <div style="overflow-x:auto">
      <table>
        <thead><tr><th>Ejecutivo</th>{''.join(f'<th>{esc(s)}</th>' for s in gs)}</tr>
          <tr class='total'><th>Meta diaria</th>{''.join(f'<th class="num">{mg[s]}</th>' for s in gs)}</tr></thead>
        <tbody>{filas_gestion}<tr class='total'><td>Total logrado hoy</td>{tot_log}</tr></tbody>
      </table>
    </div>
  </section>

  <section class="tarjeta">
    <h2>Cierre del d&iacute;a por ejecutivo &#8212; {esc(dia_txt)}</h2>
    <p class="nota">{cierre_txt}</p>
    <p class="nota">Prospectados = nuevos CRM del d&iacute;a; Atendidos = clientes con actividad; Cierres = leads que pasaron a Cierre; Venta del d&iacute;a = monto de esos cierres.</p>
    <div style="overflow-x:auto">
      <table>
        <thead><tr>
          <th>Ejecutivo</th><th class="num">Prospectados</th><th class="num">Atendidos</th>
          <th class="num">Contacto Tienda</th><th class="num">Cierres</th><th class="num">Venta del d&iacute;a</th>
        </tr></thead>
        <tbody>{filas_cierre}</tbody>
      </table>
    </div>
  </section>

  <section class="tarjeta">
    <h2>Vista por ejecutivo (como el PDF del mes)</h2>
    <p class="nota">La info del informe PDF de cada ejecutivo, directamente en pesta&ntilde;as.</p>
    {vista_html}
  </section>

  <section class="tarjeta">
    <h2>Informes PDF del mes</h2>
    <p class="nota">Gen&eacute;ralos con pdf_mensual.bat (crea GLOBAL + uno por ejecutivo) y quedan visibles y descargables aqui.</p>
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