#!/usr/bin/env bash
# Install LinuxWhispr for the current user without changing user data or system settings.
set -euo pipefail

APP_NAME="linux-whispr"

usage() {
    cat <<'EOF'
Usage: ./install.sh [--amd | --no-amd]

Install or update LinuxWhispr for the current user.

Options:
  --amd     Install the Vulkan-capable whisper.cpp dependency.
  --no-amd  Do not install the optional whisper.cpp dependency.
  -h, --help  Show this help.

Without an option, the installer keeps AMD support when the existing LinuxWhispr
configuration uses the whisper-cpp backend or this repository's virtual
environment already contains pywhispercpp.
EOF
}

fail() {
    printf 'error: %s\n' "$*" >&2
    exit 1
}

warn() {
    printf 'warning: %s\n' "$*" >&2
}

# Resolve this script, rather than the caller's working directory. This also
# supports a repository path containing spaces and a symlinked installer.
source_path=${BASH_SOURCE[0]}
while [[ -L "$source_path" ]]; do
    source_dir=$(cd -P "$(dirname "$source_path")" && pwd)
    source_path=$(readlink "$source_path")
    [[ "$source_path" != /* ]] && source_path="$source_dir/$source_path"
done
REPO_DIR=$(cd -P "$(dirname "$source_path")" && pwd)
[[ -f "$REPO_DIR/pyproject.toml" ]] || fail "could not find pyproject.toml beside $source_path"
[[ -f "$REPO_DIR/data/icons/linux-whispr.svg" ]] || fail "missing application icon in $REPO_DIR/data/icons"

amd_mode="auto"
while (($#)); do
    case "$1" in
        --amd)
            [[ "$amd_mode" != "no" ]] || fail "--amd and --no-amd cannot be used together"
            amd_mode="yes"
            ;;
        --no-amd)
            [[ "$amd_mode" != "yes" ]] || fail "--amd and --no-amd cannot be used together"
            amd_mode="no"
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            usage >&2
            fail "unknown option: $1"
            ;;
    esac
    shift
done

if ! command -v uv >/dev/null 2>&1; then
    fail "uv is required. Install it with your distribution package manager or follow https://docs.astral.sh/uv/getting-started/installation/, then rerun this installer. It will not download or install uv for you."
fi

BIN_DIR=${XDG_BIN_HOME:-"$HOME/.local/bin"}
DATA_HOME=${XDG_DATA_HOME:-"$HOME/.local/share"}
CONFIG_HOME=${XDG_CONFIG_HOME:-"$HOME/.config"}
for xdg_path in "$BIN_DIR" "$DATA_HOME" "$CONFIG_HOME"; do
    [[ "$xdg_path" = /* ]] || fail "XDG paths must be absolute; received: $xdg_path"
done

LAUNCHER="$BIN_DIR/$APP_NAME"
APPLICATIONS_DIR="$DATA_HOME/applications"
ICON_DIR="$DATA_HOME/icons/hicolor/scalable/apps"
MENU_ENTRY="$APPLICATIONS_DIR/$APP_NAME.desktop"
ICON_DESTINATION="$ICON_DIR/$APP_NAME.svg"
CONFIG_FILE="$CONFIG_HOME/$APP_NAME/config.toml"

has_existing_amd() {
    if [[ -f "$CONFIG_FILE" ]]; then
        config_contents=$(<"$CONFIG_FILE")
        if [[ "$config_contents" =~ (^|$'\n')[[:space:]]*backend[[:space:]]*=[[:space:]]*[\"\']whisper-cpp[\"\'] ]]; then
            return 0
        fi
    fi

    if [[ -x "$REPO_DIR/.venv/bin/python" ]]; then
        "$REPO_DIR/.venv/bin/python" -c 'import importlib.util; raise SystemExit(importlib.util.find_spec("pywhispercpp") is None)' >/dev/null 2>&1 && return 0
    fi

    return 1
}

shell_quote() {
    local value=$1
    value=${value//\'/\'\\\'\'}
    printf "'%s'" "$value"
}

if [[ "$amd_mode" == "auto" ]]; then
    if has_existing_amd; then
        amd_mode="yes"
        printf 'Keeping existing AMD/whisper.cpp support. Use --no-amd to remove it.\n'
    else
        amd_mode="no"
    fi
fi

package_hint() {
    local kind=$1
    local id=""
    if [[ -r /etc/os-release ]]; then
        # shellcheck disable=SC1091
        . /etc/os-release
        id=${ID:-}
    fi

    case "$id" in
        debian|ubuntu|linuxmint|pop)
            case "$kind" in
                qt-x11) printf 'sudo apt install libxcb-cursor0 libxkbcommon-x11-0\n' ;;
                qt-wayland) printf 'sudo apt install libegl1 libxkbcommon0\n' ;;
                audio) printf 'sudo apt install libportaudio2 pipewire-audio\n' ;;
                x11-injection) printf 'sudo apt install xdotool xclip\n' ;;
                wayland-injection) printf 'sudo apt install wtype wl-clipboard\n' ;;
            esac
            ;;
        fedora)
            case "$kind" in
                qt-x11) printf 'sudo dnf install libxcb xcb-util-cursor libxkbcommon-x11\n' ;;
                qt-wayland) printf 'sudo dnf install mesa-libEGL libxkbcommon\n' ;;
                audio) printf 'sudo dnf install portaudio pipewire\n' ;;
                x11-injection) printf 'sudo dnf install xdotool xclip\n' ;;
                wayland-injection) printf 'sudo dnf install wtype wl-clipboard\n' ;;
            esac
            ;;
        arch|manjaro|endeavouros)
            case "$kind" in
                qt-x11) printf 'sudo pacman -S xcb-util-cursor libxkbcommon\n' ;;
                qt-wayland) printf 'sudo pacman -S mesa libxkbcommon\n' ;;
                audio) printf 'sudo pacman -S portaudio pipewire\n' ;;
                x11-injection) printf 'sudo pacman -S xdotool xclip\n' ;;
                wayland-injection) printf 'sudo pacman -S wtype wl-clipboard\n' ;;
            esac
            ;;
        *)
            printf 'install your distribution packages for %s\n' "$kind"
            ;;
    esac
}

check_native_prerequisites() {
    local shared_libraries=""
    if command -v ldconfig >/dev/null 2>&1; then
        shared_libraries=$(ldconfig -p 2>/dev/null || true)
    else
        warn "cannot inspect native shared libraries because ldconfig is unavailable."
    fi

    # PySide6 ships Qt itself, but its X11/Wayland platform plugins still use
    # these distribution libraries. PyGObject is not required by the core UI.
    printf 'The core tray and activity popup use Qt from PySide6; PyGObject is not required.\n'
    local session=${XDG_SESSION_TYPE:-}
    if [[ "$session" == "wayland" || ( "$session" != "x11" && -n ${WAYLAND_DISPLAY:-} ) ]]; then
        printf 'Qt Wayland runtime prerequisite (if missing): %s\n' "$(package_hint qt-wayland)"
        if [[ -n "$shared_libraries" && ( "$shared_libraries" != *"libwayland-client.so"* || "$shared_libraries" != *"libEGL.so"* ) ]]; then
            warn "required Qt Wayland runtime libraries appear to be missing: $(package_hint qt-wayland)"
        fi
        if ! command -v wtype >/dev/null 2>&1 && ! command -v ydotool >/dev/null 2>&1; then
            warn "no Wayland injection helper found; install wtype or configure ydotool: $(package_hint wayland-injection)"
        fi
        if ! command -v wl-copy >/dev/null 2>&1; then
            warn "wl-clipboard is not installed; clipboard injection needs it: $(package_hint wayland-injection)"
        fi
    elif [[ "$session" == "x11" || -n ${DISPLAY:-} ]]; then
        if [[ -z ${DISPLAY:-} ]]; then
            warn "an X11 session was detected but DISPLAY is unset; Qt will need DISPLAY when launched."
        fi
        printf 'Qt X11 runtime prerequisite (if missing): %s\n' "$(package_hint qt-x11)"
        if [[ -n "$shared_libraries" && ( "$shared_libraries" != *"libxcb.so"* || "$shared_libraries" != *"libxcb-cursor.so"* || "$shared_libraries" != *"libxkbcommon-x11.so"* ) ]]; then
            warn "required Qt X11 runtime libraries appear to be missing: $(package_hint qt-x11)"
        fi
        if ! command -v xdotool >/dev/null 2>&1; then
            warn "xdotool is not installed; text injection on X11 needs it (or configure another injection method): $(package_hint x11-injection)"
        fi
        if ! command -v xclip >/dev/null 2>&1 && ! command -v xsel >/dev/null 2>&1; then
            warn "no X11 clipboard helper found; install xclip or xsel: $(package_hint x11-injection)"
        fi
    else
        warn "no X11 or Wayland session was detected. Install Qt's platform dependencies before launching: $(package_hint qt-x11)"
    fi

    if [[ -n "$shared_libraries" && "$shared_libraries" != *"libportaudio.so"* ]]; then
        warn "the PortAudio shared library appears to be missing: $(package_hint audio)"
    fi
    if ! command -v pactl >/dev/null 2>&1 && ! command -v wpctl >/dev/null 2>&1; then
        warn "no PipeWire/PulseAudio control tool found. Ensure PortAudio and your audio server are installed: $(package_hint audio)"
    fi
}

check_native_prerequisites

sync_args=(sync --project "$REPO_DIR" --locked)
if [[ "$amd_mode" == "yes" ]]; then
    sync_args+=(--extra amd)
fi
printf 'Synchronizing project virtual environment with uv%s...\n' "$([[ "$amd_mode" == "yes" ]] && printf ' (including AMD/whisper.cpp)')"
uv "${sync_args[@]}"

[[ -x "$REPO_DIR/.venv/bin/$APP_NAME" ]] || fail "uv did not create $REPO_DIR/.venv/bin/$APP_NAME"

mkdir -p "$BIN_DIR" "$APPLICATIONS_DIR" "$ICON_DIR"

# The wrapper makes desktop and autostart invocation independent of PATH or
# current directory, while forwarding every CLI argument unchanged.
quoted_launcher_path=$(shell_quote "$LAUNCHER")
quoted_entrypoint=$(shell_quote "$REPO_DIR/.venv/bin/$APP_NAME")
temp_launcher=$(mktemp "$BIN_DIR/.${APP_NAME}.XXXXXX")
cat >"$temp_launcher" <<EOF
#!/usr/bin/env sh
export LINUX_WHISPR_LAUNCHER=$quoted_launcher_path
exec $quoted_entrypoint "\$@"
EOF
chmod 755 "$temp_launcher"
mv -f "$temp_launcher" "$LAUNCHER"

# Desktop Entry values require general string escaping after Exec's argument
# quoting. This preserves literal backslashes, spaces, percent signs, and
# shell-special characters in an absolute launcher path.
desktop_string() {
    local value=$1
    printf '%s' "${value//\\/\\\\}"
}

desktop_quote() {
    local value=$1
    value=${value//\\/\\\\}
    value=${value//\"/\\\"}
    value=${value//\`/\\\`}
    value=${value//\$/\\\$}
    value=${value//%/%%}
    desktop_string "\"$value\""
}

quoted_launcher=$(desktop_quote "$LAUNCHER")
try_launcher=$(desktop_string "$LAUNCHER")
icon_value=$(desktop_string "$ICON_DESTINATION")
temp_entry=$(mktemp "$APPLICATIONS_DIR/.${APP_NAME}.XXXXXX")
cat >"$temp_entry" <<EOF
[Desktop Entry]
Type=Application
Name=LinuxWhispr
GenericName=Voice Dictation
Comment=Privacy-first voice dictation for Linux
Exec=$quoted_launcher
TryExec=$try_launcher
Icon=$icon_value
Terminal=false
Categories=Utility;Accessibility;
Keywords=voice;dictation;speech;whisper;transcription;
StartupNotify=false
StartupWMClass=linux-whispr
X-GNOME-Autostart-enabled=false
EOF
chmod 644 "$temp_entry"
mv -f "$temp_entry" "$MENU_ENTRY"
install -m 644 "$REPO_DIR/data/icons/linux-whispr.svg" "$ICON_DESTINATION"

DESKTOP_COPY=""
if command -v xdg-user-dir >/dev/null 2>&1; then
    desktop_dir=$(xdg-user-dir DESKTOP 2>/dev/null || true)
    if [[ -n "$desktop_dir" && "$desktop_dir" != "$HOME" ]]; then
        mkdir -p "$desktop_dir"
        DESKTOP_COPY="$desktop_dir/$APP_NAME.desktop"
        install -m 755 "$MENU_ENTRY" "$DESKTOP_COPY"
        if command -v gio >/dev/null 2>&1; then
            if ! gio set -t string "$DESKTOP_COPY" metadata::trusted true; then
                warn "could not mark $DESKTOP_COPY as trusted; mark it trusted from your file manager if it will not launch."
            fi
        else
            warn "gio is unavailable; $DESKTOP_COPY is executable but may need to be marked trusted in your file manager."
        fi
    else
        warn "the XDG Desktop directory is disabled; installed the menu launcher only."
    fi
else
    warn "xdg-user-dir is unavailable; installed the menu launcher only."
fi

printf '\nLinuxWhispr installed without changing your configuration, history, dictionary, or models.\n'
printf 'Launcher: %s\n' "$LAUNCHER"
printf 'Menu entry: %s\n' "$MENU_ENTRY"
printf 'Icon: %s\n' "$ICON_DESTINATION"
if [[ -n "$DESKTOP_COPY" ]]; then
    printf 'Desktop launcher: %s\n' "$DESKTOP_COPY"
fi
printf 'Launch command: %s\n' "$LAUNCHER"
printf 'Next steps: launch LinuxWhispr from your application menu or run the command above. Configure autostart separately in Settings if you want it.\n'
