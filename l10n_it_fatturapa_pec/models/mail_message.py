# Author(s): Andrea Colangelo (andreacolangelo@openforce.it)
# Copyright 2018 Openforce Srls Unipersonale (www.openforce.it)
# Copyright 2018 Sergio Corato (https://efatto.it)
# Copyright 2018 Lorenzo Battistini <https://github.com/eLBati>

from odoo import _, api, fields, models, modules, tools

class MailMessage(models.Model):
    _inherit = 'mail.message'
    _description = 'Message'

    recipients = fields.Text()
    references = fields.Text()
    in_reply_to = fields.Text()
    bounced_email = fields.Text()
    bounced_partner =  fields.Many2one('res.partner')
    bounced_msg_id = fields.Text()
    bounced_message = fields.Many2one('mail.message')
