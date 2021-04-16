# Copyright 2021 Marco Colombo <https://github.com/TheMule71>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.update_module_names(
        env.cr,
        [
            ("l10n_it_withholding_tax_causali", "l10n_it_withholding_tax_reason"),
        ],
    )
