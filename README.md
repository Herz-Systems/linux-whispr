# LinuxWhispr

**Privacy-first, open-source voice dictation for Linux** — a system-wide dictation tool that replicates the full experience of [Wispr Flow](https://wisprflow.com), with AI-powered text refinement, context awareness, and seamless integration into any text field.

## Features

- 🎤 **System-wide dictation** — works in any text field (browsers, IDEs, terminals, chat apps)
- 🔒 **Privacy-first** — local-first transcription via [faster-whisper](https://github.com/SYSTRAN/faster-whisper), no cloud by default
- 🧠 **AI text refinement** — removes filler words, fixes grammar, adapts to context (email/code/chat)
- ⌨️ **Global hotkey** — configurable hotkey works regardless of focused window (X11 + Wayland)
- 🗣️ **Voice commands** — "make this more formal", "summarize the selected text"
- 📚 **Custom dictionary** — teach it your names, technical terms, brand names
- 🔄 **Adaptive learning** — automatically learns corrections you make
- 🌍 **99+ languages** — automatic language detection via Whisper
- 🖥️ **Linux native** — Qt tray and activity popup, local web dashboard, PipeWire/PulseAudio audio, X11 + Wayland support

## Quick Start

### System Dependencies

```bash
# Ubuntu/Debian
sudo apt install libportaudio2 libxcb-cursor0 libxkbcommon-x11-0 \
    wl-clipboard xdotool xclip

# Fedora
sudo dnf install portaudio xcb-util-cursor libxkbcommon-x11 \
    wl-clipboard xdotool xclip

# Arch Linux
sudo pacman -S python portaudio xcb-util-cursor libxkbcommon \
    wl-clipboard xdotool xclip
```

### Install

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then:

```bash
git clone https://github.com/linx-systems/linux-whispr.git
cd linux-whispr
./install.sh
```

The installer creates a project-local `.venv`, a launcher at
`~/.local/bin/linux-whispr`, an application-menu entry, and a trusted executable
desktop shortcut when an XDG Desktop directory is enabled. It respects
`XDG_BIN_HOME`, `XDG_DATA_HOME`, and `XDG_CONFIG_HOME`. The launcher works from any
directory without relying on your shell's PATH. Keep the checkout in place;
rerun the installer after moving or updating it.

Re-running the installer updates these files without replacing your configuration,
history, dictionary, or models. Existing whisper.cpp/AMD support is preserved.
Use `./install.sh --amd` to install it explicitly or `./install.sh --no-amd` to
omit it. Installation neither starts dictation nor enables autostart, and never
runs sudo automatically.

The core desktop UI uses PySide6 wheels and does not require PyGObject. The
optional `--setup` wizard and native settings still require GTK4, libadwaita,
their introspection dependencies, and the `gtk` Python extra. Normal startup
uses the web dashboard without these optional GTK dependencies.

### AMD Vulkan acceleration

The default `faster-whisper` install does not provide AMD GPU acceleration. For
local AMD acceleration, install the optional `whisper.cpp` runtime from source:

```bash
# Debian / Ubuntu / Mint build and Vulkan prerequisites
sudo apt install build-essential cmake libvulkan-dev glslc libshaderc1 \
    spirv-headers mesa-vulkan-drivers

# From this repository
uv sync --extra amd
# Or launch directly with the AMD acceleration extra
uv run --extra amd linux-whispr
```

`pywhispercpp` wheels are CPU-only, so the project tells uv to build
`pywhispercpp==1.5.1` from source with Vulkan and an origin-relative shared
library RPATH. With pip, explicitly request the same source build:

```bash
GGML_VULKAN=1 CMAKE_INSTALL_RPATH='$ORIGIN' CMAKE_BUILD_WITH_INSTALL_RPATH=ON \
  pip install --no-binary=pywhispercpp "linux-whispr[amd]"
```

Restart LinuxWhispr, select **whisper.cpp (AMD / Vulkan)** with the **Vulkan**
device, then download a separate GGML model from the model page. GGML models
are not shared with faster-whisper. Vulkan is verified when the model loads;
if it cannot initialize, LinuxWhispr reports an error instead of silently using
the CPU. Select the whisper.cpp CPU device explicitly when GPU acceleration is
not available.

### Run

```bash
linux-whispr
```

`linux-whispr` and `linux-whispr-web` both start the same combined application:
the dictation engine and the dashboard. On a first normal launch, LinuxWhispr
starts with defaults; run `linux-whispr --setup` only when you want the setup
wizard.

The dashboard is available at **http://127.0.0.1:7865** while LinuxWhispr is
running. It manages settings, transcription history, dictionary entries, voice
snippets, and Whisper models. The interface supports light and dark themes,
remembers your choice, and adapts to narrow windows. Its styles, icons, and
Alpine runtime are served locally, without a CDN or frontend build step.

### Usage

1. Press **F12** (default hotkey) to start recording
2. Speak your text
3. Press **F12** again to stop (or wait for auto-stop after 2s of silence)
4. Text appears at your cursor position

Opening the dashboard does not start microphone recording; dictation starts
through the application's global hotkey or the tray's **Start Dictation** action.

The notification area shows a microphone icon with a status badge: gray while
starting, green/check when ready, red/dot while recording, blue/progress while
processing, and orange/warning when something needs attention. A problem stays
visible after processing ends and clears on the next dictation attempt. AI
refinement failures still preserve the original transcription. The tooltip
contains status only, never dictated text.

Click the icon to open the dashboard. Its context menu offers **Open Dashboard**,
**Start/Stop Dictation**, and **Quit**. Qt uses the desktop's StatusNotifier or
legacy XEmbed host, including Cinnamon's status applet. A desktop notification
area is required. Use `--no-tray` to disable the indicator without disabling
dictation, the activity popup, or the dashboard.

A compact floating pill briefly confirms readiness, displays live microphone
levels during recording, shows processing activity, and reports completion or
problems. It never activates a window or takes keyboard focus away from the
target text field. On X11 it appears near the bottom of the monitor containing
the pointer, using that monitor's available geometry rather than the combined
multi-monitor desktop. Wayland compositors control final window placement.

### Web dashboard

The dashboard defaults to English and offers an interface-language selector for
English, Deutsch, Español, and Português. The selected interface language is
stored locally in the browser; it is independent of the transcription language
configured for dictation.

Settings save automatically; restart the application to apply configuration changes.
Dictionary words, recognized variants, and vocabulary-pack selections take effect
on the next dictation without restarting.

Run the browser-localization regression tests with:

```bash
node --test tests/web_i18n.test.js
```

### Dictionary packs and recognized variants

Open **Dictionary → Bundled dictionaries** to enable the vocabulary you need.
All five packs are optional and disabled by default:

| Pack | Terms | Example correction |
| --- | ---: | --- |
| Coding | 42 | `type script` → `TypeScript`, `postgress` → `PostgreSQL` |
| DevOps | 31 | `cube control` → `kubectl`, `terra form` → `Terraform` |
| AI | 28 | `open ai` → `OpenAI`, `chat gpt` → `ChatGPT` |
| Email and office | 28 | `attachement` → `attachment`, `recieve` → `receive` |
| German business | 22 | `e mail adresse` → `E-Mail-Adresse`, `rück meldung` → `Rückmeldung` |

Expand a pack to inspect all terms, explicit recognized variants, and reference
links. Terms without variants, such as Go, Rust, and Claude, are recognition hints
only; ordinary words are not replaced with similarly sounding product names.
Enabled vocabulary also supplies bounded, personal-first hints to speech
recognition and optional AI refinement (at most 1,000 characters per context).

For project names or recurring mistakes, add a personal word and enter its
**Recognized variants**, one per line. Adding that word again with variants
updates them. Explicit personal variants take precedence over canonical spelling
normalization, learned corrections, and bundled variants. Personal canonical
spellings also override a pack's spelling of the same term.

Corrections run once after snippets and optional AI refinement, before text
injection. They work with AI disabled or unavailable, match whole tokens rather
than identifier substrings, and leave URLs, email addresses, inline code, and
fenced code unchanged. History retains the raw transcription and the final
processed text. Disabling a pack does not delete personal entries or learned
corrections, and bundled terms are never copied into the personal dictionary.

The independently curated catalog draws on the profile approach in
[Wisper](https://github.com/taraksh01/wisper/tree/main/src-tauri/resources/profiles).
Other useful references are the separation of vocabulary and corrections in
[TypeWhisper term packs](https://github.com/typewhisper/typewhisper-termpacks)
and the short recognition-context guidance in
[Voxtype](https://github.com/peteonrails/voxtype/blob/main/docs/USER_MANUAL.md).
No third-party dictionary downloads are required at runtime.

## Configuration

Edit `~/.config/linux-whispr/config.toml`:

```toml
[hotkey]
dictation = "F12"
command = "<Ctrl><Shift>h"
mode = "toggle"  # or "push-to-talk"

[stt]
backend = "faster-whisper"  # or "whisper-cpp" for the optional AMD runtime
model = "base"              # whisper.cpp supports tiny, base, small, medium, large-v3, large-v3-turbo
device = "auto"             # faster-whisper: auto, cpu, cuda; whisper.cpp: vulkan, cpu, auto
compute_type = "auto"       # faster-whisper only

[ai]
enabled = false          # enable AI text refinement
backend = "none"         # none, local (llama.cpp), ollama, openai, anthropic, groq

[audio]
silence_duration = 2.0   # seconds of silence before auto-stop
silence_threshold = 0.5  # VAD sensitivity (0.0-1.0)

[injection]
method = "auto"          # auto, wtype, xdotool, ydotool, clipboard-only
preserve_clipboard = true
```

The `whisper-cpp` `auto` device requests Vulkan just like `vulkan`; it never
falls back silently to CPU. Configuration changes apply after the next app
restart.

### Local AI refinement with Ollama

Ollama is an additional local refinement backend; the existing llama.cpp option
still accepts a GGUF file path. Start your local [Ollama service](https://docs.ollama.com/),
then choose **Settings → AI Refinement → Local (Ollama)**. The web dashboard has
one searchable dropdown for installed local text-generation models: open it and
type a model name, parameter size, or quantization. Use the arrow keys and Enter
to select; Escape cancels. Searching does not change the saved model. Recommended
models remain below the dropdown, without a second installed-model list.
Native settings also separate installed models from recommendations.
Refresh checks the service at `127.0.0.1:11434`; it never downloads models.
Cloud-routed models and embedding-only models are excluded.

Select an installed model, enable refinement, and restart LinuxWhispr to apply
the settings. For example:

```toml
[ai]
enabled = true
backend = "ollama"
model = "qwen3.5:4b"
```

These are practical multilingual starting points, not a dictation-quality
benchmark ranking. Download sizes are approximate; runtime memory usage is
higher and depends on the model and hardware.

| Model | Download | Suggested use |
| --- | ---: | --- |
| [Qwen3 8B](https://ollama.com/library/qwen3:8b) | 5.2 GB | Balanced starting point |
| [Qwen3.5 4B](https://ollama.com/library/qwen3.5:4b) | 3.3 GB | Smaller multilingual option |
| [Qwen3 14B](https://ollama.com/library/qwen3:14b) | 9.3 GB | Larger alternative when more memory is available |
| [Gemma 3 12B](https://ollama.com/library/gemma3:12b) | 8.2 GB | Multilingual alternative; download includes vision components |

The recommendations use the families' documented multilingual capabilities:
[Qwen3](https://huggingface.co/Qwen/Qwen3-8B),
[Qwen3.5](https://huggingface.co/Qwen/Qwen3.5-4B), and
[Gemma 3](https://ai.google.dev/gemma/docs/core).
For a model that is not installed, the interface displays a manual command such
as `ollama pull qwen3.5:4b`. Run it yourself, then refresh the model list.

Refinement uses Ollama's [local chat API](https://docs.ollama.com/api/chat),
disables thinking when supported by the model, and uses only the final text
response. If the service or selected model is unavailable, or generation fails,
the original transcription is preserved rather than discarded.

## Development

```bash
# Clone
git clone https://github.com/linx-systems/linux-whispr.git
cd linux-whispr

# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest

# Type checking
mypy src/

# Linting
ruff check src/
```

## Architecture

```
Hotkey → Audio Capture → VAD (auto-stop) → STT (faster-whisper / whisper.cpp Vulkan / API) → Snippets → AI Refinement (optional) → Dictionary Corrections → Text Injection → History
```

Components communicate via an internal event bus. See `specs/001-linux-whispr/spec.md` for the full specification.

## License

MIT
