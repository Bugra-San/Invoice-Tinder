#!/usr/bin/env sh
# Startet Rechnungs-Tinder auch fuer Smartphones/Tablets im WLAN (Anmeldung mit PIN).
# Beim ersten Mal den freigegebenen Ordner angeben:  ./start-netzwerk.sh --ordner ~/Rechnungen
exec "$(dirname "$0")/start.sh" --netzwerk "$@"
