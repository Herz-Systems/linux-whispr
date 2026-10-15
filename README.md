# LinuxWhispr

**Local-first voice dictation for Linux.** LinuxWhispr records from your
microphone, transcribes locally, and pastes the processed text into the focused
application. It combines a native Qt tray and recording overlay with a local web
dashboard.

## Contents

- [Install](#install)
- [Use LinuxWhispr](#use-linuxwhispr)
- [Dictionary packs and corrections](#dictionary-packs-and-corrections)
- [Configuration and local data](#configuration-and-local-data)
- [Local AI refinement with Ollama](#local-ai-refinement-with-ollama)
- [Troubleshooting](#troubleshooting)
- [Development](#development)

## What it includes

- Local transcription with [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
  by default; optional local `whisper.cpp` with AMD Vulkan acceleration.
- A configurable global dictation hotkey, voice-activity auto-stop, and
  clipboard-based text injection.
- A native Qt tray indicator and non-focus-stealing recording overlay.
- A dashboard bound to `127.0.0.1`, with settings, models, snippets, dictionary
  management, and transcription history. Its interface is available in English,
  Deutsch, Español, and Português.
- Optional local AI refinement through Ollama, and cloud STT or AI backends
  when their optional dependencies are installed and they are explicitly configured.
- Five opt-in bundled dictionary packs containing 151 terms and 113 explicit
  recognized variants, alongside personal entries and learned corrections.

The default configuration does not use a cloud service. The dashboard, models,
configuration, dictionary, and history are local. A configured cloud STT backend
sends audio to its provider; a configured cloud AI backend sends text to its
provider. Review that provider's terms and privacy policy before enabling either.

## Install

LinuxWhispr requires Python 3.10 or newer and [uv](https://docs.astral.sh/uv/getting-started/installation/).
The core desktop UI uses PySide6 and does not require PyGObject.

### System dependencies

Install PortAudio and the Qt runtime libraries for your session. The installer
checks for missing native prerequisites and prints distribution-specific hints.
For text injection, install the helper for the display server you use:

```bash
# Ubuntu / Debian
sudo apt install python3 libportaudio2 libxcb-cursor0 libxkbcommon-x11-0
# X11 text injection
sudo apt install xdotool xclip
# Wayland text injection
sudo apt install wtype wl-clipboard

# Fedora
sudo dnf install python3 portaudio xcb-util-cursor libxkbcommon-x11
sudo dnf install xdotool xclip          # X11
sudo dnf install wtype wl-clipboard     # Wayland

# Arch Linux
sudo pacman -S python portaudio xcb-util-cursor libxkbcommon
sudo pacman -S xdotool xclip             # X11
sudo pacman -S wtype wl-clipboard        # Wayland
```

### Standard install

```bash
git clone https://github.com/linx-systems/linux-whispr.git
cd linux-whispr
./install.sh
```

The default install uses the CPU-capable `faster-whisper` backend. The installer
creates a project-local `.venv`, a launcher at `~/.local/bin/linux-whispr` by
default, and an application-menu entry. When an XDG Desktop directory is
enabled, it also creates an executable desktop shortcut. It respects
`XDG_BIN_HOME`, `XDG_DATA_HOME`, and `XDG_CONFIG_HOME`, so those locations may
differ on your system.

Keep the checkout in place: the launcher points to its virtual environment.
Re-run the installer after moving or updating the checkout. Re-running updates
the launcher and desktop assets without replacing configuration, history,
dictionary data, or models. It does not start dictation, enable autostart, or
run `sudo`.

Use `./install.sh --amd` to install the optional AMD/Vulkan runtime. Use
`./install.sh --no-amd` to omit it. With no option, the installer preserves
existing `whisper.cpp` support when it is already configured or installed.

### Optional GTK setup wizard

Normal startup uses the web dashboard and needs no GTK dependencies. The
explicit `--setup` wizard and native settings require GTK4, libadwaita,
their introspection dependencies, and the `gtk` Python extra:

```bash
uv sync --extra gtk
uv run --extra gtk linux-whispr --setup
```

### AMD Vulkan acceleration

AMD Vulkan acceleration uses the optional local `whisper.cpp` backend; it is
separate from the default `faster-whisper` installation.

```bash
# Debian / Ubuntu / Mint build and Vulkan prerequisites
sudo apt install build-essential cmake libvulkan-dev glslc libshaderc1 \
    spirv-headers mesa-vulkan-drivers

# From this checkout
uv sync --extra amd
uv run --extra amd linux-whispr
```

The project builds `pywhispercpp==1.5.1` from source with Vulkan enabled because
its wheels are CPU-only. For a pip-based checkout install, request the local
extra rather than a package from PyPI:

```bash
GGML_VULKAN=1 CMAKE_INSTALL_RPATH='$ORIGIN' CMAKE_BUILD_WITH_INSTALL_RPATH=ON \
  python -m pip install --no-binary=pywhispercpp ".[amd]"
```

After installing, select **whisper.cpp (AMD / Vulkan)** and the **Vulkan**
device in settings, then download a GGML model. GGML models are separate from
`faster-whisper` models. When Vulkan cannot initialize, LinuxWhispr reports the
error rather than silently changing to CPU; choose the `cpu` device explicitly
if needed.

## Use LinuxWhispr

Start the installed launcher:

```bash
linux-whispr
```

`linux-whispr` and `linux-whispr-web` are aliases for the same combined
application: each starts the dictation engine and dashboard. On a normal first
launch, LinuxWhispr uses defaults; run `linux-whispr --setup` only to use the
optional setup wizard.

While the application runs, the dashboard is available at
`http://127.0.0.1:7865` by default. Opening it does not start recording.

The default transcription language is Portuguese (`pt`). Set `stt.language` to
the ISO 639-1 code you need, or to `auto` for `faster-whisper` language detection.

1. Press **F12** (the default dictation hotkey) to start recording.
2. Speak.
3. Press **F12** again, or wait for the default two seconds of silence.
4. LinuxWhispr transcribes, optionally refines and corrects, then pastes the
   result into the focused application.

The tray menu offers **Open Dashboard**, **Start/Stop Dictation**, and **Quit**.
Use `--no-tray` to disable only the indicator; the overlay, dashboard, and
dictation service remain available. The overlay reports readiness, recording,
processing, completion, and errors without taking keyboard focus. On X11 it is
placed using the monitor under the pointer; Wayland compositors control final
placement.

The dashboard stores its selected interface language in browser local storage,
independently of the transcription language. Settings generally take effect
after an application restart. Personal dictionary entries, recognized variants,
and pack selections update the active dictionary and apply to the next
dictation without a restart.

## Dictionary packs and corrections

Open **Dictionary → Bundled dictionaries** to enable the vocabulary you need.
All five packs are disabled by default.

| Pack | Terms | Example explicit variant |
| --- | ---: | --- |
| Coding | 42 | `type script` → `TypeScript` |
| DevOps | 31 | `cube control` → `kubectl` |
| AI | 28 | `open ai` → `OpenAI` |
| Email and office | 28 | `attachement` → `attachment` |
| German business | 22 | `e mail adresse` → `E-Mail-Adresse` |

The catalog has 151 terms and 113 explicit recognized variants. Terms without
variants, such as Go, Rust, and Claude, are recognition hints only; they do not
cause broad sound-alike replacement. Enabled vocabulary provides bounded,
personal-first hints to speech recognition and optional AI refinement (at most
1,000 characters per context).

For project names and recurring errors, add a personal word and its
**Recognized variants**, one per line. Adding an existing word with variants
updates those variants. Explicit personal variants take precedence over personal
canonical spellings, learned corrections, and bundled variants. A personal
canonical spelling also overrides a bundled spelling of the same term.

Corrections run once after snippets and optional AI refinement, before text
injection. They match whole tokens rather than identifier substrings and leave
URLs, email addresses, inline code, and fenced code unchanged. Disabling a pack
does not remove personal entries or learned corrections, and bundled terms are
never copied into the personal dictionary.

Adaptive learning is enabled by default, but it is deliberately limited: after
a successful paste, it watches clipboard changes for 15 seconds. If you copy a
sufficiently similar corrected version, it records word-level replacement pairs.
A learned pair becomes active after it has been seen twice. It does not observe
edits directly in other applications.

The independently curated catalog draws on the profile approach in
[Wisper](https://github.com/taraksh01/wisper/tree/main/src-tauri/resources/profiles).
It also references the separation of vocabulary and corrections in
[TypeWhisper term packs](https://github.com/typewhisper/typewhisper-termpacks)
and the recognition-context guidance in
[Voxtype](https://github.com/peteonrails/voxtype/blob/main/docs/USER_MANUAL.md).
No third-party dictionary downloads are required at runtime.

## Configuration and local data

By default, configuration and dictionary data are stored under
`~/.config/linux-whispr/`; models and history are under
`~/.local/share/linux-whispr/`. The application follows
`XDG_CONFIG_HOME` and `XDG_DATA_HOME`, so use the corresponding paths when
those variables are set:

- `config.toml`, `dictionary.json`, and `snippets.toml` are in
  `$XDG_CONFIG_HOME/linux-whispr/`.
- `history.db` and `models/` are in `$XDG_DATA_HOME/linux-whispr/`.

For example, edit the default configuration at
`~/.config/linux-whispr/config.toml`:

```toml
[hotkey]
dictation = "F12"

[stt]
backend = "faster-whisper"  # or "whisper-cpp" for the optional AMD runtime
model = "base"
language = "pt"             # ISO 639-1 code; use "auto" to detect language
device = "auto"             # faster-whisper: auto, cpu, cuda; whisper.cpp: auto, cpu, vulkan
compute_type = "auto"       # faster-whisper only

[ai]
enabled = false
backend = "none"            # local, ollama, or an explicitly configured cloud backend

[audio]
silence_duration = 2.0
silence_threshold = 0.5

[injection]
method = "auto"             # auto, wtype, xdotool, ydotool, clipboard-only
preserve_clipboard = false

[adaptive]
enabled = true
watch_window = 15.0
promotion_threshold = 2
```

For `whisper-cpp`, the `auto` device requests Vulkan just like `vulkan`; it
does not silently fall back to CPU.

## Local AI refinement with Ollama

[Ollama](https://docs.ollama.com/) is an optional local refinement backend.
Start its local service, then choose **Settings → AI Refinement → Local
(Ollama)**. LinuxWhispr contacts only `127.0.0.1:11434`, disables proxy use,
rejects redirects, and never downloads a model itself.

The dashboard's searchable selector lists installed local, completion-capable
models. It excludes cloud-routed and embedding-only models. Search by model
name, parameter size, or quantization; selecting a model and enabling
refinement require an application restart.

```toml
[ai]
enabled = true
backend = "ollama"
model = "qwen3.5:4b"
```

The following recommendations are practical multilingual starting points, not a
dictation-quality benchmark. Download sizes are approximate and runtime memory
use depends on the model and hardware.

| Model | Download | Suggested use |
| --- | ---: | --- |
| [Qwen3 8B](https://ollama.com/library/qwen3:8b) | 5.2 GB | Balanced starting point |
| [Qwen3.5 4B](https://ollama.com/library/qwen3.5:4b) | 3.3 GB | Smaller multilingual option |
| [Qwen3 14B](https://ollama.com/library/qwen3:14b) | 9.3 GB | Larger alternative when more memory is available |
| [Gemma 3 12B](https://ollama.com/library/gemma3:12b) | 8.2 GB | Multilingual alternative; download includes vision components |

For a model that is not installed, the dashboard shows a manual command such as
`ollama pull qwen3.5:4b`; run it yourself, then refresh the model list. If
Ollama or the selected model is unavailable, or generation fails, LinuxWhispr
keeps the original transcription.

## Troubleshooting

- **Wayland hotkeys:** LinuxWhispr uses the XDG Desktop Portal
  `GlobalShortcuts` interface and needs `dbus-python` and PyGObject. A portal
  must grant the shortcut request. If it is unavailable, an X11/XWayland or
  `pynput` fallback may work, but is compositor- and permission-dependent.
- **Text remains on the clipboard:** install and configure an injection helper
  (`xdotool` on X11, or `wtype`/`ydotool` on Wayland). If paste simulation
  fails, LinuxWhispr leaves the text on the clipboard for manual pasting.
- **Dashboard will not start:** check whether another LinuxWhispr instance or
  another process already uses the configured `web.port`, then inspect the
  startup error before choosing a free port and restarting.
- **Vulkan fails to load:** confirm the Vulkan driver and GGML model, then
  select `cpu` for `whisper-cpp` when GPU acceleration is unavailable.

## Development

From a repository checkout:

```bash
# Create the development environment. Add retained runtime extras as needed:
# for example, use --extra dev --extra amd or --extra dev --extra gtk.
uv sync --extra dev

# Python tests and static checks
uv run --extra dev pytest
uv run --extra dev ruff check src/
uv run --extra dev mypy src/

# Browser-localization tests
node --test tests/web_i18n.test.js
```

## Architecture

The dictation path is: global hotkey → audio capture → voice-activity detection
→ speech-to-text → snippets → optional AI refinement → dictionary corrections
→ clipboard paste → local history. Components communicate through an internal
event bus. See [`specs/001-linux-whispr/spec.md`](specs/001-linux-whispr/spec.md)
for the project specification.

## License

MIT
