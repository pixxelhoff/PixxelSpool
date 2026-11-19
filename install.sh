#!/usr/bin/env bash
# PixxelSpool – installation on a Raspberry Pi (Raspberry Pi OS / Debian, Bookworm or newer).
#
#   git clone <repo> ~/pixxelspool && cd ~/pixxelspool && ./install.sh
#
# Run as a normal user (not with sudo); the script asks for sudo itself for system steps.
# In a terminal a wizard guides through the setup. Running it again is safe (e.g. after an update);
# an existing installation in this folder is detected. Data in data/ is never touched.
#
# Options:
#   --port N        port of the web UI (default 80, or 8000 when 80 is taken)
#   --service NAME  name of the systemd service (default pixxelspool)
#   --no-i2c        do not enable I2C (USB reader only)
#   --no-wifi-fix   do not disable Wi-Fi power saving
#   --lang de|en|es UI language (asked on the first run if not given)
#   --remote        also set up remote access via Tailscale (asked if not given)
#   --no-remote     do not set up remote access
#   --no-os-updates do not turn on automatic security updates of the system
#   --os-updates    only turn on automatic security updates of the system (security fixes only, no restart), then stop
#   --plain         no wizard, plain text output
#   --yes           ask nothing, use defaults (implies --plain)
set -euo pipefail

PORT=""
SERVICE=""
I2C=1
WIFI_FIX=1
UI_LANG=""
REMOTE=""
OSUPD=1
ONLY_OSUPD=0
PLAIN=0
YES=0
while [ $# -gt 0 ]; do
  case "$1" in
    --port) PORT="$2"; shift 2 ;;
    --service) SERVICE="$2"; shift 2 ;;
    --no-i2c) I2C=0; shift ;;
    --no-wifi-fix) WIFI_FIX=0; shift ;;
    --lang) UI_LANG="$2"; shift 2 ;;
    --remote) REMOTE=1; shift ;;
    --no-remote) REMOTE=0; shift ;;
    --os-updates) ONLY_OSUPD=1; shift ;;
    --no-os-updates) OSUPD=0; shift ;;
    --plain) PLAIN=1; shift ;;
    --yes|-y) YES=1; PLAIN=1; shift ;;
    -h|--help) sed -n '2,22p' "$0"; exit 0 ;;
    *) echo "Unknown option / Unbekannte Option: $1" >&2; exit 1 ;;
  esac
done

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
USER_NAME="$(id -un)"
SETTINGS="$DIR/data/settings.json"
LOG="$DIR/install.log"
UNIT_DIR="$HOME/.config/systemd/user"
# t "Deutsch" "English" "Español": text in the chosen language (English when nothing was chosen)
t() { case "$UI_LANG" in de) printf '%s' "$1" ;; es) printf '%s' "$3" ;; *) printf '%s' "$2" ;; esac; }   # English is the fallback

# the name this Pi really answers to in the home network (avahi may have picked "name-2.local")
local_name() {
  local n
  n="$(busctl call org.freedesktop.Avahi / org.freedesktop.Avahi.Server GetHostNameFqdn 2>/dev/null | sed -n 's/^s "\(.*\)"$/\1/p')"
  echo "${n:-$(hostname).local}"
}

# wizard only in a real terminal and when whiptail exists (always on Raspberry Pi OS)
WIZ=0
if [ "$PLAIN" = 0 ] && [ -t 0 ] && [ -t 1 ] && command -v whiptail >/dev/null 2>&1; then WIZ=1; fi
TITLE="PixxelSpool"
# colors in PixxelSpool pink
export NEWT_COLORS='
root=white,black
window=white,black
shadow=black,black
border=magenta,black
title=brightmagenta,black
textbox=white,black
button=black,magenta
actbutton=white,magenta
compactbutton=white,black
checkbox=white,black
actcheckbox=black,magenta
entry=white,black
label=white,black
listbox=white,black
actlistbox=black,magenta
sellistbox=white,black
actsellistbox=black,magenta
emptyscale=,black
fullscale=,magenta
helpline=white,black
roottext=brightmagenta,black
'
wt() { whiptail --backtitle "PixxelSpool by pixxelhoff" --title "$TITLE" "$@" 3>&1 1>&2 2>&3; }
# window title with the step, e.g. " PixxelSpool · Schritt 2 von 4 "
step() { TITLE=" PixxelSpool · $(t "Schritt $1 von 4" "Step $1 of 4" "Paso $1 de 4") "; }
RULE="────────────────────────────────────────────────────────────"
OK_BTN() { t "Weiter" "Next" "Siguiente"; }
BACK_BTN() { t "Abbrechen" "Cancel" "Cancelar"; }
abort() {
  [ "$WIZ" = 1 ] && clear
  echo "$(t "Installation abgebrochen. Es wurde nichts verändert." "Installation cancelled. Nothing was changed." "Instalación cancelada. No se ha cambiado nada.")"
  exit 1
}

# ------------------------------------------------------------------ language
case "$UI_LANG" in de|en|es|"") ;; *) echo "--lang: de, en, es" >&2; exit 1 ;; esac
if [ -z "$UI_LANG" ] && [ -f "$SETTINGS" ]; then
  UI_LANG="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("lang", ""))' "$SETTINGS" 2>/dev/null || true)"
fi
if [ -z "$UI_LANG" ]; then
  if [ "$WIZ" = 1 ]; then
    UI_LANG="$(wt --nocancel --menu "\nSprache / Language / Idioma" 14 50 3 de "Deutsch" en "English" es "Español")" || UI_LANG=en
  elif [ -t 0 ] && [ "$YES" = 0 ]; then
    echo "Sprache / Language / Idioma:   1) Deutsch   2) English   3) Español"
    read -r -p "[1-3]: " a
    case "$a" in 1) UI_LANG=de ;; 3) UI_LANG=es ;; *) UI_LANG=en ;; esac
  else
    UI_LANG=en
  fi
fi

if [ "$(id -u)" -eq 0 ]; then
  echo "$(t "Bitte als normaler Benutzer starten (ohne sudo): ./install.sh" "Please run as a normal user (without sudo): ./install.sh" "Ejecútalo como usuario normal (sin sudo): ./install.sh")" >&2
  exit 1
fi
if [ ! -f "$DIR/filament_tool/main.py" ]; then
  echo "$(t "install.sh muss im PixxelSpool-Ordner liegen." "install.sh must be inside the PixxelSpool folder." "install.sh debe estar en la carpeta de PixxelSpool.")" >&2
  exit 1
fi

s_osupdates() {
  # automatic security updates of the system: Debian security archive only (on 32-bit Raspbian its stable updates),
  # the Pi never restarts by itself
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -o Dpkg::Progress-Fancy=0 unattended-upgrades
  sudo tee /etc/apt/apt.conf.d/52pixxelspool-security >/dev/null <<'A'
// PixxelSpool (install.sh): automatic security updates only, never a restart by itself
#clear Unattended-Upgrade::Origins-Pattern;
Unattended-Upgrade::Origins-Pattern {
  "origin=Debian,codename=${distro_codename}-security,label=Debian-Security";
  "origin=Debian,codename=${distro_codename},label=Debian-Security";
  // 32-bit Raspberry Pi OS (Raspbian) has no separate security archive: its stable updates carry the fixes
  "origin=Raspbian,codename=${distro_codename},label=Raspbian";
};
Unattended-Upgrade::Automatic-Reboot "false";
APT::Periodic::Enable "1";
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
A
  sudo systemctl enable --now apt-daily.timer apt-daily-upgrade.timer 2>/dev/null || true
}
# ------------------------------------------------------------------ only the system security updates (./install.sh --os-updates)
if [ "$ONLY_OSUPD" = 1 ]; then
  echo "$(t "Automatische Sicherheitsupdates des Systems werden eingeschaltet (nur Sicherheitskorrekturen, kein automatischer Neustart)." "Turning on automatic security updates of the system (security fixes only, no automatic restart)." "Activando las actualizaciones de seguridad automáticas del sistema (solo correcciones de seguridad, sin reinicio automático).")"
  sudo -v -p "$(t "Passwort für %u: " "Password for %u: " "Contraseña de %u: ")"
  s_osupdates
  echo "$(t "Fertig. Ab jetzt installiert der Pi Sicherheitsupdates des Systems täglich selbst. Ein gelegentlicher Neustart (sudo reboot) aktiviert Kernel-Korrekturen." "Done. From now on the Pi installs security updates of the system daily by itself. A restart now and then (sudo reboot) activates kernel fixes." "Listo. A partir de ahora la Pi instala cada día las actualizaciones de seguridad del sistema. Un reinicio de vez en cuando (sudo reboot) activa las correcciones del kernel.")"
  exit 0
fi

# ------------------------------------------------------------------ detect an existing installation
# If a service already runs from this folder, keep its name and port (update instead of a new install).
EXISTING=""
if [ -d "$UNIT_DIR" ]; then
  for f in "$UNIT_DIR"/*.service; do
    [ -f "$f" ] || continue
    case "$f" in *-backup.service) continue ;; esac
    if grep -qx "WorkingDirectory=$DIR" "$f" && grep -q "run.py" "$f"; then
      EXISTING="$(basename "$f" .service)"
      [ -z "$SERVICE" ] && SERVICE="$EXISTING"
      if [ -z "$PORT" ]; then
        PORT="$(sed -n 's/.*--port \([0-9][0-9]*\).*/\1/p' "$f" | head -1)"
      fi
      break
    fi
  done
fi
SERVICE="${SERVICE:-pixxelspool}"
# port in use by something other than PixxelSpool?
port_busy() { command -v ss >/dev/null 2>&1 && [ -n "$(ss -ltnH "sport = :$1" 2>/dev/null)" ]; }
if [ -z "$PORT" ]; then
  # new install: port 80, so the address needs no port number; fall back to 8000 if 80 is taken
  if port_busy 80; then PORT=8000; else PORT=80; fi
fi
VERSION="$(cat "$DIR/VERSION" 2>/dev/null || echo "?")"
[ -z "$REMOTE" ] && command -v tailscale >/dev/null 2>&1 && REMOTE=1

# ------------------------------------------------------------------ wizard
if [ "$WIZ" = 1 ]; then
  if [ -n "$EXISTING" ]; then
    INTRO="$(t "PixxelSpool ist hier schon installiert (Dienst „$EXISTING“, Port $PORT).

Der Assistent bringt die Einrichtung auf den Stand von Version $VERSION. Dein Lager, deine Einstellungen und Sicherungen bleiben unverändert." \
"PixxelSpool is already installed here (service \"$EXISTING\", port $PORT).

The assistant brings the setup up to version $VERSION. Your storage, settings and backups stay untouched." \
"PixxelSpool ya está instalado aquí (servicio «$EXISTING», puerto $PORT).

El asistente actualiza la configuración a la versión $VERSION. Tu almacén, tus ajustes y las copias de seguridad no se tocan.")"
  else
    INTRO="$(t "  PixxelSpool $VERSION
  Lagerverwaltung für deine Filamentrollen
  $RULE

  Das richtet der Assistent ein:

     ✓  Pakete und NFC-Leser (USB-Leser oder PN532-Platine)
     ✓  PixxelSpool als Dienst, startet mit dem Pi
     ✓  tägliche Sicherung um 3:30 Uhr
     ○  Fernzugriff von unterwegs, wenn du willst

  Beim ersten Mal dauert das ein paar Minuten." \
"  PixxelSpool $VERSION
  Storage manager for your filament spools
  $RULE

  The assistant sets up:

     ✓  packages and NFC reader (USB reader or PN532 board)
     ✓  PixxelSpool as a service that starts with the Pi
     ✓  a daily backup at 3:30 am
     ○  remote access when you are away, if you want

  The first run takes a few minutes." \
"  PixxelSpool $VERSION
  Gestión de almacén para tus bobinas de filamento
  $RULE

  El asistente configura:

     ✓  paquetes y lector NFC (lector USB o placa PN532)
     ✓  PixxelSpool como servicio que arranca con la Pi
     ✓  una copia de seguridad diaria a las 3:30
     ○  acceso remoto desde fuera, si quieres

  La primera vez tarda unos minutos.")"
  fi
  step 1
  wt --yes-button "$(OK_BTN)" --no-button "$(BACK_BTN)" --yesno "\n$INTRO" 21 72 || abort

  onoff() { [ "$1" = 1 ] && echo ON || echo OFF; }
  step 2
  CH="$(wt --ok-button "$(OK_BTN)" --cancel-button "$(BACK_BTN)" --separate-output --checklist \
    "\n$(t "Was soll eingerichtet werden? (Leertaste: an/aus)" "What should be set up? (Space: on/off)" "¿Qué se debe configurar? (Espacio: sí/no)")" 17 74 4 \
    i2c "$(t "PN532-Platine am Pi (I2C einschalten)" "PN532 board on the Pi (enable I2C)" "Placa PN532 en la Pi (activar I2C)")" "$(onoff "$I2C")" \
    wifi "$(t "WLAN-Stromsparen aus (Pi reagiert flotter)" "Wi-Fi power saving off (Pi responds faster)" "Ahorro de Wi-Fi desactivado (Pi más ágil)")" "$(onoff "$WIFI_FIX")" \
    remote "$(t "Fernzugriff von unterwegs (Tailscale)" "Remote access when away (Tailscale)" "Acceso remoto desde fuera (Tailscale)")" "$(onoff "${REMOTE:-1}")" \
    osupd "$(t "Sicherheitsupdates des Systems automatisch" "Automatic system security updates" "Actualizaciones de seguridad automáticas")" "$(onoff "$OSUPD")")" || abort
  I2C=0; WIFI_FIX=0; REMOTE=0; OSUPD=0
  for c in $CH; do case "$c" in i2c) I2C=1 ;; wifi) WIFI_FIX=1 ;; remote) REMOTE=1 ;; osupd) OSUPD=1 ;; esac; done

  step 3
  while :; do
    P="$(wt --ok-button "$(OK_BTN)" --cancel-button "$(BACK_BTN)" --inputbox \
      "\n$(t "Auf welchem Port soll die Weboberfläche laufen?" "Which port should the web interface use?" "¿En qué puerto debe funcionar la interfaz web?")" 11 64 "$PORT")" || abort
    case "$P" in ''|*[!0-9]*) continue ;; esac
    { [ "$P" -lt 80 ] || [ "$P" -gt 65535 ]; } && continue
    if [ "$P" != "$PORT" ] || [ -z "$EXISTING" ]; then
      if [ -z "$EXISTING" ] && port_busy "$P"; then
        wt --msgbox "\n$(t "Port $P ist schon belegt. Bitte einen anderen wählen, z. B. 8000." "Port $P is already in use. Please choose another one, e.g. 8000." "El puerto $P ya está en uso. Elige otro, p. ej. 8000.")" 10 64 || true
        continue
      fi
    fi
    PORT="$P"; break
  done

  yn() { [ "$1" = 1 ] && echo "✓  $(t "ja" "yes" "sí")" || echo "–  $(t "nein" "no" "no")"; }
  step 4
  wt --yes-button "$(t "Installieren" "Install" "Instalar")" --no-button "$(BACK_BTN)" --yesno "\n  $(t "Alles bereit. Das wird eingerichtet:" "All set. This will be set up:" "Todo listo. Se configurará:")
  $RULE

  $(t "Ordner" "Folder" "Carpeta"):          $DIR
  $(t "Dienst" "Service" "Servicio"):          $SERVICE
  Port:            $PORT
  PN532 / I2C:     $(yn "$I2C")
  $(t "WLAN-Fix" "Wi-Fi fix" "Ajuste Wi-Fi"):        $(yn "$WIFI_FIX")
  $(t "Fernzugriff" "Remote access" "Acceso remoto"):     $(yn "$REMOTE")
  $(t "System-Updates" "System updates" "Actualizaciones"):  $(yn "$OSUPD")

  $RULE
  $(t "Gleich fragt der Pi einmal nach deinem Passwort (sudo)." "The Pi will ask for your password once (sudo)." "La Pi te pedirá la contraseña una vez (sudo).")" 22 74 || abort
  TITLE="PixxelSpool"
  clear
elif [ -z "$REMOTE" ]; then
  if [ -t 0 ] && [ "$YES" = 0 ]; then
    read -r -p "$(t "Fernzugriff von unterwegs einrichten (Tailscale)? [J/n]: " "Set up remote access (Tailscale)? [Y/n]: " "¿Configurar el acceso remoto (Tailscale)? [S/n]: ")" a
    case "$a" in n|N) REMOTE=0 ;; *) REMOTE=1 ;; esac
  else
    REMOTE=0
  fi
fi
REMOTE="${REMOTE:-0}"

# ask for sudo once up front and keep it alive in the background (the progress gauge cannot prompt for it)
echo "$(t "PixxelSpool braucht für die Systemschritte einmal dein Passwort." "PixxelSpool needs your password once for the system steps." "PixxelSpool necesita tu contraseña una vez para los pasos del sistema.")"
sudo -v -p "$(t "Passwort für %u: " "Password for %u: " "Contraseña de %u: ")"
( while kill -0 $$ 2>/dev/null; do sudo -n true 2>/dev/null; sleep 50; done ) &
KEEPALIVE=$!
trap 'kill $KEEPALIVE 2>/dev/null || true' EXIT

# ------------------------------------------------------------------ steps
s_packages() {
  sudo apt-get update
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -o Dpkg::Progress-Fancy=0 python3-venv python3-pip python3-pyscard pcscd pcsc-tools libccid sqlite3 i2c-tools
}
s_reader() {
  sudo tee /etc/modprobe.d/blacklist-pixxelspool-nfc.conf >/dev/null <<'B'
# PixxelSpool: USB NFC readers (ACR122U etc.) via pcscd instead of the kernel driver
blacklist pn533_usb
blacklist pn533
blacklist nfc
B
  sudo modprobe -r pn533_usb pn533 nfc 2>/dev/null || true
  sudo systemctl enable --now pcscd.socket
}
s_i2c() {
  if command -v raspi-config >/dev/null; then
    sudo raspi-config nonint do_i2c 0
  else
    echo "raspi-config fehlt – I2C bitte selbst einschalten (dtparam=i2c_arm=on)."
  fi
  if getent group i2c >/dev/null; then sudo usermod -aG i2c "$USER_NAME"; fi
}
s_rights() {
  sudo tee /etc/polkit-1/rules.d/50-pixxelspool.rules >/dev/null <<R
polkit.addRule(function(action, subject) {
  if (subject.user == "$USER_NAME" &&
      (action.id == "org.debian.pcsc-lite.access_pcsc" ||
       action.id == "org.debian.pcsc-lite.access_card" ||
       action.id == "org.freedesktop.login1.power-off" ||
       action.id == "org.freedesktop.login1.power-off-multiple-sessions" ||
       action.id == "org.freedesktop.login1.reboot" ||
       action.id == "org.freedesktop.login1.reboot-multiple-sessions")) {
    return polkit.Result.YES;
  }
});
R
  sudo systemctl restart polkit 2>/dev/null || true
  sudo systemctl restart pcscd 2>/dev/null || true
  sudo loginctl enable-linger "$USER_NAME"
}
s_wifi() {
  [ -d /etc/NetworkManager ] || return 0
  sudo mkdir -p /etc/NetworkManager/conf.d
  printf '[connection]\nwifi.powersave = 2\n' | sudo tee /etc/NetworkManager/conf.d/wifi-powersave-off.conf >/dev/null
  sudo iw dev wlan0 set power_save off 2>/dev/null || true
}
s_remote() {
  if ! command -v tailscale >/dev/null 2>&1; then
    curl -fsSL https://tailscale.com/install.sh | sh
  fi
  sudo systemctl enable --now tailscaled
  # let PixxelSpool control Tailscale without sudo (sign-in, HTTPS address, on/off)
  sudo tailscale set --operator="$USER_NAME"
}
s_python() {
  # after a system upgrade (e.g. Bookworm to Trixie: Python 3.11 to 3.13) the old environment no longer fits:
  # set it up again (the old one is kept as .venv.old until the next time)
  local want have
  want="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
  have="$("$DIR/.venv/bin/python" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || true)"
  if [ -d "$DIR/.venv" ] && [ "$have" != "$want" ]; then
    echo "$(t "Python hat sich geändert (${have:-?} → $want): Python-Umgebung wird neu angelegt." "Python changed (${have:-?} → $want): setting up the Python environment again." "Python ha cambiado (${have:-?} → $want): se crea de nuevo el entorno de Python.")"
    rm -rf "$DIR/.venv.old"
    mv "$DIR/.venv" "$DIR/.venv.old"
  fi
  if [ ! -x "$DIR/.venv/bin/python" ]; then
    python3 -m venv --system-site-packages "$DIR/.venv"
  fi
  "$DIR/.venv/bin/pip" install --disable-pip-version-check --progress-bar off -r "$DIR/requirements.txt"
  mkdir -p "$DIR/data"
  chmod 700 "$DIR/data"
  # level of the system setup done here (filament_tool/host.py SETUP_LEVEL; a newer version may ask to run this again)
  level="$(sed -n 's/^SETUP_LEVEL = \([0-9][0-9]*\).*/\1/p' "$DIR/filament_tool/host.py")"
  printf '{"level": %s, "version": "%s"}\n' "${level:-1}" "$VERSION" > "$DIR/data/setup.json"
  # write the language to data/settings.json (new install: the setup wizard starts)
  python3 - "$SETTINGS" "$UI_LANG" <<'P'
import json, os, sys
path, lang = sys.argv[1], sys.argv[2]
try:
    data = json.load(open(path, encoding="utf-8"))
except (OSError, ValueError):
    # no database: new install, start the wizard; otherwise leave the existing stock alone
    data = {} if any(os.path.exists(os.path.join(os.path.dirname(path), n)) for n in ("inventory.db",)) else {"setup_done": False}
data["lang"] = lang
with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
P
}
s_service() {
  mkdir -p "$UNIT_DIR"
  cat > "$UNIT_DIR/$SERVICE.service" <<U
[Unit]
Description=PixxelSpool
After=network-online.target

[Service]
WorkingDirectory=$DIR
ExecStart=$DIR/.venv/bin/python run.py --lan --port $PORT --no-browser
Restart=always
RestartSec=5
TimeoutStopSec=8

[Install]
WantedBy=default.target
U
  cat > "$UNIT_DIR/$SERVICE-backup.service" <<U
[Unit]
Description=PixxelSpool Sicherung

[Service]
Type=oneshot
WorkingDirectory=$DIR
ExecStart=$DIR/.venv/bin/python -m filament_tool.daily_backup
U
  cat > "$UNIT_DIR/$SERVICE-backup.timer" <<U
[Unit]
Description=PixxelSpool daily backup

[Timer]
OnCalendar=*-*-* 03:30
Persistent=true

[Install]
WantedBy=timers.target
U
  export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
  systemctl --user daemon-reload
  systemctl --user enable --now "$SERVICE-backup.timer"
  systemctl --user enable "$SERVICE.service"
  systemctl --user restart "$SERVICE.service"
}
s_port() {
  # ports below 1024 need root; allow them for normal users (PixxelSpool runs as a user service)
  printf 'net.ipv4.ip_unprivileged_port_start=%s\n' "$PORT" | sudo tee /etc/sysctl.d/90-pixxelspool.conf >/dev/null
  sudo sysctl -q -p /etc/sysctl.d/90-pixxelspool.conf
}
s_wait() {
  # wait until the web UI answers (90 seconds at most)
  for n in $(seq 1 45); do
    if python3 -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:$PORT/api/update', timeout=2)" 2>/dev/null; then return 0; fi
    echo "$(t "Warte auf Antwort von PixxelSpool …" "Waiting for PixxelSpool to answer …" "Esperando respuesta de PixxelSpool …") ($(( n * 2 )) s)"
    sleep 2
  done
  # explain why: the last error from PixxelSpool's own log
  local err
  err="$(grep -h "ERROR" "$DIR/data/logs/pixxelspool.log" 2>/dev/null | tail -n 1 | cut -d' ' -f5- || true)"
  echo "REASON: $(t "PixxelSpool startet nicht." "PixxelSpool does not start." "PixxelSpool no arranca.") ${err}"
  case "$err" in
    *"ermission denied"*|*"Errno 13"*) echo "HINT: $(t "Port $PORT darf nicht benutzt werden. Installation mit --port 8000 wiederholen." "Port $PORT may not be used. Run the installation again with --port 8000." "No se puede usar el puerto $PORT. Repite la instalación con --port 8000.")" ;;
    *"ddress already in use"*|*"Errno 98"*) echo "HINT: $(t "Port $PORT ist schon belegt. Installation mit --port 8000 wiederholen." "Port $PORT is already in use. Run the installation again with --port 8000." "El puerto $PORT ya está en uso. Repite la instalación con --port 8000.")" ;;
    *) echo "HINT: $(t "Status ansehen: systemctl --user status $SERVICE" "Check the status: systemctl --user status $SERVICE" "Ver el estado: systemctl --user status $SERVICE")" ;;
  esac
  return 1
}
s_name() {
  # the .local name can end up as "name-2.local" when the Pi hears its own announcement twice (Wi-Fi with
  # mDNS reflection): restarting avahi usually gets the plain name back
  local n
  n="$(local_name)"
  case "$n" in *-[0-9].local|*-[0-9][0-9].local)
    sudo systemctl restart avahi-daemon 2>/dev/null || true
    sleep 4 ;;
  esac
  echo "$(local_name)"
}

STEPS=("s_packages|$(t "Pakete installieren (dauert beim ersten Mal ein paar Minuten)" "Installing packages (takes a few minutes the first time)" "Instalando paquetes (la primera vez tarda unos minutos)")"
       "s_reader|$(t "USB-Leser vorbereiten" "Preparing the USB reader" "Preparando el lector USB")")
[ "$I2C" = 1 ] && STEPS+=("s_i2c|$(t "PN532-Platine: I2C einschalten" "PN532 board: enabling I2C" "Placa PN532: activando I2C")")
[ "$PORT" -lt 1024 ] && STEPS+=("s_port|$(t "Port $PORT freigeben" "Allowing port $PORT" "Habilitando el puerto $PORT")")
STEPS+=("s_rights|$(t "Rechte für Leser, Neustart und Ausschalten" "Permissions for reader, restart and shutdown" "Permisos para lector, reinicio y apagado")")
[ "$WIFI_FIX" = 1 ] && STEPS+=("s_wifi|$(t "WLAN-Stromsparmodus ausschalten" "Turning off Wi-Fi power saving" "Desactivando el ahorro de energía del Wi-Fi")")
[ "$OSUPD" = 1 ] && STEPS+=("s_osupdates|$(t "Automatische Sicherheitsupdates des Systems" "Automatic security updates of the system" "Actualizaciones de seguridad automáticas del sistema")")
[ "$REMOTE" = 1 ] && STEPS+=("s_remote|$(t "Fernzugriff: Tailscale installieren" "Remote access: installing Tailscale" "Acceso remoto: instalando Tailscale")")
STEPS+=("s_python|$(t "Python-Umgebung einrichten" "Setting up the Python environment" "Configurando el entorno de Python")"
        "s_service|$(t "Dienst $SERVICE einrichten und starten" "Setting up and starting service $SERVICE" "Configurando e iniciando el servicio $SERVICE")"
        "s_wait|$(t "Auf PixxelSpool warten" "Waiting for PixxelSpool" "Esperando a PixxelSpool")"
        "s_name|$(t "Adresse im Heimnetz prüfen" "Checking the address in your network" "Comprobando la dirección en tu red")")

: > "$LOG"
FAILED=""
N=${#STEPS[@]}
if [ "$WIZ" = 1 ]; then
  FAILFILE="$(mktemp)"
  {
    set +e
    # rough share of the total time per step, so the bar moves evenly
    weight() { case "$1" in s_packages) echo 40 ;; s_python) echo 25 ;; s_remote) echo 15 ;; s_osupdates) echo 6 ;; s_wait) echo 6 ;; *) echo 2 ;; esac; }
    TOTAL=0; for s in "${STEPS[@]}"; do TOTAL=$(( TOTAL + $(weight "${s%%|*}") )); done
    i=0; done_w=0
    for s in "${STEPS[@]}"; do
      fn="${s%%|*}"; label="${s#*|}"; w=$(weight "$fn")
      echo "=== $fn" >>"$LOG"
      ( set -e; "$fn" ) >>"$LOG" 2>&1 &
      pid=$!; k=0
      while kill -0 "$pid" 2>/dev/null; do
        # the bar creeps towards the end of this step's share; below it the line the step is working on
        pct=$(( (done_w * 100 + w * 100 * k / (k + 20)) / TOTAL ))
        line="$(tail -n 1 "$LOG" 2>/dev/null | tr -d '\r' | sed -e 's/\x1b\[[0-9;]*[a-zA-Z]//g' -e 's/^=== .*//' | cut -c1-62)"
        printf 'XXX\n%d\n\n%s  (%d/%d)\n\n%s\nXXX\n' "$pct" "$label" $(( i + 1 )) "$N" "$line"
        sleep 1; k=$(( k + 1 ))
      done
      wait "$pid"
      if [ $? -ne 0 ]; then printf '%s' "$s" >"$FAILFILE"; break; fi
      i=$(( i + 1 )); done_w=$(( done_w + w ))
    done
    printf 'XXX\n100\n\n%s\nXXX\n' "$(t "Fertig" "Done" "Listo")"
    sleep 1
  } | whiptail --backtitle "PixxelSpool by pixxelhoff" --title "$TITLE $VERSION" --gauge "" 13 74 0
  FAILED="$(cat "$FAILFILE")"; rm -f "$FAILFILE"
else
  printf '\n\033[1;35m  PixxelSpool %s\033[0m  by pixxelhoff\n' "$VERSION"
  i=0
  for s in "${STEPS[@]}"; do
    fn="${s%%|*}"; label="${s#*|}"; i=$(( i + 1 ))
    printf '\n\033[1m[%d/%d] %s\033[0m\n' "$i" "$N" "$label"
    set +e
    ( set -e; "$fn" ) 2>&1 | tee -a "$LOG"
    rc=${PIPESTATUS[0]}
    set -e
    if [ "$rc" -ne 0 ]; then FAILED="$s"; break; fi
  done
fi

# ------------------------------------------------------------------ result
HOST="$(local_name)"
IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
SUFFIX=""; [ "$PORT" != 80 ] && SUFFIX=":$PORT"
URL="http://$HOST$SUFFIX"
if [ -n "$FAILED" ]; then
  # a short reason instead of the raw log: the step's own explanation, else its last error-looking lines
  STEPLOG="$(awk -v f="=== ${FAILED%%|*}" '$0==f{p=1;next} /^=== /{p=0} p' "$LOG" | grep -v '^+ ' | tr -d '\r' || true)"
  REASON="$(printf '%s\n' "$STEPLOG" | sed -n 's/^REASON: //p;s/^HINT: //p')"
  [ -z "$REASON" ] && REASON="$(printf '%s\n' "$STEPLOG" | grep -iE 'error|fehler|failed|E: |denied|not found|unable' | tail -n 4 || true)"
  [ -z "$REASON" ] && REASON="$(printf '%s\n' "$STEPLOG" | tail -n 4)"
  MSG="$(t "Dieser Schritt hat nicht geklappt:" "This step failed:" "Este paso ha fallado:") ${FAILED#*|}

$REASON

$(t "Das ganze Protokoll steht in" "The full log is in" "El registro completo está en") $LOG
$(t "Du kannst ./install.sh einfach noch einmal starten, deine Daten bleiben erhalten." "You can simply run ./install.sh again, your data is kept." "Puedes volver a ejecutar ./install.sh, tus datos se conservan.")"
  if [ "$WIZ" = 1 ]; then wt --msgbox "$MSG" 24 78 || true; clear; fi
  echo "$MSG" >&2
  exit 1
fi

DONE="$(t "PixxelSpool läuft unter" "PixxelSpool is running at" "PixxelSpool está disponible en"):

    $URL
    ($(t "oder" "or" "o") http://$IP$SUFFIX)
"
[ -z "$EXISTING" ] && DONE+="
$(t "Beim ersten Öffnen startet der Einrichtungsassistent." "The setup assistant starts the first time you open it." "La primera vez que lo abras se inicia el asistente de configuración.")"
[ "$REMOTE" = 1 ] && DONE+="
$(t "Fernzugriff: in PixxelSpool unter Optionen → Fernzugriff → Einrichten anmelden. Für HTTPS vorher unter login.tailscale.com/admin/dns MagicDNS und HTTPS Certificates einschalten." "Remote access: sign in under Options → Remote access → Set up in PixxelSpool. For HTTPS, first turn on MagicDNS and HTTPS Certificates at login.tailscale.com/admin/dns." "Acceso remoto: inicia sesión en PixxelSpool en Opciones → Acceso remoto → Configurar. Para HTTPS, activa antes MagicDNS y HTTPS Certificates en login.tailscale.com/admin/dns.")"
REBOOT=0
if [ "$I2C" = 1 ] && ! [ -e /dev/i2c-1 ]; then REBOOT=1; fi
if [ "$I2C" = 1 ] && getent group i2c >/dev/null && ! id -nG "$USER_NAME" | grep -qw i2c; then REBOOT=1; fi
[ "$REBOOT" = 1 ] && DONE+="

$(t "Für die PN532-Platine einmal neu starten: sudo reboot" "Restart once for the PN532 board: sudo reboot" "Reinicia una vez para la placa PN532: sudo reboot")"

if [ "$WIZ" = 1 ]; then
  wt --ok-button "Enter" --msgbox "\n$(t "PixxelSpool ist fertig installiert." "PixxelSpool is installed." "PixxelSpool está instalado.")\n\n$(t "Enter drücken: Danach stehen hier die Adresse und ein QR-Code fürs Handy." "Press Enter: the address and a QR code for your phone are shown next." "Pulsa Enter: a continuación verás la dirección y un código QR para el móvil.")" 11 74 || true
  clear
fi
printf '\n\033[1;35m  PixxelSpool %s\033[0m  ✓\n\n' "$VERSION"
echo "$DONE"
# QR code to open it on a phone
"$DIR/.venv/bin/python" -c "import segno,sys; segno.make(sys.argv[1]).terminal(compact=True)" "$URL" 2>/dev/null || true
echo
