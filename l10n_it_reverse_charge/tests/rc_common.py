from odoo.tests.common import Form, TransactionCase


class ReverseChargeCommon(TransactionCase):
    def setUp(self):
        super(ReverseChargeCommon, self).setUp()
        self.invoice_model = self.env["account.move"].with_context(
            default_move_type="in_invoice"
        )
        self.invoice_line_model = self.env["account.move.line"]
        self.partner_model = self.env["res.partner"]

        cls._create_account()
        cls._create_taxes()
        cls._create_journals()
        cls._create_rc_types()
        cls._create_rc_type_taxes()
        cls._create_fiscal_position()

        cls.supplier_extraEU = cls.partner_model.create(
            {
                "name": "Extra EU supplier",
                "property_account_position_id": self.fiscal_position_extra.id,
            }
        )
        cls.supplier_intraEU = cls.partner_model.create(
            {
                "name": "Intra EU supplier",
                "property_account_position_id": self.fiscal_position_intra.id,
            }
        )
        cls.supplier_intraEU_exempt = cls.partner_model.create(
            {
                "name": "Intra EU supplier exempt",
                "property_account_position_id": self.fiscal_position_exempt.id,
            }
        )
        # self.invoice_account = (
        #     self.env["account.account"]
        #     .search(
        #         [
        #             (
        #                 "user_type_id",
        #                 "=",
        #                 self.env.ref("account.data_account_type_payable").id,
        #             )
        #         ],
        #         limit=1,
        #     )
        # ).id
        self.invoice_line_account = self.env["account.account"].search(
            [
                (
                    "user_type_id",
                    "=",
                    self.env.ref("account.data_account_type_expenses").id,
                )
            ],
            limit=1,
        )
        self.term_15_30 = self.env["account.payment.term"].create(
            {
                "name": "15 30",
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "value": "percent",
                            "value_amount": 50,
                            "days": 15,
                            "sequence": 1,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "value": "balance",
                            "days": 30,
                            "sequence": 2,
                        },
                    ),
                ],
            }
        )

    def create_invoice(self, partner, lines):
        move_form = Form(self.invoice_model)
        move_form.partner_id = partner
        for line in lines:
            with move_form.invoice_line_ids.new() as line_form:
                line_form.name = line["name"]
                line_form.product_id = line["product_id"]
                line_form.price_unit = line["price_unit"]
                line_form.account_id = line["account_id"]
                # if line.get('tax_ids'):
        return move_form.save()

    @classmethod
    def create_invoice(cls, partner, amounts, taxes=None, post=True):
        invoice = cls.init_invoice(
            "in_invoice", partner=partner, post=post, amounts=amounts, taxes=taxes
        )
        for line in invoice.invoice_line_ids:
            line.account_id = cls.invoice_line_account.id
        return invoice

    @classmethod
    def _create_account(cls):
        account_model = cls.env["account.account"]
        cls.account_selfinvoice = account_model.create(
            {
                "code": "295000",
                "name": "selfinvoice temporary",
                "user_type_id": cls.env.ref(
                    "account.data_account_type_current_liabilities"
                ).id,
            }
        )

    @classmethod
    def _create_taxes(cls):
        tax_model = cls.env["account.tax"]
        cls.tax_22ae = tax_model.create(
            {
                "name": "Tax 22% Purchase Extra-EU",
                "type_tax_use": "purchase",
                "amount": 22,
            }
        )
        cls.tax_22ai = tax_model.create(
            {
                "name": "Tax 22% Purchases Intra-EU",
                "type_tax_use": "purchase",
                "amount": 22,
            }
        )
        cls.tax_22vi = tax_model.create(
            {"name": "Tax 22% Sales Intra-EU", "type_tax_use": "sale", "amount": 22}
        )
        cls.tax_22ve = tax_model.create(
            {"name": "Tax 22% Sales Extra-EU", "type_tax_use": "sale", "amount": 22}
        )
        cls.tax_22 = tax_model.create(
            {"name": "Tax 22%", "type_tax_use": "purchase", "amount": 22}
        )
        cls.tax_0_pur = tax_model.create(
            {"name": "Tax 0%", "type_tax_use": "purchase", "amount": 0}
        )
        cls.tax_0_sal = tax_model.create(
            {"name": "Tax 0%", "type_tax_use": "sale", "amount": 0}
        )

    def _create_journals(self):
        journal_model = self.env["account.journal"]
        self.journal_selfinvoice = journal_model.create(
            {"name": "selfinvoice", "type": "sale", "code": "SLF"}
        )

        cls.journal_reconciliation = journal_model.create(
            {
                "name": "RC reconciliation",
                "type": "bank",
                "code": "SLFRC",
                "default_account_id": self.account_selfinvoice.id,
            }
        )

        self.journal_selfinvoice_extra = journal_model.create(
            {"name": "Extra Selfinvoice", "type": "sale", "code": "SLFEX"}
        )

        self.journal_cee_extra = journal_model.create(
            {"name": "Extra CEE", "type": "purchase", "code": "EXCEE"}
        )

    @classmethod
    def _create_rc_types(cls):
        rc_type_model = cls.env["account.rc.type"]
        cls.rc_type_ieu = rc_type_model.create(
            {
                "name": "Intra EU (selfinvoice)",
                "method": "selfinvoice",
                "partner_type": "supplier",
                "journal_id": cls.journal_selfinvoice.id,
                "payment_journal_id": cls.journal_reconciliation.id,
                "transitory_account_id": cls.account_selfinvoice.id,
            }
        )

        cls.rc_type_eeu = rc_type_model.create(
            {
                "name": "Extra EU (selfinvoice)",
                "method": "selfinvoice",
                "partner_type": "other",
                "with_supplier_self_invoice": True,
                "partner_id": cls.env.ref("base.main_partner").id,
                "journal_id": cls.journal_selfinvoice_extra.id,
                "supplier_journal_id": cls.journal_cee_extra.id,
                "payment_journal_id": cls.journal_reconciliation.id,
                "transitory_account_id": cls.account_selfinvoice.id,
            }
        )

        cls.rc_type_exempt = rc_type_model.create(
            {
                "name": "Intra EU (exempt)",
                "method": "selfinvoice",
                "partner_type": "supplier",
                "journal_id": cls.journal_selfinvoice.id,
                "payment_journal_id": cls.journal_reconciliation.id,
                "transitory_account_id": cls.account_selfinvoice.id,
            }
        )

    @classmethod
    def _create_rc_type_taxes(cls):
        rc_type_tax_model = cls.env["account.rc.type.tax"]
        cls.rc_type_tax_ieu = rc_type_tax_model.create(
            {
                "rc_type_id": cls.rc_type_ieu.id,
                "purchase_tax_id": cls.tax_22ai.id,
                "sale_tax_id": cls.tax_22vi.id,
            }
        )

        cls.rc_type_tax_eeu = rc_type_tax_model.create(
            {
                "rc_type_id": cls.rc_type_eeu.id,
                "purchase_tax_id": cls.tax_22ae.id,
                "sale_tax_id": cls.tax_22ve.id,
            }
        )

        cls.rc_type_tax_exempt = rc_type_tax_model.create(
            {
                "rc_type_id": cls.rc_type_exempt.id,
                "purchase_tax_id": cls.tax_0_pur.id,
                "sale_tax_id": cls.tax_0_sal.id,
            }
        )

    @classmethod
    def _create_fiscal_position(cls):
        model_fiscal_position = cls.env["account.fiscal.position"]
        cls.fiscal_position_intra = model_fiscal_position.create(
            {"name": "Intra EU", "rc_type_id": cls.rc_type_ieu.id}
        )

        cls.fiscal_position_extra = model_fiscal_position.create(
            {"name": "Extra EU", "rc_type_id": cls.rc_type_eeu.id}
        )

        cls.fiscal_position_exempt = model_fiscal_position.create(
            {"name": "Intra EU exempt", "rc_type_id": cls.rc_type_exempt.id}
        )
