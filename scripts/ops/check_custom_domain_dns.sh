#!/usr/bin/env bash
# Operator script (Christopher). Not for Dennis.
#
# Mechanically compare the tools.prosema.ch custom-domain records against the
# Azure values. Hostpoint's TXT has differed from Azure's by four E→F
# substitutions and a truncated tail — that is not something to re-check by eye.

set -euo pipefail

DOMAIN="tools.prosema.ch"
# Copied from the Azure portal copy button. Never transcribe these by hand.
TARGET="prosema-tools-prod-htceewc9dta5h5g9.switzerlandnorth-01.azurewebsites.net"
EXPECTED_TXT="AFE6D10860C53F1D23859D4616836F4C1DE36F98003A12DE7DAB17E235DA1336"

cname=$(dig +short "$DOMAIN" CNAME | sed 's/\.$//')
txt=$(dig +short "asuid.$DOMAIN" TXT | tr -d '"')

rc=0
[ "$cname" = "$TARGET" ] \
  && echo "CNAME  OK" \
  || { printf 'CNAME  MISMATCH\n  expected: %s\n  got:      %s\n' "$TARGET" "$cname"; rc=1; }
[ "$txt" = "$EXPECTED_TXT" ] \
  && echo "TXT    OK" \
  || { printf 'TXT    MISMATCH\n  expected: %s\n  got:      %s\n' "$EXPECTED_TXT" "$txt"; rc=1; }
exit $rc
