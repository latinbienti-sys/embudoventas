# Embudo de Ventas - Dashboard + PDF mensual (Odoo 16, SOLO LECTURA)

Dashboard dinamico que consulta el **embudo de ventas del CRM de Odoo 16**, lo
muestra **por dia y por ejecutivo** y genera un **PDF visual mensual**.
El sistema **NUNCA modifica datos en el ERP**: usa la API **JSON-RPC** con
metodos de lectura, una vez al dia, y guarda un cache local.

## Como funciona

```
Odoo (solo lectura, JSON-RPC con sesion y cookies)
     | 1 vez al dia (Tarea programada de Windows: agendar_sync.bat)
     v
SQLite local (crm_cache.db)  <---------- el dashboard SOLO lee de aqui
     |                  ^
     v                  |
_Dashboard Flask_  ___boton [+/-] "Contacto Tienda" por ejecutivo___
   http://127.0.0.1:8080        (se guarda en el cache local, no en Odoo)
     |
     v
__PDF mensual visual (matplotlib)__
```

- La sincronizacion diaria baja (todo de sola lectura): ejecutivos, etapas del
  CRM, leads por etapa, leads creados/atendidos por dia, **actividades** de
  seguimiento, y **movimientos de etapa** (flujo).
- **Embudo = FLUJO DEL MES**: cuenta los *movimientos* de cada etapa por
  ejecutivo en el mes (quien entro a Cada etapa, oportunidades ganadas,
  facturados), no el stock acumulado.
- **Contacto Tienda**: no existe en el CRM y no tiene nombre; se contabiliza con
  un **boton en el tablero** que suma/resta por dia y ejecutivo en el cache
  local. No ensucia el embudo real de Odoo.
- **Ejecutivos activos**: solo se muestran los 9 ejecutivos de ventas
  configurados (whitelist `executives_active`); se excluyen usuarios de
  sistema/pools (`executives_exclude`).

## Seguridad

- `config.json` (con credenciales reales) esta **excluido de Git**. Aun no
  lo agregues ni lo edites en el repositorio. Solo se publica
  `config.example.json` con valores de ejemplo.
- El cliente rechaza cualquier metodo de escritura (`create`, `write`, `unlink`,
  `copy`, etc.) localmente, antes de enviarlo al ERP.
- Si la sesion del servidor expira a mitad de trabajo, re-autentica
  automaticamente (sigue siendo solo lectura).

## Puesta en marcha

1. Instalar Python 3.11+.
2. `instalar.bat` (instala flask y matplotlib).
3. Copiar `config.example.json` a `config.json` y completar:
   - `odoo.url`, `odoo.db`, `odoo.user`, `odoo.api_key` (API key Odoo 16).
   - `stage_mapping`: nombre de tu embudo -> etapas del CRM (normalizado sin
     tildes; "Contacto Tienda" y "Seguimiento whatsapp" no usan etapas).
   - `executives_active`: nombres de los ejecutivos que se muestran.
4. `sincronizar.bat` (primer llenado: ultimos 45 dias; luego a diario).
5. `dashboard.bat` y abrir http://127.0.0.1:8080
6. `agendar_sync.bat` una sola vez para que la sincronizacion corra CADA dia a
   las 06:30 sin afectar la operacion.
7. `pdf_mensual.bat` escribe el PDF del mes; tambien se descarga desde el tablero.