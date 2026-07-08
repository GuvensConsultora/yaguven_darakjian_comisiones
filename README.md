# yaguven_darakjian_comisiones

Módulo Odoo 19 — **Comisiones por vendedor** para Darakjian Jewelers.

Lógica de negocio (definida por Ara, aclarada por Gabriel 2026-07-08):

- **Objetivo mensual de volumen** de ventas en USD, definido por Janel mes a mes por vendedor.
- **Tasa única por tramo sobre el total** (efecto *cliff*, no marginal):
  - ventas `< objetivo` → **3%**
  - `objetivo ≤ ventas < 125% objetivo` → **6%**
  - `ventas ≥ 125% objetivo` → **9%**
- El porcentaje se aplica sobre el **margen** (precio − costo), no sobre la facturación.
- **Criterio percibido:** la comisión se vuelve pagable cuando la factura está cobrada.
- Cálculo **mensual**, por **vendedor individual**.

Diseño no invasivo: lee los nativos (`account.move`, `account.move.line`,
`account.payment`) como *datasource* de solo lectura y escribe únicamente en
modelos propios (`yaguven.commission.*`). No depende ni hereda del módulo de
comisiones nativo de Odoo (`sale_commission`).

Yagüven C.G.
