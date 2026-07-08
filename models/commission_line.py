from odoo import api, fields, models


class YaguvenCommissionLine(models.Model):
    """Detalle de comisión por factura del vendedor en el mes.

    Una línea por comprobante (factura o nota de crédito) del vendedor dentro del
    período del ``target``. Los snapshots ``volume`` y ``cost_total`` se congelan
    al crear la línea (motor de recálculo en ``yaguven.commission.target``); el
    ``pct_applied`` y el estado de cobro se refrescan en cada recálculo, y de ahí
    se derivan los importes de comisión.
    """

    _name = 'yaguven.commission.line'
    _description = 'Darakjian — Línea de comisión'
    _order = 'target_id, invoice_date, move_id'

    target_id = fields.Many2one(
        'yaguven.commission.target',
        required=True,
        index=True,
        ondelete='cascade',
    )
    salesperson_id = fields.Many2one(
        related='target_id.salesperson_id',
        store=True,
        index=True,
    )
    company_id = fields.Many2one(
        related='target_id.company_id',
        store=True,
        index=True,
    )
    currency_id = fields.Many2one(
        related='company_id.currency_id',
        store=True,
    )

    # --- Comprobante origen (datasource nativo, solo lectura) ---
    move_id = fields.Many2one(
        'account.move',
        string='Comprobante',
        required=True,
        index=True,
        ondelete='cascade',
    )
    move_name = fields.Char(related='move_id.name', string='Número')
    invoice_date = fields.Date(related='move_id.invoice_date', store=True)
    move_type = fields.Selection(related='move_id.move_type')

    # --- Snapshots congelados a la fecha de la factura ---
    volume = fields.Monetary(
        currency_field='currency_id',
        help='Neto facturado atribuido (con signo: las notas de crédito restan).',
    )
    cost_total = fields.Monetary(
        currency_field='currency_id',
        help='Costo total de las líneas de producto, congelado a la fecha de la factura.',
    )
    margin = fields.Monetary(
        currency_field='currency_id',
        compute='_compute_margin',
        store=True,
        help='Margen = neto facturado − costo. Base de la comisión.',
    )

    # --- Tramo y comisión ---
    pct_applied = fields.Float(
        string='% aplicado',
        digits=(5, 2),
        help='Porcentaje del tramo alcanzado por el volumen del mes (cliff).',
    )
    commission_amount = fields.Monetary(
        string='Comisión devengada',
        currency_field='currency_id',
        compute='_compute_commission_amount',
        store=True,
    )

    # --- Cobro (criterio percibido) ---
    is_collected = fields.Boolean(
        string='Cobrada',
        help='La factura origen está cobrada (payment_state paid/in_payment).',
    )
    commission_payable = fields.Monetary(
        string='Comisión pagable',
        currency_field='currency_id',
        compute='_compute_commission_payable',
        store=True,
        help='Comisión que ya se puede pagar: devengada solo si la factura está cobrada.',
    )

    _sql_constraints = [
        (
            'target_move_uniq',
            'unique(target_id, move_id)',
            'Ya existe una línea de comisión para este comprobante en este período.',
        ),
    ]

    @api.depends('volume', 'cost_total')
    def _compute_margin(self):
        for rec in self:
            rec.margin = rec.volume - rec.cost_total

    @api.depends('margin', 'pct_applied')
    def _compute_commission_amount(self):
        for rec in self:
            rec.commission_amount = rec.margin * rec.pct_applied / 100.0

    @api.depends('commission_amount', 'is_collected')
    def _compute_commission_payable(self):
        for rec in self:
            rec.commission_payable = rec.commission_amount if rec.is_collected else 0.0
