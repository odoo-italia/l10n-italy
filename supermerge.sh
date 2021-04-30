#!/bin/sh -

# Questo script serve per ricreare/aggiornare una copia locale del branch supermerge
# NOTA: non tutti i pull possono essere "puliti"
# Vanno risolti un paio di conflitti che possono riguardare file comuni aggiornati
# contemporaneamente dai vari moduli, in pratica sono .pre-commit-config.yaml e
# requirements.txt. Una volta risolti i conflitti potete rilanciare lo script.

# clone iniziale
if [ ! -x l10n-italy -a ! -x .git ]; then
	git clone --single-branch --branch 14.0 https://github.com/OCA/l10n-italy 
	(cd l10n-italy; git checkout -b 14.0-supermerge)
fi
[ -x l10n-italy ] && cd l10n-italy

set -xe
git pull --no-ff --no-edit --quiet https://github.com/odoo-italia/l10n-italy 14.0-premerge
# merged # git pull --no-ff --no-edit --quiet https://github.com/OCA/l10n-italy pull/1929/head
# merged # git pull --no-ff --no-edit --quiet https://github.com/OCA/l10n-italy pull/1930/head
# merged # git pull --no-ff --no-edit --quiet https://github.com/OCA/l10n-italy pull/1931/head
# merged # git pull --no-ff --no-edit --quiet https://github.com/OCA/l10n-italy pull/1938/head
# merged # git pull --no-ff --no-edit --quiet https://github.com/OCA/l10n-italy pull/1939/head
# merged # git pull --no-ff --no-edit --quiet https://github.com/OCA/l10n-italy pull/1942/head
# merged # git pull --no-ff --no-edit --quiet https://github.com/fredzamoabg/l10n-italy pull/5/head
# merged # git pull --no-ff --no-edit --quiet https://github.com/OCA/l10n-italy pull/1950/head
# closed, see #2234 # git pull --no-ff --no-edit --quiet https://github.com/OCA/l10n-italy pull/1959/head
# merged # git pull --no-ff --no-edit --quiet https://github.com/OCA/l10n-italy pull/1973/head
# merged # git pull --no-ff --no-edit --quiet https://github.com/OCA/l10n-italy pull/1974/head
# merged # git pull --no-ff --no-edit --quiet https://github.com/OCA/l10n-italy pull/1975/head
git pull --no-ff --no-edit --quiet https://github.com/OCA/l10n-italy pull/1984/head
git pull --no-ff --no-edit --quiet https://github.com/OCA/l10n-italy pull/1985/head
git pull --no-ff --no-edit --quiet https://github.com/OCA/l10n-italy pull/2154/head
git pull --no-ff --no-edit --quiet https://github.com/OCA/l10n-italy pull/1987/head
git pull --no-ff --no-edit --quiet https://github.com/OCA/l10n-italy pull/1988/head
git pull --no-ff --no-edit --quiet https://github.com/OCA/l10n-italy pull/1989/head
git pull --no-ff --no-edit --quiet https://github.com/OCA/l10n-italy pull/1990/head
git pull --no-ff --no-edit --quiet https://github.com/OCA/l10n-italy pull/2043/head
git pull --no-ff --no-edit --quiet https://github.com/OCA/l10n-italy pull/2044/head
# merged # git pull --no-ff --no-edit --quiet https://github.com/OCA/l10n-italy pull/2079/head
# merged # git pull --no-ff --no-edit --quiet https://github.com/OCA/l10n-italy pull/2077/head
git pull --no-ff --no-edit --quiet https://github.com/OCA/l10n-italy pull/2080/head
git pull --no-ff --no-edit --quiet https://github.com/OCA/l10n-italy pull/2128/head
# merged # git pull --no-ff --no-edit --quiet https://github.com/TheMule71/l10n-italy 14.0-mig-l10n_it_reverse_charge
git pull --no-ff --no-edit --quiet https://github.com/OCA/l10n-italy pull/2138/head
git pull --no-ff --no-edit --quiet https://github.com/OCA/l10n-italy pull/2139/head
# merged # git pull --no-ff --no-edit --quiet https://github.com/OCA/l10n-italy pull/2140/head
# merged # git pull --no-ff --no-edit --quiet https://github.com/OCA/l10n-italy pull/2141/head
git pull --no-ff --no-edit --quiet https://github.com/OCA/l10n-italy pull/2149/head
# merged # as #2210 # git pull --no-ff --no-edit --quiet https://github.com/OCA/l10n-italy pull/2153/head
# merged # git pull --no-ff --no-edit --quiet https://github.com/OCA/l10n-italy pull/2156/head
git pull --no-ff --no-edit --quiet https://github.com/OCA/l10n-italy pull/2157/head
git pull --no-ff --no-edit --quiet https://github.com/OCA/l10n-italy pull/2166/head
git pull --no-ff --no-edit --quiet https://github.com/OCA/l10n-italy pull/2195/head
git pull --no-ff --no-edit --quiet https://github.com/OCA/l10n-italy pull/2198/head
# closed, see #2230 # git pull --no-ff --no-edit --quiet https://github.com/OCA/l10n-italy pull/2199/head
git pull --no-ff --no-edit --quiet https://github.com/OCA/l10n-italy pull/2200/head
git pull --no-ff --no-edit --quiet https://github.com/OCA/l10n-italy pull/2202/head
git pull --no-ff --no-edit --quiet https://github.com/OCA/l10n-italy pull/2205/head
git pull --no-ff --no-edit --quiet https://github.com/OCA/l10n-italy pull/2220/head
git pull --no-ff --no-edit --quiet https://github.com/OCA/l10n-italy pull/2225/head
git pull --no-ff --no-edit --quiet https://github.com/OCA/l10n-italy pull/2228/head
git pull --no-ff --no-edit --quiet https://github.com/OCA/l10n-italy pull/2229/head
git pull --no-ff --no-edit --quiet https://github.com/OCA/l10n-italy pull/2230/head
git pull --no-ff --no-edit --quiet https://github.com/OCA/l10n-italy pull/2234/head
git pull --no-ff --no-edit --quiet https://github.com/OCA/l10n-italy pull/2258/head
git pull --no-ff --no-edit --quiet https://github.com/OCA/l10n-italy pull/2259/head
