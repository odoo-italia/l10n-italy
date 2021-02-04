# Copyright 2019 Sergio Corato (https://efatto.it)
# Copyright 2021 Matteo Boscolo (https://www.omniasolutions.eu)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Italian Localization - Fattura elettronica - Import ZIP",
    "summary": "Permette di importare uno ZIP diversi file XML di "
               "fatture elettroniche di acquisto",
    "version": "14.0.1.0.1",
    "development_status": "Beta",
    "category": "other",
    "website": "https://github.com/OCA/l10n-italy",
    "author": "Efatto.it di Sergio Corato, Odoo Community Association (OCA)",
    "maintainers": ["sergiocorato",'info@omniasolutions.eu'],
    "license": "AGPL-3",
    "application": False,
    "installable": True,
    "depends": [
        "l10n_it_fatturapa_in",
    ],
    "external_dependencies": {
        "python": ["zipfile"],
    },
    "data": [
        "security/ir.model.access.csv",
        "wizard/wizard_import_invoice.xml",
    ],
}
