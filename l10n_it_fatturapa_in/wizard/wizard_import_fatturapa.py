import logging
from datetime import datetime

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_is_zero
from odoo.tools.translate import _

from odoo.addons.base_iban.models.res_partner_bank import pretty_iban

from . import efattura

_logger = logging.getLogger(__name__)

WT_CODES_MAPPING = {
    "RT01": "ritenuta",
    "RT02": "ritenuta",
    "RT03": "inps",
    "RT04": "enasarco",
    "RT05": "enpam",
    "RT06": "other",
}


class WizardImportFatturapa(models.TransientModel):
    _name = "wizard.import.fatturapa"
    _description = "Import E-bill"

    e_invoice_detail_level = fields.Selection(
        [
            ("0", "Minimum"),
            ("1", "Tax rate"),
            ("2", "Maximum"),
        ],
        string="E-bills Detail Level",
        help="Minimum level: Bill is created with no lines; "
        "User will have to create them, according to what specified in "
        "the electronic bill.\n"
        "Tax rate level: Rate level: an invoice line is created for each "
        "rate present in the electronic invoice\n"
        "Maximum level: every line contained in the electronic bill "
        "will create a line in the bill.",
        required=True,
    )

    @api.model
    def default_get(self, fields):
        res = super(WizardImportFatturapa, self).default_get(fields)
        res["e_invoice_detail_level"] = "2"
        fatturapa_attachment_ids = self.env.context.get("active_ids", False)
        fatturapa_attachment_obj = self.env["fatturapa.attachment.in"]
        partners = self.env["res.partner"]
        for fatturapa_attachment_id in fatturapa_attachment_ids:
            fatturapa_attachment = fatturapa_attachment_obj.browse(
                fatturapa_attachment_id
            )
            if fatturapa_attachment.in_invoice_ids:
                raise UserError(
                    _("File %s is linked to bills yet.") % fatturapa_attachment.name
                )
            partners |= fatturapa_attachment.xml_supplier_id
            if len(partners) == 1:
                res["e_invoice_detail_level"] = partners[0].e_invoice_detail_level
        return res

    def CountryByCode(self, CountryCode):
        country_model = self.env["res.country"]
        return country_model.search([("code", "=", CountryCode)])

    def ProvinceByCode(self, provinceCode):
        province_model = self.env["res.country.state"]
        return province_model.search(
            [("code", "=", provinceCode), ("country_id.code", "=", "IT")]
        )

    def log_inconsistency(self, message):
        inconsistencies = self.env.context.get("inconsistencies", "")
        if inconsistencies:
            inconsistencies += "\n"
        inconsistencies += message
        # we can't set
        # self = self.with_context(inconsistencies=inconsistencies)
        # because self is a locale variable.
        # We use __dict__ to modify attributes of self
        # self.__dict__.update(
        #    self.with_context(inconsistencies=inconsistencies).__dict__
        # )
        # XXX - da controllare

    def check_partner_base_data(self, partner_id, DatiAnagrafici):
        partner = self.env["res.partner"].browse(partner_id)
        if (
            'Denominazione' in DatiAnagrafici.Anagrafica and DatiAnagrafici.Anagrafica.Denominazione
            and partner.name != DatiAnagrafici.Anagrafica.Denominazione
        ):
            self.log_inconsistency(
                _("Company Name field contains '%s'." " Your System contains '%s'")
                % (DatiAnagrafici.Anagrafica.Denominazione, partner.name)
            )
        if (
            'Nome' in DatiAnagrafici.Anagrafica and DatiAnagrafici.Anagrafica.Nome
            and partner.firstname != DatiAnagrafici.Anagrafica.Nome
        ):
            self.log_inconsistency(
                _("Name field contains '%s'." " Your System contains '%s'")
                % (DatiAnagrafici.Anagrafica.Nome, partner.firstname)
            )
        if (
            'Cognome' in DatiAnagrafici.Anagrafica and DatiAnagrafici.Anagrafica.Cognome
            and partner.lastname != DatiAnagrafici.Anagrafica.Cognome
        ):
            self.log_inconsistency(
                _("Surname field contains '%s'." " Your System contains '%s'")
                % (DatiAnagrafici.Anagrafica.Cognome, partner.lastname)
            )

    def getPartnerBase(self, DatiAnagrafici):  # noqa: C901
        if not DatiAnagrafici:
            return False
        partner_model = self.env["res.partner"]
        cf = False if 'CodiceFiscale' not in DatiAnagrafici else DatiAnagrafici.CodiceFiscale
        vat = False
        if 'IdFiscaleIVA' in DatiAnagrafici:
            # Format Italian VAT ID to always have 11 char
            # to avoid validation error when creating the given partner
            IdPaese = False if 'IdPaese' not in DatiAnagrafici.IdFiscaleIVA else DatiAnagrafici.IdFiscaleIVA.IdPaese
            IdCodice = "0" if 'IdCodice' not in DatiAnagrafici.IdFiscaleIVA else DatiAnagrafici.IdFiscaleIVA.IdCodice

            if IdPaese.upper() == "IT":
                vat = "{}{}".format(
                    IdPaese,
                    IdCodice.rjust(11, "0"),
                )
            else:
                vat = "{}{}".format(
                    DatiAnagrafici.IdFiscaleIVA.IdPaese,
                    DatiAnagrafici.IdFiscaleIVA.IdCodice,
                )
        partners = partner_model
        if vat:
            domain = [("vat", "=", vat)]
            if self.env.context.get("from_attachment"):
                att = self.env.context.get("from_attachment")
                domain.extend(
                    [
                        "|",
                        ("company_id", "child_of", att.company_id.id),
                        ("company_id", "=", False),
                    ]
                )
            partners = partner_model.search(domain)
        if not partners and cf:
            domain = [("fiscalcode", "=", cf)]
            if self.env.context.get("from_attachment"):
                att = self.env.context.get("from_attachment")
                domain.extend(
                    [
                        "|",
                        ("company_id", "child_of", att.company_id.id),
                        ("company_id", "=", False),
                    ]
                )
            partners = partner_model.search(domain)
        commercial_partner_id = False
        if len(partners) > 1:
            for partner in partners:
                if (
                    commercial_partner_id
                    and partner.commercial_partner_id.id != commercial_partner_id
                ):
                    raise UserError(
                        _(
                            "Two distinct partners with "
                            "VAT number %s or Fiscal Code %s already "
                            "present in db." % (vat, cf)
                        )
                    )
                commercial_partner_id = partner.commercial_partner_id.id
        if partners:
            if not commercial_partner_id:
                commercial_partner_id = partners[0].commercial_partner_id.id
            self.check_partner_base_data(commercial_partner_id, DatiAnagrafici)
            return commercial_partner_id
        else:
            # partner to be created
            country_id = False
            if 'IdFiscaleIVA' in DatiAnagrafici and DatiAnagrafici.IdFiscaleIVA:
                CountryCode = DatiAnagrafici.IdFiscaleIVA.IdPaese
                countries = self.CountryByCode(CountryCode)
                if countries:
                    country_id = countries[0].id
                else:
                    raise UserError(
                        _("Country Code %s not found in system.") % CountryCode
                    )
            denominazione = False if 'Denominazione' not in DatiAnagrafici.Anagrafica else DatiAnagrafici.Anagrafica.Denominazione
            eori_code = "" if 'CodEORI' not in DatiAnagrafici.Anagrafica else DatiAnagrafici.Anagrafica.CodEORI
            vals = {
                "vat": vat,
                "fiscalcode": cf,
                "is_company": (
                    denominazione and True or False
                ),
                "eori_code": eori_code,
                "country_id": country_id,
            }
            if 'Nome' in DatiAnagrafici.Anagrafica and DatiAnagrafici.Anagrafica.Nome:
                vals["firstname"] = DatiAnagrafici.Anagrafica.Nome
            if 'Cognome' in DatiAnagrafici.Anagrafica and DatiAnagrafici.Anagrafica.Cognome:
                vals["lastname"] = DatiAnagrafici.Anagrafica.Cognome
            if 'Denominazione' in DatiAnagrafici.Anagrafica and DatiAnagrafici.Anagrafica.Denominazione:
                vals["name"] = DatiAnagrafici.Anagrafica.Denominazione

            return partner_model.create(vals).id

    def getCedPrest(self, cedPrest):
        partner_model = self.env["res.partner"]
        partner_id = self.getPartnerBase(cedPrest.DatiAnagrafici)
        no_contact_update = False
        if partner_id:
            no_contact_update = partner_model.browse(
                partner_id
            ).electronic_invoice_no_contact_update
        fiscalPosModel = self.env["fatturapa.fiscal_position"]
        if partner_id and not no_contact_update:
            partner_company_id = partner_model.browse(partner_id).company_id.id
            register = ""
            if 'AlboProfessionale' in cedPrest.DatiAnagrafici:
                register = cedPrest.DatiAnagrafici.AlboProfessionale or ""

            vals = {
                "street": cedPrest.Sede.Indirizzo,
                "zip": cedPrest.Sede.CAP,
                "city": cedPrest.Sede.Comune,
                "register": register,
            }
            if 'ProvinciaAlbo' in cedPrest.DatiAnagrafici and cedPrest.DatiAnagrafici.ProvinciaAlbo:
                ProvinciaAlbo = cedPrest.DatiAnagrafici.ProvinciaAlbo
                prov = self.ProvinceByCode(ProvinciaAlbo)
                if not prov:
                    self.log_inconsistency(
                        _("Register Province ( %s ) not present " "in your system")
                        % ProvinciaAlbo
                    )
                else:
                    vals["register_province"] = prov[0].id
            if 'Provincia' in cedPrest.Sede and cedPrest.Sede.Provincia:
                Provincia = cedPrest.Sede.Provincia
                prov_sede = self.ProvinceByCode(Provincia)
                if not prov_sede:
                    self.log_inconsistency(
                        _("Province ( %s ) not present in your system") % Provincia
                    )
                else:
                    vals["state_id"] = prov_sede[0].id

            NumeroIscrizioneAlbo = False
            DataIscrizioneAlbo = False
            if 'NumeroIscrizioneAlbo' in cedPrest.DatiAnagrafici:
                NumeroIscrizioneAlbo = cedPrest.DatiAnagrafici.NumeroIscrizioneAlbo
            if 'DataIscrizioneAlbo' in cedPrest.DatiAnagrafici:
                DataIscrizioneAlbo = cedPrest.DatiAnagrafici.DataIscrizioneAlbo
            vals["register_code"] = NumeroIscrizioneAlbo
            vals["register_regdate"] = DataIscrizioneAlbo


            if 'RegimeFiscale' in cedPrest.DatiAnagrafici and cedPrest.DatiAnagrafici.RegimeFiscale:
                rfPos = cedPrest.DatiAnagrafici.RegimeFiscale
                FiscalPos = fiscalPosModel.search([("code", "=", rfPos)])
                if not FiscalPos:
                    raise UserError(
                        _("Tax Regime %s not present in your system.") % rfPos
                    )
                else:
                    vals["register_fiscalpos"] = FiscalPos[0].id

            if 'IscrizioneREA' in cedPrest and cedPrest.IscrizioneREA:
                REA = cedPrest.IscrizioneREA
                offices = False
                rea_nr = False
                if 'Ufficio' in REA:
                    offices = self.ProvinceByCode(REA.Ufficio)
                if 'NumeroREA' in REA:
                    rea_nr = REA.NumeroREA

                if not offices:
                    office_id = False
                    self.log_inconsistency(
                        _(
                            "REA Office Province Code ( %s ) not present in "
                            "your system"
                        )
                        % REA.Ufficio
                    )
                else:
                    office_id = offices[0].id
                    vals["rea_office"] = office_id

                rea_domain = [
                    ("rea_code", "=", rea_nr),
                    ("company_id", "=", partner_company_id),
                    ("id", "!=", partner_id),
                ]
                if office_id:
                    rea_domain.append(("rea_office", "=", office_id))
                rea_partners = partner_model.search(rea_domain)
                if rea_partners:
                    rea_names = ", ".join(rea_partners.mapped("name"))
                    p_name = partner_model.browse(partner_id).name
                    self.log_inconsistency(
                        _(
                            "Current invoice is from {} with REA Code"
                            " {}. Yet it seems that partners {} have the same"
                            " REA Code. This code should be unique; please fix"
                            " it.".format(p_name, rea_nr, rea_names)
                        )
                    )
                else:
                    vals["rea_code"] = REA.NumeroREA

                vals["rea_capital"] = 0.0 if 'CapitaleSociale' not in REA else REA.CapitaleSociale
                vals["rea_member_type"] = False if 'SocioUnico' not in REA else REA.SocioUnico
                vals["rea_liquidation_state"] = False if 'StatoLiquidazione' not in REA else REA.StatoLiquidazione

            if 'Contatti' in cedPrest and cedPrest.Contatti:
                vals["phone"] = "" if 'Telefono' not in cedPrest.Contatti else cedPrest.Contatti.Telefono
                vals["email"] = "" if 'Email' not in cedPrest.Contatti else cedPrest.Contatti.Email
            partner_model.browse(partner_id).write(vals)
        return partner_id

    def getCarrirerPartner(self, Carrier):

        if 'DatiAnagraficiVettore' not in Carrier:
            return False
        partner_model = self.env["res.partner"]
        partner_id = self.getPartnerBase(Carrier.DatiAnagraficiVettore)
        no_contact_update = False
        if partner_id:
            no_contact_update = partner_model.browse(
                partner_id
            ).electronic_invoice_no_contact_update
        if partner_id and not no_contact_update:
            vals = {
                "license_number": Carrier.DatiAnagraficiVettore.NumeroLicenzaGuida
                or "",
            }
            partner_model.browse(partner_id).write(vals)
        return partner_id

    # move_line.tax_ids
    def _prepare_generic_line_data(self, line):
        retLine = {}
        natura = None if 'Natura' not in line else line.Natura
        aliquota = None if 'AliquotaIVA' not in line else line.AliquotaIVA
        account_taxes = self.get_account_taxes(aliquota,natura)
        if account_taxes:
            retLine["tax_ids"] = [(6, 0, [account_taxes[0].id])]
        return retLine

    def get_account_taxes(self, AliquotaIVA, Natura):
        account_tax_model = self.env["account.tax"]
        # check if a default tax exists and generate def_purchase_tax object
        ir_values = self.env["ir.default"]
        company_id = self.env.company.id
        supplier_taxes_ids = ir_values.get(
            "product.product", "supplier_taxes_id", company_id=company_id
        )
        def_purchase_tax = False
        if supplier_taxes_ids:
            def_purchase_tax = account_tax_model.browse(supplier_taxes_ids, limit=1)
        if float(AliquotaIVA) == 0.0 and Natura:
            account_taxes = account_tax_model.search(
                [
                    ("type_tax_use", "=", "purchase"),
                    ("kind_id.code", "=", Natura),
                    ("amount", "=", 0.0),
                ],
                order="sequence",
            )
            if not account_taxes:
                self.log_inconsistency(
                    _(
                        "No tax with percentage "
                        "%s and nature %s found. Please configure this tax."
                    )
                    % (AliquotaIVA, Natura)
                )
            if len(account_taxes) > 1:
                self.log_inconsistency(
                    _(
                        "Too many taxes with percentage "
                        "%s and nature %s found. Tax %s with lower priority has "
                        "been set on invoice lines."
                    )
                    % (AliquotaIVA, Natura, account_taxes[0].description)
                )
        else:
            account_taxes = account_tax_model.search(
                [
                    ("type_tax_use", "=", "purchase"),
                    ("amount", "=", float(AliquotaIVA)),
                    ("price_include", "=", False),
                    # partially deductible VAT must be set by user
                    ("children_tax_ids", "=", False),
                ],
                order="sequence",
            )
            if not account_taxes:
                self.log_inconsistency(
                    _(
                        "XML contains tax with percentage '%s' "
                        "but it does not exist in your system"
                    )
                    % AliquotaIVA
                )
            # check if there are multiple taxes with
            # same percentage
            if len(account_taxes) > 1:
                # just logging because this is an usual case: see split payment
                _logger.warning(
                    _(
                        "Too many taxes with percentage equals "
                        "to '%s'.\nFix it if required"
                    )
                    % AliquotaIVA
                )
                # if there are multiple taxes with same percentage
                # and there is a default tax with this percentage,
                # set taxes list equal to supplier_taxes_id, loaded before
                if def_purchase_tax and def_purchase_tax.amount == (float(AliquotaIVA)):
                    account_taxes = def_purchase_tax
        return account_taxes

    def get_line_product(self, line, partner):
        product = False
        supplier_info = self.env["product.supplierinfo"]
        if 'CodiceArticolo' in line and len(line.CodiceArticolo or []) == 1:
            supplier_code = line.CodiceArticolo[0].CodiceValore
            supplier_infos = supplier_info.search(
                [("product_code", "=", supplier_code), ("name", "=", partner.id)]
            )
            if supplier_infos:
                products = supplier_infos.mapped("product_id")
                if len(products) == 1:
                    product = products[0]
                else:
                    templates = supplier_infos.mapped("product_tmpl_id")
                    if len(templates) == 1:
                        product = templates.product_variant_ids[0]
        if not product and partner.e_invoice_default_product_id:
            product = partner.e_invoice_default_product_id
        return product

    def adjust_accounting_data(self, product, line_vals):
        if product.product_tmpl_id.property_account_expense_id:
            line_vals[
                "account_id"
            ] = product.product_tmpl_id.property_account_expense_id.id
        elif product.product_tmpl_id.categ_id.property_account_expense_categ_id:
            line_vals[
                "account_id"
            ] = product.product_tmpl_id.categ_id.property_account_expense_categ_id.id
        account = self.env["account.account"].browse(line_vals["account_id"])
        new_tax = None
        if len(product.product_tmpl_id.supplier_taxes_id) == 1:
            new_tax = product.product_tmpl_id.supplier_taxes_id[0]
        elif len(account.tax_ids) == 1:
            new_tax = account.tax_ids[0]
        if new_tax:
            line_tax_id = line_vals.get("tax_ids") and line_vals["tax_ids"][0][2][0]
            line_tax = self.env["account.tax"].browse(line_tax_id)
            if new_tax.id != line_tax_id:
                if line_tax and new_tax._get_tax_amount() != line_tax._get_tax_amount():
                    self.log_inconsistency(
                        _(
                            "XML contains tax %s. Product %s has tax %s. Using "
                            "the XML one"
                        )
                        % (line_tax.name, product.name, new_tax.name)
                    )
                else:
                    # If product has the same amount of the one in XML,
                    # I use it. Typical case: 22% det 50%
                    line_vals["tax_ids"] = [(6, 0, [new_tax.id])]

    # move_line.tax_ids
    # move_line.name
    # move_line.sequence
    # move_line.account_id
    # move_line.price_unit
    # move_line.quantity
    def _prepareInvoiceLineAliquota(self, credit_account_id, line, nline):
        retLine = {}
        account_taxes = self.get_account_taxes(line.AliquotaIVA, line.Natura)
        if account_taxes:
            retLine["tax_ids"] = [(6, 0, [account_taxes[0].id])]

        retLine.update(
            {
                "name": "Riepilogo Aliquota {}".format(line.AliquotaIVA),
                "sequence": nline,
                "account_id": credit_account_id,
                "price_unit": float(abs(line.ImponibileImporto)),
            }
        )
        return retLine

    # move_line.name
    # move_line.sequence
    # move_line.account_id
    # move_line.price_unit
    # move_line.quantity
    # move_line.discount
    # move_line.admin_ref
    # move_line.invoice_line_tax_wt_ids
    def _prepareInvoiceLine(self, credit_account_id, line, wt_founds=False):
        retLine = self._prepare_generic_line_data(line)
        retLine.update(
            {
                "name": line.Descrizione,
                "sequence": int(line.NumeroLinea),
                "account_id": credit_account_id,
                "price_unit": float(line.PrezzoUnitario),
            }
        )
        if 'Quantita' not in line or line.Quantita is None:
            retLine["quantity"] = 1.0
        else:
            retLine["quantity"] = float(line.Quantita)
        if (
            'PrezzoUnitario' in line and 'Quantita' in line and 'ScontoMaggiorazione' in line and
            float(line.PrezzoUnitario)
            and line.Quantita
            and float(line.Quantita)
            and line.ScontoMaggiorazione  # Quantita not required
        ):
            retLine["discount"] = self._computeDiscount(line)
        if 'RiferimentoAmministrazione' in line and line.RiferimentoAmministrazione:
            retLine["admin_ref"] = line.RiferimentoAmministrazione
        if wt_founds and 'Ritenuta' in line and line.Ritenuta:
            retLine["invoice_line_tax_wt_ids"] = [(6, 0, [x.id for x in wt_founds])]

        return retLine

    def _prepareRelDocsLine(self, invoice_id, line, doc_type):
        res = []
        lineref = False if 'RiferimentoNumeroLinea' not in line else (line.RiferimentoNumeroLinea or False)
        IdDoc = "Error" if 'IdDocumento' not in line else (line.IdDocumento or "Error")
        Data =  False if 'Data' not in line else (line.Data or False)
        NumItem = "" if 'NumItem' not in line else (line.NumItem or "")
        Code = "" if 'CodiceCommessaConvenzione' not in line else (line.CodiceCommessaConvenzione or "")
        Cig = "" if 'CodiceCIG' not in line else (line.CodiceCIG or "")
        Cup = "" if 'CodiceCUP' not in line else (line.CodiceCUP or "")
        invoice_lineid = False
        if lineref:
            for numline in lineref:
                invoice_lineid = False
                invoice_line_model = self.env["account.move.line"]
                invoice_lines = invoice_line_model.search(
                    [
                        ("move_id", "=", invoice_id),
                        ("sequence", "=", int(numline)),
                    ]
                )
                if invoice_lines:
                    invoice_lineid = invoice_lines[0].id
                val = {
                    "type": doc_type,
                    "name": IdDoc,
                    "lineRef": numline,
                    "invoice_line_id": invoice_lineid,
                    "invoice_id": invoice_id,
                    "date": Data,
                    "numitem": NumItem,
                    "code": Code,
                    "cig": Cig,
                    "cup": Cup,
                }
                res.append(val)
        else:
            val = {
                "type": doc_type,
                "name": IdDoc,
                "invoice_line_id": invoice_lineid,
                "invoice_id": invoice_id,
                "date": Data,
                "numitem": NumItem,
                "code": Code,
                "cig": Cig,
                "cup": Cup,
            }
            res.append(val)
        return res

    def _prepareWelfareLine(self, invoice_id, line):
        TipoCassa = False if 'TipoCassa' not in line else line.TipoCassa
        AlCassa = None if 'AlCassa' not in line else (float(line.AlCassa) / 100)
        ImportoContributoCassa = None if 'ImportoContributoCassa' not in line else (
            line.ImportoContributoCassa and float(line.ImportoContributoCassa)
        )
        ImponibileCassa = None if 'ImponibileCassa' not in line else (line.ImponibileCassa and float(line.ImponibileCassa) or None)
        AliquotaIVA = None if 'AliquotaIVA' not in line else (line.AliquotaIVA and (float(line.AliquotaIVA) / 100) or None)
        Ritenuta = "" if 'Ritenuta' not in line else line.Ritenuta
        Natura = False if 'Natura' not in line else line.Natura or False
        kind_id = False
        if Natura:
            kind = self.env["account.tax.kind"].search([("code", "=", Natura)])
            if not kind:
                self.log_inconsistency(_("Tax kind %s not found") % Natura)
            else:
                kind_id = kind[0].id

        RiferimentoAmministrazione = "" if 'RiferimentoAmministrazione' not in line else line.RiferimentoAmministrazione
        WelfareTypeModel = self.env["welfare.fund.type"]
        if not TipoCassa:
            raise UserError(_("Welfare Fund is not defined."))
        WelfareType = WelfareTypeModel.search([("name", "=", TipoCassa)])

        res = {
            "welfare_rate_tax": AlCassa,
            "welfare_amount_tax": ImportoContributoCassa,
            "welfare_taxable": ImponibileCassa,
            "welfare_Iva_tax": AliquotaIVA,
            "subjected_withholding": Ritenuta,
            "kind_id": kind_id,
            "pa_line_code": RiferimentoAmministrazione,
            "invoice_id": invoice_id,
        }
        if not WelfareType:
            raise UserError(
                _("Welfare Fund %s not present in your system.") % TipoCassa
            )
        else:
            res["name"] = WelfareType[0].id

        return res

    def _prepareDiscRisePriceLine(self, line_id, line):
        Tipo = False if 'Tipo' not in line.Tipo else line.Tipo
        Percentuale = 0.0 if 'Percentuale' not in line else float(line.Percentuale)
        Importo = 0.0 if 'Importo' not in line else float(line.Importo)
        res = {
            "percentage": Percentuale,
            "amount": Importo,
            self.env.context.get("drtype"): line_id,
        }
        res["name"] = Tipo

        return res

    def _computeDiscount(self, DettaglioLinea):
        line_total = float(DettaglioLinea.PrezzoTotale)
        line_unit = line_total / float(DettaglioLinea.Quantita)
        discount = (1 - (line_unit / float(DettaglioLinea.PrezzoUnitario))) * 100.0
        return discount

    def _addGlobalDiscount(self, invoice_id, DatiGeneraliDocumento):
        discount = 0.0
        if (
            'ScontoMaggiorazione' in DatiGeneraliDocumento and DatiGeneraliDocumento.ScontoMaggiorazione
            and self.e_invoice_detail_level == "2"
        ):
            invoice = self.env["account.move"].browse(invoice_id)
            for DiscRise in DatiGeneraliDocumento.ScontoMaggiorazione:
                if 'Percentuale' in DiscRise and DiscRise.Percentuale:
                    amount = invoice.amount_total * (float(DiscRise.Percentuale) / 100)
                    if 'Tipo' in DiscRise and DiscRise.Tipo == "SC":
                        discount -= amount
                    elif 'Tipo' in DiscRise and DiscRise.Tipo == "MG":
                        discount += amount
                elif 'Importo' in DiscRise and DiscRise.Importo:
                    if 'Tipo' in DiscRise and DiscRise.Tipo == "SC":
                        discount -= float(DiscRise.Importo)
                    elif 'Tipo' in DiscRise and DiscRise.Tipo == "MG":
                        discount += float(DiscRise.Importo)
            journal = self.get_purchase_journal(invoice.company_id)
            credit_account_id = journal.default_account_id.id
            line_vals = {
                "move_id": invoice_id,
                "name": _("Global bill discount from document general data"),
                "account_id": credit_account_id,
                "price_unit": discount,
                "quantity": 1,
            }
            if self.env.company.sconto_maggiorazione_product_id:
                sconto_maggiorazione_product = (
                    self.env.company.sconto_maggiorazione_product_id
                )
                line_vals["product_id"] = sconto_maggiorazione_product.id
                line_vals["name"] = sconto_maggiorazione_product.name
                self.adjust_accounting_data(sconto_maggiorazione_product, line_vals)
            self.env["account.move.line"].with_context(
                check_move_validity=False
            ).create(line_vals)
        return True

    def _createPaymentsLine(self, payment_id, line, partner_id):
        details = False if 'DettaglioPagamento' not in line else line.DettaglioPagamento
        if details:
            PaymentModel = self.env["fatturapa.payment.detail"]
            PaymentMethodModel = self.env["fatturapa.payment_method"]
            BankModel = self.env["res.bank"]
            PartnerBankModel = self.env["res.partner.bank"]
            for dline in details:
                method = PaymentMethodModel.search(
                    [("code", "=", dline.ModalitaPagamento)]
                )
                if not method:
                    raise UserError(
                        _(
                            "Payment method %s is not defined in your system."
                            % dline.ModalitaPagamento
                        )
                    )
                val = {
                    "recipient": False if 'Beneficiario' not in dline else dline.Beneficiario,
                    "fatturapa_pm_id": method[0].id,
                    "payment_term_start": False if 'DataRiferimentoTerminiPagamento' not in dline else dline.DataRiferimentoTerminiPagamento,
                    "payment_days": 0 if 'GiorniTerminiPagamento' not in dline else dline.GiorniTerminiPagamento,
                    "payment_due_date": False if 'DataScadenzaPagamento' not in dline else dline.DataScadenzaPagamento,
                    "payment_amount": 0.0 if 'ImportoPagamento' not in dline else dline.ImportoPagamento,
                    "post_office_code": "" if 'CodUfficioPostale' not in dline else dline.CodUfficioPostale,
                    "recepit_surname": "" if 'CognomeQuietanzante' not in dline else dline.CognomeQuietanzante,
                    "recepit_name": "" if 'NomeQuietanzante' not in dline else dline.NomeQuietanzante,
                    "recepit_cf": "" if 'CFQuietanzante' not in dline else dline.CFQuietanzante,
                    "recepit_title": "1" if 'TitoloQuietanzante' not in dline else dline.TitoloQuietanzante,
                    "payment_bank_name": "" if 'IstitutoFinanziario' not in dline else dline.IstitutoFinanziario,
                    "payment_bank_iban": "" if 'IBAN' not in dline else dline.IBAN,
                    "payment_bank_abi": "" if 'ABI' not in dline else dline.ABI,
                    "payment_bank_cab": "" if 'CAB' not in dline else dline.CAB,
                    "payment_bank_bic": "" if 'BIC' not in dline else dline.BIC,
                    "payment_bank": False,
                    "prepayment_discount": 0.0 if 'ScontoPagamentoAnticipato' not in dline else dline.ScontoPagamentoAnticipato,
                    "max_payment_date": False if 'DataLimitePagamentoAnticipato' not in dline else dline.DataLimitePagamentoAnticipato,
                    "penalty_amount": 0.0 if 'PenalitaPagamentiRitardati' not in dline else dline.PenalitaPagamentiRitardati,
                    "penalty_date": False if 'DataDecorrenzaPenale' not in dline else dline.DataDecorrenzaPenale,
                    "payment_code": "" if 'CodicePagamento' not in dline else dline.CodicePagamento,
                    "payment_data_id": payment_id,
                }
                bank = False
                payment_bank_id = False
                if 'BIC' in dline and dline.BIC:
                    banks = BankModel.search([("bic", "=", dline.BIC.strip())])
                    if not banks:
                        if not dline.IstitutoFinanziario:
                            self.log_inconsistency(
                                _(
                                    "Name of Bank with BIC '%s' is not set."
                                    " Can't create bank"
                                )
                                % dline.BIC
                            )
                        else:
                            bank = BankModel.create(
                                {
                                    "name": dline.IstitutoFinanziario,
                                    "bic": dline.BIC,
                                }
                            )
                    else:
                        bank = banks[0]
                if 'IBAN' in dline and dline.IBAN:
                    SearchDom = [
                        ("acc_number", "=", pretty_iban(dline.IBAN.strip())),
                        ("partner_id", "=", partner_id),
                    ]
                    payment_bank_id = False
                    payment_banks = PartnerBankModel.search(SearchDom)
                    if not payment_banks and not bank:
                        self.log_inconsistency(
                            _(
                                "BIC is required and not exist in Xml\n"
                                "Curr bank data is: \n"
                                "IBAN: %s\n"
                                "Bank Name: %s\n"
                            )
                            % (
                                dline.IBAN.strip() or "",
                                "" if 'IstitutoFinanziario' not in dline else (dline.IstitutoFinanziario or ""),
                            )
                        )
                    elif not payment_banks and bank:
                        payment_bank_id = PartnerBankModel.create(
                            {
                                "acc_number": dline.IBAN.strip(),
                                "partner_id": partner_id,
                                "bank_id": bank.id,
                                "bank_name": bank.name if 'IstitutoFinanziario' not in dline else (dline.IstitutoFinanziario or bank.name),
                                "bank_bic": bank.bic if 'BIC' not in dline else (dline.BIC or bank.bic),
                            }
                        ).id
                    if payment_banks:
                        payment_bank_id = payment_banks[0].id

                if payment_bank_id:
                    val["payment_bank"] = payment_bank_id
                PaymentModel.create(val)
        return True

    # TODO sul partner?
    def set_StabileOrganizzazione(self, CedentePrestatore, invoice):
        if 'StabileOrganizzazione' in CedentePrestatore and CedentePrestatore.StabileOrganizzazione:
            invoice.efatt_stabile_organizzazione_indirizzo = (
                False if 'Indirizzo' not in CedentePrestatore.StabileOrganizzazione else
                CedentePrestatore.StabileOrganizzazione.Indirizzo
            )
            invoice.efatt_stabile_organizzazione_civico = (
                False if 'NumeroCivico' not in CedentePrestatore.StabileOrganizzazione else
                CedentePrestatore.StabileOrganizzazione.NumeroCivico
            )
            invoice.efatt_stabile_organizzazione_cap = (
                False if 'CAP' not in CedentePrestatore.StabileOrganizzazione else
                CedentePrestatore.StabileOrganizzazione.CAP
            )
            invoice.efatt_stabile_organizzazione_comune = (
                False if 'Comune' not in CedentePrestatore.StabileOrganizzazione else
                CedentePrestatore.StabileOrganizzazione.Comune
            )
            invoice.efatt_stabile_organizzazione_provincia = (
                False if 'Provincia' not in CedentePrestatore.StabileOrganizzazione else
                CedentePrestatore.StabileOrganizzazione.Provincia
            )
            invoice.efatt_stabile_organizzazione_nazione = (
                False if 'Nazione' not in CedentePrestatore.StabileOrganizzazione else
                CedentePrestatore.StabileOrganizzazione.Nazione
            )

    def get_purchase_journal(self, company):
        journal_model = self.env["account.journal"]
        journals = journal_model.search(
            [("type", "=", "purchase"), ("company_id", "=", company.id)], limit=1
        )
        if not journals:
            raise UserError(
                _("Define a purchase journal " "for this company: '%s' (id: %d).")
                % (company.name, company.id)
            )
        return journals[0]

    def create_e_invoice_line(self, line):
        line_number= 0 if 'NumeroLinea' not in line else int(line.NumeroLinea or 0)
        service_type= False if 'TipoCessionePrestazione' not in line else line.TipoCessionePrestazione
        name= line.Descrizione
        qty= 0 if 'Quantita' not in line else float(line.Quantita or 0)
        uom= False if 'UnitaMisura' not in line else line.UnitaMisura
        period_start_date= False if 'DataInizioPeriodo' not in line else line.DataInizioPeriodo
        period_end_date= False if 'DataFinePeriodo' not in line else line.DataFinePeriodo
        unit_price= False if 'PrezzoUnitario' not in line else float(line.PrezzoUnitario or 0)
        total_price= False if 'PrezzoTotale' not in line else float(line.PrezzoTotale or 0)
        tax_amount= 0 if 'AliquotaIVA' not in line else float(line.AliquotaIVA or 0)
        wt_amount= False if 'Ritenuta' not in line else line.Ritenuta
        tax_kind= False if 'Natura' not in line else line.Natura
        admin_ref= False if 'RiferimentoAmministrazione' not in line else line.RiferimentoAmministrazione

        vals = {
                   "line_number": line_number,
                   "service_type": service_type,
                   "name": name,
                   "qty": qty,
                   "uom": uom,
                   "period_start_date": period_start_date,
                   "period_end_date": period_end_date,
                   "unit_price": unit_price,
                   "total_price": total_price,
                   "tax_amount": tax_amount,
                   "wt_amount": wt_amount,
                   "tax_kind": tax_kind,
                   "admin_ref": admin_ref,
                }

        einvoiceline = self.env["einvoice.line"].create(vals)
        if 'CodiceArticolo' in line and line.CodiceArticolo:
            for caline in line.CodiceArticolo:
                self.env["fatturapa.article.code"].create(
                    {
                        "name": "" if 'CodiceTipo' not in caline.CodiceTipo else caline.CodiceTipo,
                        "code_val": "" if 'CodiceValore' not in caline.CodiceValore else caline.CodiceValore,
                        "e_invoice_line_id": einvoiceline.id,
                    }
                )
        if 'ScontoMaggiorazione' in line and line.ScontoMaggiorazione:
            for DiscRisePriceLine in line.ScontoMaggiorazione:
                DiscRisePriceVals = self.with_context(
                    drtype="e_invoice_line_id"
                )._prepareDiscRisePriceLine(einvoiceline.id, DiscRisePriceLine)
                self.env["discount.rise.price"].create(DiscRisePriceVals)
        if 'AltriDatiGestionali' in line and line.AltriDatiGestionali:
            for dato in line.AltriDatiGestionali:
                self.env["einvoice.line.other.data"].create(
                    {
                        "name": "" if 'TipoDato' not in dato else dato.TipoDato,
                        "text_ref": "" if 'RiferimentoTesto' not in dato else dato.RiferimentoTesto,
                        "num_ref": 0 if 'RiferimentoNumero' not in dato else float(dato.RiferimentoNumero or 0),
                        "date_ref": False if 'RiferimentoData' not in dato else dato.RiferimentoData,
                        "e_invoice_line_id": einvoiceline.id,
                    }
                )
        return einvoiceline

    def invoiceCreate(self, fatt, fatturapa_attachment, FatturaBody, partner_id):
        partner_model = self.env["res.partner"]
        invoice_model = self.env["account.move"]
        currency_model = self.env["res.currency"]
        ftpa_doctype_model = self.env["fiscal.document.type"]
        rel_docs_model = self.env["fatturapa.related_document_type"]

        company = self.env.company
        partner = partner_model.browse(partner_id)

        # currency 2.1.1.2
        currency = currency_model.search(
            [("name", "=", FatturaBody.DatiGenerali.DatiGeneraliDocumento.Divisa)]
        )
        if not currency:
            raise UserError(
                _(
                    "No currency found with code %s."
                    % FatturaBody.DatiGenerali.DatiGeneraliDocumento.Divisa
                )
            )
        purchase_journal = self.get_purchase_journal(company)
        credit_account_id = purchase_journal.default_account_id.id
        comment = ""
        # 2.1.1
        docType_id = False
        invtype = "in_invoice"
        docType = False if 'TipoDocumento' not in FatturaBody.DatiGenerali.DatiGeneraliDocumento else FatturaBody.DatiGenerali.DatiGeneraliDocumento.TipoDocumento
        if docType:
            docType_record = ftpa_doctype_model.search([("code", "=", docType)])
            if docType_record:
                docType_id = docType_record[0].id
            else:
                raise UserError(_("Document type %s not handled.") % docType)
            if docType == "TD04":
                invtype = "in_refund"
        # 2.1.1.11
        causLst = False if 'Causale' not in FatturaBody.DatiGenerali.DatiGeneraliDocumento else FatturaBody.DatiGenerali.DatiGeneraliDocumento.Causale
        if causLst:
            for rel_doc in causLst:
                comment += rel_doc + "\n"

        if fatturapa_attachment.e_invoice_received_date:
            e_invoice_received_date = (
                fatturapa_attachment.e_invoice_received_date.date()
            )
        else:
            e_invoice_received_date = fatturapa_attachment.create_date.date()

        e_invoice_date = datetime.strptime(
            FatturaBody.DatiGenerali.DatiGeneraliDocumento.Data, "%Y-%m-%d"
        ).date()

        invoice_data = {
            "e_invoice_received_date": e_invoice_received_date,
            "date": e_invoice_received_date
            if company.in_invoice_registration_date == "rec_date"
            else e_invoice_date,
            "fiscal_document_type_id": docType_id,
            "sender": False if 'SoggettoEmittente' not in fatt.FatturaElettronicaHeader else fatt.FatturaElettronicaHeader.SoggettoEmittente,
            "move_type": invtype,
            "partner_id": partner_id,
            "currency_id": currency[0].id,
            "journal_id": purchase_journal.id,
            # 'origin': xmlData.datiOrdineAcquisto,
            "fiscal_position_id": (partner.property_account_position_id.id or False),
            "invoice_payment_term_id": partner.property_supplier_payment_term_id.id,
            "company_id": company.id,
            "fatturapa_attachment_in_id": fatturapa_attachment.id,
            "narration": comment,
        }

        # 2.1.1.10
        self.set_efatt_rounding(FatturaBody, invoice_data)

        # 2.1.1.12
        self.set_art73(FatturaBody, invoice_data)

        # 2.1.1.5
        wt_founds = self.set_withholding_tax(FatturaBody, invoice_data)

        self.set_e_invoice_lines(FatturaBody, invoice_data)

        invoice = invoice_model.create(invoice_data)

        # 2.2.1
        self.set_invoice_line_ids(
            FatturaBody, credit_account_id, partner, wt_founds, invoice
        )

        # 2.1.1.7
        self.set_welfares_fund(FatturaBody, credit_account_id, invoice, wt_founds)

        invoice._onchange_invoice_line_wt_ids()
        invoice._recompute_dynamic_lines()
        invoice.write(invoice._convert_to_write(invoice._cache))

        rel_docs_dict = {
            # 2.1.2
            "order": False if 'DatiOrdineAcquisto' not in FatturaBody.DatiGenerali else FatturaBody.DatiGenerali.DatiOrdineAcquisto,
            # 2.1.3
            "contract": False if 'DatiContratto' not in FatturaBody.DatiGenerali else FatturaBody.DatiGenerali.DatiContratto,
            # 2.1.4
            "agreement": False if 'DatiConvenzione' not in FatturaBody.DatiGenerali else FatturaBody.DatiGenerali.DatiConvenzione,
            # 2.1.5
            "reception": False if 'DatiRicezione' not in FatturaBody.DatiGenerali else FatturaBody.DatiGenerali.DatiRicezione,
            # 2.1.6
            "invoice": False if 'DatiFattureCollegate' not in FatturaBody.DatiGenerali else FatturaBody.DatiGenerali.DatiFattureCollegate,
        }

        for rel_doc_key, rel_doc_data in rel_docs_dict.items():
            if not rel_doc_data:
                continue
            for rel_doc in rel_doc_data:
                doc_datas = self._prepareRelDocsLine(invoice.id, rel_doc, rel_doc_key)
                for doc_data in doc_datas:
                    # Note for v12: must take advantage of batch creation
                    rel_docs_model.create(doc_data)

        # 2.1.7
        self.set_activity_progress(FatturaBody, invoice)

        # 2.1.8
        self.set_ddt_data(FatturaBody, invoice)

        # 2.1.9
        self.set_delivery_data(FatturaBody, invoice)

        # 2.2.2
        self.set_summary_data(FatturaBody, invoice)

        # 2.1.10
        self.set_parent_invoice_data(FatturaBody, invoice)

        # 2.3
        self.set_vehicles_data(FatturaBody, invoice)

        # 2.4
        self.set_payments_data(FatturaBody, invoice, partner_id)

        # 2.5
        self.set_attachments_data(FatturaBody, invoice)

        if 'DatiGeneraliDocumento' in FatturaBody.DatiGenerali:
            self._addGlobalDiscount(
                invoice.id, FatturaBody.DatiGenerali.DatiGeneraliDocumento
            )


        # compute the invoice
        invoice._move_autocomplete_invoice_lines_values()

        self.set_vendor_bill_data(FatturaBody, invoice)



        # this can happen with refunds with negative amounts
        invoice.process_negative_lines()
        return invoice

    def set_vendor_bill_data(self, FatturaBody, invoice):
        if not invoice.invoice_date:
            invoice.update(
                {
                    "invoice_date": datetime.strptime(
                        FatturaBody.DatiGenerali.DatiGeneraliDocumento.Data, "%Y-%m-%d"
                    ).date(),
                }
            )
        if not invoice.payment_reference:
            today = fields.Date.context_today(self)
            x = invoice.line_ids.filtered(
                lambda line: line.account_id.user_type_id.type
                in ("receivable", "payable")
            ).sorted(lambda line: line.date_maturity or today)
            if x:
                x[-1].name = FatturaBody.DatiGenerali.DatiGeneraliDocumento.Numero
                invoice.payment_reference = (
                    FatturaBody.DatiGenerali.DatiGeneraliDocumento.Numero
                )

    def set_parent_invoice_data(self, FatturaBody, invoice):
        ParentInvoice = False if 'FatturaPrincipale' not in FatturaBody.DatiGenerali else FatturaBody.DatiGenerali.FatturaPrincipale
        if ParentInvoice:
            parentinv_vals = {
                "related_invoice_code": "" if 'NumeroFatturaPrincipale' in ParentInvoice else ParentInvoice.NumeroFatturaPrincipale,
                "related_invoice_date": False if 'DataFatturaPrincipale' in ParentInvoice else ParentInvoice.DataFatturaPrincipale,
            }
            invoice.write(parentinv_vals)

    def set_vehicles_data(self, FatturaBody, invoice):
        Vehicle = False if 'DatiVeicoli' not in FatturaBody else FatturaBody.DatiVeicoli
        if Vehicle:
            veicle_vals = {
                "vehicle_registration": False if 'Data' not in Vehicle else Vehicle.Data,
                "total_travel": "" if 'TotalePercorso' not in Vehicle else Vehicle.TotalePercorso,
            }
            invoice.write(veicle_vals)

    def set_attachments_data(self, FatturaBody, invoice):
        invoice_id = invoice.id
        AttachmentsData = False if 'Allegati'not in FatturaBody else FatturaBody.Allegati
        if AttachmentsData:
            self.env["fatturapa.attachment.in"].extract_attachments(
                AttachmentsData, invoice_id
            )

    def set_ddt_data(self, FatturaBody, invoice):
        invoice_id = invoice.id
        DdtDatas = False if 'DatiDDT' not in FatturaBody.DatiGenerali else FatturaBody.DatiGenerali.DatiDDT
        if not DdtDatas:
            return
        invoice_line_model = self.env["account.move.line"]
        DdTModel = self.env["fatturapa.related_ddt"]
        for DdtDataLine in DdtDatas:
            if not 'RiferimentoNumeroLinea' in DdtDataLine or not DdtDataLine.RiferimentoNumeroLinea:
                DdTModel.create(
                    {
                        "name": "" if 'NumeroDDT' not in DdtDataLine else DdtDataLine.NumeroDDT,
                        "date": False if 'DataDDT' not in DdtDataLine else DdtDataLine.DataDDT,
                        "invoice_id": invoice_id,
                    }
                )
            else:
                for numline in DdtDataLine.RiferimentoNumeroLinea:
                    invoice_lines = invoice_line_model.search(
                        [
                            ("move_id", "=", invoice_id),
                            ("sequence", "=", int(numline)),
                        ]
                    )
                    invoice_lineid = False
                    if invoice_lines:
                        invoice_lineid = invoice_lines[0].id
                    DdTModel.create(
                        {
                            "name": "" if 'NumeroDDT' not in DdtDataLine else DdtDataLine.NumeroDDT,
                            "date": False if 'DataDDT' not in DdtDataLine else DdtDataLine.DataDDT,
                            "invoice_id": invoice_id,
                            "invoice_line_id": invoice_lineid,
                        }
                    )

    def set_art73(self, FatturaBody, invoice_data):
        if 'Art73' in FatturaBody.DatiGenerali.DatiGeneraliDocumento:
            invoice_data["art73"] = True

    def set_roundings(self,FatturaBody, invoice,invoice_lines, invoice_line_model):
        rounding = 0.0
        if 'DatiRiepilogo' in FatturaBody.DatiBeniServizi:
            for summary in FatturaBody.DatiBeniServizi.DatiRiepilogo:
                rounding += 0.0 if 'Arrotondamento' not in summary else float(summary.Arrotondamento or 0.0)
        if 'DatiGeneraliDocumento' in FatturaBody.DatiGenerali:
            summary = FatturaBody.DatiGenerali.DatiGeneraliDocumento
            rounding += 0.0 if 'Arrotondamento' not in summary else float(summary.Arrotondamento or 0.0)


        if rounding:
            arrotondamenti_attivi_account_id = (
                self.env.company.arrotondamenti_attivi_account_id
            )
            if not arrotondamenti_attivi_account_id:
                raise UserError(
                    _("Round up account is not set " "in Accounting Settings")
                )

            arrotondamenti_passivi_account_id = (
                self.env.company.arrotondamenti_passivi_account_id
            )
            if not arrotondamenti_passivi_account_id:
                raise UserError(
                    _("Round down account is not set " "in Accounting Settings")
                )

            arrotondamenti_tax_id = self.env.company.arrotondamenti_tax_id
            if not arrotondamenti_tax_id:
                self.log_inconsistency(_("Round up and down tax is not set"))

            sequences = invoice.invoice_line_ids.mapped("sequence")
            if len(sequences)>0:
                line_sequence = max(sequences)
            else:
                line_sequence = 1
            line_vals = []
            for summary in FatturaBody.DatiBeniServizi.DatiRiepilogo:
                # XXX fallisce cattivo se non trova l'imposta Arrotondamento
                to_round = 0.0 if 'Arrotondamento' not in summary else float(summary.Arrotondamento or 0.0)
                if to_round != 0.0:
                    aliquotaIva =  None if 'AliquotaIVA' not in summary else summary.AliquotaIVA
                    natura = False if 'Natura' not in summary else summary.Natura
                    account_taxes = self.get_account_taxes(
                        aliquotaIva,natura
                    )
                    credit = 0.0
                    debit = 0.0

                    if to_round > 0.0:
                        arrotondamenti_account_id = arrotondamenti_passivi_account_id.id
                        debit = to_round
                    else:
                        arrotondamenti_account_id = arrotondamenti_attivi_account_id.id
                        credit = - to_round

                    invoice_line_tax_id = (
                        account_taxes[0].id
                        if account_taxes
                        else arrotondamenti_tax_id.id
                    )
                    name = _("Rounding down") if to_round > 0.0 else _("Rounding up")
                    line_sequence += 1
                    line_vals.append(
                        {
                            "sequence": line_sequence,
                            "move_id": invoice.id,
                            "name": name,
                            "account_id": arrotondamenti_account_id,
                            "price_unit": to_round,
                            "tax_ids": [(6, 0, [invoice_line_tax_id])]
                        }
                    )
            if line_vals:
                self._set_invoice_lines(
                    False, line_vals, invoice_lines, invoice_line_model
                )

                # line = self.env["account.move.line"].with_context(
                #     check_move_validity=False
                # ).create(line_vals)
                # invoice.line_ids |=line


    def set_efatt_rounding(self, FatturaBody, invoice_data):
        if 'Arrotondamento' in FatturaBody.DatiGenerali.DatiGeneraliDocumento:
            invoice_data["efatt_rounding"] = float(
                FatturaBody.DatiGenerali.DatiGeneraliDocumento.Arrotondamento
            )

    def set_activity_progress(self, FatturaBody, invoice):
        invoice_id = invoice.id
        SalDatas = False if 'DatiSAL' not in FatturaBody.DatiGenerali else FatturaBody.DatiGenerali.DatiSAL
        if SalDatas:
            SalModel = self.env["faturapa.activity.progress"]
            for SalDataLine in SalDatas:
                SalModel.create(
                    {
                        "fatturapa_activity_progress": SalDataLine.RiferimentoFase or 0,
                        "invoice_id": invoice_id,
                    }
                )

    def _get_last_due_date(self, DatiPagamento):
        dates = []
        for PaymentLine in DatiPagamento or []:
            details = PaymentLine.DettaglioPagamento
            if details:
                for dline in details:
                    if 'DataScadenzaPagamento' in dline and dline.DataScadenzaPagamento:
                        dates.append(fields.Date.to_date(dline.DataScadenzaPagamento))
        dates.sort(reverse=True)
        return dates

    def set_payments_data(self, FatturaBody, invoice, partner_id):
        invoice_id = invoice.id
        PaymentsData = False if 'DatiPagamento' not in FatturaBody else FatturaBody.DatiPagamento
        partner = self.env["res.partner"].browse(partner_id)
        if not partner.property_supplier_payment_term_id:
            if 'DatiPagamento' in FatturaBody:
                due_dates = self._get_last_due_date(FatturaBody.DatiPagamento)
                if due_dates:
                    self.env["account.move"].browse(
                        invoice_id
                    ).invoice_date_due = due_dates[0]
        if PaymentsData:
            PaymentDataModel = self.env["fatturapa.payment.data"]
            PaymentTermsModel = self.env["fatturapa.payment_term"]
            for PaymentLine in PaymentsData:
                cond = False if 'CondizioniPagamento' not in PaymentLine else PaymentLine.CondizioniPagamento
                if not cond:
                    raise UserError(_("Payment method code not found in document."))
                terms = PaymentTermsModel.search([("code", "=", cond)])
                if not terms:
                    raise UserError(_("Payment method code %s is incorrect.") % cond)
                else:
                    term_id = terms[0].id
                PayDataId = PaymentDataModel.create(
                    {"payment_terms": term_id, "invoice_id": invoice_id}
                ).id
                self._createPaymentsLine(PayDataId, PaymentLine, partner_id)

    def set_withholding_tax(self, FatturaBody, invoice_data):
        Withholdings = False if 'DatiRitenuta' not in FatturaBody.DatiGenerali.DatiGeneraliDocumento else FatturaBody.DatiGenerali.DatiGeneraliDocumento.DatiRitenuta
        if not Withholdings:
            return None
        invoice_data["ftpa_withholding_ids"] = []
        wt_founds = []
        for Withholding in Withholdings:
            wts = self.env["withholding.tax"].search(
                [("causale_pagamento_id.code", "=", Withholding.CausalePagamento)]
            )
            if not wts:
                raise UserError(
                    _(
                        "The bill contains withholding tax with "
                        "payment reason %s, "
                        "but such a tax is not found in your system. Please "
                        "set it."
                    )
                    % Withholding.CausalePagamento
                )

            for wt in wts:
                if (
                    wt.tax == float(Withholding.AliquotaRitenuta)
                    and WT_CODES_MAPPING[Withholding.TipoRitenuta] == wt.wt_types
                ):
                    wt_founds.append(wt)
                    break
            else:
                raise UserError(
                    _(
                        "No withholding tax found with "
                        "document payment reason %s, rate %s and type %s."
                    )
                    % (
                        Withholding.CausalePagamento,
                        Withholding.AliquotaRitenuta,
                        WT_CODES_MAPPING[Withholding.TipoRitenuta],
                    )
                )
            invoice_data["ftpa_withholding_ids"].append(
                (
                    0,
                    0,
                    {
                        "name": Withholding.TipoRitenuta,
                        "amount": Withholding.ImportoRitenuta,
                    },
                )
            )
        return wt_founds

    def set_welfares_fund(self, FatturaBody, credit_account_id, invoice, wt_founds):
        if not self.e_invoice_detail_level == "2":
            return

        Welfares = False if 'DatiCassaPrevidenziale' not in FatturaBody.DatiGenerali.DatiGeneraliDocumento else FatturaBody.DatiGenerali.DatiGeneraliDocumento.DatiCassaPrevidenziale
        if not Welfares:
            return

        WelfareFundLineModel = self.env["welfare.fund.data.line"]
        for welfareLine in Welfares:
            WalfarLineVals = self._prepareWelfareLine(invoice.id, welfareLine)
            WelfareFundLineModel.create(WalfarLineVals)

            if welfareLine.TipoCassa == "TC07":
                continue

            line_vals = self._prepare_generic_line_data(welfareLine)
            line_vals.update(
                {
                    "name": _("Welfare Fund: %s") % welfareLine.TipoCassa,
                    "price_unit": float(welfareLine.ImportoContributoCassa),
                    "move_id": invoice.id,
                    "account_id": credit_account_id,
                }
            )
            if 'Ritenuta' in welfareLine and welfareLine.Ritenuta:
                if not wt_founds:
                    raise UserError(
                        _(
                            "Welfare Fund data %s has withholding tax but no "
                            "withholding tax was found in the system."
                        )
                        % welfareLine.TipoCassa
                    )
                line_vals["invoice_line_tax_wt_ids"] = [
                    (6, 0, [wt.id for wt in wt_founds])
                ]
            if self.env.company.cassa_previdenziale_product_id:
                cassa_previdenziale_product = (
                    self.env.company.cassa_previdenziale_product_id
                )
                line_vals["product_id"] = cassa_previdenziale_product.id
                line_vals["name"] = cassa_previdenziale_product.name
                self.adjust_accounting_data(cassa_previdenziale_product, line_vals)
            self.env["account.move.line"].with_context(
                check_move_validity=False
            ).create(line_vals)

    def _convert_datetime(self, dtstring):
        ret = False
        try:
            dt = datetime.strptime(dtstring, "%Y-%m-%dT%H:%M:%S")
            if dt:
                ret = dt.strftime("%Y-%m-%d %H:%M:%S")
        except (TypeError, ValueError):
            pass
        return ret

    def set_delivery_data(self, FatturaBody, invoice):
        Delivery = False if 'DatiTrasporto' not in FatturaBody.DatiGenerali else FatturaBody.DatiGenerali.DatiTrasporto
        if Delivery:
            delivery_id = self.getCarrirerPartner(Delivery)
            delivery_dict = {
                "carrier_id": delivery_id,
                "transport_vehicle": "" if 'MezzoTrasporto' not in Delivery else Delivery.MezzoTrasporto,
                "transport_reason": "" if 'CausaleTrasporto' not in Delivery else Delivery.CausaleTrasporto,
                "number_items": 0 if 'NumeroColli' not in Delivery else Delivery.NumeroColli,
                "description": "" if 'Descrizione' not in Delivery else Delivery.Descrizione,
                "unit_weight": 0.0 if 'UnitaMisuraPeso' not in Delivery else Delivery.UnitaMisuraPeso,
                "gross_weight": 0.0 if 'PesoLordo' not in Delivery else Delivery.PesoLordo,
                "net_weight": 0.0 if 'PesoNetto' not in Delivery else Delivery.PesoNetto,
                "pickup_datetime": False if 'DataOraRitiro' not in Delivery else Delivery.DataOraRitiro,
                "transport_date": False if 'DataInizioTrasporto' not in Delivery else Delivery.DataInizioTrasporto,
                "delivery_datetime": False if 'DataOraConsegna' not in Delivery else Delivery.DataOraConsegna,
                "delivery_address": "",
                "ftpa_incoterms": "" if 'TipoResa' not in Delivery else Delivery.TipoResa
            }

            if 'IndirizzoResa' in Delivery and Delivery.IndirizzoResa:
                delivery_dict["delivery_address"] = "{}, {}\n{} - {}\n{} {}".format(
                    "" if 'Indirizzo' not in Delivery.IndirizzoResa else Delivery.IndirizzoResa.Indirizzo,
                    "" if 'NumeroCivico' not in Delivery.IndirizzoResa else Delivery.IndirizzoResa.NumeroCivico,
                    "" if 'CAP' not in Delivery.IndirizzoResa else Delivery.IndirizzoResa.CAP,
                    "" if 'Comune' not in Delivery.IndirizzoResa else Delivery.IndirizzoResa.Comune,
                    "" if 'Provincia' not in Delivery.IndirizzoResa else Delivery.IndirizzoResa.Provincia,
                    "" if 'Nazione' not in Delivery.IndirizzoResa else Delivery.IndirizzoResa.Nazione,
                )
            invoice.write(delivery_dict)

    def set_summary_data(self, FatturaBody, invoice):
        invoice_id = invoice.id
        Summary_datas = False if 'DatiRiepilogo' not in FatturaBody.DatiBeniServizi else FatturaBody.DatiBeniServizi.DatiRiepilogo
        summary_data_model = self.env["faturapa.summary.data"]
        if Summary_datas:
            for summary in Summary_datas:
                summary_line = {
                    "tax_rate": 0.0 if 'AliquotaIVA' not in summary else summary.AliquotaIVA,
                    "non_taxable_nature": False if 'Natura' not in summary else summary.Natura,
                    "incidental_charges": 0.0 if 'SpeseAccessorie' not in summary else summary.SpeseAccessorie,
                    "rounding": 0.0 if 'Arrotondamento' not in summary else summary.Arrotondamento,
                    "amount_untaxed": 0.0 if 'ImponibileImporto' not in summary else summary.ImponibileImporto,
                    "amount_tax": 0.0 if 'Imposta' not in summary else summary.Imposta,
                    "payability": False if 'EsigibilitaIVA' not in summary else summary.EsigibilitaIVA,
                    "law_reference": "" if 'RiferimentoNormativo' not in summary else summary.RiferimentoNormativo,
                    "invoice_id": invoice_id,
                }
                summary_data_model.create(summary_line)

    def set_e_invoice_lines(self, FatturaBody, invoice_data):
        e_invoice_lines = self.env["einvoice.line"].browse()
        if 'DettaglioLinee' in FatturaBody.DatiBeniServizi:
            for line in FatturaBody.DatiBeniServizi.DettaglioLinee:
                e_invoice_lines |= self.create_e_invoice_line(line)
        if e_invoice_lines:
            invoice_data["e_invoice_line_ids"] = [(6, 0, e_invoice_lines.ids)]

    def _set_invoice_lines(
        self, product, invoice_line_data, invoice_lines, invoice_line_model
    ):

        if product:
            invoice_line_data["product_id"] = product.id
            self.adjust_accounting_data(product, invoice_line_data)
        invoice_line_id = (
            invoice_line_model.with_context(check_move_validity=False)
            .create(invoice_line_data)
            .id
        )
        invoice_lines.append(invoice_line_id)

    # move_id
    # account_id
    def set_invoice_line_ids(
        self, FatturaBody, credit_account_id, partner, wt_founds, invoice
    ):

        if self.e_invoice_detail_level == "0":
            return

        pay_acc_id = partner.property_account_payable_id.id
        invoice_lines = []
        invoice_line_model = self.env["account.move.line"]
        if self.e_invoice_detail_level == "1":
            for nline, line in enumerate(FatturaBody.DatiBeniServizi.DatiRiepilogo):
                invoice_line_data = self._prepareInvoiceLineAliquota(
                    credit_account_id, line, nline
                )
                invoice_line_data["move_id"] = invoice.id

                product = partner.e_invoice_default_product_id
                self._set_invoice_lines(
                    product, invoice_line_data, invoice_lines, invoice_line_model
                )

        elif self.e_invoice_detail_level == "2":
            for line in FatturaBody.DatiBeniServizi.DettaglioLinee:
                invoice_line_data = self._prepareInvoiceLine(
                    credit_account_id, line, wt_founds
                )
                invoice_line_data["move_id"] = invoice.id

                product = self.get_line_product(line, partner)
                self._set_invoice_lines(
                    product, invoice_line_data, invoice_lines, invoice_line_model
                )


        self.set_roundings(FatturaBody, invoice,invoice_lines, invoice_line_model)

        invoice.with_context(check_move_validity=False).update(
            {"invoice_line_ids": [(6, 0, invoice_lines)]}
        )

    def check_invoice_amount(self, invoice, FatturaElettronicaBody):
        dgd = False if 'DatiGeneraliDocumento' not in FatturaElettronicaBody.DatiGenerali else FatturaElettronicaBody.DatiGenerali.DatiGeneraliDocumento

        if dgd and 'ScontoMaggiorazione' in dgd and dgd.ScontoMaggiorazione and 'ImportoTotaleDocumento' in dgd and dgd.ImportoTotaleDocumento:
            # assuming that, if someone uses
            # DatiGeneraliDocumento.ScontoMaggiorazione, also fills
            # DatiGeneraliDocumento.ImportoTotaleDocumento
            ImportoTotaleDocumento = float(dgd.ImportoTotaleDocumento)
            if not float_is_zero(
                invoice.amount_total - ImportoTotaleDocumento, precision_digits=2
            ):
                self.log_inconsistency(
                    _("Bill total %s is different from " "document total amount %s")
                    % (invoice.amount_total, ImportoTotaleDocumento)
                )
        else:
            # else, we can only check DatiRiepilogo if
            # DatiGeneraliDocumento.ScontoMaggiorazione is not present,
            # because otherwise DatiRiepilogo and odoo invoice total would
            # differ
            amount_untaxed = invoice.compute_xml_amount_untaxed(FatturaElettronicaBody)
            if not float_is_zero(
                invoice.amount_untaxed - amount_untaxed, precision_digits=2
            ):
                self.log_inconsistency(
                    _("Computed amount untaxed %s is different from" " summary data %s")
                    % (invoice.amount_untaxed, amount_untaxed)
                )

    def get_invoice_obj(self, fatturapa_attachment):
        xml_string = fatturapa_attachment.get_xml_string()
        return efattura.CreateFromDocument(xml_string)

    def importFatturaPA(self):
        self.ensure_one()
        fatturapa_attachment_obj = self.env["fatturapa.attachment.in"]
        fatturapa_attachment_ids = self.env.context.get("active_ids", False)
        new_invoices = []
        for fatturapa_attachment_id in fatturapa_attachment_ids:
            # XXX - da controllare
            # self.__dict__.update(self.with_context(inconsistencies="").__dict__)
            fatturapa_attachment = fatturapa_attachment_obj.browse(
                fatturapa_attachment_id
            )
            if fatturapa_attachment.in_invoice_ids:
                raise UserError(_("File is linked to bills yet."))

            fatt = self.get_invoice_obj(fatturapa_attachment)
            cedentePrestatore = fatt.FatturaElettronicaHeader.CedentePrestatore
            # 1.2
            partner_id = self.getCedPrest(cedentePrestatore)
            # 1.3
            TaxRappresentative = False if 'RappresentanteFiscale' not in fatt.FatturaElettronicaHeader else fatt.FatturaElettronicaHeader.RappresentanteFiscale
            # 1.5
            Intermediary = (
                False if 'TerzoIntermediarioOSoggettoEmittente' not in fatt.FatturaElettronicaHeader else fatt.FatturaElettronicaHeader.TerzoIntermediarioOSoggettoEmittente
            )

            generic_inconsistencies = ""
            if self.env.context.get("inconsistencies"):
                generic_inconsistencies = self.env.context["inconsistencies"] + "\n\n"

            xmlproblems = getattr(fatt, "_xmldoctor", None)
            if xmlproblems:  # None or []
                generic_inconsistencies += "\n".join(xmlproblems) + "\n\n"

            # 2
            for fattura in fatt.FatturaElettronicaBody:

                # reset inconsistencies
                # self.__dict__.update(self.with_context(inconsistencies="").__dict__)

                invoice = self.invoiceCreate(
                    fatt, fatturapa_attachment, fattura, partner_id
                )

                self.set_StabileOrganizzazione(cedentePrestatore, invoice)
                if TaxRappresentative:
                    tax_partner_id = self.getPartnerBase(
                        TaxRappresentative.DatiAnagrafici
                    )
                    invoice.write({"tax_representative_id": tax_partner_id})
                if Intermediary:
                    Intermediary_id = self.getPartnerBase(Intermediary.DatiAnagrafici)
                    invoice.write({"intermediary": Intermediary_id})
                new_invoices.append(invoice.id)
                self.check_invoice_amount(invoice, fattura)

                invoice.set_einvoice_data(fattura)

                if self.env.context.get("inconsistencies"):
                    invoice_inconsistencies = self.env.context["inconsistencies"]
                else:
                    invoice_inconsistencies = ""
                invoice.inconsistencies = (
                    generic_inconsistencies + invoice_inconsistencies
                )

        return {
            "view_type": "form",
            "name": "Electronic Bills",
            "view_mode": "tree,form",
            "res_model": "account.move",
            "type": "ir.actions.act_window",
            "domain": [("id", "in", new_invoices)],
        }
