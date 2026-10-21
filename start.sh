#!/usr/bin/env sh
# Startet Rechnungs-Tinder (Linux / macOS). Beim ersten Start wird alles eingerichtet.
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
  echo "Erster Start: Programm wird eingerichtet. Das dauert einen Moment ..."
  python3 -m venv .venv && .venv/bin/python -m pip install -q -r requirements.txt || {
    echo "Fehler bei der Einrichtung. Ist Python 3 installiert?"; exit 1; }
fi
exec .venv/bin/python -m rechnungs_tinder "$@"
