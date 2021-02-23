# Copyright 2014 Davide Corio
# Copyright 2015-2016 Lorenzo Battistini - Agile Business Group
# Copyright 2018 Simone Rubino - Agile Business Group
# Copyright 2018 Sergio Corato
# Copyright 2019 Alex Comba - Agile Business Group
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

import base64
import logging
import random
import string

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.translate import _

from .efattura import EFatturaOut

_logger = logging.getLogger(__name__)

try:
    from pyxb.utils import domutils
    from pyxb.binding.datatypes import decimal as pyxb_decimal
    from unidecode import unidecode
    from pyxb.exceptions_ import SimpleFacetValueError, SimpleTypeValueError
except ImportError as err:
    _logger.debug(err)



class FatturapaBDS(domutils.BindingDOMSupport):

    def valueAsText(self, value, enable_default_namespace=True):
        if isinstance(value, pyxb_decimal) and hasattr(value, '_CF_pattern'):
            # PyXB changes the text representation of decimals
            # so that it breaks pattern matching.
            # We have to use directly the string value
            # instead of letting PyXB edit it
            return str(value)
        return super(FatturapaBDS, self) \
            .valueAsText(value, enable_default_namespace)


fatturapaBDS = FatturapaBDS()




def id_generator(
    size=5, chars=string.ascii_uppercase + string.digits + string.ascii_lowercase
):
    return "".join(random.choice(chars) for dummy in range(size))


class WizardExportFatturapa(models.TransientModel):
    _name = "wizard.export.fatturapa"
    _description = "Export E-invoice"

    @api.model
    def _domain_ir_values(self):
        model_name = self.env.context.get("active_model", False)
        # Get all print actions for current model
        return [
            ("binding_model_id", "=", model_name),
            ("type", "=", "ir.actions.report"),
        ]

    report_print_menu = fields.Many2one(
        comodel_name="ir.actions.actions",
        domain=_domain_ir_values,
        help="This report will be automatically included in the created XML",
    )

    def saveAttachment(self, fatturapa, number):
        attach_obj = self.env["fatturapa.attachment.out"]
        vat = attach_obj.get_file_vat()

        attach_str = fatturapa.to_xml(self.env)
        attach_vals = {
            "name": "{}_{}.xml".format(vat, number),
            "datas": base64.encodebytes(attach_str),
        }
        return attach_obj.create(attach_vals)

    def getPartnerId(self, invoice_ids):

        invoice_model = self.env["account.move"]
        partner = False

        invoices = invoice_model.browse(invoice_ids)

        for invoice in invoices:
            if not partner:
                partner = invoice.partner_id
            if invoice.partner_id != partner:
                raise UserError(
                    _("Invoices %s must belong to the same partner.")
                    % invoices.mapped("number")
                )

        return partner

    def group_invoices_by_partner(self):
        invoice_ids = self.env.context.get("active_ids", False)
        res = {}
        for invoice in self.env["account.move"].browse(invoice_ids):
            if invoice.partner_id.id not in res:
                res[invoice.partner_id.id] = []
            res[invoice.partner_id.id].append(invoice.id)
        return res

    def exportFatturaPA(self):
        invoices_by_partner = self.group_invoices_by_partner()
        attachments = self.env["fatturapa.attachment.out"]
        for partner_id in invoices_by_partner:
            invoice_ids = invoices_by_partner[partner_id]
            partner = self.getPartnerId(invoice_ids)
            context_partner = self.env.context.copy()
            context_partner.update({"lang": partner.lang})

            progressivo_invio = id_generator()
            while self.env["fatturapa.attachment.out"].file_name_exists(
                progressivo_invio
            ):
                progressivo_invio = id_generator()

            invoice_ids = (
                self.env["account.move"]
                .with_context(context_partner)
                .browse(invoice_ids)
            )

            self.checkPaymentTerms(invoice_ids)
            fatturapa = EFatturaOut(self, partner, invoice_ids, progressivo_invio)

            attach = self.saveAttachment(fatturapa, progressivo_invio)
            attachments |= attach

            invoice_ids.write({"fatturapa_attachment_out_id": attach.id})

        action = {
            "name": "Export Electronic Invoice",
            "res_model": "fatturapa.attachment.out",
            "type": "ir.actions.act_window",
        }
        if len(attachments) == 1:
            action["view_mode"] = "form"
            action["res_id"] = attachments[0].id
        else:
            action["view_mode"] = "tree,form"
            action["domain"] = [("id", "in", attachments.ids)]
        return action

    def checkPaymentTerms(self,invoices):
        for invoice in invoices:
            if invoice.invoice_payment_term_id.fatturapa_pt_id.code is False:
                raise UserError(
                    _("Invoice %s fiscal payment term must be set for the selected payment term %s",
                    invoice.name, invoice.invoice_payment_term_id.name)
                )

            if invoice.invoice_payment_term_id.fatturapa_pm_id.code is False:
                raise UserError(
                    _("Invoice %s fiscal payment method must be set for the selected payment term %s",
                    invoice.name, invoice.invoice_payment_term_id.name)
                )
    def generate_attach_report(self, inv):
        binding_model_id = self.with_context(
            lang=None
        ).report_print_menu.binding_model_id.id
        name = self.report_print_menu.name
        report_model = (
            self.env["ir.actions.report"]
            .with_context(lang=None)
            .search([("binding_model_id", "=", binding_model_id), ("name", "=", name)])
        )
        attachment, attachment_type = report_model.render_qweb_pdf(inv.ids)
        att_id = self.env["ir.attachment"].create(
            {
                "name": "{}.pdf".format(inv.number),
                "type": "binary",
                "datas": base64.encodebytes(attachment),
                "res_model": "account.move",
                "res_id": inv.id,
                "mimetype": "application/x-pdf",
            }
        )
        inv.write(
            {
                "fatturapa_doc_attachments": [
                    (
                        0,
                        0,
                        {
                            "is_pdf_invoice_print": True,
                            "ir_attachment_id": att_id.id,
                            "description": _(
                                "Attachment generated by " "electronic invoice export"
                            ),
                        },
                    )
                ]
            }
        )
