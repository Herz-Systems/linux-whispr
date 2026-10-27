# Working on LinuxWhispr

These instructions apply to the whole repository. Use `README.md` for current
setup, usage, architecture, and preview instructions; `pyproject.toml` defines
Python compatibility, dependencies, and tool settings. Older specs describe some
superseded implementation details: check the current entry points before acting.

## UI: concise by default

- **Keep UI copy compact.** Prefer short action labels such as “Launch LinuxWhispr
  on startup” and “Open dashboard on launch”. Add helper text only when it adds
  necessary information, usually one short sentence. Put detailed explanations
  and troubleshooting in the README instead of filling settings with prose.
- Preserve the existing product UI, navigation, themes, and responsive layout.
  Reuse existing controls and styles rather than introducing a second convention.
- Align peer controls in form grids without divider lines between them. Reserve
  separators for actual sections or stacked groups.
- Update English, German, Spanish, and Portuguese together. English text is also
  the translation key in `src/linux_whispr/web/static/i18n.js`. Keep catalog keys,
  placeholders, and plural forms consistent. Remove replaced keys rather than
  retaining aliases.
- Keep interface language independent of transcription language. Use the existing
  locale-aware number, date, duration, and size formatters.

## Frontend changes

- The dashboard lives in `src/linux_whispr/web/static/`: Alpine.js, plain
  JavaScript, CSS, and vendored assets. Small UI changes need no new build system.
- Preserve settings autosave through `saveConfig()`, including its snapshot queue
  and error feedback. Cosmetic changes must not alter config bindings or defaults.
- Bump the shared query revision for **both** `app.js` and `i18n.js` in
  `index.html` when either script changes. Bump the stylesheet's separate revision
  when `app.css` changes. Cached old scripts can break otherwise correct new HTML.
- Render user/API text as text with the existing escaping conventions, not raw
  HTML. Preserve accessible labels and helper-text associations when shortening copy.
- Verify changed UI in a real browser on wide and narrow screens, checking the
  relevant theme and state. For asset changes, also reload an already-cached
  origin; a fresh preview port alone does not prove the upgrade works.

## Runtime and privacy boundaries

- Both `linux-whispr` and `linux-whispr-web` launch the combined dictation engine
  and dashboard. The dashboard server always runs on loopback while the normal
  app runs; `web.auto_open` controls only automatic browser opening. Manual tray
  “Open Dashboard” must still work when auto-open is off.
- `autostart` means launch after desktop login via an XDG desktop entry, not a
  pre-login system service. Keep it independent of browser auto-open. Config API
  updates and reset must synchronize the actual entry, not just the saved boolean.
- Core desktop UI uses Qt/PySide6. GTK settings and the explicit setup wizard are
  optional paths, not the normal dashboard. Preserve X11/Wayland integration and
  the Qt main-thread lifecycle when touching native components.
- Keep processing local-first and cloud processing explicitly opt-in. Preserve
  loopback-only local services; do not introduce telemetry or upload user audio,
  transcripts, dictionaries, or credentials as a development shortcut.
- AI refinement preserves the transcription's language, meaning, mixed-language
  passages, and technical terms; it must not silently translate the output.

## Configuration and validation

- Respect the selected `--config` path through the existing active-config API
  helpers. Partial updates must preserve unrelated settings. Honor XDG directories
  and the installed launcher path rather than hard-coding a developer's home.
- Use disposable XDG directories and a separate port for interface experiments;
  the isolated dashboard procedure is in `README.md` under Development. Its
  unavailable-dictation status is expected, unlike the normal combined app.
- Preserve existing worktree changes and user data. Leave live settings,
  recordings, history, models, and shortcuts untouched unless the task requires
  changing them. Check that dictation is idle before a necessary restart.
- Use the existing environment for focused checks; retain configured runtime
  extras, especially `amd`, if synchronizing dependencies. Run affected Python
  tests and checks from the README, and `node --test tests/web_i18n.test.js` after
  localization or dashboard JavaScript changes.
- Test consumer-visible behavior and boundaries. Verify wording and layout in the
  browser instead of pinning incidental copy in permanent tests. Report only
  checks actually exercised; documentation-only edits need no application restart.
- Keep README labels and behavior descriptions aligned with UI changes. Keep this
  file focused on durable project rules rather than task logs or machine state.
