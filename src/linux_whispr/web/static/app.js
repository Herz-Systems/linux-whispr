const OLLAMA_RECOMMENDATION_TAGS = new Set([
  "qwen3:8b",
  "qwen3.5:4b",
  "qwen3:14b",
  "gemma3:12b",
]);

function app() {
  const i18n =
    (typeof window !== "undefined" && window.WhisprI18n) ||
    globalThis.WhisprI18n;
  const storedUiLanguage = (() => {
    if (typeof window === "undefined") return null;
    try {
      return window.localStorage.getItem("uiLanguage");
    } catch (_) {
      return null;
    }
  })();
  const uiLanguage = i18n.normalizeLanguage(storedUiLanguage);
  const storedTheme = (() => {
    try {
      return localStorage.getItem("darkMode");
    } catch (_) {
      return null;
    }
  })();
  const systemPrefersDark =
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches;

  return {
    uiLanguage,
    languages: i18n.languages,
    darkMode: storedTheme === null ? systemPrefersDark : storedTheme === "true",
    currentPage: "dashboard",
    mobileNavOpen: false,
    toast: { show: false, message: "", type: "success", params: {} },
    confirmation: { title: "", message: "", params: {} },
    navItems: [
      { id: "dashboard", label: "Dashboard", icon: "layout-dashboard" },
      { id: "config", label: "Settings", icon: "settings" },
      { id: "history", label: "History", icon: "history" },
      { id: "dictionary", label: "Dictionary", icon: "book" },
      { id: "snippets", label: "Snippets", icon: "bolt" },
      { id: "models", label: "Models", icon: "database" },
    ],

    status: { version: "", status: "loading", app_name: "LinuxWhispr" },
    stats: {},
    config: {
      audio: {},
      stt: {},
      ai: {},
      hotkey: {},
      injection: {},
      history: {},
      adaptive: {},
    },
    configOpen: {
      stt: false,
      audio: false,
      ai: false,
      hotkey: false,
      injection: false,
      historyConf: false,
    },
    historyEntries: [],
    historySearch: "",
    historyPage: 1,
    historyLimit: 20,
    historyTotal: 0,
    historyHasMore: false,
    recentHistory: [],
    dictionary: { entries: [], corrections: [], packs: [] },
    snippets: [],
    models: [],
    modelBackend: "faster-whisper",
    diskUsage: { bytes: 0, mb: 0, gb: 0 },
    ollamaCatalog: {
      available: false,
      models: [],
      recommended: [],
      error: null,
      warnings: [],
    },
    ollamaModelPickerOpen: false,
    ollamaModelQuery: "",
    ollamaModelActiveIndex: 0,
    newWord: "",
    newWordCategory: "general",
    newWordAliases: "",
    newSnippetTrigger: "",
    newSnippetExpansion: "",

    loading: {
      status: false,
      stats: false,
      config: false,
      history: false,
      recentHistory: false,
      dictionary: false,
      snippets: false,
      models: false,
      ollama: false,
      diskUsage: false,
    },
    errors: {
      status: "",
      stats: "",
      config: "",
      history: "",
      recentHistory: "",
      dictionary: "",
      snippets: "",
      models: "",
      ollama: "",
      diskUsage: "",
    },
    busy: { config: false, word: false, snippet: false, historyClear: false },
    dictionaryPackBusy: {},
    dictionaryPackErrors: {},
    saveState: "",

    _toastTimer: null,
    _historyRequestId: 0,
    _modelRequestId: 0,
    _ollamaRequestId: 0,
    _ollamaContextId: 0,
    _aiModelSelectionByBackend: {},
    _activeAiBackend: null,
    _modelOperations: {},
    _confirmationAction: null,
    _confirmationTrigger: null,
    _savingConfig: false,
    _queuedConfig: null,
    _configSavePromise: null,
    _dialogListenerAttached: false,

    async init() {
      this.attachConfirmationDialogListener();
      await Promise.all([
        this.loadStatus(),
        this.loadStats(),
        this.loadConfig(),
        this.loadHistory(),
        this.loadRecentHistory(),
        this.loadDictionary(),
        this.loadSnippets(),
        this.loadModels(),
        this.loadDiskUsage(),
      ]);
    },

    attachConfirmationDialogListener() {
      if (this._dialogListenerAttached) return;
      this.$nextTick(() => {
        const dialog = document.getElementById("confirmation-dialog");
        if (!dialog || this._dialogListenerAttached) return;
        dialog.addEventListener("cancel", (event) => {
          event.preventDefault();
          this.cancelConfirmation();
        });
        this._dialogListenerAttached = true;
      });
    },

    navigate(id) {
      this.currentPage = id;
      this.mobileNavOpen = false;
      this.$nextTick(() => {
        const heading = document.getElementById("page-heading");
        if (heading) heading.focus();
      });
    },

    toggleTheme() {
      this.darkMode = !this.darkMode;
      try {
        localStorage.setItem("darkMode", String(this.darkMode));
      } catch (_) {
        // A private browsing context can deny persistent storage.
      }
    },

    get localeTag() {
      return i18n.localeTag(this.uiLanguage);
    },

    t(key, params = {}) {
      return i18n.translate(this.uiLanguage, key, params);
    },

    setLanguage(code) {
      const uiLanguage = i18n.normalizeLanguage(code);
      this.uiLanguage = uiLanguage;
      if (typeof window === "undefined") return;
      try {
        window.localStorage.setItem("uiLanguage", uiLanguage);
      } catch (_) {
        // A private browsing context can deny persistent storage.
      }
    },

    showToast(key, type = "success", params = {}) {
      this.toast = { show: true, message: key, type, params };
      clearTimeout(this._toastTimer);
      this._toastTimer = setTimeout(() => {
        this.toast.show = false;
      }, 3000);
    },

    requestConfirmation(titleKey, messageKey, action, params = {}) {
      this._confirmationTrigger =
        document.activeElement instanceof HTMLElement
          ? document.activeElement
          : null;
      this.confirmation = { title: titleKey, message: messageKey, params };
      this._confirmationAction = action;
      this.$nextTick(() => {
        const dialog = document.getElementById("confirmation-dialog");
        if (!dialog) return;
        if (!dialog.open) dialog.showModal();
        const cancelButton = dialog.querySelector(
          ".dialog-actions .button-secondary",
        );
        if (cancelButton instanceof HTMLElement) cancelButton.focus();
      });
    },

    async confirmAction() {
      const action = this._confirmationAction;
      this._confirmationAction = null;
      try {
        if (typeof action === "function") await action();
      } catch (_) {
        this.showToast("Could not complete the action.", "error");
      } finally {
        this.closeConfirmationDialog();
      }
    },

    cancelConfirmation() {
      this._confirmationAction = null;
      this.closeConfirmationDialog();
    },

    closeConfirmationDialog() {
      const dialog = document.getElementById("confirmation-dialog");
      if (dialog && dialog.open) dialog.close();
      const trigger = this._confirmationTrigger;
      this._confirmationTrigger = null;
      this.$nextTick(() => {
        if (trigger && document.contains(trigger)) trigger.focus();
      });
    },

    formatDate(timestamp) {
      return i18n.formatDate(this.uiLanguage, timestamp);
    },

    formatNumber(value, options = {}) {
      return i18n.formatNumber(this.uiLanguage, value, options);
    },

    formatDuration(value) {
      return i18n.formatDuration(this.uiLanguage, value);
    },

    async copyToClipboard(text) {
      try {
        if (
          !navigator.clipboard ||
          typeof navigator.clipboard.writeText !== "function"
        ) {
          throw new Error("clipboard-unavailable");
        }
        await navigator.clipboard.writeText(text);
        this.showToast("Text copied to clipboard.");
      } catch (_) {
        this.showToast("Could not copy text.", "error");
      }
    },

    async api(url, options = {}) {
      let response;
      try {
        response = await fetch(url, {
          headers: {
            "Content-Type": "application/json",
            ...(options.headers || {}),
          },
          ...options,
        });
      } catch (_) {
        throw new Error("connection");
      }

      let data = null;
      try {
        const body = await response.text();
        data = body ? JSON.parse(body) : null;
      } catch (_) {
        throw new Error("invalid-response");
      }

      if (!response.ok) throw new Error("request-failed");
      if (data && data.status === "error") throw new Error("request-failed");
      return data;
    },

    assertSuccessful(data) {
      if (!data || data.status !== "ok") throw new Error("request-failed");
      return data;
    },

    async loadResource(key, request, apply, errorMessage) {
      this.loading[key] = true;
      this.errors[key] = "";
      try {
        const data = await request();
        apply(data);
        return data;
      } catch (_) {
        this.errors[key] = errorMessage;
        return null;
      } finally {
        this.loading[key] = false;
      }
    },

    async loadStatus() {
      return this.loadResource(
        "status",
        () => this.api("/api/status"),
        (data) => {
          this.status = data;
        },
        "Could not check the dashboard connection.",
      );
    },

    async loadStats() {
      return this.loadResource(
        "stats",
        () => this.api("/api/history/stats"),
        (data) => {
          this.stats = data;
        },
        "Could not load statistics.",
      );
    },

    async loadConfig() {
      return this.loadResource(
        "config",
        () => this.api("/api/config"),
        (data) => {
          this.config = data;
          const normalized = this.normalizeSttBackendConfig();
          this.rememberCurrentAiModel();
          this.selectModelBackend(this.modelBackendForConfig());
          if (this.isOllamaBackend()) this.loadOllamaModels();
          if (normalized) this.saveConfig();
        },
        "Could not load settings.",
      );
    },

    async loadHistory() {
      const requestId = ++this._historyRequestId;
      const page = this.historyPage;
      const query = this.historySearch.trim();
      const search = query ? `&q=${encodeURIComponent(query)}` : "";
      this.loading.history = true;
      this.errors.history = "";
      try {
        const data = await this.api(
          `/api/history?page=${page}&limit=${this.historyLimit}${search}`,
        );
        if (requestId !== this._historyRequestId) return null;
        this.historyEntries = Array.isArray(data.entries) ? data.entries : [];
        this.historyTotal = Number(data.total) || 0;
        this.historyHasMore = Boolean(data.has_more);
        return data;
      } catch (_) {
        if (requestId === this._historyRequestId) {
          this.errors.history = "Could not load history.";
        }
        return null;
      } finally {
        if (requestId === this._historyRequestId) this.loading.history = false;
      }
    },

    searchHistory() {
      this.historyPage = 1;
      return this.loadHistory();
    },

    async loadRecentHistory() {
      return this.loadResource(
        "recentHistory",
        () => this.api("/api/history?page=1&limit=5"),
        (data) => {
          this.recentHistory = Array.isArray(data.entries) ? data.entries : [];
        },
        "Could not load recent transcriptions.",
      );
    },

    async loadDictionary() {
      return this.loadResource(
        "dictionary",
        () => this.api("/api/dictionary"),
        (data) => {
          this.dictionary = data;
        },
        "Could not load dictionary.",
      );
    },

    dictionaryPacks() {
      return Array.isArray(this.dictionary?.packs) ? this.dictionary.packs : [];
    },

    dictionaryPackName(pack) {
      const names = {
        coding: "Dictionary pack: Coding",
        devops: "Dictionary pack: DevOps",
        ai: "Dictionary pack: AI",
        email: "Dictionary pack: Email",
        "de-business": "Dictionary pack: German business",
      };
      return names[pack?.id]
        ? this.t(names[pack.id])
        : String(pack?.name || pack?.id || "");
    },

    dictionaryPackDescription(pack) {
      const descriptions = {
        coding: "Dictionary pack description: Coding",
        devops: "Dictionary pack description: DevOps",
        ai: "Dictionary pack description: AI",
        email: "Dictionary pack description: Email",
        "de-business": "Dictionary pack description: German business",
      };
      return descriptions[pack?.id]
        ? this.t(descriptions[pack.id])
        : String(pack?.description || "");
    },

    dictionaryPackCounts(pack) {
      return this.t("{terms} terms, {aliases} aliases", {
        terms: this.formatNumber(Number(pack?.term_count) || 0),
        aliases: this.formatNumber(Number(pack?.alias_count) || 0),
      });
    },

    safeExternalUrl(url) {
      try {
        const parsed = new URL(url);
        return parsed.protocol === "https:" ? parsed.href : "";
      } catch (_) {
        return "";
      }
    },

    aliasesFromText() {
      const seen = new Set();
      return this.newWordAliases
        .split(/\r?\n/)
        .map((alias) => alias.trim())
        .filter((alias) => {
          const normalized = alias.toLocaleLowerCase();
          if (!normalized || seen.has(normalized)) return false;
          seen.add(normalized);
          return true;
        });
    },

    async setDictionaryPack(pack, enabled) {
      const packId = pack?.id;
      if (!packId || this.dictionaryPackBusy[packId]) return;

      const current = this.dictionaryPacks().find((item) => item.id === packId);
      if (!current || Boolean(current.enabled) === Boolean(enabled)) return;

      const previous = Boolean(current.enabled);
      current.enabled = Boolean(enabled);
      this.dictionaryPackBusy = { ...this.dictionaryPackBusy, [packId]: true };
      this.dictionaryPackErrors = { ...this.dictionaryPackErrors, [packId]: "" };

      try {
        this.assertSuccessful(
          await this.api(`/api/dictionary/packs/${encodeURIComponent(packId)}`, {
            method: "PUT",
            body: JSON.stringify({ enabled: Boolean(enabled) }),
          }),
        );
      } catch (_) {
        const refreshed = await this.loadDictionary();
        if (!refreshed) {
          const visiblePack = this
            .dictionaryPacks()
            .find((item) => item.id === packId);
          if (visiblePack) visiblePack.enabled = previous;
        }
        this.dictionaryPackErrors = {
          ...this.dictionaryPackErrors,
          [packId]: "Could not update dictionary pack.",
        };
      } finally {
        const { [packId]: _, ...remaining } = this.dictionaryPackBusy;
        this.dictionaryPackBusy = remaining;
      }
    },

    async loadSnippets() {
      return this.loadResource(
        "snippets",
        () => this.api("/api/snippets"),
        (data) => {
          this.snippets = Array.isArray(data.snippets) ? data.snippets : [];
        },
        "Could not load snippets.",
      );
    },

    modelBackendForConfig() {
      return this.config.stt?.backend === "whisper-cpp"
        ? "whisper-cpp"
        : "faster-whisper";
    },

    currentAiBackend() {
      return this.config.ai?.backend || "none";
    },

    isOllamaBackend() {
      return this.currentAiBackend() === "ollama";
    },

    rememberCurrentAiModel() {
      const backend = this.currentAiBackend();
      this._activeAiBackend = backend;
      this._aiModelSelectionByBackend[backend] = this.config.ai?.model || "";
    },

    selectAiBackend() {
      const ai = this.config.ai || (this.config.ai = {});
      const nextBackend = this.currentAiBackend();
      const previousBackend = this._activeAiBackend;
      if (previousBackend && previousBackend !== nextBackend) {
        this._aiModelSelectionByBackend[previousBackend] = ai.model || "";
      }
      if (previousBackend !== nextBackend) {
        this._ollamaContextId += 1;
        this.closeOllamaModelPicker();
        ai.model = Object.hasOwn(this._aiModelSelectionByBackend, nextBackend)
          ? this._aiModelSelectionByBackend[nextBackend]
          : "";
      }
      this._activeAiBackend = nextBackend;
      this._aiModelSelectionByBackend[nextBackend] = ai.model || "";
      if (nextBackend === "ollama") this.loadOllamaModels();
      return this.saveConfig();
    },

    isInstalledOllamaModel(modelName) {
      return this.ollamaInstalledModels().some(
        (model) => model.name === modelName,
      );
    },

    selectOllamaModel(model) {
      if (!this.isOllamaBackend()) return Promise.resolve();
      const selected = model || "";
      if (selected && !this.isInstalledOllamaModel(selected)) {
        return Promise.resolve();
      }
      this.config.ai.model = selected;
      this._aiModelSelectionByBackend.ollama = selected;
      return this.saveConfig();
    },

    useOllamaRecommendation(recommendation) {
      if (!recommendation?.installed) return Promise.resolve();
      return this.selectOllamaModel(recommendation.name);
    },

    ollamaInstalledModels() {
      return Array.isArray(this.ollamaCatalog.models)
        ? this.ollamaCatalog.models
        : [];
    },

    hasUnavailableOllamaModel() {
      const selected = this.config.ai?.model || "";
      return Boolean(selected) && !this.isInstalledOllamaModel(selected);
    },

    formatOllamaModel(model) {
      const details = [
        model.parameter_size,
        model.quantization_level || model.quantization,
      ].filter(Boolean);
      return details.length ? `${model.name} (${details.join(", ")})` : model.name;
    },

    ollamaModelSearchText(model) {
      return [
        model.name,
        model.parameter_size,
        model.quantization_level || model.quantization,
      ]
        .filter(Boolean)
        .join(" ")
        .toLocaleLowerCase();
    },

    filteredOllamaInstalledModels() {
      const query = this.ollamaModelQuery.trim().toLocaleLowerCase();
      return query
        ? this.ollamaInstalledModels().filter((model) =>
            this.ollamaModelSearchText(model).includes(query),
          )
        : this.ollamaInstalledModels();
    },

    ollamaModelPickerOptionCount() {
      return this.filteredOllamaInstalledModels().length + 1;
    },

    ollamaModelDisplayValue() {
      const selected = this.config.ai?.model || "";
      if (!selected) return this.t("Select an installed model");
      if (this.hasUnavailableOllamaModel()) {
        return this.t("Unavailable model: {model}", { model: selected });
      }
      const model = this.ollamaInstalledModels().find(
        (item) => item.name === selected,
      );
      return model ? this.formatOllamaModel(model) : selected;
    },

    ollamaModelActiveOptionId() {
      return this.ollamaModelPickerOpen && this.ollamaModelActiveIndex >= 0
        ? `ai-ollama-model-option-${this.ollamaModelActiveIndex}`
        : "";
    },

    afterOllamaPickerRender(callback) {
      if (typeof this.$nextTick === "function") {
        this.$nextTick(callback);
      } else {
        callback();
      }
    },

    scrollOllamaModelActiveOptionIntoView() {
      const option = document.getElementById?.(
        this.ollamaModelActiveOptionId(),
      );
      option?.scrollIntoView?.({ block: "nearest" });
    },

    openOllamaModelPicker() {
      if (!this.isOllamaBackend()) return;
      this.ollamaModelPickerOpen = true;
      this.ollamaModelQuery = "";
      const selected = this.config.ai?.model || "";
      const selectedIndex = this.ollamaInstalledModels().findIndex(
        (model) => model.name === selected,
      );
      this.ollamaModelActiveIndex = selectedIndex >= 0 ? selectedIndex + 1 : -1;
      this.afterOllamaPickerRender(() => {
        document.getElementById?.("ai-ollama-model-search")?.focus?.();
        this.scrollOllamaModelActiveOptionIntoView();
      });
    },

    closeOllamaModelPicker(restoreFocus = false) {
      if (!this.ollamaModelPickerOpen) return;
      this.ollamaModelPickerOpen = false;
      this.ollamaModelQuery = "";
      if (restoreFocus) {
        this.afterOllamaPickerRender(() => {
          document.getElementById?.("ai-ollama-model")?.focus?.();
        });
      }
    },

    closeOllamaModelPickerOnFocusOut(event) {
      if (event.currentTarget.contains(event.relatedTarget)) return;
      this.closeOllamaModelPicker();
    },

    onOllamaModelSearchInput() {
      this.ollamaModelActiveIndex = -1;
    },

    moveOllamaModelPicker(direction) {
      if (!this.ollamaModelPickerOpen) {
        this.openOllamaModelPicker();
        return;
      }
      const count = this.ollamaModelPickerOptionCount();
      if (this.ollamaModelActiveIndex < 0) {
        this.ollamaModelActiveIndex =
          direction > 0 ? Math.min(1, count - 1) : count - 1;
      } else {
        this.ollamaModelActiveIndex =
          (this.ollamaModelActiveIndex + direction + count) % count;
      }
      this.afterOllamaPickerRender(() =>
        this.scrollOllamaModelActiveOptionIntoView(),
      );
    },

    commitOllamaModel(model) {
      const selection = model || "";
      if (selection && !this.isInstalledOllamaModel(selection)) return;
      const save = this.selectOllamaModel(selection);
      this.closeOllamaModelPicker();
      return save;
    },

    commitActiveOllamaModel() {
      if (this.ollamaModelActiveIndex === 0) {
        return this.commitOllamaModel("");
      }
      const model =
        this.filteredOllamaInstalledModels()[this.ollamaModelActiveIndex - 1];
      return model ? this.commitOllamaModel(model.name) : undefined;
    },

    ollamaPullCommand(name) {
      return OLLAMA_RECOMMENDATION_TAGS.has(name) ? `ollama pull ${name}` : "";
    },

    async loadOllamaModels() {
      const requestId = ++this._ollamaRequestId;
      const contextId = this._ollamaContextId;
      this.loading.ollama = true;
      this.errors.ollama = "";
      try {
        const data = await this.api("/api/ollama/models");
        if (
          requestId !== this._ollamaRequestId ||
          contextId !== this._ollamaContextId ||
          !this.isOllamaBackend()
        ) {
          return null;
        }
        this.ollamaCatalog = {
          available: Boolean(data.available),
          models: Array.isArray(data.models) ? data.models : [],
          recommended: Array.isArray(data.recommended) ? data.recommended : [],
          error: typeof data.error === "string" ? data.error : null,
          warnings: Array.isArray(data.warnings) ? data.warnings : [],
        };
        if (
          this.ollamaModelPickerOpen &&
          this.ollamaModelActiveIndex >= this.ollamaModelPickerOptionCount()
        ) {
          this.ollamaModelActiveIndex = 0;
        }
        return data;
      } catch (_) {
        if (requestId === this._ollamaRequestId && this.isOllamaBackend()) {
          this.errors.ollama = "Could not load installed Ollama models.";
        }
        return null;
      } finally {
        if (requestId === this._ollamaRequestId) {
          this.loading.ollama = false;
        }
      }
    },

    dictationStatusLabel() {
      if (this.errors.status) return "Panel unavailable";
      const runtime = this.status?.runtime;
      if (
        this.status?.status !== "running" ||
        !runtime?.available ||
        runtime.state === "error"
      ) {
        return "Dictation unavailable";
      }
      if (runtime.state === "recording") return "Recording";
      if (runtime.state === "processing") return "Processing";
      return "Dictation ready";
    },

    dictationStatusClass() {
      return this.dictationStatusLabel() === "Dictation unavailable"
        ? "badge-muted"
        : "badge-success";
    },

    isLocalSttBackend() {
      return ["faster-whisper", "whisper-cpp"].includes(
        this.config.stt?.backend,
      );
    },

    isWhisperCppSttBackend() {
      return this.config.stt?.backend === "whisper-cpp";
    },

    normalizeSttBackendConfig() {
      const stt = this.config.stt || {};
      let changed = false;
      if (stt.backend === "whisper-cpp") {
        if (stt.device !== "vulkan" && stt.device !== "cpu") {
          stt.device = "vulkan";
          changed = true;
        }
        if (stt.compute_type !== "auto") {
          stt.compute_type = "auto";
          changed = true;
        }
        if (!this.sttModelOptions().some((model) => model.name === stt.model)) {
          stt.model = "base";
          changed = true;
        }
      } else if (stt.backend === "faster-whisper" && stt.device === "vulkan") {
        stt.device = "auto";
        changed = true;
      }
      return changed;
    },

    sttModelOptions() {
      if (this.isWhisperCppSttBackend()) {
        return [
          { name: "tiny", sizeMb: 75 },
          { name: "base", sizeMb: 142 },
          { name: "small", sizeMb: 466 },
          { name: "medium", sizeMb: 1463 },
          { name: "large-v3", sizeMb: 2952 },
          { name: "large-v3-turbo", sizeMb: 1550 },
        ];
      }
      return [
        { name: "tiny", sizeMb: 75 },
        { name: "base", sizeMb: 150 },
        { name: "small", sizeMb: 500 },
        { name: "medium", sizeGb: 1.5 },
        { name: "large-v3", sizeGb: 3.1 },
        { name: "large-v3-turbo", sizeGb: 1.6 },
        { name: "distil-large-v3", sizeGb: 1.5 },
      ];
    },

    formatSttModel(model) {
      const size = model.sizeGb
        ? `${this.formatNumber(model.sizeGb)} GB`
        : `${this.formatNumber(model.sizeMb)} MB`;
      return `${model.name} (~${size})`;
    },

    selectSttBackend() {
      if (this.isWhisperCppSttBackend()) {
        this.config.stt.device = "vulkan";
        this.config.stt.compute_type = "auto";
        if (
          !this.sttModelOptions().some(
            (model) => model.name === this.config.stt.model,
          )
        ) {
          this.config.stt.model = "base";
        }
      } else if (
        this.config.stt.backend === "faster-whisper" &&
        this.config.stt.device === "vulkan"
      ) {
        this.config.stt.device = "auto";
      }
      this.selectModelBackend(this.modelBackendForConfig());
      return this.saveConfig();
    },

    selectModelBackend(backend) {
      const selected =
        backend === "whisper-cpp" ? "whisper-cpp" : "faster-whisper";
      this.modelBackend = selected;
      return this.loadModels(selected);
    },

    modelOperationKey(backend, name) {
      return `${backend}:${name}`;
    },

    modelOperation(backend, name) {
      return this._modelOperations[this.modelOperationKey(backend, name)] || "";
    },

    isModelBusy(backend, name) {
      return Boolean(this.modelOperation(backend, name));
    },

    isModelDownloading(backend, name) {
      return this.modelOperation(backend, name) === "downloading";
    },

    isModelDeleting(backend, name) {
      return this.modelOperation(backend, name) === "deleting";
    },

    async loadModels(backend = this.modelBackend) {
      const requestId = ++this._modelRequestId;
      this.loading.models = true;
      this.errors.models = "";
      try {
        const data = await this.api(
          `/api/models?backend=${encodeURIComponent(backend)}`,
        );
        if (requestId !== this._modelRequestId || backend !== this.modelBackend) {
          return null;
        }
        this.models = Array.isArray(data.models)
          ? data.models.map((model) => ({ ...model, backend }))
          : [];
        return data;
      } catch (_) {
        if (requestId === this._modelRequestId && backend === this.modelBackend) {
          this.errors.models = "Could not load models.";
        }
        return null;
      } finally {
        if (requestId === this._modelRequestId && backend === this.modelBackend) {
          this.loading.models = false;
        }
      }
    },

    async loadDiskUsage() {
      return this.loadResource(
        "diskUsage",
        () => this.api("/api/models/disk-usage"),
        (data) => {
          this.diskUsage = data;
        },
        "Could not load disk usage.",
      );
    },

    async saveConfig() {
      this._queuedConfig = JSON.parse(JSON.stringify(this.config));
      if (this._savingConfig) return this._configSavePromise;

      this._savingConfig = true;
      this._configSavePromise = (async () => {
        while (this._queuedConfig) {
          const snapshot = this._queuedConfig;
          this._queuedConfig = null;
          this.busy.config = true;
          this.saveState = "saving";
          try {
            this.assertSuccessful(
              await this.api("/api/config", {
                method: "PUT",
                body: JSON.stringify(snapshot),
              }),
            );
            if (!this._queuedConfig) {
              this.saveState = "saved";
              if (this.currentPage === "models") {
                await this.loadModels(this.modelBackend);
              }
            }
          } catch (_) {
            if (!this._queuedConfig) {
              this.saveState = "error";
              this.showToast("Could not save settings.", "error");
            }
          }
        }
      })();

      try {
        await this._configSavePromise;
      } finally {
        this.busy.config = false;
        this._savingConfig = false;
        this._configSavePromise = null;
      }
    },

    async resetConfig() {
      if (this.busy.config) return;
      this.busy.config = true;
      this.saveState = "saving";
      try {
        this.assertSuccessful(
          await this.api("/api/config/reset", { method: "POST" }),
        );
        await this.loadConfig();
        if (!this.errors.config) {
          this.saveState = "saved";
          this.showToast("Settings restored to defaults.");
        } else {
          this.saveState = "error";
        }
      } catch (_) {
        this.saveState = "error";
        this.showToast("Could not restore settings.", "error");
      } finally {
        this.busy.config = false;
      }
    },

    async deleteHistoryEntry(id) {
      if (this.busy.historyClear) return;
      this.busy.historyClear = true;
      try {
        this.assertSuccessful(
          await this.api(`/api/history/${id}`, { method: "DELETE" }),
        );
        this.showToast("Transcription deleted.");
        await Promise.all([
          this.loadHistory(),
          this.loadStats(),
          this.loadRecentHistory(),
        ]);
      } catch (_) {
        this.showToast("Could not delete transcription.", "error");
      } finally {
        this.busy.historyClear = false;
      }
    },

    async clearHistory() {
      if (this.busy.historyClear) return;
      this.busy.historyClear = true;
      try {
        this.assertSuccessful(
          await this.api("/api/history", { method: "DELETE" }),
        );
        this.showToast("History cleared.");
        await Promise.all([
          this.loadHistory(),
          this.loadStats(),
          this.loadRecentHistory(),
        ]);
      } catch (_) {
        this.showToast("Could not clear history.", "error");
      } finally {
        this.busy.historyClear = false;
      }
    },

    async addWord() {
      const word = this.newWord.trim();
      if (!word || this.busy.word) return;
      this.busy.word = true;
      try {
        this.assertSuccessful(
          await this.api("/api/dictionary/words", {
            method: "POST",
            body: JSON.stringify({
              word,
              category: this.newWordCategory,
              aliases: this.aliasesFromText(),
            }),
          }),
        );
        this.newWord = "";
        this.newWordAliases = "";
        this.showToast("Dictionary entry saved.");
        await this.loadDictionary();
      } catch (_) {
        this.showToast("Could not add word.", "error");
      } finally {
        this.busy.word = false;
      }
    },

    async removeWord(word) {
      if (this.busy.word) return;
      this.busy.word = true;
      try {
        this.assertSuccessful(
          await this.api(`/api/dictionary/words/${encodeURIComponent(word)}`, {
            method: "DELETE",
          }),
        );
        this.showToast("Word removed from dictionary.");
        await this.loadDictionary();
      } catch (_) {
        this.showToast("Could not remove word.", "error");
      } finally {
        this.busy.word = false;
      }
    },

    async removeCorrection(index) {
      if (this.busy.word) return;
      this.busy.word = true;
      try {
        this.assertSuccessful(
          await this.api(`/api/dictionary/corrections/${index}`, {
            method: "DELETE",
          }),
        );
        this.showToast("Correction removed from dictionary.");
        await this.loadDictionary();
      } catch (_) {
        this.showToast("Could not remove correction.", "error");
      } finally {
        this.busy.word = false;
      }
    },

    async addSnippet() {
      const trigger = this.newSnippetTrigger.trim();
      const expansion = this.newSnippetExpansion.trim();
      if (!trigger || !expansion || this.busy.snippet) return;
      this.busy.snippet = true;
      try {
        this.assertSuccessful(
          await this.api("/api/snippets", {
            method: "POST",
            body: JSON.stringify({ trigger, expansion }),
          }),
        );
        this.newSnippetTrigger = "";
        this.newSnippetExpansion = "";
        this.showToast("Snippet added.");
        await this.loadSnippets();
      } catch (_) {
        this.showToast("Could not add snippet.", "error");
      } finally {
        this.busy.snippet = false;
      }
    },

    async removeSnippet(trigger) {
      if (this.busy.snippet) return;
      this.busy.snippet = true;
      try {
        this.assertSuccessful(
          await this.api(`/api/snippets/${encodeURIComponent(trigger)}`, {
            method: "DELETE",
          }),
        );
        this.showToast("Snippet removed.");
        await this.loadSnippets();
      } catch (_) {
        this.showToast("Could not remove snippet.", "error");
      } finally {
        this.busy.snippet = false;
      }
    },

    async downloadModel(name, backend = this.modelBackend) {
      const key = this.modelOperationKey(backend, name);
      if (this._modelOperations[key]) return;
      this._modelOperations[key] = "downloading";
      try {
        this.assertSuccessful(
          await this.api(
            `/api/models/${encodeURIComponent(name)}/download?backend=${encodeURIComponent(backend)}`,
            { method: "POST" },
          ),
        );
        this.showToast("Model downloaded.");
        await Promise.all([this.loadModels(backend), this.loadDiskUsage()]);
      } catch (_) {
        this.showToast("Could not download model.", "error");
      } finally {
        if (this._modelOperations[key] === "downloading") {
          delete this._modelOperations[key];
        }
      }
    },

    async deleteModel(name, backend = this.modelBackend) {
      const key = this.modelOperationKey(backend, name);
      if (this._modelOperations[key]) return;
      this._modelOperations[key] = "deleting";
      try {
        this.assertSuccessful(
          await this.api(
            `/api/models/${encodeURIComponent(name)}?backend=${encodeURIComponent(backend)}`,
            { method: "DELETE" },
          ),
        );
        this.showToast("Model deleted.");
        await Promise.all([this.loadModels(backend), this.loadDiskUsage()]);
      } catch (_) {
        this.showToast("Could not delete model.", "error");
      } finally {
        if (this._modelOperations[key] === "deleting") {
          delete this._modelOperations[key];
        }
      }
    },
  };
}
