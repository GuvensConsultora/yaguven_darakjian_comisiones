import calendar
from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

MONTHS = [
    ('1', 'Enero'), ('2', 'Febrero'), ('3', 'Marzo'), ('4', 'Abril'),
    ('5', 'Mayo'), ('6', 'Junio'), ('7', 'Julio'), ('8', 'Agosto'),
    ('9', 'Septiembre'), ('10', 'Octubre'), ('11', 'Noviembre'), ('12', 'Diciembre'),
]

# Estados de cobro del comprobante que consideramos "percibido".
COLLECTED_STATES = ('in_payment', 'paid')


class YaguvenCommissionTarget(models.Model):
    """Objetivo mensual de comisión por vendedor + pantalla de resultado.

    Es lo único que carga Janel: vendedor, mes y objetivo de volumen. El resto
    (volumen real, tramo, comisión devengada y percibida) lo materializa el motor
    de recálculo leyendo las facturas nativas del vendedor en el mes.
    """

    _name = 'yaguven.commission.target'
    _description = 'Darakjian — Objetivo mensual de comisión'
    _inherit = ['mail.thread']
    _order = 'year desc, month desc, salesperson_id'
    _rec_name = 'name'

    name = fields.Char(compute='_compute_name', store=True)

    salesperson_id = fields.Many2one(
        'res.users',
        string='Vendedor',
        required=True,
        index=True,
        domain="[('share', '=', False)]",
        tracking=True,
    )
    year = fields.Integer(
        required=True,
        default=lambda self: fields.Date.context_today(self).year,
        tracking=True,
    )
    month = fields.Selection(
        MONTHS,
        required=True,
        default=lambda self: str(fields.Date.context_today(self).month),
        tracking=True,
    )
    objective_usd = fields.Monetary(
        string='Objetivo (USD)',
        currency_field='currency_id',
        tracking=True,
        help='Objetivo mensual de volumen de ventas. Lo define Janel.',
    )

    company_id = fields.Many2one(
        'res.company',
        required=True,
        index=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(related='company_id.currency_id', store=True)
    config_id = fields.Many2one(
        'yaguven.commission.config',
        string='Configuración de tramos',
        ondelete='restrict',
        default=lambda self: self.env['yaguven.commission.config']._get_for_company(self.env.company),
    )

    line_ids = fields.One2many('yaguven.commission.line', 'target_id')
    line_count = fields.Integer(compute='_compute_totals', store=True)

    # --- Agregados de la pantalla por vendedor ---
    volume_total = fields.Monetary(
        string='Volumen facturado',
        currency_field='currency_id',
        compute='_compute_totals',
        store=True,
    )
    margin_total = fields.Monetary(
        string='Margen total',
        currency_field='currency_id',
        compute='_compute_totals',
        store=True,
    )
    tier = fields.Selection(
        [('below', 'Bajo objetivo'), ('target', 'En objetivo'), ('super', 'Sobre objetivo')],
        string='Tramo alcanzado',
        compute='_compute_tier',
        store=True,
    )
    pct = fields.Float(
        string='% aplicado',
        digits=(5, 2),
        compute='_compute_tier',
        store=True,
    )
    commission_earned = fields.Monetary(
        string='Comisión devengada',
        currency_field='currency_id',
        compute='_compute_commission_earned',
        store=True,
    )
    commission_collected = fields.Monetary(
        string='Comisión cobrada',
        currency_field='currency_id',
        compute='_compute_totals',
        store=True,
    )
    commission_pending = fields.Monetary(
        string='Pendiente de cobro',
        currency_field='currency_id',
        compute='_compute_commission_pending',
        store=True,
    )
    last_recompute = fields.Datetime(string='Último recálculo', readonly=True)

    _sql_constraints = [
        (
            'salesperson_period_uniq',
            'unique(salesperson_id, year, month, company_id)',
            'Ya existe un objetivo para este vendedor en este mes.',
        ),
    ]

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends('salesperson_id', 'year', 'month')
    def _compute_name(self):
        month_label = dict(MONTHS)
        for rec in self:
            vendor = rec.salesperson_id.name or _('(sin vendedor)')
            rec.name = '%s — %s %s' % (vendor, month_label.get(rec.month, ''), rec.year)

    @api.depends('line_ids.volume', 'line_ids.margin', 'line_ids.commission_payable')
    def _compute_totals(self):
        for rec in self:
            rec.volume_total = sum(rec.line_ids.mapped('volume'))
            rec.margin_total = sum(rec.line_ids.mapped('margin'))
            rec.commission_collected = sum(rec.line_ids.mapped('commission_payable'))
            rec.line_count = len(rec.line_ids)

    @api.depends('volume_total', 'objective_usd', 'config_id',
                 'config_id.super_threshold_pct', 'config_id.pct_below',
                 'config_id.pct_target', 'config_id.pct_super')
    def _compute_tier(self):
        for rec in self:
            config = rec.config_id or self.env['yaguven.commission.config']._get_for_company(rec.company_id)
            rec.tier, rec.pct = config._resolve_tier(rec.volume_total, rec.objective_usd)

    @api.depends('margin_total', 'pct')
    def _compute_commission_earned(self):
        for rec in self:
            rec.commission_earned = rec.margin_total * rec.pct / 100.0

    @api.depends('commission_earned', 'commission_collected')
    def _compute_commission_pending(self):
        for rec in self:
            rec.commission_pending = rec.commission_earned - rec.commission_collected

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------
    @api.constrains('year', 'month')
    def _check_period(self):
        for rec in self:
            if rec.year < 2000 or rec.year > 2100:
                raise ValidationError(_('El año del período no es válido.'))

    # ------------------------------------------------------------------
    # Motor de recálculo
    # ------------------------------------------------------------------
    def _period_range(self):
        self.ensure_one()
        y, m = self.year, int(self.month)
        last_day = calendar.monthrange(y, m)[1]
        return date(y, m, 1), date(y, m, last_day)

    def _find_moves(self, date_from, date_to):
        """Facturas y NC posteadas del vendedor en el período (datasource nativo)."""
        self.ensure_one()
        return self.env['account.move'].search([
            ('company_id', '=', self.company_id.id),
            ('state', '=', 'posted'),
            ('move_type', 'in', ('out_invoice', 'out_refund')),
            ('invoice_user_id', '=', self.salesperson_id.id),
            ('invoice_date', '>=', date_from),
            ('invoice_date', '<=', date_to),
        ])

    def _move_snapshot(self, move):
        """Snapshot de volumen (neto) y costo del comprobante, en moneda de la compañía.

        NC (out_refund) entran con signo negativo. El costo usa el costo del
        producto en Odoo (standard_price) leído en el contexto de la compañía.
        """
        self.ensure_one()
        company = self.company_id
        sign = -1.0 if move.move_type == 'out_refund' else 1.0
        net_move_ccy = 0.0
        cost_total = 0.0
        for line in move.invoice_line_ids.filtered(lambda l: l.product_id):
            net_move_ccy += line.price_subtotal
            unit_cost = line.product_id.with_company(company).standard_price
            cost_total += unit_cost * line.quantity
        # Neto en moneda de la compañía (USD); el costo ya viene en moneda de la compañía.
        if move.currency_id and move.currency_id != company.currency_id:
            rate_date = move.invoice_date or fields.Date.context_today(self)
            net_company = move.currency_id._convert(
                net_move_ccy, company.currency_id, company, rate_date)
        else:
            net_company = net_move_ccy
        return {
            'volume': sign * net_company,
            'cost_total': sign * cost_total,
            'is_collected': move.payment_state in COLLECTED_STATES,
        }

    def _recompute_one(self):
        self.ensure_one()
        config = self.config_id or self.env['yaguven.commission.config']._get_for_company(self.company_id)
        date_from, date_to = self._period_range()
        moves = self._find_moves(date_from, date_to)

        existing = {line.move_id.id: line for line in self.line_ids}
        seen = set()
        for move in moves:
            seen.add(move.id)
            snap = self._move_snapshot(move)
            line = existing.get(move.id)
            if line:
                # Volumen y costo quedan congelados; solo refrescamos el cobro.
                line.is_collected = snap['is_collected']
            else:
                self.env['yaguven.commission.line'].create({
                    'target_id': self.id,
                    'move_id': move.id,
                    'volume': snap['volume'],
                    'cost_total': snap['cost_total'],
                    'is_collected': snap['is_collected'],
                })
        # Bajas: comprobantes que dejaron de calificar (despoteados/cancelados/reasignados).
        stale = self.line_ids.filtered(lambda l: l.move_id.id not in seen)
        stale.unlink()

        # Tramo por el volumen del mes y % único aplicado a todas las líneas (cliff).
        volume_total = sum(self.line_ids.mapped('volume'))
        _tier, pct = config._resolve_tier(volume_total, self.objective_usd)
        if self.line_ids:
            self.line_ids.write({'pct_applied': pct})
        self.last_recompute = fields.Datetime.now()

    def _recompute(self):
        for target in self:
            target._recompute_one()
        return True

    def action_recompute(self):
        self.with_context(skip_commission_recompute=True)._recompute()
        return True

    # ------------------------------------------------------------------
    # Disparadores automáticos
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.with_context(skip_commission_recompute=True)._recompute()
        return records

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get('skip_commission_recompute'):
            triggers = {'objective_usd', 'salesperson_id', 'year', 'month', 'company_id', 'config_id'}
            if triggers & set(vals):
                self.with_context(skip_commission_recompute=True)._recompute()
        return res

    @api.model
    def _cron_recompute(self):
        """Refresca el mes en curso y el anterior (cobros que van entrando)."""
        today = fields.Date.context_today(self)
        prev = today.replace(day=1) - date.resolution
        targets = self.search(
            ['|',
             '&', ('year', '=', today.year), ('month', '=', str(today.month)),
             '&', ('year', '=', prev.year), ('month', '=', str(prev.month))]
        )
        targets.with_context(skip_commission_recompute=True)._recompute()
        return True
