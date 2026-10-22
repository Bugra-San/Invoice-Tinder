#!/usr/bin/env bash
# =============================================================================
#  Rechnungs-Tinder auf einem Ubuntu-Server einrichten, aktualisieren oder entfernen
#
#    sudo ./installieren-ubuntu.sh                einrichten bzw. aktualisieren
#    sudo ./installieren-ubuntu.sh --entfernen    Programm entfernen (Rechnungen bleiben)
#
#  Weitere Optionen:
#    --lokaler-ordner PFAD   statt NAS einen Ordner auf dem Server verwenden (z. B. zum Ausprobieren)
#    --ja                    vorhandene Einstellungen ohne Rückfrage übernehmen
#
#  Das Skript
#    1. installiert Docker und die Werkzeuge für Windows-Freigaben (SMB/CIFS),
#    2. bindet die NAS-Freigabe dauerhaft unter /mnt/rechnungen ein
#       (die passende SMB-Version – auch für ältere Synology-Geräte – wird automatisch gesucht),
#    3. prüft, ob Lesen und Schreiben auf dem NAS klappt,
#    4. installiert das Programm nach /opt/rechnungs-tinder und startet es,
#    5. sorgt dafür, dass alles nach einem Neustart des Servers von selbst wieder läuft.
# =============================================================================
set -euo pipefail

QUELLE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ZIEL=/opt/rechnungs-tinder
KONFIG=/etc/rechnungs-tinder
ZUGANG=$KONFIG/nas-zugang
ANTWORTEN=$KONFIG/einrichtung.conf
MOUNTPUNKT=/mnt/rechnungen
BENUTZER=rechnungstinder
FSTAB_MARKE="# rechnungs-tinder"
DOCKER_DROPIN=/etc/systemd/system/docker.service.d/rechnungs-tinder.conf

# ----------------------------------------------------------------- Ausgaben
info()   { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
ok()     { printf '    \033[32m✔ %s\033[0m\n' "$*"; }
hinweis(){ printf '    \033[33m! %s\033[0m\n' "$*"; }
fehler() { printf '\n\033[1;31mFEHLER: %s\033[0m\n' "$*" >&2; exit 1; }

frage() {  # frage VARIABLE "Frage" "Vorgabe"
    local var=$1 text=$2 vorgabe=${3:-} antwort
    if [[ -n $vorgabe ]]; then
        read -r -p "    $text [$vorgabe]: " antwort || true
    else
        read -r -p "    $text: " antwort || true
    fi
    printf -v "$var" '%s' "${antwort:-$vorgabe}"
}

ja_nein() {  # ja_nein "Frage" -> 0 = ja (Vorgabe ja)
    local antwort
    read -r -p "    $1 [J/n]: " antwort || true
    [[ -z $antwort || $antwort =~ ^[JjYy] ]]
}

systemd_aktiv() { [[ -d /run/systemd/system ]]; }

# ----------------------------------------------------------------- Optionen
LOKALER_ORDNER=""
ENTFERNEN=0
OHNE_RUECKFRAGE=0
while [[ $# -gt 0 ]]; do
    case $1 in
        --lokaler-ordner) LOKALER_ORDNER=${2:?Pfad fehlt}; shift 2 ;;
        --entfernen) ENTFERNEN=1; shift ;;
        --ja) OHNE_RUECKFRAGE=1; shift ;;
        -h|--hilfe|--help) sed -n '2,20p' "$0"; exit 0 ;;
        *) fehler "Unbekannte Option: $1 (Hilfe: --hilfe)" ;;
    esac
done

[[ $EUID -eq 0 ]] || fehler "Bitte mit sudo starten:  sudo $0"
if ! grep -qi ubuntu /etc/os-release 2>/dev/null; then
    hinweis "Dieses Skript ist für Ubuntu gedacht – andere Systeme auf eigene Gefahr."
fi

compose() { docker compose --project-directory "$ZIEL" -f "$ZIEL/docker-compose.yml" "$@"; }

# ================================================================= Entfernen
if [[ $ENTFERNEN -eq 1 ]]; then
    info "Rechnungs-Tinder wird entfernt"
    if [[ -f $ZIEL/docker-compose.yml ]] && command -v docker >/dev/null; then
        compose down --volumes || true
        ok "Programm gestoppt und entfernt"
    fi
    if mountpoint -q "$MOUNTPUNKT"; then umount "$MOUNTPUNKT" || true; fi
    sed -i "\|$FSTAB_MARKE|d" /etc/fstab
    rm -f "$DOCKER_DROPIN"
    systemd_aktiv && systemctl daemon-reload || true
    chattr -i "$MOUNTPUNKT" 2>/dev/null || true
    rm -rf "$ZIEL" "$KONFIG"
    ok "NAS-Einbindung und Einstellungen entfernt. Die Rechnungen auf dem NAS sind unverändert."
    exit 0
fi

# ================================================================= Einstellungen
NAS_ADRESSE="" NAS_FREIGABE="" NAS_BENUTZER="" NAS_PASSWORT="" SMB_VERSION=""
PORT=8765 PIN=""
VORHANDEN=0
if [[ -f $ANTWORTEN ]]; then
    # shellcheck disable=SC1090
    source "$ANTWORTEN"
    VORHANDEN=1
fi

echo
echo "  ╔════════════════════════════════════════════════════════════╗"
echo "  ║            Rechnungs-Tinder – Einrichtung (Ubuntu)         ║"
echo "  ╚════════════════════════════════════════════════════════════╝"

NEU_FRAGEN=1
if [[ $VORHANDEN -eq 1 && -z $LOKALER_ORDNER ]]; then
    info "Vorhandene Einrichtung gefunden"
    if [[ -n $NAS_ADRESSE ]]; then
        echo "    NAS:   //$NAS_ADRESSE/$NAS_FREIGABE (Benutzer $NAS_BENUTZER, SMB $SMB_VERSION)"
    else
        echo "    Ordner: ${LOKAL:-?}"
    fi
    echo "    Port:  $PORT     PIN: $PIN"
    if [[ $OHNE_RUECKFRAGE -eq 1 ]] || ja_nein "Diese Einstellungen übernehmen (nur Programm aktualisieren)?"; then
        NEU_FRAGEN=0
    fi
fi

if [[ $NEU_FRAGEN -eq 1 ]]; then
    info "Ein paar Angaben"
    if [[ -n $LOKALER_ORDNER ]]; then
        LOKAL=$(realpath -m "$LOKALER_ORDNER")
        NAS_ADRESSE="" NAS_FREIGABE="" NAS_BENUTZER="" SMB_VERSION=""
        echo "    Rechnungsordner auf diesem Server: $LOKAL"
    else
        LOKAL=""
        echo "    Angaben zur Synology (siehe docs/SERVER.md, Abschnitt „Synology vorbereiten“):"
        frage NAS_ADRESSE  "IP-Adresse oder Name des NAS (z. B. 192.168.1.10)" "$NAS_ADRESSE"
        frage NAS_FREIGABE "Name des freigegebenen Ordners (z. B. Rechnungen)" "${NAS_FREIGABE:-Rechnungen}"
        frage NAS_BENUTZER "NAS-Benutzer mit Schreibrechten" "${NAS_BENUTZER:-rechnungen}"
        read -r -s -p "    Passwort dieses NAS-Benutzers: " NAS_PASSWORT || true; echo
        [[ -n $NAS_ADRESSE && -n $NAS_FREIGABE && -n $NAS_BENUTZER && -n $NAS_PASSWORT ]] \
            || fehler "Bitte alle Angaben zum NAS ausfüllen."
        NAS_FREIGABE=${NAS_FREIGABE#/}
    fi
    frage PORT "Port für das Programm" "$PORT"
    [[ $PORT =~ ^[0-9]+$ ]] || fehler "Der Port muss eine Zahl sein."
    [[ -n $PIN ]] || PIN=$(printf '%06d' $(( $(od -An -N4 -tu4 /dev/urandom) % 1000000 )))
    frage PIN "PIN zum Anmelden (nur Ziffern, mind. 6 empfohlen)" "$PIN"
    [[ $PIN =~ ^[0-9]{4,12}$ ]] || fehler "Die PIN muss aus 4 bis 12 Ziffern bestehen."
fi

# ================================================================= Pakete
info "Benötigte Programme werden installiert"
export DEBIAN_FRONTEND=noninteractive
PAKETE=(ca-certificates curl)
[[ -z ${LOKAL:-} ]] && PAKETE+=(cifs-utils)
FEHLT=()
for p in "${PAKETE[@]}"; do dpkg -s "$p" >/dev/null 2>&1 || FEHLT+=("$p"); done
if [[ ${#FEHLT[@]} -gt 0 ]]; then
    apt-get update -qq
    apt-get install -y -qq "${FEHLT[@]}" >/dev/null
fi
ok "Werkzeuge vorhanden"
if ! command -v docker >/dev/null; then
    echo "    Docker wird installiert (dauert ein paar Minuten) …"
    curl -fsSL https://get.docker.com | sh >/dev/null
fi
if ! docker compose version >/dev/null 2>&1; then
    apt-get install -y -qq docker-compose-plugin >/dev/null 2>&1 \
        || apt-get install -y -qq docker-compose-v2 >/dev/null 2>&1 \
        || fehler "Docker Compose konnte nicht installiert werden."
fi
systemd_aktiv && systemctl enable --now docker >/dev/null 2>&1 || true
ok "Docker $(docker version --format '{{.Server.Version}}' 2>/dev/null || echo '?') bereit"

# ================================================================= Dienstbenutzer
if ! id -u "$BENUTZER" >/dev/null 2>&1; then
    useradd --system --no-create-home --shell /usr/sbin/nologin "$BENUTZER"
fi
PUID=$(id -u "$BENUTZER")
PGID=$(id -g "$BENUTZER")
ok "Programm läuft als Benutzer „$BENUTZER“ ($PUID:$PGID)"

mkdir -p "$KONFIG"
chmod 700 "$KONFIG"

# ================================================================= Rechnungsordner
schreibtest() {  # schreibtest ORDNER -> prüft Schreibrechte als Dienstbenutzer
    local datei="$1/.rechnungs-tinder-schreibtest"
    if runuser -u "$BENUTZER" -- sh -c "echo test > '$datei' && rm -f '$datei'" 2>/dev/null; then
        return 0
    fi
    rm -f "$datei" 2>/dev/null || true
    return 1
}

if [[ -n ${LOKAL:-} ]]; then
    info "Rechnungsordner auf dem Server"
    mkdir -p "$LOKAL"
    chown "$PUID:$PGID" "$LOKAL"
    RECHNUNGEN_ORDNER=$LOKAL
    schreibtest "$LOKAL" || fehler "Der Benutzer $BENUTZER darf nicht in $LOKAL schreiben."
    ok "$LOKAL"
else
    info "NAS-Freigabe wird eingebunden"
    if [[ $NEU_FRAGEN -eq 1 ]]; then
        umask 077
        printf 'username=%s\npassword=%s\n' "$NAS_BENUTZER" "$NAS_PASSWORT" > "$ZUGANG"
        umask 022
    fi
    [[ -f $ZUGANG ]] || fehler "Zugangsdaten fehlen ($ZUGANG). Bitte neu einrichten."
    chmod 600 "$ZUGANG"

    GERAET="//$NAS_ADRESSE/$NAS_FREIGABE"
    OPTIONEN="credentials=$ZUGANG,uid=$PUID,gid=$PGID,file_mode=0664,dir_mode=0775,iocharset=utf8"

    mkdir -p "$MOUNTPUNKT"
    if mountpoint -q "$MOUNTPUNKT"; then umount "$MOUNTPUNKT" || umount -l "$MOUNTPUNKT"; fi
    # Ohne eingebundenes NAS darf niemand in den leeren Ordner schreiben.
    chattr +i "$MOUNTPUNKT" 2>/dev/null || true

    VERSIONEN=(3.1.1 3.0 2.1 2.0 1.0)
    [[ $NEU_FRAGEN -eq 0 && -n $SMB_VERSION ]] && VERSIONEN=("$SMB_VERSION" "${VERSIONEN[@]}")
    LETZTER_FEHLER=""
    GEFUNDEN=""
    echo "    Verbinde mit $GERAET …"
    for v in "${VERSIONEN[@]}"; do
        if MELDUNG=$(mount -t cifs "$GERAET" "$MOUNTPUNKT" -o "$OPTIONEN,vers=$v" 2>&1); then
            GEFUNDEN=$v
            break
        fi
        # "Version nicht unterstützt" (95/22) sagt nichts über die eigentliche Ursache.
        if [[ -z $LETZTER_FEHLER || ! $MELDUNG =~ error\((95|22)\) ]]; then
            LETZTER_FEHLER=$MELDUNG
        fi
    done
    if [[ -z $GEFUNDEN ]]; then
        echo "    Meldung: $LETZTER_FEHLER"
        case $LETZTER_FEHLER in
            *"error(13)"*) fehler "Benutzer oder Passwort falsch, oder der Benutzer hat keinen Zugriff auf „$NAS_FREIGABE“." ;;
            *"error(2)"*|*"error(6)"*) fehler "Die Freigabe „$NAS_FREIGABE“ gibt es auf dem NAS nicht (Groß-/Kleinschreibung beachten)." ;;
            *"error(112)"*|*"error(113)"*|*"error(115)"*|*"error(110)"*)
                fehler "Das NAS $NAS_ADRESSE ist nicht erreichbar. Adresse richtig? Ist der SMB-Dienst auf der Synology aktiviert?" ;;
            *"error(19)"*) fehler "Diesem Server fehlt die SMB-Unterstützung im Kernel (Paket linux-modules-extra-$(uname -r) installieren)." ;;
            *) fehler "Die NAS-Freigabe konnte nicht eingebunden werden. Bitte die Angaben und die SMB-Einstellungen der Synology prüfen (docs/SERVER.md)." ;;
        esac
    fi
    SMB_VERSION=$GEFUNDEN
    ok "$GERAET eingebunden unter $MOUNTPUNKT (SMB $SMB_VERSION)"
    [[ $SMB_VERSION == 1.0 ]] && hinweis "Das NAS spricht nur das alte SMB 1. Das funktioniert, ist aber unsicher – wenn möglich in der Synology SMB 2/3 aktivieren."

    ANZAHL=$(find "$MOUNTPUNKT" -maxdepth 2 -iname '*.pdf' 2>/dev/null | wc -l)
    ok "Lesen klappt ($ANZAHL PDF-Dateien in der Freigabe und ihren Unterordnern gefunden)"
    schreibtest "$MOUNTPUNKT" || fehler "Lesen klappt, aber Schreiben nicht. Bitte dem NAS-Benutzer „$NAS_BENUTZER“ Lese-/Schreibrechte auf „$NAS_FREIGABE“ geben."
    ok "Schreiben klappt"

    # Dauerhaft einbinden (auch nach Neustarts)
    GERAET_FSTAB=${GERAET// /\\040}
    sed -i "\|$FSTAB_MARKE|d" /etc/fstab
    printf '%s  %s  cifs  %s,vers=%s,_netdev,nofail  0  0  %s\n' \
        "$GERAET_FSTAB" "$MOUNTPUNKT" "$OPTIONEN" "$SMB_VERSION" "$FSTAB_MARKE" >> /etc/fstab
    ok "Einbindung in /etc/fstab eingetragen"

    # Docker erst starten, wenn das NAS eingebunden ist
    if systemd_aktiv; then
        MOUNT_UNIT=$(systemd-escape -p --suffix=mount "$MOUNTPUNKT")
        mkdir -p "$(dirname "$DOCKER_DROPIN")"
        printf '[Unit]\nWants=network-online.target %s\nAfter=network-online.target %s\n' \
            "$MOUNT_UNIT" "$MOUNT_UNIT" > "$DOCKER_DROPIN"
        systemctl daemon-reload
        ok "Autostart: Docker wartet beim Hochfahren auf das NAS"
    fi
    RECHNUNGEN_ORDNER=$MOUNTPUNKT
fi

# Antworten merken (ohne Passwort – das steht nur in $ZUGANG)
umask 077
cat > "$ANTWORTEN" <<EOF
NAS_ADRESSE=$(printf %q "$NAS_ADRESSE")
NAS_FREIGABE=$(printf %q "$NAS_FREIGABE")
NAS_BENUTZER=$(printf %q "$NAS_BENUTZER")
SMB_VERSION=$(printf %q "$SMB_VERSION")
LOKAL=$(printf %q "${LOKAL:-}")
PORT=$PORT
PIN=$PIN
EOF
umask 022

# ================================================================= Programm
info "Programm wird installiert"
if [[ $QUELLE != "$ZIEL" ]]; then
    [[ -f $QUELLE/Dockerfile && -d $QUELLE/rechnungs_tinder ]] \
        || fehler "Programmdateien nicht gefunden. Bitte das Skript aus dem entpackten Programmordner starten."
    mkdir -p "$ZIEL"
    rm -rf "$ZIEL/rechnungs_tinder"
    cp -r "$QUELLE/rechnungs_tinder" "$ZIEL/"
    cp "$QUELLE"/{Dockerfile,.dockerignore,docker-compose.yml,requirements.txt,installieren-ubuntu.sh} "$ZIEL/"
    find "$ZIEL/rechnungs_tinder" -name '__pycache__' -prune -exec rm -rf {} +
fi
umask 077
cat > "$ZIEL/.env" <<EOF
# Von installieren-ubuntu.sh erzeugt. Änderungen: Skript erneut ausführen.
PIN=$PIN
PORT=$PORT
RECHNUNGEN_ORDNER=$RECHNUNGEN_ORDNER
PUID=$PUID
PGID=$PGID
ORDNER_BEWILLIGT=Bewilligt
ORDNER_ABGELEHNT=Abgelehnt
HINTER_PROXY=0
EOF
umask 022
ok "Dateien in $ZIEL"

if command -v ufw >/dev/null && ufw status 2>/dev/null | grep -q "Status: active"; then
    ufw allow "$PORT/tcp" comment "Rechnungs-Tinder" >/dev/null
    ok "Firewall: Port $PORT geöffnet"
fi

info "Programm wird gebaut und gestartet (beim ersten Mal einige Minuten)"
# Immer neu erstellen, damit der Container die frisch eingebundene NAS-Freigabe sieht.
compose up -d --build --force-recreate --remove-orphans
STATUS=""
for _ in $(seq 1 45); do
    STATUS=$(docker inspect -f '{{.State.Health.Status}}' rechnungs-tinder 2>/dev/null || true)
    [[ $STATUS == healthy ]] && break
    sleep 2
done
[[ $STATUS == healthy ]] || { compose logs --tail 30; fehler "Das Programm ist nicht richtig gestartet (Protokoll siehe oben)."; }
ok "Programm läuft"

IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo
echo "  ╔════════════════════════════════════════════════════════════╗"
echo "  ║  Fertig! Rechnungs-Tinder läuft.                           ║"
echo "  ╚════════════════════════════════════════════════════════════╝"
echo
echo "    Im Browser öffnen (PC, Tablet, Smartphone):"
echo "        http://${IP:-<server>}:$PORT"
echo "    PIN:  $PIN"
echo "    Rechnungen: ${GERAET:-$RECHNUNGEN_ORDNER}"
echo
echo "    Protokoll:     sudo docker compose --project-directory $ZIEL logs -f"
echo "    Neu starten:   sudo docker compose --project-directory $ZIEL restart"
echo "    Aktualisieren: neue Version herunterladen und  sudo ./installieren-ubuntu.sh  erneut ausführen"
echo
