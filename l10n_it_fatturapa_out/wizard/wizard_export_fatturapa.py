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
from functools import partial
from itertools import islice

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.translate import _

from .efattura import EFatturaOut

_logger = logging.getLogger(__name__)


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
        def getNewId():
            out = id_generator()
            while self.env["fatturapa.attachment.out"].file_name_exists(out):
                out = id_generator()
            return out

        invoices_by_partner = self.group_invoices_by_partner()
        attachments = self.env["fatturapa.attachment.out"]
        for partner_id in invoices_by_partner:
            invoice_ids = invoices_by_partner[partner_id]
            partner = self.getPartnerId(invoice_ids)
            context_partner = self.env.context.copy()
            context_partner.update({"lang": partner.lang})

            invoice_ids = (
                self.env["account.move"]
                .with_context(context_partner)
                .browse(invoice_ids)
            )

            invoice_ids.preventive_checks()

            # generate attachments (PDF version of invoice)
            for inv in invoice_ids:
                if not inv.fatturapa_doc_attachments and self.report_print_menu:
                    self.generate_attach_report(inv)

            # https://more-itertools.readthedocs.io/en/stable/_modules/more_itertools/recipes.html#take # noqa: B950
            def take(n, iterable):
                """Return first *n* items of the iterable as a list.

                    >>> take(3, range(10))
                    [0, 1, 2]

                If there are fewer than *n* items in the iterable, all of them are
                returned.

                    >>> take(10, range(3))
                    [0, 1, 2]

                """
                return list(islice(iterable, n))

            # https://more-itertools.readthedocs.io/en/stable/_modules/more_itertools/more.html#chunked # noqa: B950
            def chunked(iterable, n, strict=False):
                """Break *iterable* into lists of length *n*:

                    >>> list(chunked([1, 2, 3, 4, 5, 6], 3))
                    [[1, 2, 3], [4, 5, 6]]

                By the default, the last yielded list will have fewer than *n* elements
                if the length of *iterable* is not divisible by *n*:

                    >>> list(chunked([1, 2, 3, 4, 5, 6, 7, 8], 3))
                    [[1, 2, 3], [4, 5, 6], [7, 8]]

                To use a fill-in value instead, see the :func:`grouper` recipe.

                If the length of *iterable* is not divisible by *n* and *strict* is
                ``True``, then then ``ValueError`` will be raised before the last
                list is yielded.

                """
                iterator = iter(partial(take, n, iter(iterable)), [])
                if strict:

                    def ret():
                        for chunk in iterator:
                            if len(chunk) != n:
                                raise ValueError("iterable is not divisible by n.")
                            yield chunk

                    return iter(ret())
                else:
                    return iterator

            # TODO: integrate Fichera's changes from 12.0 - #1859
            # chunk_size = partner.max_invoice_in_xml or 1000
            chunk_size = 1000
            if not self.env.context.get("group_invoice", False):
                chunk_size = 1

            for invoice_chunk in chunked(invoice_ids, chunk_size):
                progressivo_invio = getNewId()
                fatturapa = EFatturaOut(self, partner, invoice_chunk, progressivo_invio)

                attach = self.saveAttachment(fatturapa, progressivo_invio)
                attachments |= attach

                for invoice in invoice_chunk:
                    invoice.write({"fatturapa_attachment_out_id": attach.id})

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
        attachment, attachment_type = report_model._render_qweb_pdf(inv.ids)
        att_id = self.env["ir.attachment"].create(
            {
                "name": "{}.pdf".format(inv.name),
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
