# © 2020 Lorenzo Battistini
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "ITA - Fattura elettronica - Import ZIP",
    "description": (
        "Allow to massively import XML e-invoices, in and out, through a ZIP file.\n"
        "This is typically used while starting to use the system, to import invoices"
        " from previous software."
    ),
    "version": "12.0.1.0.0",
    "category": "Localization/Italy",
    "website": "https://github.com/OCA/l10n-italy",
    "author": "TAKOBI",
    "license": "AGPL-3",
    "application": False,
    "installable": True,
    "depends": [
        "l10n_it_account",
        "l10n_it_fatturapa_out",
        "l10n_it_fatturapa_in",
        "l10n_it_fatturapa_pec",
    ],
    "data": [
        "views/account_invoice_views.xml",
        "views/attachment_views.xml",
        "security/ir.model.access.csv",
        "security/rules.xml",
    ],
    "auto_install": False,
}
