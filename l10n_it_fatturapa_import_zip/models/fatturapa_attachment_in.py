# -*- coding: utf-8 -*-
##############################################################################
#
#    OmniaSolutions, ERP-PLM-CAD Open Source Solution
#    Copyright (C) 2011-2021 https://OmniaSolutions.website
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this prograIf not, see <http://www.gnu.org/licenses/>.
#
##############################################################################
'''
Created on 4 Feb 2021

@author: mboscolo
'''
import os
from pathlib import Path
import logging
import base64
from odoo import models
from odoo import fields
from odoo import api
from odoo import _
from odoo.tools.misc import format_date

class FatturaAttachmentIn(models.Model):
    _inherit = 'fatturapa.attachment.in'

    @api.depends('ir_attachment_id.datas')
    def _compute_xml_data(self):
        for att in self:
            try:
                wiz_obj = self.env['wizard.import.fatturapa'].with_context(from_attachment=att)
                fatt = wiz_obj.get_invoice_obj(att)
                cedentePrestatore = fatt.FatturaElettronicaHeader.CedentePrestatore
                partner_id = wiz_obj.getCedPrest(cedentePrestatore)
                att.xml_supplier_id = partner_id
                att.invoices_number = len(fatt.FatturaElettronicaBody)
                att.invoices_total = 0
                invoices_date = []
                try:
                    for invoice_body in fatt.FatturaElettronicaBody:
                        att.invoices_total += float(
                            invoice_body.DatiGenerali.DatiGeneraliDocumento.
                            ImportoTotaleDocumento or 0
                        )
                        invoice_date = format_date(
                            att.with_context(
                                lang=att.env.user.lang).env, fields.Date.from_string(
                                    invoice_body.DatiGenerali.DatiGeneraliDocumento.Data))
                        if invoice_date not in invoices_date:
                            invoices_date.append(invoice_date)
                    att.invoices_date = ' '.join(invoices_date)
                except Exception as ex:
                    logging.error(ex)
                    att.invoices_date = ' '
            except Exception as ex:
                logging.error(ex)
                att.invoices_date = ' '

    def create_fatturapa_from_file(self, file_path):
        file_path = str(file_path)
        file_name = os.path.basename(file_path)
        try:
            fatturapa_atts = self.search([('name', '=', file_name)])
            if fatturapa_atts:
                logging.info(
                    "Invoice xml already processed in %s"
                    % fatturapa_atts.mapped('name'))
            else:
                with open(file_path, 'rb') as f:
                    return self.create({'name': file_name,
                                        'datas': base64.b64encode(f.read())})
        except Exception as ex:
            logging.error("Unable to load the electronic invoice %s" % file_name)
            logging.error("File %r" % file_path)
            logging.error("%r" % ex)


    def get_xml_customer_invoice(self, pa_in_folder):
        out = self.env['fatturapa.attachment.in']
        for xml_file in Path(pa_in_folder).rglob("*.xml"):
            logging.info("Processing FatturaPA file: %r" % xml_file)
            out+=self.create_fatturapa_from_file(xml_file)
        return out  
