@echo off
rem Startet Rechnungs-Tinder auch fuer Smartphones/Tablets im WLAN (Anmeldung mit PIN).
rem Beim ersten Mal den freigegebenen Ordner angeben, z. B.:
rem     start-netzwerk.bat --ordner "D:\Rechnungen"
call "%~dp0start.bat" --netzwerk %*
