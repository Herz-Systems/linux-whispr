(function (global) {
  "use strict";

  const languages = Object.freeze([
    Object.freeze({ code: "en", name: "English", tag: "en-US" }),
    Object.freeze({ code: "de", name: "Deutsch", tag: "de-DE" }),
    Object.freeze({ code: "es", name: "Español", tag: "es-ES" }),
    Object.freeze({ code: "pt", name: "Português", tag: "pt-BR" }),
  ]);

  const languageTags = Object.fromEntries(
    languages.map(({ code, tag }) => [code, tag]),
  );

  const catalogs = {
    en: {
      "Skip to content": "Skip to content",
      "Main navigation": "Main navigation",
      "Version {version}": "Version {version}",
      "Local panel": "Local panel",
      "Close menu": "Close menu",
      Sections: "Sections",
      "Use light theme": "Use light theme",
      "Use dark theme": "Use dark theme",
      "Recording status is shown in the app.":
        "Recording status is shown in the app.",
      "Open menu": "Open menu",
      "Interface language": "Interface language",
      "Panel unavailable": "Panel unavailable",
      "Panel connected": "Panel connected",
      Dashboard: "Dashboard",
      "Track your dictation space and latest transcriptions.":
        "Track your dictation space and latest transcriptions.",
      Retry: "Retry",
      "Your voice, in text.": "Your voice, in text.",
      "Use the app shortcut to dictate into any text field.":
        "Use the app shortcut to dictate into any text field.",
      "Shortcut not configured": "Shortcut not configured",
      "View settings": "View settings",
      "Usage summary": "Usage summary",
      Model: "Model",
      "Not set": "Not set",
      Language: "Language",
      "Auto-detect": "Auto-detect",
      Portuguese: "Portuguese",
      English: "English",
      Spanish: "Spanish",
      French: "French",
      German: "German",
      Italian: "Italian",
      Japanese: "Japanese",
      Chinese: "Chinese",
      Refinement: "Refinement",
      Enabled: "Enabled",
      Disabled: "Disabled",
      "Transcription statistics": "Transcription statistics",
      "Transcriptions today": "Transcriptions today",
      "Items logged today": "Items logged today",
      "Words today": "Words today",
      "Recognized text": "Recognized text",
      "Total transcriptions": "Total transcriptions",
      "In your history": "In your history",
      "Average duration": "Average duration",
      "Per transcription": "Per transcription",
      "Recent transcriptions": "Recent transcriptions",
      "Your latest texts are available in history.":
        "Your latest texts are available in history.",
      "View history": "View history",
      "{count} words": { one: "{count} word", other: "{count} words" },
      "No transcriptions yet": "No transcriptions yet",
      "Use the configured app shortcut to create your first entry.":
        "Use the configured app shortcut to create your first entry.",
      Settings: "Settings",
      "Adjust recognition, shortcuts, and text injection.":
        "Adjust recognition, shortcuts, and text injection.",
      Saving: "Saving",
      Saved: "Saved",
      "Could not save settings.": "Could not save settings.",
      "Changes are saved automatically and persist for the next startup. Restart the app when needed.":
        "Changes are saved automatically and persist for the next startup. Restart the app when needed.",
      "Transcription (STT)": "Transcription (STT)",
      "STT backend": "STT backend",
      Local: "Local",
      "Whisper model": "Whisper model",
      "Compute device": "Compute device",
      Auto: "Auto",
      "Compute type": "Compute type",
      "whisper.cpp (AMD / Vulkan)": "whisper.cpp (AMD / Vulkan)",
      "Vulkan (AMD GPU)": "Vulkan (AMD GPU)",
      "Model format": "Model format",
      "faster-whisper (CPU / CUDA)": "faster-whisper (CPU / CUDA)",
      Audio: "Audio",
      "Silence duration": "Silence duration",
      "VAD sensitivity": "VAD sensitivity",
      "Whisper mode": "Whisper mode",
      "Boost gain for quiet environments": "Boost gain for quiet environments",
      "AI refinement": "AI refinement",
      "Enable AI refinement": "Enable AI refinement",
      "Clean text, correct grammar, and format for context":
        "Clean text, correct grammar, and format for context",
      "LLM backend": "LLM backend",
      None: "None",
      "Local (llama.cpp)": "Local (llama.cpp)",
      "Local (Ollama)": "Local (Ollama)",
      "Installed local model": "Installed local model",
      "Refresh installed Ollama models": "Refresh installed Ollama models",
      "Refreshing…": "Refreshing…",
      "Select an installed model": "Select an installed model",
      "Search installed models": "Search installed models",
      "No installed models match your search.":
        "No installed models match your search.",
      "Clear selected model": "Clear selected model",
      "Unavailable model: {model}": "Unavailable model: {model}",
      "Ollama runs locally at 127.0.0.1:11434. Your dictation stays on this computer.":
        "Ollama runs locally at 127.0.0.1:11434. Your dictation stays on this computer.",
      "Loading installed Ollama models…": "Loading installed Ollama models…",
      "Could not load installed Ollama models.":
        "Could not load installed Ollama models.",
      "Ollama service is unavailable.": "Ollama service is unavailable.",
      "No installed Ollama models": "No installed Ollama models",
      "Install a recommended model below, then refresh this list.":
        "Install a recommended model below, then refresh this list.",
      Installed: "Installed",
      "Recommended models": "Recommended models",
      "Larger models need more memory and take longer to download.":
        "Larger models need more memory and take longer to download.",
      "Balanced multilingual refinement; recommended starting point.":
        "Balanced multilingual refinement; recommended starting point.",
      "Smaller download for quick corrections on modest hardware.":
        "Smaller download for quick corrections on modest hardware.",
      "Larger multilingual model for more demanding edits.":
        "Larger multilingual model for more demanding edits.",
      "Multilingual alternative; larger download includes vision components.":
        "Multilingual alternative; larger download includes vision components.",
      "Download: {size} GB": "Download: {size} GB",
      Use: "Use",
      "Install manually:": "Install manually:",
      "Dictation status is shown in this dashboard.":
        "Dictation status is shown in this dashboard.",
      "Dictation unavailable": "Dictation unavailable",
      Recording: "Recording",
      Processing: "Processing",
      "Dictation ready": "Dictation ready",
      "e.g. gpt-4o-mini": "e.g. gpt-4o-mini",
      "Custom prompt": "Custom prompt",
      "Leave empty to use the default": "Leave empty to use the default",
      "Keyboard shortcuts": "Keyboard shortcuts",
      "Dictation hotkey": "Dictation hotkey",
      "Command hotkey": "Command hotkey",
      "Activation mode": "Activation mode",
      Toggle: "Toggle",
      "Push-to-Talk": "Push-to-Talk",
      "Text injection": "Text injection",
      Method: "Method",
      "Clipboard only": "Clipboard only",
      "Preserve clipboard": "Preserve clipboard",
      "Restore previous content after injection":
        "Restore previous content after injection",
      "History and adaptive": "History and adaptive",
      "Retention (days)": "Retention (days)",
      "Adaptive learning": "Adaptive learning",
      "Learn corrections automatically": "Learn corrections automatically",
      "Try saving again": "Try saving again",
      "Reset settings?": "Reset settings?",
      "All settings will return to their default values.":
        "All settings will return to their default values.",
      "Reset to defaults": "Reset to defaults",
      "Transcription history": "Transcription history",
      "Search, copy, or remove previously recognized text.":
        "Search, copy, or remove previously recognized text.",
      "Export JSON": "Export JSON",
      "Clear all history?": "Clear all history?",
      "This action cannot be undone.": "This action cannot be undone.",
      "Clear all": "Clear all",
      "Search transcriptions": "Search transcriptions",
      Refresh: "Refresh",
      "History table": "History table",
      Date: "Date",
      Text: "Text",
      Words: "Words",
      Duration: "Duration",
      App: "App",
      Actions: "Actions",
      "Original: {text}": "Original: {text}",
      "Not provided": "Not provided",
      "Copy transcription": "Copy transcription",
      "Delete transcription?": "Delete transcription?",
      "Delete transcription": "Delete transcription",
      "No transcriptions found": "No transcriptions found",
      "Adjust your search or use the app to create a new transcription.":
        "Adjust your search or use the app to create a new transcription.",
      "{count} transcriptions": {
        one: "{count} transcription",
        other: "{count} transcriptions",
      },
      Previous: "Previous",
      "Page {page}": "Page {page}",
      Next: "Next",
      "Custom dictionary": "Custom dictionary",
      "Keep names, brands, and technical terms easier to recognize.":
        "Keep names, brands, and technical terms easier to recognize.",
      "Bundled dictionaries": "Bundled dictionaries",
      "Choose optional term packs. Changes take effect with the next dictation without restarting.":
        "Choose optional term packs. Changes take effect with the next dictation without restarting.",
      "Dictionary pack: Coding": "Coding",
      "Dictionary pack: DevOps": "DevOps",
      "Dictionary pack: AI": "AI",
      "Dictionary pack: Email": "Email",
      "Dictionary pack: German business": "German business",
      "Dictionary pack description: Coding":
        "Programming languages, tools, and frameworks.",
      "Dictionary pack description: DevOps":
        "Infrastructure, delivery, and operations terms.",
      "Dictionary pack description: AI":
        "AI models, platforms, and machine-learning terms.",
      "Dictionary pack description: Email":
        "Email protocols, addresses, and common message terms.",
      "Dictionary pack description: German business":
        "German business and office terms.",
      "{terms} terms, {aliases} aliases": "{terms} terms, {aliases} aliases",
      "Enable {pack}": "Enable {pack}",
      "Inspect terms and recognized variants":
        "Inspect terms and recognized variants",
      "Recognition hint only": "Recognition hint only",
      Sources: "Sources",
      "Recognized variants (one per line)":
        "Recognized variants (one per line)",
      "Personal words and their variants are kept when packs change and take priority over pack variants. Save the same word again to update it.":
        "Personal words and their variants are kept when packs change and take priority over pack variants. Save the same word again to update it.",
      "Recognized variants": "Recognized variants",
      "No recognized variants": "No recognized variants",
      "Add word": "Add word",
      "Add a term for future use.": "Add a term for future use.",
      "Word or term": "Word or term",
      "Please fill out this field.": "Please fill out this field.",
      Category: "Category",
      General: "General",
      "Personal names": "Personal names",
      Technical: "Technical",
      Brand: "Brand",
      "Adding…": "Adding…",
      Add: "Add",
      "{count} items": { one: "{count} item", other: "{count} items" },
      Word: "Word",
      Source: "Source",
      Frequency: "Frequency",
      Manual: "Manual",
      Learned: "Learned",
      Automatic: "Automatic",
      "Delete word?": "Delete word?",
      "The word will be removed from the dictionary.":
        "The word will be removed from the dictionary.",
      "Delete word": "Delete word",
      "No words in the dictionary": "No words in the dictionary",
      "Add a name, brand, or technical term to get started.":
        "Add a name, brand, or technical term to get started.",
      "Learned corrections": "Learned corrections",
      Heard: "Heard",
      Corrected: "Corrected",
      Times: "Times",
      "Last seen": "Last seen",
      "Delete correction?": "Delete correction?",
      "The learned correction will be removed.":
        "The learned correction will be removed.",
      "Delete correction": "Delete correction",
      "No learned corrections": "No learned corrections",
      "Automatic corrections will appear here.":
        "Automatic corrections will appear here.",
      "Voice shortcuts": "Voice shortcuts",
      "Use trigger phrases to insert recurring responses and text.":
        "Use trigger phrases to insert recurring responses and text.",
      "Add snippet": "Add snippet",
      "Define the spoken phrase and inserted text.":
        "Define the spoken phrase and inserted text.",
      "Trigger phrase": "Trigger phrase",
      "e.g. my email": "e.g. my email",
      Expansion: "Expansion",
      "e.g. hello@example.com": "e.g. hello@example.com",
      "Configured snippets": "Configured snippets",
      Trigger: "Trigger",
      "Delete snippet?": "Delete snippet?",
      "The voice shortcut will be removed.":
        "The voice shortcut will be removed.",
      "Delete snippet": "Delete snippet",
      "No snippets configured": "No snippets configured",
      "Create a shortcut to insert text you use often.":
        "Create a shortcut to insert text you use often.",
      "Whisper models": "Whisper models",
      "Download and manage models available for local transcription.":
        "Download and manage models available for local transcription.",
      "GGML models are stored separately. Vulkan acceleration requires the AMD runtime and a Vulkan-capable driver.":
        "GGML models are stored separately. Vulkan acceleration requires the AMD runtime and a Vulkan-capable driver.",
      "Total usage: {size} MB": "Total usage: {size} MB",
      "~{size} MB": "~{size} MB",
      Active: "Active",
      Downloaded: "Downloaded",
      "Not downloaded": "Not downloaded",
      "Downloading…": "Downloading…",
      Download: "Download",
      "Delete model?": "Delete model?",
      "The model will be removed from this computer.":
        "The model will be removed from this computer.",
      "Deleting…": "Deleting…",
      Delete: "Delete",
      "No models available": "No models available",
      "Refresh the list to check the models offered by the app.":
        "Refresh the list to check the models offered by the app.",
      "Refresh models": "Refresh models",
      Cancel: "Cancel",
      Confirm: "Confirm",
      History: "History",
      Dictionary: "Dictionary",
      Snippets: "Snippets",
      Models: "Models",
      "Could not complete the action.": "Could not complete the action.",
      "Text copied to clipboard.": "Text copied to clipboard.",
      "Could not copy text.": "Could not copy text.",
      "Could not check the dashboard connection.":
        "Could not check the dashboard connection.",
      "Could not load statistics.": "Could not load statistics.",
      "Could not load settings.": "Could not load settings.",
      "Could not load history.": "Could not load history.",
      "Could not load recent transcriptions.":
        "Could not load recent transcriptions.",
      "Could not load dictionary.": "Could not load dictionary.",
      "Could not load snippets.": "Could not load snippets.",
      "Could not load models.": "Could not load models.",
      "Could not load disk usage.": "Could not load disk usage.",
      "Settings restored to defaults.": "Settings restored to defaults.",
      "Could not restore settings.": "Could not restore settings.",
      "Transcription deleted.": "Transcription deleted.",
      "Could not delete transcription.": "Could not delete transcription.",
      "History cleared.": "History cleared.",
      "Could not clear history.": "Could not clear history.",
      "Word added to dictionary.": "Word added to dictionary.",
      "Dictionary entry saved.": "Dictionary entry saved.",
      "Could not update dictionary pack.": "Could not update dictionary pack.",
      "Could not add word.": "Could not add word.",
      "Word removed from dictionary.": "Word removed from dictionary.",
      "Could not remove word.": "Could not remove word.",
      "Correction removed from dictionary.":
        "Correction removed from dictionary.",
      "Could not remove correction.": "Could not remove correction.",
      "Snippet added.": "Snippet added.",
      "Could not add snippet.": "Could not add snippet.",
      "Snippet removed.": "Snippet removed.",
      "Could not remove snippet.": "Could not remove snippet.",
      "Model downloaded.": "Model downloaded.",
      "Could not download model.": "Could not download model.",
      "Model deleted.": "Model deleted.",
      "Could not delete model.": "Could not delete model.",
    },
    de: {
      "Skip to content": "Zum Inhalt springen",
      "Main navigation": "Hauptnavigation",
      "Version {version}": "Version {version}",
      "Local panel": "Lokales Bedienfeld",
      "Close menu": "Menü schließen",
      Sections: "Bereiche",
      "Use light theme": "Helles Design verwenden",
      "Use dark theme": "Dunkles Design verwenden",
      "Recording status is shown in the app.":
        "Der Aufnahmestatus wird in der App angezeigt.",
      "Open menu": "Menü öffnen",
      "Interface language": "Sprache der Benutzeroberfläche",
      "Panel unavailable": "Bedienfeld nicht verfügbar",
      "Panel connected": "Bedienfeld verbunden",
      Dashboard: "Übersicht",
      "Track your dictation space and latest transcriptions.":
        "Behalten Sie Ihren Diktierbereich und die neuesten Transkriptionen im Blick.",
      Retry: "Erneut versuchen",
      "Your voice, in text.": "Ihre Stimme als Text.",
      "Use the app shortcut to dictate into any text field.":
        "Verwenden Sie den App-Kurzbefehl, um in jedes Textfeld zu diktieren.",
      "Shortcut not configured": "Kurzbefehl nicht konfiguriert",
      "View settings": "Einstellungen anzeigen",
      "Usage summary": "Nutzungsübersicht",
      Model: "Modell",
      "Not set": "Nicht festgelegt",
      Language: "Sprache",
      "Auto-detect": "Automatisch erkennen",
      Portuguese: "Portugiesisch",
      English: "Englisch",
      Spanish: "Spanisch",
      French: "Französisch",
      German: "Deutsch",
      Italian: "Italienisch",
      Japanese: "Japanisch",
      Chinese: "Chinesisch",
      Refinement: "Überarbeitung",
      Enabled: "Aktiviert",
      Disabled: "Deaktiviert",
      "Transcription statistics": "Transkriptionsstatistik",
      "Transcriptions today": "Transkriptionen heute",
      "Items logged today": "Heute erfasste Einträge",
      "Words today": "Wörter heute",
      "Recognized text": "Erkannter Text",
      "Total transcriptions": "Transkriptionen insgesamt",
      "In your history": "In Ihrem Verlauf",
      "Average duration": "Durchschnittliche Dauer",
      "Per transcription": "Pro Transkription",
      "Recent transcriptions": "Letzte Transkriptionen",
      "Your latest texts are available in history.":
        "Ihre letzten Texte sind im Verlauf verfügbar.",
      "View history": "Verlauf anzeigen",
      "{count} words": { one: "{count} Wort", other: "{count} Wörter" },
      "No transcriptions yet": "Noch keine Transkriptionen",
      "Use the configured app shortcut to create your first entry.":
        "Verwenden Sie den konfigurierten App-Kurzbefehl, um Ihren ersten Eintrag zu erstellen.",
      Settings: "Einstellungen",
      "Adjust recognition, shortcuts, and text injection.":
        "Passen Sie Erkennung, Kurzbefehle und Texteingabe an.",
      Saving: "Wird gespeichert",
      Saved: "Gespeichert",
      "Could not save settings.":
        "Einstellungen konnten nicht gespeichert werden.",
      "Changes are saved automatically and persist for the next startup. Restart the app when needed.":
        "Änderungen werden automatisch gespeichert und bleiben bis zum nächsten Start erhalten. Starten Sie die App bei Bedarf neu.",
      "Transcription (STT)": "Transkription (STT)",
      "STT backend": "STT-Backend",
      Local: "Lokal",
      "Whisper model": "Whisper-Modell",
      "Compute device": "Rechengerät",
      Auto: "Automatisch",
      "Compute type": "Rechentyp",
      "whisper.cpp (AMD / Vulkan)": "whisper.cpp (AMD / Vulkan)",
      "Vulkan (AMD GPU)": "Vulkan (AMD-GPU)",
      "Model format": "Modellformat",
      "faster-whisper (CPU / CUDA)": "faster-whisper (CPU / CUDA)",
      Audio: "Audio",
      "Silence duration": "Stille-Dauer",
      "VAD sensitivity": "VAD-Empfindlichkeit",
      "Whisper mode": "Flüstermodus",
      "Boost gain for quiet environments":
        "Verstärkung für leise Umgebungen erhöhen",
      "AI refinement": "KI-Überarbeitung",
      "Enable AI refinement": "KI-Überarbeitung aktivieren",
      "Clean text, correct grammar, and format for context":
        "Text bereinigen, Grammatik korrigieren und passend zum Kontext formatieren",
      "LLM backend": "LLM-Backend",
      None: "Keine",
      "Local (llama.cpp)": "Lokal (llama.cpp)",
      "Local (Ollama)": "Lokal (Ollama)",
      "Installed local model": "Installiertes lokales Modell",
      "Refresh installed Ollama models": "Installierte Ollama-Modelle aktualisieren",
      "Refreshing…": "Wird aktualisiert…",
      "Select an installed model": "Installiertes Modell auswählen",
      "Search installed models": "Installierte Modelle durchsuchen",
      "No installed models match your search.":
        "Keine installierten Modelle entsprechen Ihrer Suche.",
      "Clear selected model": "Modellauswahl löschen",
      "Unavailable model: {model}": "Nicht verfügbares Modell: {model}",
      "Ollama runs locally at 127.0.0.1:11434. Your dictation stays on this computer.":
        "Ollama läuft lokal unter 127.0.0.1:11434. Ihre Diktate bleiben auf diesem Computer.",
      "Loading installed Ollama models…": "Installierte Ollama-Modelle werden geladen…",
      "Could not load installed Ollama models.":
        "Installierte Ollama-Modelle konnten nicht geladen werden.",
      "Ollama service is unavailable.": "Der Ollama-Dienst ist nicht verfügbar.",
      "No installed Ollama models": "Keine Ollama-Modelle installiert",
      "Install a recommended model below, then refresh this list.":
        "Installieren Sie unten ein empfohlenes Modell und aktualisieren Sie dann diese Liste.",
      Installed: "Installiert",
      "Recommended models": "Empfohlene Modelle",
      "Larger models need more memory and take longer to download.":
        "Größere Modelle benötigen mehr Arbeitsspeicher und brauchen länger zum Herunterladen.",
      "Balanced multilingual refinement; recommended starting point.":
        "Ausgewogene mehrsprachige Überarbeitung; empfohlener Einstiegspunkt.",
      "Smaller download for quick corrections on modest hardware.":
        "Kleinerer Download für schnelle Korrekturen auf leistungsschwächerer Hardware.",
      "Larger multilingual model for more demanding edits.":
        "Größeres mehrsprachiges Modell für anspruchsvollere Überarbeitungen.",
      "Multilingual alternative; larger download includes vision components.":
        "Mehrsprachige Alternative; der größere Download enthält Bildverarbeitungskomponenten.",
      "Download: {size} GB": "Download: {size} GB",
      Use: "Verwenden",
      "Install manually:": "Manuell installieren:",
      "Dictation status is shown in this dashboard.":
        "Der Diktierstatus wird in diesem Dashboard angezeigt.",
      "Dictation unavailable": "Diktieren nicht verfügbar",
      Recording: "Aufnahme",
      Processing: "Wird verarbeitet",
      "Dictation ready": "Diktieren bereit",
      "e.g. gpt-4o-mini": "z. B. gpt-4o-mini",
      "Custom prompt": "Benutzerdefinierte Eingabeaufforderung",
      "Leave empty to use the default":
        "Leer lassen, um den Standard zu verwenden",
      "Keyboard shortcuts": "Tastenkürzel",
      "Dictation hotkey": "Diktier-Kurzbefehl",
      "Command hotkey": "Befehls-Kurzbefehl",
      "Activation mode": "Aktivierungsmodus",
      Toggle: "Umschalten",
      "Push-to-Talk": "Drücken zum Sprechen",
      "Text injection": "Texteingabe",
      Method: "Methode",
      "Clipboard only": "Nur Zwischenablage",
      "Preserve clipboard": "Zwischenablage beibehalten",
      "Restore previous content after injection":
        "Vorherigen Inhalt nach der Eingabe wiederherstellen",
      "History and adaptive": "Verlauf und Anpassung",
      "Retention (days)": "Aufbewahrung (Tage)",
      "Adaptive learning": "Adaptives Lernen",
      "Learn corrections automatically": "Korrekturen automatisch lernen",
      "Try saving again": "Speichern erneut versuchen",
      "Reset settings?": "Einstellungen zurücksetzen?",
      "All settings will return to their default values.":
        "Alle Einstellungen werden auf ihre Standardwerte zurückgesetzt.",
      "Reset to defaults": "Auf Standardwerte zurücksetzen",
      "Transcription history": "Transkriptionsverlauf",
      "Search, copy, or remove previously recognized text.":
        "Suchen, kopieren oder entfernen Sie zuvor erkannten Text.",
      "Export JSON": "JSON exportieren",
      "Clear all history?": "Gesamten Verlauf löschen?",
      "This action cannot be undone.":
        "Diese Aktion kann nicht rückgängig gemacht werden.",
      "Clear all": "Alles löschen",
      "Search transcriptions": "Transkriptionen suchen",
      Refresh: "Aktualisieren",
      "History table": "Verlaufstabelle",
      Date: "Datum",
      Text: "Text",
      Words: "Wörter",
      Duration: "Dauer",
      App: "App",
      Actions: "Aktionen",
      "Original: {text}": "Original: {text}",
      "Not provided": "Nicht angegeben",
      "Copy transcription": "Transkription kopieren",
      "Delete transcription?": "Transkription löschen?",
      "Delete transcription": "Transkription löschen",
      "No transcriptions found": "Keine Transkriptionen gefunden",
      "Adjust your search or use the app to create a new transcription.":
        "Passen Sie Ihre Suche an oder verwenden Sie die App, um eine neue Transkription zu erstellen.",
      "{count} transcriptions": {
        one: "{count} Transkription",
        other: "{count} Transkriptionen",
      },
      Previous: "Zurück",
      "Page {page}": "Seite {page}",
      Next: "Weiter",
      "Custom dictionary": "Benutzerdefiniertes Wörterbuch",
      "Keep names, brands, and technical terms easier to recognize.":
        "Machen Sie Namen, Marken und Fachbegriffe leichter erkennbar.",
      "Bundled dictionaries": "Mitgelieferte Wörterbücher",
      "Choose optional term packs. Changes take effect with the next dictation without restarting.":
        "Wählen Sie optionale Begriffspakete. Änderungen wirken bei der nächsten Diktation ohne Neustart.",
      "Dictionary pack: Coding": "Programmierung",
      "Dictionary pack: DevOps": "DevOps",
      "Dictionary pack: AI": "KI",
      "Dictionary pack: Email": "E-Mail",
      "Dictionary pack: German business": "Deutscher Geschäftsalltag",
      "Dictionary pack description: Coding":
        "Programmiersprachen, Werkzeuge und Frameworks.",
      "Dictionary pack description: DevOps":
        "Begriffe zu Infrastruktur, Bereitstellung und Betrieb.",
      "Dictionary pack description: AI":
        "KI-Modelle, Plattformen und Begriffe zum maschinellen Lernen.",
      "Dictionary pack description: Email":
        "E-Mail-Protokolle, Adressen und häufige Nachrichtenbegriffe.",
      "Dictionary pack description: German business":
        "Deutsche Begriffe aus Büro und Geschäftsalltag.",
      "{terms} terms, {aliases} aliases":
        "{terms} Begriffe, {aliases} Varianten",
      "Enable {pack}": "{pack} aktivieren",
      "Inspect terms and recognized variants":
        "Begriffe und erkannte Varianten anzeigen",
      "Recognition hint only": "Nur Erkennungshinweis",
      Sources: "Quellen",
      "Recognized variants (one per line)":
        "Erkannte Varianten (eine pro Zeile)",
      "Personal words and their variants are kept when packs change and take priority over pack variants. Save the same word again to update it.":
        "Persönliche Wörter und Varianten bleiben bei Paketänderungen erhalten und haben Vorrang vor Paketvarianten. Speichern Sie dasselbe Wort erneut, um es zu aktualisieren.",
      "Recognized variants": "Erkannte Varianten",
      "No recognized variants": "Keine erkannten Varianten",
      "Add word": "Wort hinzufügen",
      "Add a term for future use.":
        "Fügen Sie einen Begriff für die spätere Verwendung hinzu.",
      "Word or term": "Wort oder Begriff",
      "Please fill out this field.": "Bitte füllen Sie dieses Feld aus.",
      Category: "Kategorie",
      General: "Allgemein",
      "Personal names": "Personennamen",
      Technical: "Technisch",
      Brand: "Marke",
      "Adding…": "Wird hinzugefügt…",
      Add: "Hinzufügen",
      "{count} items": { one: "{count} Element", other: "{count} Elemente" },
      Word: "Wort",
      Source: "Quelle",
      Frequency: "Häufigkeit",
      Manual: "Manuell",
      Learned: "Gelernt",
      Automatic: "Automatisch",
      "Delete word?": "Wort löschen?",
      "The word will be removed from the dictionary.":
        "Das Wort wird aus dem Wörterbuch entfernt.",
      "Delete word": "Wort löschen",
      "No words in the dictionary": "Keine Wörter im Wörterbuch",
      "Add a name, brand, or technical term to get started.":
        "Fügen Sie zum Starten einen Namen, eine Marke oder einen Fachbegriff hinzu.",
      "Learned corrections": "Gelernte Korrekturen",
      Heard: "Gehört",
      Corrected: "Korrigiert",
      Times: "Anzahl",
      "Last seen": "Zuletzt gesehen",
      "Delete correction?": "Korrektur löschen?",
      "The learned correction will be removed.":
        "Die gelernte Korrektur wird entfernt.",
      "Delete correction": "Korrektur löschen",
      "No learned corrections": "Keine gelernten Korrekturen",
      "Automatic corrections will appear here.":
        "Automatische Korrekturen erscheinen hier.",
      "Voice shortcuts": "Sprachkurzbefehle",
      "Use trigger phrases to insert recurring responses and text.":
        "Verwenden Sie Auslösephrasen, um wiederkehrende Antworten und Texte einzufügen.",
      "Add snippet": "Textbaustein hinzufügen",
      "Define the spoken phrase and inserted text.":
        "Legen Sie die gesprochene Phrase und den eingefügten Text fest.",
      "Trigger phrase": "Auslösephrase",
      "e.g. my email": "z. B. meine E-Mail",
      Expansion: "Ersetzung",
      "e.g. hello@example.com": "z. B. hallo@beispiel.de",
      "Configured snippets": "Konfigurierte Textbausteine",
      Trigger: "Auslöser",
      "Delete snippet?": "Textbaustein löschen?",
      "The voice shortcut will be removed.":
        "Der Sprachkurzbefehl wird entfernt.",
      "Delete snippet": "Textbaustein löschen",
      "No snippets configured": "Keine Textbausteine konfiguriert",
      "Create a shortcut to insert text you use often.":
        "Erstellen Sie einen Kurzbefehl für Text, den Sie häufig verwenden.",
      "Whisper models": "Whisper-Modelle",
      "Download and manage models available for local transcription.":
        "Laden Sie Modelle für die lokale Transkription herunter und verwalten Sie sie.",
      "GGML models are stored separately. Vulkan acceleration requires the AMD runtime and a Vulkan-capable driver.":
        "GGML-Modelle werden separat gespeichert. Vulkan-Beschleunigung erfordert die AMD-Laufzeit und einen Vulkan-fähigen Treiber.",
      "Total usage: {size} MB": "Gesamtnutzung: {size} MB",
      "~{size} MB": "~{size} MB",
      Active: "Aktiv",
      Downloaded: "Heruntergeladen",
      "Not downloaded": "Nicht heruntergeladen",
      "Downloading…": "Wird heruntergeladen…",
      Download: "Herunterladen",
      "Delete model?": "Modell löschen?",
      "The model will be removed from this computer.":
        "Das Modell wird von diesem Computer entfernt.",
      "Deleting…": "Wird gelöscht…",
      Delete: "Löschen",
      "No models available": "Keine Modelle verfügbar",
      "Refresh the list to check the models offered by the app.":
        "Aktualisieren Sie die Liste, um die von der App angebotenen Modelle zu prüfen.",
      "Refresh models": "Modelle aktualisieren",
      Cancel: "Abbrechen",
      Confirm: "Bestätigen",
      History: "Verlauf",
      Dictionary: "Wörterbuch",
      Snippets: "Textbausteine",
      Models: "Modelle",
      "Could not complete the action.":
        "Die Aktion konnte nicht abgeschlossen werden.",
      "Text copied to clipboard.": "Text wurde in die Zwischenablage kopiert.",
      "Could not copy text.": "Text konnte nicht kopiert werden.",
      "Could not check the dashboard connection.":
        "Dashboard-Verbindung konnte nicht geprüft werden.",
      "Could not load statistics.": "Statistiken konnten nicht geladen werden.",
      "Could not load settings.": "Einstellungen konnten nicht geladen werden.",
      "Could not load history.": "Verlauf konnte nicht geladen werden.",
      "Could not load recent transcriptions.":
        "Letzte Transkriptionen konnten nicht geladen werden.",
      "Could not load dictionary.": "Wörterbuch konnte nicht geladen werden.",
      "Could not load snippets.": "Textbausteine konnten nicht geladen werden.",
      "Could not load models.": "Modelle konnten nicht geladen werden.",
      "Could not load disk usage.":
        "Speichernutzung konnte nicht geladen werden.",
      "Settings restored to defaults.":
        "Die Einstellungen wurden auf die Standardwerte zurückgesetzt.",
      "Could not restore settings.":
        "Einstellungen konnten nicht wiederhergestellt werden.",
      "Transcription deleted.": "Transkription wurde gelöscht.",
      "Could not delete transcription.":
        "Die Transkription konnte nicht gelöscht werden.",
      "History cleared.": "Verlauf wurde gelöscht.",
      "Could not clear history.": "Verlauf konnte nicht gelöscht werden.",
      "Word added to dictionary.": "Wort wurde zum Wörterbuch hinzugefügt.",
      "Dictionary entry saved.": "Wörterbucheintrag gespeichert.",
      "Could not update dictionary pack.":
        "Wörterbuchpaket konnte nicht aktualisiert werden.",
      "Could not add word.": "Wort konnte nicht hinzugefügt werden.",
      "Word removed from dictionary.":
        "Wort wurde aus dem Wörterbuch entfernt.",
      "Could not remove word.": "Wort konnte nicht entfernt werden.",
      "Correction removed from dictionary.":
        "Korrektur wurde aus dem Wörterbuch entfernt.",
      "Could not remove correction.": "Korrektur konnte nicht entfernt werden.",
      "Snippet added.": "Textbaustein wurde hinzugefügt.",
      "Could not add snippet.": "Textbaustein konnte nicht hinzugefügt werden.",
      "Snippet removed.": "Textbaustein wurde entfernt.",
      "Could not remove snippet.": "Textbaustein konnte nicht entfernt werden.",
      "Model downloaded.": "Modell wurde heruntergeladen.",
      "Could not download model.":
        "Modell konnte nicht heruntergeladen werden.",
      "Model deleted.": "Modell wurde gelöscht.",
      "Could not delete model.": "Modell konnte nicht gelöscht werden.",
    },
    es: {
      "Skip to content": "Saltar al contenido",
      "Main navigation": "Navegación principal",
      "Version {version}": "Versión {version}",
      "Local panel": "Panel local",
      "Close menu": "Cerrar menú",
      Sections: "Secciones",
      "Use light theme": "Usar tema claro",
      "Use dark theme": "Usar tema oscuro",
      "Recording status is shown in the app.":
        "El estado de la grabación se muestra en la aplicación.",
      "Open menu": "Abrir menú",
      "Interface language": "Idioma de la interfaz",
      "Panel unavailable": "Panel no disponible",
      "Panel connected": "Panel conectado",
      Dashboard: "Panel",
      "Track your dictation space and latest transcriptions.":
        "Consulta tu espacio de dictado y las transcripciones más recientes.",
      Retry: "Reintentar",
      "Your voice, in text.": "Tu voz, en texto.",
      "Use the app shortcut to dictate into any text field.":
        "Usa el atajo de la aplicación para dictar en cualquier campo de texto.",
      "Shortcut not configured": "Atajo no configurado",
      "View settings": "Ver configuración",
      "Usage summary": "Resumen de uso",
      Model: "Modelo",
      "Not set": "Sin configurar",
      Language: "Idioma",
      "Auto-detect": "Detectar automáticamente",
      Portuguese: "Portugués",
      English: "Inglés",
      Spanish: "Español",
      French: "Francés",
      German: "Alemán",
      Italian: "Italiano",
      Japanese: "Japonés",
      Chinese: "Chino",
      Refinement: "Refinamiento",
      Enabled: "Activado",
      Disabled: "Desactivado",
      "Transcription statistics": "Estadísticas de transcripción",
      "Transcriptions today": "Transcripciones de hoy",
      "Items logged today": "Elementos registrados hoy",
      "Words today": "Palabras de hoy",
      "Recognized text": "Texto reconocido",
      "Total transcriptions": "Total de transcripciones",
      "In your history": "En tu historial",
      "Average duration": "Duración media",
      "Per transcription": "Por transcripción",
      "Recent transcriptions": "Transcripciones recientes",
      "Your latest texts are available in history.":
        "Tus últimos textos están disponibles en el historial.",
      "View history": "Ver historial",
      "{count} words": { one: "{count} palabra", other: "{count} palabras" },
      "No transcriptions yet": "Aún no hay transcripciones",
      "Use the configured app shortcut to create your first entry.":
        "Usa el atajo configurado en la aplicación para crear tu primera entrada.",
      Settings: "Configuración",
      "Adjust recognition, shortcuts, and text injection.":
        "Ajusta el reconocimiento, los atajos y la inserción de texto.",
      Saving: "Guardando",
      Saved: "Guardado",
      "Could not save settings.": "No se pudo guardar la configuración.",
      "Changes are saved automatically and persist for the next startup. Restart the app when needed.":
        "Los cambios se guardan automáticamente y se conservan para el próximo inicio. Reinicia la aplicación cuando sea necesario.",
      "Transcription (STT)": "Transcripción (STT)",
      "STT backend": "Motor STT",
      Local: "Local",
      "Whisper model": "Modelo de Whisper",
      "Compute device": "Dispositivo de cálculo",
      Auto: "Automático",
      "Compute type": "Tipo de cálculo",
      "whisper.cpp (AMD / Vulkan)": "whisper.cpp (AMD / Vulkan)",
      "Vulkan (AMD GPU)": "Vulkan (GPU AMD)",
      "Model format": "Formato de modelo",
      "faster-whisper (CPU / CUDA)": "faster-whisper (CPU / CUDA)",
      Audio: "Audio",
      "Silence duration": "Duración del silencio",
      "VAD sensitivity": "Sensibilidad de VAD",
      "Whisper mode": "Modo susurro",
      "Boost gain for quiet environments":
        "Aumentar la ganancia en entornos silenciosos",
      "AI refinement": "Refinamiento con IA",
      "Enable AI refinement": "Activar el refinamiento con IA",
      "Clean text, correct grammar, and format for context":
        "Limpiar el texto, corregir la gramática y dar formato según el contexto",
      "LLM backend": "Motor LLM",
      None: "Ninguno",
      "Local (llama.cpp)": "Local (llama.cpp)",
      "Local (Ollama)": "Local (Ollama)",
      "Installed local model": "Modelo local instalado",
      "Refresh installed Ollama models": "Actualizar los modelos de Ollama instalados",
      "Refreshing…": "Actualizando…",
      "Select an installed model": "Selecciona un modelo instalado",
      "Search installed models": "Buscar modelos instalados",
      "No installed models match your search.":
        "Ningún modelo instalado coincide con tu búsqueda.",
      "Clear selected model": "Borrar el modelo seleccionado",
      "Unavailable model: {model}": "Modelo no disponible: {model}",
      "Ollama runs locally at 127.0.0.1:11434. Your dictation stays on this computer.":
        "Ollama se ejecuta localmente en 127.0.0.1:11434. Tu dictado permanece en este equipo.",
      "Loading installed Ollama models…": "Cargando los modelos de Ollama instalados…",
      "Could not load installed Ollama models.":
        "No se pudieron cargar los modelos de Ollama instalados.",
      "Ollama service is unavailable.": "El servicio de Ollama no está disponible.",
      "No installed Ollama models": "No hay modelos de Ollama instalados",
      "Install a recommended model below, then refresh this list.":
        "Instala un modelo recomendado a continuación y luego actualiza esta lista.",
      Installed: "Instalado",
      "Recommended models": "Modelos recomendados",
      "Larger models need more memory and take longer to download.":
        "Los modelos más grandes necesitan más memoria y tardan más en descargarse.",
      "Balanced multilingual refinement; recommended starting point.":
        "Refinamiento multilingüe equilibrado; punto de partida recomendado.",
      "Smaller download for quick corrections on modest hardware.":
        "Descarga más pequeña para correcciones rápidas en equipos modestos.",
      "Larger multilingual model for more demanding edits.":
        "Modelo multilingüe más grande para ediciones más exigentes.",
      "Multilingual alternative; larger download includes vision components.":
        "Alternativa multilingüe; la descarga más grande incluye componentes de visión.",
      "Download: {size} GB": "Descarga: {size} GB",
      Use: "Usar",
      "Install manually:": "Instalar manualmente:",
      "Dictation status is shown in this dashboard.":
        "El estado del dictado se muestra en este panel.",
      "Dictation unavailable": "Dictado no disponible",
      Recording: "Grabando",
      Processing: "Procesando",
      "Dictation ready": "Dictado listo",
      "e.g. gpt-4o-mini": "p. ej., gpt-4o-mini",
      "Custom prompt": "Instrucción personalizada",
      "Leave empty to use the default":
        "Déjalo vacío para usar el valor predeterminado",
      "Keyboard shortcuts": "Atajos de teclado",
      "Dictation hotkey": "Atajo de dictado",
      "Command hotkey": "Atajo de comandos",
      "Activation mode": "Modo de activación",
      Toggle: "Alternar",
      "Push-to-Talk": "Pulsar para hablar",
      "Text injection": "Inserción de texto",
      Method: "Método",
      "Clipboard only": "Solo portapapeles",
      "Preserve clipboard": "Conservar el portapapeles",
      "Restore previous content after injection":
        "Restaurar el contenido anterior después de la inserción",
      "History and adaptive": "Historial y aprendizaje adaptativo",
      "Retention (days)": "Conservación (días)",
      "Adaptive learning": "Aprendizaje adaptativo",
      "Learn corrections automatically":
        "Aprender correcciones automáticamente",
      "Try saving again": "Intentar guardar de nuevo",
      "Reset settings?": "¿Restablecer la configuración?",
      "All settings will return to their default values.":
        "Toda la configuración volverá a sus valores predeterminados.",
      "Reset to defaults": "Restablecer valores predeterminados",
      "Transcription history": "Historial de transcripciones",
      "Search, copy, or remove previously recognized text.":
        "Busca, copia o elimina texto reconocido anteriormente.",
      "Export JSON": "Exportar JSON",
      "Clear all history?": "¿Borrar todo el historial?",
      "This action cannot be undone.": "Esta acción no se puede deshacer.",
      "Clear all": "Borrar todo",
      "Search transcriptions": "Buscar transcripciones",
      Refresh: "Actualizar",
      "History table": "Tabla de historial",
      Date: "Fecha",
      Text: "Texto",
      Words: "Palabras",
      Duration: "Duración",
      App: "Aplicación",
      Actions: "Acciones",
      "Original: {text}": "Original: {text}",
      "Not provided": "No indicado",
      "Copy transcription": "Copiar transcripción",
      "Delete transcription?": "¿Eliminar transcripción?",
      "Delete transcription": "Eliminar transcripción",
      "No transcriptions found": "No se encontraron transcripciones",
      "Adjust your search or use the app to create a new transcription.":
        "Ajusta tu búsqueda o usa la aplicación para crear una nueva transcripción.",
      "{count} transcriptions": {
        one: "{count} transcripción",
        other: "{count} transcripciones",
      },
      Previous: "Anterior",
      "Page {page}": "Página {page}",
      Next: "Siguiente",
      "Custom dictionary": "Diccionario personalizado",
      "Keep names, brands, and technical terms easier to recognize.":
        "Haz que los nombres, las marcas y los términos técnicos sean más fáciles de reconocer.",
      "Bundled dictionaries": "Diccionarios incluidos",
      "Choose optional term packs. Changes take effect with the next dictation without restarting.":
        "Elige paquetes de términos opcionales. Los cambios se aplican en el próximo dictado sin reiniciar.",
      "Dictionary pack: Coding": "Programación",
      "Dictionary pack: DevOps": "DevOps",
      "Dictionary pack: AI": "IA",
      "Dictionary pack: Email": "Correo electrónico",
      "Dictionary pack: German business": "Negocios en alemán",
      "Dictionary pack description: Coding":
        "Lenguajes de programación, herramientas y frameworks.",
      "Dictionary pack description: DevOps":
        "Términos de infraestructura, entrega y operaciones.",
      "Dictionary pack description: AI":
        "Modelos de IA, plataformas y términos de aprendizaje automático.",
      "Dictionary pack description: Email":
        "Protocolos de correo, direcciones y términos comunes de mensajes.",
      "Dictionary pack description: German business":
        "Términos alemanes de negocios y oficina.",
      "{terms} terms, {aliases} aliases":
        "{terms} términos, {aliases} variantes",
      "Enable {pack}": "Activar {pack}",
      "Inspect terms and recognized variants":
        "Inspeccionar términos y variantes reconocidas",
      "Recognition hint only": "Solo sugerencia de reconocimiento",
      Sources: "Fuentes",
      "Recognized variants (one per line)":
        "Variantes reconocidas (una por línea)",
      "Personal words and their variants are kept when packs change and take priority over pack variants. Save the same word again to update it.":
        "Las palabras personales y sus variantes se conservan al cambiar paquetes y tienen prioridad sobre las variantes del paquete. Guarda la misma palabra otra vez para actualizarla.",
      "Recognized variants": "Variantes reconocidas",
      "No recognized variants": "No hay variantes reconocidas",
      "Add word": "Añadir palabra",
      "Add a term for future use.":
        "Añade un término para usarlo en el futuro.",
      "Word or term": "Palabra o término",
      "Please fill out this field.": "Completa este campo.",
      Category: "Categoría",
      General: "General",
      "Personal names": "Nombres personales",
      Technical: "Técnico",
      Brand: "Marca",
      "Adding…": "Añadiendo…",
      Add: "Añadir",
      "{count} items": { one: "{count} elemento", other: "{count} elementos" },
      Word: "Palabra",
      Source: "Origen",
      Frequency: "Frecuencia",
      Manual: "Manual",
      Learned: "Aprendido",
      Automatic: "Automático",
      "Delete word?": "¿Eliminar palabra?",
      "The word will be removed from the dictionary.":
        "La palabra se eliminará del diccionario.",
      "Delete word": "Eliminar palabra",
      "No words in the dictionary": "No hay palabras en el diccionario",
      "Add a name, brand, or technical term to get started.":
        "Añade un nombre, una marca o un término técnico para empezar.",
      "Learned corrections": "Correcciones aprendidas",
      Heard: "Escuchado",
      Corrected: "Corregido",
      Times: "Veces",
      "Last seen": "Visto por última vez",
      "Delete correction?": "¿Eliminar corrección?",
      "The learned correction will be removed.":
        "La corrección aprendida se eliminará.",
      "Delete correction": "Eliminar corrección",
      "No learned corrections": "No hay correcciones aprendidas",
      "Automatic corrections will appear here.":
        "Las correcciones automáticas aparecerán aquí.",
      "Voice shortcuts": "Atajos de voz",
      "Use trigger phrases to insert recurring responses and text.":
        "Usa frases de activación para insertar respuestas y texto recurrentes.",
      "Add snippet": "Añadir fragmento",
      "Define the spoken phrase and inserted text.":
        "Define la frase hablada y el texto insertado.",
      "Trigger phrase": "Frase de activación",
      "e.g. my email": "p. ej., mi correo",
      Expansion: "Expansión",
      "e.g. hello@example.com": "p. ej., hola@ejemplo.com",
      "Configured snippets": "Fragmentos configurados",
      Trigger: "Activador",
      "Delete snippet?": "¿Eliminar fragmento?",
      "The voice shortcut will be removed.": "El atajo de voz se eliminará.",
      "Delete snippet": "Eliminar fragmento",
      "No snippets configured": "No hay fragmentos configurados",
      "Create a shortcut to insert text you use often.":
        "Crea un atajo para insertar texto que usas a menudo.",
      "Whisper models": "Modelos de Whisper",
      "Download and manage models available for local transcription.":
        "Descarga y administra modelos disponibles para la transcripción local.",
      "GGML models are stored separately. Vulkan acceleration requires the AMD runtime and a Vulkan-capable driver.":
        "Los modelos GGML se almacenan por separado. La aceleración Vulkan requiere el entorno de ejecución AMD y un controlador compatible con Vulkan.",
      "Total usage: {size} MB": "Uso total: {size} MB",
      "~{size} MB": "~{size} MB",
      Active: "Activo",
      Downloaded: "Descargado",
      "Not downloaded": "No descargado",
      "Downloading…": "Descargando…",
      Download: "Descargar",
      "Delete model?": "¿Eliminar modelo?",
      "The model will be removed from this computer.":
        "El modelo se eliminará de este equipo.",
      "Deleting…": "Eliminando…",
      Delete: "Eliminar",
      "No models available": "No hay modelos disponibles",
      "Refresh the list to check the models offered by the app.":
        "Actualiza la lista para consultar los modelos que ofrece la aplicación.",
      "Refresh models": "Actualizar modelos",
      Cancel: "Cancelar",
      Confirm: "Confirmar",
      History: "Historial",
      Dictionary: "Diccionario",
      Snippets: "Fragmentos",
      Models: "Modelos",
      "Could not complete the action.": "No se pudo completar la acción.",
      "Text copied to clipboard.": "Texto copiado al portapapeles.",
      "Could not copy text.": "No se pudo copiar el texto.",
      "Could not check the dashboard connection.":
        "No se pudo comprobar la conexión con el panel.",
      "Could not load statistics.": "No se pudieron cargar las estadísticas.",
      "Could not load settings.": "No se pudo cargar la configuración.",
      "Could not load history.": "No se pudo cargar el historial.",
      "Could not load recent transcriptions.":
        "No se pudieron cargar las transcripciones recientes.",
      "Could not load dictionary.": "No se pudo cargar el diccionario.",
      "Could not load snippets.": "No se pudieron cargar los fragmentos.",
      "Could not load models.": "No se pudieron cargar los modelos.",
      "Could not load disk usage.": "No se pudo cargar el uso de disco.",
      "Settings restored to defaults.":
        "La configuración se restauró a los valores predeterminados.",
      "Could not restore settings.": "No se pudo restaurar la configuración.",
      "Transcription deleted.": "Transcripción eliminada.",
      "Could not delete transcription.":
        "No se pudo eliminar la transcripción.",
      "History cleared.": "Historial borrado.",
      "Could not clear history.": "No se pudo borrar el historial.",
      "Word added to dictionary.": "Palabra añadida al diccionario.",
      "Dictionary entry saved.": "Entrada del diccionario guardada.",
      "Could not update dictionary pack.":
        "No se pudo actualizar el paquete de diccionario.",
      "Could not add word.": "No se pudo añadir la palabra.",
      "Word removed from dictionary.": "Palabra eliminada del diccionario.",
      "Could not remove word.": "No se pudo eliminar la palabra.",
      "Correction removed from dictionary.":
        "Corrección eliminada del diccionario.",
      "Could not remove correction.": "No se pudo eliminar la corrección.",
      "Snippet added.": "Fragmento añadido.",
      "Could not add snippet.": "No se pudo añadir el fragmento.",
      "Snippet removed.": "Fragmento eliminado.",
      "Could not remove snippet.": "No se pudo eliminar el fragmento.",
      "Model downloaded.": "Modelo descargado.",
      "Could not download model.": "No se pudo descargar el modelo.",
      "Model deleted.": "Modelo eliminado.",
      "Could not delete model.": "No se pudo eliminar el modelo.",
    },
    pt: {
      "Skip to content": "Pular para o conteúdo",
      "Main navigation": "Navegação principal",
      "Version {version}": "Versão {version}",
      "Local panel": "Painel local",
      "Close menu": "Fechar menu",
      Sections: "Seções",
      "Use light theme": "Usar tema claro",
      "Use dark theme": "Usar tema escuro",
      "Recording status is shown in the app.":
        "O status da gravação é exibido no aplicativo.",
      "Open menu": "Abrir menu",
      "Interface language": "Idioma da interface",
      "Panel unavailable": "Painel indisponível",
      "Panel connected": "Painel conectado",
      Dashboard: "Painel",
      "Track your dictation space and latest transcriptions.":
        "Acompanhe seu espaço de ditado e as transcrições mais recentes.",
      Retry: "Tentar novamente",
      "Your voice, in text.": "Sua voz, em texto.",
      "Use the app shortcut to dictate into any text field.":
        "Use o atalho do aplicativo para ditar em qualquer campo de texto.",
      "Shortcut not configured": "Atalho não configurado",
      "View settings": "Ver configurações",
      "Usage summary": "Resumo de uso",
      Model: "Modelo",
      "Not set": "Não definido",
      Language: "Idioma",
      "Auto-detect": "Detectar automaticamente",
      Portuguese: "Português",
      English: "Inglês",
      Spanish: "Espanhol",
      French: "Francês",
      German: "Alemão",
      Italian: "Italiano",
      Japanese: "Japonês",
      Chinese: "Chinês",
      Refinement: "Refinamento",
      Enabled: "Ativado",
      Disabled: "Desativado",
      "Transcription statistics": "Estatísticas de transcrição",
      "Transcriptions today": "Transcrições hoje",
      "Items logged today": "Itens registrados hoje",
      "Words today": "Palavras hoje",
      "Recognized text": "Texto reconhecido",
      "Total transcriptions": "Total de transcrições",
      "In your history": "No seu histórico",
      "Average duration": "Duração média",
      "Per transcription": "Por transcrição",
      "Recent transcriptions": "Transcrições recentes",
      "Your latest texts are available in history.":
        "Seus últimos textos ficam disponíveis no histórico.",
      "View history": "Ver histórico",
      "{count} words": { one: "{count} palavra", other: "{count} palavras" },
      "No transcriptions yet": "Ainda não há transcrições",
      "Use the configured app shortcut to create your first entry.":
        "Use o atalho configurado no aplicativo para criar seu primeiro registro.",
      Settings: "Configurações",
      "Adjust recognition, shortcuts, and text injection.":
        "Ajuste o reconhecimento, os atalhos e a injeção de texto.",
      Saving: "Salvando",
      Saved: "Salvo",
      "Could not save settings.": "Não foi possível salvar as configurações.",
      "Changes are saved automatically and persist for the next startup. Restart the app when needed.":
        "As alterações são salvas automaticamente e persistem para a próxima inicialização. Reinicie o aplicativo quando necessário.",
      "Transcription (STT)": "Transcrição (STT)",
      "STT backend": "Backend STT",
      Local: "Local",
      "Whisper model": "Modelo Whisper",
      "Compute device": "Dispositivo de computação",
      Auto: "Automático",
      "Compute type": "Tipo de computação",
      "whisper.cpp (AMD / Vulkan)": "whisper.cpp (AMD / Vulkan)",
      "Vulkan (AMD GPU)": "Vulkan (GPU AMD)",
      "Model format": "Formato do modelo",
      "faster-whisper (CPU / CUDA)": "faster-whisper (CPU / CUDA)",
      Audio: "Áudio",
      "Silence duration": "Duração do silêncio",
      "VAD sensitivity": "Sensibilidade VAD",
      "Whisper mode": "Modo sussurro",
      "Boost gain for quiet environments":
        "Aumentar ganho para ambientes silenciosos",
      "AI refinement": "Refinamento com IA",
      "Enable AI refinement": "Ativar refinamento com IA",
      "Clean text, correct grammar, and format for context":
        "Limpar texto, corrigir gramática e formatar por contexto",
      "LLM backend": "Backend LLM",
      None: "Nenhum",
      "Local (llama.cpp)": "Local (llama.cpp)",
      "Local (Ollama)": "Local (Ollama)",
      "Installed local model": "Modelo local instalado",
      "Refresh installed Ollama models": "Atualizar modelos Ollama instalados",
      "Refreshing…": "Atualizando…",
      "Select an installed model": "Selecione um modelo instalado",
      "Search installed models": "Pesquisar modelos instalados",
      "No installed models match your search.":
        "Nenhum modelo instalado corresponde à sua pesquisa.",
      "Clear selected model": "Limpar modelo selecionado",
      "Unavailable model: {model}": "Modelo indisponível: {model}",
      "Ollama runs locally at 127.0.0.1:11434. Your dictation stays on this computer.":
        "O Ollama é executado localmente em 127.0.0.1:11434. Seu ditado permanece neste computador.",
      "Loading installed Ollama models…": "Carregando modelos Ollama instalados…",
      "Could not load installed Ollama models.":
        "Não foi possível carregar os modelos Ollama instalados.",
      "Ollama service is unavailable.": "O serviço Ollama não está disponível.",
      "No installed Ollama models": "Nenhum modelo Ollama instalado",
      "Install a recommended model below, then refresh this list.":
        "Instale um modelo recomendado abaixo e atualize esta lista.",
      Installed: "Instalado",
      "Recommended models": "Modelos recomendados",
      "Larger models need more memory and take longer to download.":
        "Modelos maiores precisam de mais memória e demoram mais para baixar.",
      "Balanced multilingual refinement; recommended starting point.":
        "Refinamento multilíngue equilibrado; ponto de partida recomendado.",
      "Smaller download for quick corrections on modest hardware.":
        "Download menor para correções rápidas em hardware modesto.",
      "Larger multilingual model for more demanding edits.":
        "Modelo multilíngue maior para edições mais exigentes.",
      "Multilingual alternative; larger download includes vision components.":
        "Alternativa multilíngue; o download maior inclui componentes de visão.",
      "Download: {size} GB": "Download: {size} GB",
      Use: "Usar",
      "Install manually:": "Instalar manualmente:",
      "Dictation status is shown in this dashboard.":
        "O status do ditado é mostrado neste painel.",
      "Dictation unavailable": "Ditado indisponível",
      Recording: "Gravando",
      Processing: "Processando",
      "Dictation ready": "Ditado pronto",
      "e.g. gpt-4o-mini": "ex.: gpt-4o-mini",
      "Custom prompt": "Prompt personalizado",
      "Leave empty to use the default": "Deixe vazio para usar o padrão",
      "Keyboard shortcuts": "Atalhos de teclado",
      "Dictation hotkey": "Atalho de ditado",
      "Command hotkey": "Atalho de comando",
      "Activation mode": "Modo de ativação",
      Toggle: "Alternar",
      "Push-to-Talk": "Pressionar para falar",
      "Text injection": "Injeção de texto",
      Method: "Método",
      "Clipboard only": "Somente área de transferência",
      "Preserve clipboard": "Preservar área de transferência",
      "Restore previous content after injection":
        "Restaurar o conteúdo anterior após a injeção",
      "History and adaptive": "Histórico e adaptativo",
      "Retention (days)": "Retenção (dias)",
      "Adaptive learning": "Aprendizado adaptativo",
      "Learn corrections automatically": "Aprender correções automaticamente",
      "Try saving again": "Tentar salvar novamente",
      "Reset settings?": "Redefinir configurações?",
      "All settings will return to their default values.":
        "Todas as configurações voltarão aos valores padrão.",
      "Reset to defaults": "Restaurar padrões",
      "Transcription history": "Histórico de transcrições",
      "Search, copy, or remove previously recognized text.":
        "Pesquise, copie ou remova textos reconhecidos anteriormente.",
      "Export JSON": "Exportar JSON",
      "Clear all history?": "Limpar todo o histórico?",
      "This action cannot be undone.": "Esta ação não pode ser desfeita.",
      "Clear all": "Limpar tudo",
      "Search transcriptions": "Buscar transcrições",
      Refresh: "Atualizar",
      "History table": "Tabela de histórico",
      Date: "Data",
      Text: "Texto",
      Words: "Palavras",
      Duration: "Duração",
      App: "Aplicativo",
      Actions: "Ações",
      "Original: {text}": "Original: {text}",
      "Not provided": "Não informado",
      "Copy transcription": "Copiar transcrição",
      "Delete transcription?": "Excluir transcrição?",
      "Delete transcription": "Excluir transcrição",
      "No transcriptions found": "Nenhuma transcrição encontrada",
      "Adjust your search or use the app to create a new transcription.":
        "Ajuste a busca ou use o aplicativo para criar uma nova transcrição.",
      "{count} transcriptions": {
        one: "{count} transcrição",
        other: "{count} transcrições",
      },
      Previous: "Anterior",
      "Page {page}": "Página {page}",
      Next: "Próxima",
      "Custom dictionary": "Dicionário personalizado",
      "Keep names, brands, and technical terms easier to recognize.":
        "Mantenha nomes, marcas e termos técnicos mais fáceis de reconhecer.",
      "Bundled dictionaries": "Dicionários incluídos",
      "Choose optional term packs. Changes take effect with the next dictation without restarting.":
        "Escolha pacotes opcionais de termos. As alterações entram em vigor no próximo ditado sem reiniciar.",
      "Dictionary pack: Coding": "Programação",
      "Dictionary pack: DevOps": "DevOps",
      "Dictionary pack: AI": "IA",
      "Dictionary pack: Email": "E-mail",
      "Dictionary pack: German business": "Negócios em alemão",
      "Dictionary pack description: Coding":
        "Linguagens de programação, ferramentas e frameworks.",
      "Dictionary pack description: DevOps":
        "Termos de infraestrutura, entrega e operações.",
      "Dictionary pack description: AI":
        "Modelos de IA, plataformas e termos de aprendizado de máquina.",
      "Dictionary pack description: Email":
        "Protocolos de e-mail, endereços e termos comuns de mensagens.",
      "Dictionary pack description: German business":
        "Termos alemães de negócios e escritório.",
      "{terms} terms, {aliases} aliases":
        "{terms} termos, {aliases} variantes",
      "Enable {pack}": "Ativar {pack}",
      "Inspect terms and recognized variants":
        "Inspecionar termos e variantes reconhecidas",
      "Recognition hint only": "Apenas dica de reconhecimento",
      Sources: "Fontes",
      "Recognized variants (one per line)":
        "Variantes reconhecidas (uma por linha)",
      "Personal words and their variants are kept when packs change and take priority over pack variants. Save the same word again to update it.":
        "As palavras pessoais e suas variantes são mantidas quando os pacotes mudam e têm prioridade sobre as variantes do pacote. Salve a mesma palavra novamente para atualizá-la.",
      "Recognized variants": "Variantes reconhecidas",
      "No recognized variants": "Nenhuma variante reconhecida",
      "Add word": "Adicionar palavra",
      "Add a term for future use.": "Inclua um termo para uso futuro.",
      "Word or term": "Palavra ou termo",
      "Please fill out this field.": "Preencha este campo.",
      Category: "Categoria",
      General: "Geral",
      "Personal names": "Nomes pessoais",
      Technical: "Técnico",
      Brand: "Marca",
      "Adding…": "Adicionando…",
      Add: "Adicionar",
      "{count} items": { one: "{count} item", other: "{count} itens" },
      Word: "Palavra",
      Source: "Fonte",
      Frequency: "Frequência",
      Manual: "Manual",
      Learned: "Aprendida",
      Automatic: "Automática",
      "Delete word?": "Excluir palavra?",
      "The word will be removed from the dictionary.":
        "A palavra será removida do dicionário.",
      "Delete word": "Excluir palavra",
      "No words in the dictionary": "Nenhuma palavra no dicionário",
      "Add a name, brand, or technical term to get started.":
        "Adicione um nome, marca ou termo técnico para começar.",
      "Learned corrections": "Correções aprendidas",
      Heard: "Ouvido",
      Corrected: "Corrigido",
      Times: "Vezes",
      "Last seen": "Última vez",
      "Delete correction?": "Excluir correção?",
      "The learned correction will be removed.":
        "A correção aprendida será removida.",
      "Delete correction": "Excluir correção",
      "No learned corrections": "Nenhuma correção aprendida",
      "Automatic corrections will appear here.":
        "As correções automáticas aparecerão aqui.",
      "Voice shortcuts": "Atalhos de voz",
      "Use trigger phrases to insert recurring responses and text.":
        "Use frases de gatilho para inserir respostas e textos recorrentes.",
      "Add snippet": "Adicionar snippet",
      "Define the spoken phrase and inserted text.":
        "Defina a frase falada e o texto inserido.",
      "Trigger phrase": "Frase de gatilho",
      "e.g. my email": "ex.: meu e-mail",
      Expansion: "Expansão",
      "e.g. hello@example.com": "ex.: ola@exemplo.com",
      "Configured snippets": "Snippets configurados",
      Trigger: "Gatilho",
      "Delete snippet?": "Excluir snippet?",
      "The voice shortcut will be removed.": "O atalho de voz será removido.",
      "Delete snippet": "Excluir snippet",
      "No snippets configured": "Nenhum snippet configurado",
      "Create a shortcut to insert text you use often.":
        "Crie um atalho para inserir um texto que você usa com frequência.",
      "Whisper models": "Modelos Whisper",
      "Download and manage models available for local transcription.":
        "Baixe e gerencie os modelos disponíveis para transcrição local.",
      "GGML models are stored separately. Vulkan acceleration requires the AMD runtime and a Vulkan-capable driver.":
        "Os modelos GGML são armazenados separadamente. A aceleração Vulkan requer o ambiente de execução AMD e um driver compatível com Vulkan.",
      "Total usage: {size} MB": "Uso total: {size} MB",
      "~{size} MB": "~{size} MB",
      Active: "Ativo",
      Downloaded: "Baixado",
      "Not downloaded": "Não baixado",
      "Downloading…": "Baixando…",
      Download: "Baixar",
      "Delete model?": "Excluir modelo?",
      "The model will be removed from this computer.":
        "O modelo será removido deste computador.",
      "Deleting…": "Excluindo…",
      Delete: "Excluir",
      "No models available": "Nenhum modelo disponível",
      "Refresh the list to check the models offered by the app.":
        "Atualize a lista para consultar os modelos oferecidos pelo aplicativo.",
      "Refresh models": "Atualizar modelos",
      Cancel: "Cancelar",
      Confirm: "Confirmar",
      History: "Histórico",
      Dictionary: "Dicionário",
      Snippets: "Snippets",
      Models: "Modelos",
      "Could not complete the action.": "Não foi possível concluir a ação.",
      "Text copied to clipboard.":
        "Texto copiado para a área de transferência.",
      "Could not copy text.": "Não foi possível copiar o texto.",
      "Could not check the dashboard connection.":
        "Não foi possível verificar a conexão com o painel.",
      "Could not load statistics.":
        "Não foi possível carregar as estatísticas.",
      "Could not load settings.": "Não foi possível carregar as configurações.",
      "Could not load history.": "Não foi possível carregar o histórico.",
      "Could not load recent transcriptions.":
        "Não foi possível carregar as transcrições recentes.",
      "Could not load dictionary.": "Não foi possível carregar o dicionário.",
      "Could not load snippets.": "Não foi possível carregar os snippets.",
      "Could not load models.": "Não foi possível carregar os modelos.",
      "Could not load disk usage.": "Não foi possível carregar o uso de disco.",
      "Settings restored to defaults.":
        "Configurações restauradas para os valores padrão.",
      "Could not restore settings.":
        "Não foi possível restaurar as configurações.",
      "Transcription deleted.": "Transcrição excluída.",
      "Could not delete transcription.":
        "Não foi possível excluir a transcrição.",
      "History cleared.": "Histórico limpo.",
      "Could not clear history.": "Não foi possível limpar o histórico.",
      "Word added to dictionary.": "Palavra adicionada ao dicionário.",
      "Dictionary entry saved.": "Entrada do dicionário salva.",
      "Could not update dictionary pack.":
        "Não foi possível atualizar o pacote de dicionário.",
      "Could not add word.": "Não foi possível adicionar a palavra.",
      "Word removed from dictionary.": "Palavra removida do dicionário.",
      "Could not remove word.": "Não foi possível remover a palavra.",
      "Correction removed from dictionary.": "Correção removida do dicionário.",
      "Could not remove correction.": "Não foi possível remover a correção.",
      "Snippet added.": "Snippet adicionado.",
      "Could not add snippet.": "Não foi possível adicionar o snippet.",
      "Snippet removed.": "Snippet removido.",
      "Could not remove snippet.": "Não foi possível remover o snippet.",
      "Model downloaded.": "Modelo baixado.",
      "Could not download model.": "Não foi possível baixar o modelo.",
      "Model deleted.": "Modelo excluído.",
      "Could not delete model.": "Não foi possível excluir o modelo.",
    },
  };

  function normalizeLanguage(value) {
    return typeof value === "string" && Object.hasOwn(languageTags, value)
      ? value
      : "en";
  }

  function localeTag(code) {
    return languageTags[normalizeLanguage(code)];
  }

  function formatNumber(code, value, options) {
    const number = Number(value);
    return new Intl.NumberFormat(localeTag(code), options || {}).format(
      Number.isFinite(number) ? number : 0,
    );
  }

  function formatDate(code, timestamp) {
    if (!timestamp) return "";
    const date = new Date(timestamp);
    if (Number.isNaN(date.getTime())) return "";
    return new Intl.DateTimeFormat(localeTag(code), {
      dateStyle: "short",
      timeStyle: "short",
    }).format(date);
  }

  function formatDuration(code, value) {
    return formatNumber(code, value, { maximumFractionDigits: 1 }) + " s";
  }

  function interpolate(message, params, code, isPlural) {
    return message.replace(/\{([A-Za-z0-9_]+)\}/g, (placeholder, name) => {
      if (!Object.hasOwn(params, name)) return placeholder;
      if (name === "count" && isPlural) {
        return formatNumber(code, params[name]);
      }
      return String(params[name]);
    });
  }

  function translate(code, key, params) {
    if (key === null || key === undefined || key === "") return "";
    const sourceKey = String(key);
    const values = params && typeof params === "object" ? params : {};
    const language = normalizeLanguage(code);
    const translation =
      catalogs[language][sourceKey] ?? catalogs.en[sourceKey] ?? sourceKey;

    if (translation && typeof translation === "object") {
      const count = Number(values.count);
      const form = new Intl.PluralRules(localeTag(language)).select(
        Number.isFinite(count) ? count : 0,
      );
      const message =
        translation[form] ?? translation.other ?? translation.one ?? sourceKey;
      return interpolate(message, values, language, true);
    }

    return interpolate(String(translation), values, language, false);
  }

  const api = {
    languages,
    catalogs,
    normalizeLanguage,
    localeTag,
    translate,
    formatNumber,
    formatDate,
    formatDuration,
  };

  global.WhisprI18n = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
