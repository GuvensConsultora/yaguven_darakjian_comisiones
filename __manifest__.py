{
    'name': 'Darakjian — Comisiones',
    'summary': 'Comisiones por vendedor: tasa única por tramo (cliff) sobre el margen, criterio percibido.',
    'description': """
Módulo de comisiones para Darakjian Jewelers.

Lógica de negocio (definida por Ara, aclarada por Gabriel 2026-07-08):

- Objetivo mensual de volumen de ventas en USD, definido por Janel por vendedor.
- Tasa única por tramo sobre el TOTAL (efecto "cliff", NO marginal):
    * ventas < objetivo                     -> 3%
    * objetivo <= ventas < 125% objetivo    -> 6%
    * ventas >= 125% objetivo               -> 9%
- El porcentaje se aplica sobre el MARGEN (precio - costo), no sobre la facturación.
- Criterio PERCIBIDO: la comisión se vuelve pagable cuando la factura está cobrada.
- Cálculo MENSUAL, por vendedor INDIVIDUAL.

Diseño no invasivo: lee los nativos (account.move, account.move.line,
account.payment) como datasource de solo lectura y escribe únicamente en modelos
propios (yaguven.commission.*). No depende ni hereda del módulo de comisiones
nativo de Odoo (sale_commission).
""",
    'author': 'Yagüven C.G.',
    'maintainer': 'Yagüven C.G.',
    'category': 'Sales/Commissions',
    'version': '19.0.1.0.0',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'account',
        'product',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/commission_config_data.xml',
        'data/commission_cron.xml',
        'views/commission_config_views.xml',
        'views/commission_target_views.xml',
        'views/commission_line_views.xml',
        'views/menu.xml',
    ],
    'application': True,
    'installable': True,
    'auto_install': False,
}
