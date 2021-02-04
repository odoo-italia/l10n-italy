# -*- coding: utf-8 -*-
##############################################################################
#
#    OmniaSolutions, ERP-PLM-CAD Open Source Solutions
#    Copyright (C) 2011-2020 https://OmniaSolutions.website
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
Created on 15 Jan 2020

@author: mboscolo
'''

import os
import logging
import datetime
from io import BytesIO
from odoo import models
from odoo import fields
from odoo import api
from odoo import _
from odoo.exceptions import UserError
from datetime import timedelta
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT
from zipfile import ZipFile
import base64

class ImportFatturaPaZip(models.Model):
    _name = "import.fatturepa_zip"
    
    data = fields.Binary("File")
    
    def ImportIN(self):
        whereToExtract = os.path.join('/tmp', "IN_%s" % datetime.datetime.now().strftime('%Y%m%d%H%M'))
        with ZipFile(BytesIO(base64.b64decode(self.data)), 'r') as f:
            f.extractall(whereToExtract)
        imported_ids = self.env['fatturapa.attachment.in'].get_xml_customer_invoice(whereToExtract)
        return {
            "type": "ir.actions.act_window",
            "name": "Imported Invoice",
            "res_model": "fatturapa.attachment.in",
            "view_mode": "list,form",
            "view_type": "list",
            "domain": [('id','in', imported_ids.ids)]
        }  
        
        

    