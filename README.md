# Embudo de Ventas - Dashboard + PDF mensual (Odoo 16, solo lectura)

Dashboard dinamico que consulta el **embudo de ventas del CRM de Odoo 16** y lo
muestra por dia por ejecutivo, generando **PDF visual mensual**. El sistema
**NUNCA modifica datos en el ERP**: solo usa la API XML-RPC con metodos de
lectura, una vez al dia, y guarda un cache local.

## Como funciona

```
Odoo (solo lectura, XML-RPC)
     | 1 vez al dia (Tarea programada de Windows: agendar_sync.bat)
     v
SQLite local (crm_cache.db)  <-- <-- dashboard lee SOLO de aqui
     |                ^
     v                |
_Dashboard Flask_  __boton [+] "Contacto Tienda" por ejecutivo__
   http://127.0.0.1:8080        (se guarda en el cache local)
     |
     v
__PDF mensual visual (matplotlib)__
```

- La sincronizacion diaria baja: etapas del CRM, ejecutivos (usuarios con leads),
  embudo por etapa y por ejecutivo, leads creados por dia y leads atendidos por dia.
- **Contacto Tienda**: no existe en el CRM y no tiene nombre, por lo que se
  contabiliza con un **boton en el tablero** que suma por dia y por ejecutivo en
  el cache local. No contamina el embudo real de Odoo.

## Puesta en marcha

1. Instalar Python 3.11+.
2. `instalar.bat` (instala flask y matplotlib).
3. Copiar `config.example.json` a `config.json` y completar:
   - `odoo.url`, `odoo.db`, `odoo.user`, `odoo.api_key` (API key de Odoo 16).
   - `funnel_stages`: nombres EXACTOS de tus etapas en el CRM.
   - `executives`: ejecutivos que no aparezcan en el CRM (opcional).
4. `sincronizar.bat` (primer llenado: ultimos 45 dias; luego a diario).
5. `dashboard.bat` y abrir http://127.0.0.1:8080
6. `agendar_sync.bat` una sola vez para que la sincronizacion corra sola CADA dia
   a las 06:30 sin afectar la operacion.
7. `pdf_mensual.bat` escribe el PDF mensual; tambien se descarga desde el tablero.

## Notas de seguridad

- `config.json` contiene credenciales y esta excluido del repo (.gitignore).
- Las consultas a Odoo son exclusivamente `search_read`/`read`; no existe ninguna
  llamada de escritura hacia el ERP.
- La base local se crea sola; si se borra, `sincronizar.bat` la reconstruye.