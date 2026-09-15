# -*- coding: utf-8 -*-
"""Envio del cierre de gestion diario por WhatsApp via GoHighLevel (SOLO SALIDA).

Genera el mensaje (resumen + tabla por ejecutivo) para el dia indicado y lo
envia por WhatsApp usando la API de GoHighLevel (Conversations API):
  - gerencia  -> resumen + tabla completa
  - ejecutivo -> resumen + su fila (si tiene telefono configurado)

Credenciales SOLO en config.json (gitignored). Si no hay api_key configurada
(aun), el script funciona en modo prueba/imprimir mensaje (--test) y genera
enlaces wa.me para enviar manualmente.

Uso:
    python gohighlevel.py                                # dia de hoy, envia
    python gohighlevel.py --day 2026-09-14              # un dia concreto
    python gohighlevel.py --test                         # imprime, NO envia
"""
import argparse
import json
import sys
import urllib.request
import urllib.error
from datetime import date
from pathlib import Path

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))

import store
import dashboard_app  # noqa: E402  (reusa build_cierre + config)

cfg = dashboard_app.cfg


def _fecha(d: date):
    return d.strftime("%d/%m/%Y")


def _fila(x):
    return (f"{x['nombre'][:26]:<26} Pros {x['prospect']:>3} | Atd {x['atendidos']:>3} "
            f"| Tienda {x['tienda']:>3} | Cierre {x['cierres']:>3} | ${x['venta']:,.2f}")


def build_mensajes(day: date):
    """Construye los mensajes: (gerencia_texto, {nombre_norm: texto_ejecutivo})."""
    cierre = dashboard_app.build_cierre(day)
    t = cierre["total"]
    gestion = dashboard_app.build_gestion(day)
    v = gestion["ventas"]
    ventas_uid, _ = store.get_ventas_month(cfg["sqlite_path"], day.year, day.month)

    resumen = (
        f"\U0001F4CA CIERRE DE GESTION - LATINBIEN\n"
        f"Fecha: {_fecha(day)}\n\n"
        f"RESUMEN DEL DIA\n"
        f"\u2022 Prospectados: {t['prospect']}\n"
        f"\u2022 Atendidos: {t['atendidos']}\n"
        f"\u2022 Cierres: {t['cierres']}\n"
        f"\u2022 Venta del dia: ${t['venta']:,.2f}\n"
        f"\u2022 Venta del mes: ${v['logrado']:,.2f} "
        f"(Meta ${v['meta']:,.0f}, pendiente ${v['pendiente']:,.2f})"
    )

    tabla = ""
    if cierre["rows"]:
        tabla = "\n\nTABLA DE CIERRE POR EJECUTIVO\n" + "\n".join(_fila(x) for x in cierre["rows"])
    else:
        tabla = "\n\n(sin registro de actividad para el dia)"

    gerencia = resumen + tabla

    por_ejec = {}
    for x in cierre["rows"]:
        nombre_norm = store.normalize(x["nombre"])
        venta_ej = ventas_uid.get(x["uid"], 0) or 0
        por_ejec[nombre_norm] = (
            resumen + "\n\nTU REGISTRO DE HOY\n"
            + _fila({**x, "venta": venta_ej})
            + f"\nVenta del mes a tu nombre: ${venta_ej:,.2f}"
        )
    return gerencia, por_ejec


def _http_json(url, payload, headers):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def _base_headers():
    g = cfg["gohighlevel"]
    return {
        "Authorization": f"Bearer {g['api_key']}",
        "Version": g.get("version", "2021-07-28"),
        "Content-Type": "application/json",
    }


def _find_or_create_contact(phone):
    g = cfg["gohighlevel"]
    headers = _base_headers()
    url = f"{g['api_base'].rstrip('/')}/contacts/lookup"
    try:
        data = _http_json(url, {"phone": phone}, headers)
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
        data = {"contact": None}
    contact = data.get("contact") if isinstance(data, dict) else None
    if contact and contact.get("id"):
        return contact["id"]
    creado = _http_json(f"{g['api_base'].rstrip('/')}/contacts",
                        {"phone": phone, "locationId": g["location_id"]}, headers)
    cid = creado.get("contact", {}).get("id")
    if not cid:
        raise RuntimeError(f"No se pudo crear el contacto para {phone}: {creado}")
    return cid


def _get_or_create_conversation(contact_id):
    g = cfg["gohighlevel"]
    headers = _base_headers()
    base = g["api_base"].rstrip("/")
    url = f"{base}/conversations?contactId={contact_id}&limit=1&locationId={g['location_id']}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read().decode())
    convs = data.get("conversations", []) or []
    if convs:
        return convs[0]["id"]
    creado = _http_json(f"{base}/conversations",
                        {"contactId": contact_id, "locationId": g["location_id"],
                         "source": "whatsapp"}, headers)
    cid = creado.get("conversation", {}).get("id") or creado.get("id")
    if not cid:
        raise RuntimeError(f"No se pudo crear conversacion para contacto {contact_id}: {creado}")
    return cid


def enviar_whatsapp(texto, telefono):
    """Envia un texto por WhatsApp a un telefono usando GoHighLevel."""
    g = cfg["gohighlevel"]
    cid = g.get("fixed_conversation_id")
    if not cid:
        contacto = _find_or_create_contact(telefono)
        cid = _get_or_create_conversation(contacto)
    url = f"{g['api_base'].rstrip('/')}/conversations/{cid}/messages"
    _http_json(url, {"messageType": "whatsapp", "body": texto}, _base_headers())
    return cid


def wa_links(texto, telefono):
    from urllib.parse import quote
    enlace = f"https://wa.me/{telefono}?text={quote(texto[:1200])}"
    return f"  wa.me/{telefono}: {enlace}"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--day", help="fecha YYYY-MM-DD (default hoy)")
    ap.add_argument("--test", action="store_true", help="imprime mensajes, NO envia")
    args = ap.parse_args()

    day = date.fromisoformat(args.day) if args.day else date.today()
    gerencia, por_ejec = build_mensajes(day)

    destinos = []
    for tel in cfg.get("gerencia_whatsapp", []):
        if tel:
            destinos.append((tel, gerencia))
    for nombre_norm, tel in cfg.get("ejecutivos_whatsapp", {}).items():
        if tel and nombre_norm in por_ejec:
            destinos.append((tel, por_ejec[nombre_norm]))

    print(f"Cierre de gestion {_fecha(day)} - {len(destinos)} destinatarios")
    for tel, texto in destinos:
        solo_fila = "fila ejecutivo" if texto is not gerencia else "completo"
        print(f"\n=== -> {tel} ({solo_fila}) ===")
        print(texto.replace("\U0001F4CA", "[Cierre]"))
        if args.test:
            print(wa_links(texto, tel))
            continue
        if not cfg.get("gohighlevel", {}).get("api_key"):
            print("  [AVISO] Sin api_key: no se envia. Usa --test o configura gohighlevel.api_key.")
            print(wa_links(texto, tel))
            continue
        try:
            cid = enviar_whatsapp(texto, tel)
            print(f"  ENVIADO (conversacion {cid})")
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR enviando a {tel}: {e}")


if __name__ == "__main__":
    main()