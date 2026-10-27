const OLLAMA_RECOMMENDATION_TAGS = new Set([
  "qwen3:8b",
  "qwen3.5:4b",
  "qwen3:14b",
  "gemma3:12b",
]);

const IMPORT_ERROR_DETAIL_MAX_LENGTH = 500;

const STATUS_REFRESH_INTERVAL_MS = 2000;

const PROMPT_TEMPLATE_INSTRUCTIONS = Object.freeze({
  default: "",
  formal:
    "Use a formal, professional tone while preserving the original meaning and language.",
  casual:
    "Use a natural, casual tone while preserving the original meaning and language.",
  concise:
    "Make the text concise while preserving all facts, meaning, language, and technical terms.",
  bullets:
    "Organize the dictated points as clear bullet points without adding or omitting content. Preserve the original language and technical terms.",
});

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
      { id: "dashboard", path: "/", label: "Dashboard", icon: "layout-dashboard" },
      { id: "config", path: "/settings", label: "Settings", icon: "settings" },
      { id: "history", path: "/history", label: "History", icon: "history" },
      { id: "dictionary", path: "/dictionary", label: "Dictionary", icon: "book" },
      { id: "snippets", path: "/snippets", label: "Snippets", icon: "bolt" },
      { id: "models", path: "/models", label: "Models", icon: "database" },
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
      web: { port: 7865, auto_open: true },
      preload_models: true,
      autostart: false,
    },
    promptTemplate: "default",

    configOpen: {
      startup: false,
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
    dictionaryImportMode: "file",
    dictionaryImportUrl: "",
    dictionaryImportContent: "",
    dictionaryImportFilename: "",
    dictionaryImportTargetId: null,
    dictionaryImportPreview: null,
    dictionaryImportToken: "",
    dictionaryImportFiles: [],
    dictionaryImportSourceUrl: "",
    dictionaryImportBusy: false,
    dictionaryImportError: "",
    dictionaryImportErrorDetail: "",
    dictionaryImportAcknowledged: false,
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

    setup: {
      detection: null,
      success: "",
      open: false,
    },
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
      setup: false,
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
      setup: "",
    },
    busy: {
      config: false,
      word: false,
      snippet: false,
      historyClear: false,
      setup: false,
    },
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
    _modelOperationPromises: {},
    _confirmationAction: null,
    _confirmationTrigger: null,
    _savingConfig: false,
    _queuedConfig: [],
    _configSavePromise: null,
    _dialogListenerAttached: false,
    _dictionaryImportRequestId: 0,
    _popstateListener: null,
    _visibilityChangeListener: null,
    _statusRefreshTimer: null,
    _statusRefreshPromise: null,
    _setupRequestId: 0,
    _lastConfigSaveError: null,
    async init() {
      this.currentPage = this.pageForPath(window.location.pathname);
      this._popstateListener = () => {
        this.navigate(this.pageForPath(window.location.pathname), {
          updateHistory: false,
        });
      };
      window.addEventListener("popstate", this._popstateListener);
      if (typeof document.addEventListener === "function") {
        this._visibilityChangeListener = () => this.handleStatusVisibilityChange();
        document.addEventListener(
          "visibilitychange",
          this._visibilityChangeListener,
        );
      }
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
      if (this.config.first_run === true) {
        await this.detectOptimalSetup({ open: false });
      }
      this.startStatusRefresh();
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

    destroy() {
      if (this._popstateListener) {
        window.removeEventListener("popstate", this._popstateListener);
        this._popstateListener = null;
      }
      if (
        this._visibilityChangeListener &&
        typeof document.removeEventListener === "function"
      ) {
        document.removeEventListener(
          "visibilitychange",
          this._visibilityChangeListener,
        );
      }
      this._visibilityChangeListener = null;
      this.stopStatusRefresh();
    },


    isDocumentVisible() {
      return (
        typeof document === "undefined" || document.visibilityState !== "hidden"
      );
    },

    startStatusRefresh() {
      if (
        this._statusRefreshTimer !== null ||
        !this.isDocumentVisible() ||
        typeof window === "undefined" ||
        typeof window.setInterval !== "function"
      ) {
        return;
      }
      this._statusRefreshTimer = window.setInterval(() => {
        if (this.isDocumentVisible()) this.loadStatus();
      }, STATUS_REFRESH_INTERVAL_MS);
    },

    stopStatusRefresh() {
      const timer = this._statusRefreshTimer;
      this._statusRefreshTimer = null;
      if (timer !== null && typeof window.clearInterval === "function") {
        window.clearInterval(timer);
      }
    },

    handleStatusVisibilityChange() {
      if (this.isDocumentVisible()) {
        this.loadStatus();
        this.startStatusRefresh();
      } else {
        this.stopStatusRefresh();
      }
    },

    pageForPath(pathname) {
      const normalizedPath = pathname.replace(/\/+$/, "") || "/";
      return (
        this.navItems.find((item) => item.path === normalizedPath)?.id ||
        "dashboard"
      );
    },

    handleNavigation(event, id) {
      if (
        event.defaultPrevented ||
        event.button !== 0 ||
        event.metaKey ||
        event.ctrlKey ||
        event.shiftKey ||
        event.altKey
      ) {
        return;
      }
      event.preventDefault();
      this.navigate(id);
    },

    navigate(id, { updateHistory = true } = {}) {
      const page = this.navItems.find((item) => item.id === id);
      if (!page) return;

      const pageChanged = this.currentPage !== page.id;
      this.currentPage = page.id;
      if (updateHistory && pageChanged) {
        window.history.pushState(null, "", page.path);
      }
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

    promptTemplateFor(customPrompt = this.config.ai?.custom_prompt) {
      const prompt = String(customPrompt ?? "");
      if (!prompt.trim()) return "default";
      return (
        Object.entries(PROMPT_TEMPLATE_INSTRUCTIONS).find(
          ([templateId, instructions]) =>
            templateId !== "default" && prompt === instructions,
        )?.[0] || "custom"
      );
    },

    syncPromptTemplate(customPrompt) {
      this.promptTemplate = this.promptTemplateFor(customPrompt);
    },

    applyPromptTemplate(templateId) {

      const instructions = PROMPT_TEMPLATE_INSTRUCTIONS[templateId];
      if (instructions === undefined) {
        this.syncPromptTemplate();
        return;
      }

      this.config.ai.custom_prompt = instructions;
      this.promptTemplate = templateId;
      this.saveConfig();
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

    formatMegabytes(value) {
      return i18n.formatMegabytes(this.uiLanguage, value);
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

      if (!response.ok || (data && data.status === "error")) {
        const error = new Error("request-failed");
        if (typeof data?.detail === "string") {
          error.detail = data.detail.slice(0, IMPORT_ERROR_DETAIL_MAX_LENGTH);
        }
        throw error;
      }
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
    loadStatus() {
      if (this._statusRefreshPromise) return this._statusRefreshPromise;
      const request = this.loadResource(
        "status",
        () => this.api("/api/status"),
        (data) => {
          this.status = data;
          this.startStatusRefresh();
        },
        "Could not check the dashboard connection.",
      );
      this._statusRefreshPromise = request;
      request.then(
        () => {
          if (this._statusRefreshPromise === request) {
            this._statusRefreshPromise = null;
          }
        },
        () => {
          if (this._statusRefreshPromise === request) {
            this._statusRefreshPromise = null;
          }
        },
      );
      return request;
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
          this.syncPromptTemplate();
          const normalized = this.normalizeSttBackendConfig();
          this.rememberCurrentAiModel();
          this.selectModelBackend(this.modelBackendForConfig());
          if (this.isOllamaBackend()) this.loadOllamaModels();
          if (normalized) this.saveConfig();
        },
        "Could not load settings.",
      );
    },

    setupMemory(value) {
      if (value === null || value === undefined) return this.t("Unknown");
      const amount = Number(value);
      return Number.isFinite(amount) && amount >= 0
        ? `${this.formatNumber((amount * 1048576) / 1000000000, {
            minimumFractionDigits: 1,
            maximumFractionDigits: 1,
          })} GB`
        : this.t("Unknown");
    },

    setupGpuList() {
      const gpus = this.setup.detection?.hardware?.gpus;
      return Array.isArray(gpus) ? gpus : [];
    },

    setupWarningLabel(code) {
      return this.t(`Setup warning: ${code}`);
    },

    setupReasonLabel(reason) {
      return this.t(`Setup reason: ${reason}`);
    },

    setupNeedsAmdExtra() {
      const warnings = this.setup.detection?.warnings;
      return (
        Array.isArray(warnings) &&
        warnings.some((warning) =>
          ["amd_runtime_missing", "vulkan_unavailable"].includes(warning),
        )
      );
    },

    setupIsDownloaded() {
      return Boolean(this.setup.detection?.recommendation?.downloaded);
    },

    async detectOptimalSetup({ open = true } = {}) {
      if (this.busy.setup) return null;
      if (open) this.setup.open = true;
      const requestId = ++this._setupRequestId;
      this.loading.setup = true;
      this.errors.setup = "";
      this.setup.success = "";
      try {
        const data = this.assertSuccessful(await this.api("/api/setup/detect"));
        if (requestId !== this._setupRequestId) return null;
        this.setup.detection = data;
        return data;
      } catch (_) {
        if (requestId === this._setupRequestId) {
          this.errors.setup = "Could not detect an optimal setup.";
        }
        return null;
      } finally {
        if (requestId === this._setupRequestId) this.loading.setup = false;
      }
    },

    setupRecommendationConfig(recommendation) {
      return {
        backend: recommendation.backend,
        model: recommendation.model,
        device: recommendation.device,
        compute_type: recommendation.compute_type,
      };
    },

    restoreOptimalSetupConfig(config, previousSetup) {
      const stt = { ...(config.stt || {}) };
      for (const [field, value] of Object.entries(previousSetup.stt)) {
        if (value === undefined) {
          delete stt[field];
        } else {
          stt[field] = value;
        }
      }
      return { ...config, first_run: previousSetup.first_run, stt };
    },

    rollbackOptimalSetupConfig(previousSetup) {
      this.config = this.restoreOptimalSetupConfig(this.config, previousSetup);
      for (const entry of this._queuedConfig) {
        entry.snapshot = this.restoreOptimalSetupConfig(
          entry.snapshot,
          previousSetup,
        );
      }
    },

    async dismissOptimalSetup() {
      if (this.busy.setup || this.config.first_run !== true) return;
      const previousConfig = this.config;
      this.busy.setup = true;
      this.errors.setup = "";
      try {
        this.config = { ...this.config, first_run: false };
        await this.saveConfig({ throwOnError: true });
        this.setup.success = "";
        this.showToast("Saved");
      } catch (_) {
        this.config = previousConfig;
        this.errors.setup = "Could not save setup preference.";
      } finally {
        this.busy.setup = false;
      }
    },

    async applyOptimalSetup() {
      const detection = this.setup.detection;
      const recommendation = detection?.recommendation;
      if (!recommendation || this.busy.setup || this.loading.setup) return;

      const requestId = this._setupRequestId;
      this.busy.setup = true;
      this.errors.setup = "";
      this.setup.success = "";
      try {
        await this.downloadModel(recommendation.model, recommendation.backend, {
          throwOnError: true,
        });
        if (requestId !== this._setupRequestId) return;

        const previousSetup = {
          first_run: this.config.first_run,
          stt: Object.fromEntries(
            Object.keys(this.setupRecommendationConfig(recommendation)).map(
              (field) => [field, this.config.stt?.[field]],
            ),
          ),
        };
        this.config = {
          ...this.config,
          first_run: false,
          stt: {
            ...(this.config.stt || {}),
            ...this.setupRecommendationConfig(recommendation),
          },
        };
        await this.saveConfig({
          throwOnError: true,
          onFailure: () => this.rollbackOptimalSetupConfig(previousSetup),
        });
        this.selectModelBackend(recommendation.backend);
        this.setup.success =
          "Setup saved. Restart LinuxWhispr to activate the recommendation.";
        this.showToast(this.setup.success);
      } catch (_) {
        this.errors.setup = "Could not apply the recommended setup.";
      } finally {
        this.busy.setup = false;
      }
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

    bundledDictionaryPacks() {
      return this.dictionaryPacks().filter((pack) => pack?.kind !== "community");
    },

    communityDictionaryPacks() {
      return this.dictionaryPacks().filter((pack) => pack?.kind === "community");
    },

    dictionaryPackTerms(pack) {
      return Array.isArray(pack?.terms) ? pack.terms : [];
    },

    dictionaryPackSources(pack) {
      return Array.isArray(pack?.sources) ? pack.sources : [];
    },

    dictionaryPackSourceUrl(pack) {
      return pack?.source?.kind === "url"
        ? this.safeExternalUrl(pack.source.url)
        : "";
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

    invalidateDictionaryImportPreview() {
      this._dictionaryImportRequestId += 1;
      this.dictionaryImportPreview = null;
      this.dictionaryImportToken = "";
      this.dictionaryImportFiles = [];
      this.dictionaryImportSourceUrl = "";
      this.dictionaryImportError = "";
      this.dictionaryImportErrorDetail = "";
      this.dictionaryImportAcknowledged = false;
    },

    onDictionaryImportModeChange() {
      this.invalidateDictionaryImportPreview();
    },

    async handleDictionaryImportFile(event) {
      this.invalidateDictionaryImportPreview();
      const file = event?.target?.files?.[0];
      this.dictionaryImportContent = "";
      this.dictionaryImportFilename = "";
      if (!file) return;

      const requestId = this._dictionaryImportRequestId;
      this.dictionaryImportFilename = String(file.name || "");
      try {
        const content = await file.text();
        if (requestId !== this._dictionaryImportRequestId) return;
        this.dictionaryImportContent = content;
      } catch (_) {
        if (requestId === this._dictionaryImportRequestId) {
          this.dictionaryImportError = "Could not read dictionary file.";
        }
      }
    },

    dictionaryImportPreviewData() {
      return this.dictionaryImportPreview && typeof this.dictionaryImportPreview === "object"
        ? this.dictionaryImportPreview
        : null;
    },

    dictionaryImportDocument() {
      return this.dictionaryImportPreviewData()?.document || {};
    },

    dictionaryImportEntries() {
      const entries = this.dictionaryImportDocument().entries;
      return Array.isArray(entries) ? entries : [];
    },

    dictionaryEntryDescription(entry) {
      const word = String(entry?.word || "");
      const aliases = Array.isArray(entry?.aliases) ? entry.aliases : [];
      return aliases.length ? `${word} (${aliases.join(", ")})` : word;
    },

    dictionaryImportChanges() {
      const changes = this.dictionaryImportPreviewData()?.changes;
      return changes && typeof changes === "object" ? changes : {};
    },

    dictionaryImportConflicts() {
      const conflicts = this.dictionaryImportPreviewData()?.conflicts;
      return Array.isArray(conflicts) ? conflicts : [];
    },

    dictionaryImportHasConflicts() {
      return this.dictionaryImportConflicts().length > 0;
    },

    dictionaryImportPreviewSourceUrl() {
      return this.safeExternalUrl(this.dictionaryImportPreviewData()?.source?.url);
    },

    dictionaryImportTargetName() {
      const pack = this.dictionaryPacks().find(
        (item) => item?.id === this.dictionaryImportTargetId,
      );
      return this.dictionaryImportPackName(pack) || this.dictionaryImportTargetId || "";
    },

    dictionaryImportPackName(pack) {
      return String(pack?.name || pack?.document_id || pack?.id || "");
    },

    async requestDictionaryImportPreview(request) {
      if (this.dictionaryImportBusy) return;
      const requestId = ++this._dictionaryImportRequestId;
      this.dictionaryImportBusy = true;
      this.dictionaryImportError = "";
      this.dictionaryImportErrorDetail = "";
      this.dictionaryImportPreview = null;
      this.dictionaryImportToken = "";
      this.dictionaryImportFiles = [];
      this.dictionaryImportSourceUrl = "";
      this.dictionaryImportAcknowledged = false;
      try {
        const data = this.assertSuccessful(await request());
        if (requestId !== this._dictionaryImportRequestId) return;
        if (data.kind === "selection" && Array.isArray(data.files)) {
          this.dictionaryImportFiles = data.files;
          this.dictionaryImportSourceUrl = String(data.source_url || "");
          return;
        }
        if (
          data.kind === "preview" &&
          typeof data.token === "string" &&
          data.token &&
          data.preview &&
          typeof data.preview === "object"
        ) {
          this.dictionaryImportPreview = data.preview;
          this.dictionaryImportToken = data.token;
          return;
        }
        throw new Error("invalid-preview");
      } catch (error) {
        if (requestId === this._dictionaryImportRequestId) {
          this.dictionaryImportError = "Could not preview dictionary.";
          this.dictionaryImportErrorDetail =
            typeof error?.detail === "string"
              ? error.detail.slice(0, IMPORT_ERROR_DETAIL_MAX_LENGTH)
              : "";
        }
      } finally {
        if (requestId === this._dictionaryImportRequestId) {
          this.dictionaryImportBusy = false;
        }
      }
    },

    previewDictionaryImport() {
      this.invalidateDictionaryImportPreview();
      const packId = this.dictionaryImportTargetId || undefined;
      if (this.dictionaryImportMode === "file") {
        if (!this.dictionaryImportContent || !this.dictionaryImportFilename) {
          this.dictionaryImportError = "Choose a dictionary file.";
          return;
        }
        return this.requestDictionaryImportPreview(() =>
          this.api("/api/dictionary/import/preview", {
            method: "POST",
            body: JSON.stringify({
              content: this.dictionaryImportContent,
              filename: this.dictionaryImportFilename,
              ...(packId ? { pack_id: packId } : {}),
            }),
          }),
        );
      }

      const url = this.dictionaryImportUrl.trim();
      if (!url) {
        this.dictionaryImportError = "Enter a dictionary URL.";
        return;
      }
      return this.requestDictionaryImportPreview(() =>
        this.api("/api/dictionary/import/preview", {
          method: "POST",
          body: JSON.stringify({
            url,
            ...(packId ? { pack_id: packId } : {}),
          }),
        }),
      );
    },

    selectDictionaryImportFile(file) {
      if (!file?.name || !this.dictionaryImportSourceUrl) return;
      return this.requestDictionaryImportPreview(() =>
        this.api("/api/dictionary/import/preview", {
          method: "POST",
          body: JSON.stringify({
            url: this.dictionaryImportSourceUrl,
            filename: String(file.name),
            ...(this.dictionaryImportTargetId
              ? { pack_id: this.dictionaryImportTargetId }
              : {}),
          }),
        }),
      );
    },

    prepareDictionaryFileReplacement(pack) {
      const packId = String(pack?.id || "");
      if (!packId) return;
      this.invalidateDictionaryImportPreview();
      this.dictionaryImportMode = "file";
      this.dictionaryImportTargetId = packId;
      this.dictionaryImportContent = "";
      this.dictionaryImportFilename = "";
      const input = document.getElementById("dictionary-import-file");
      if (input instanceof HTMLInputElement) input.value = "";
      this.$nextTick(() => input?.focus?.());
    },

    checkDictionaryPackUpdate(pack) {
      const packId = String(pack?.id || "");
      if (!packId || this.dictionaryImportBusy) return;
      this.invalidateDictionaryImportPreview();
      this.dictionaryImportTargetId = packId;
      return this.requestDictionaryImportPreview(() =>
        this.api(
          `/api/dictionary/packs/${encodeURIComponent(packId)}/check-update`,
          { method: "POST" },
        ),
      );
    },

    cancelDictionaryImport() {
      this.invalidateDictionaryImportPreview();
      this.dictionaryImportContent = "";
      this.dictionaryImportFilename = "";
      this.dictionaryImportTargetId = null;
      this.dictionaryImportBusy = false;
      const input = document.getElementById("dictionary-import-file");
      if (input instanceof HTMLInputElement) input.value = "";
    },

    async confirmDictionaryImport() {
      const token = this.dictionaryImportToken;
      if (
        !token ||
        !this.dictionaryImportPreview ||
        this.dictionaryImportBusy ||
        (this.dictionaryImportHasConflicts() &&
          !this.dictionaryImportAcknowledged)
      ) {
        return;
      }

      const requestId = this._dictionaryImportRequestId;
      this.dictionaryImportBusy = true;
      this.dictionaryImportError = "";
      this.dictionaryImportErrorDetail = "";
      try {
        this.assertSuccessful(
          await this.api("/api/dictionary/import/confirm", {
            method: "POST",
            body: JSON.stringify({
              token,
              acknowledge_conflicts: this.dictionaryImportAcknowledged,
            }),
          }),
        );
        if (requestId !== this._dictionaryImportRequestId) return;
        this.showToast("Community dictionary saved.");
        this.cancelDictionaryImport();
        await this.loadDictionary();
      } catch (error) {
        if (requestId === this._dictionaryImportRequestId) {
          this.dictionaryImportError = "Could not save community dictionary.";
          this.dictionaryImportErrorDetail =
            typeof error?.detail === "string"
              ? error.detail.slice(0, IMPORT_ERROR_DETAIL_MAX_LENGTH)
              : "";
        }
      } finally {
        if (requestId === this._dictionaryImportRequestId) {
          this.dictionaryImportBusy = false;
        }
      }
    },

    async removeCommunityDictionaryPack(pack) {
      const packId = String(pack?.id || "");
      if (!packId || this.dictionaryPackBusy[packId]) return;
      this.dictionaryPackBusy = { ...this.dictionaryPackBusy, [packId]: true };
      this.dictionaryPackErrors = { ...this.dictionaryPackErrors, [packId]: "" };
      try {
        this.assertSuccessful(
          await this.api(`/api/dictionary/packs/${encodeURIComponent(packId)}`, {
            method: "DELETE",
          }),
        );
        this.showToast("Community dictionary removed.");
        await this.loadDictionary();
      } catch (_) {
        this.dictionaryPackErrors = {
          ...this.dictionaryPackErrors,
          [packId]: "Could not remove community dictionary.",
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
      if (runtime.state === "idle" && runtime.models_preparing === true) {
        return "Preparing models";
      }
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
      const sizeMb = model.sizeMb ?? model.sizeGb * 1000;
      return `${model.name} (~${this.formatMegabytes(sizeMb)})`;
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

    saveConfig({ throwOnError = false, onFailure = null } = {}) {
      const snapshot = JSON.parse(JSON.stringify(this.config));
      let resolve;
      const result = new Promise((done) => {
        resolve = done;
      });
      const queued = this._queuedConfig;
      const lastEntry = queued.at(-1);
      if (!throwOnError && lastEntry && !lastEntry.throwOnError) {
        lastEntry.snapshot = snapshot;
        lastEntry.resolvers.push(resolve);
      } else {
        queued.push({
          snapshot,
          throwOnError,
          onFailure,
          resolvers: [resolve],
        });
      }

      if (!this._savingConfig) {
        this._savingConfig = true;
        this._configSavePromise = (async () => {
          while (this._queuedConfig.length) {
            const entry = this._queuedConfig.shift();
            this.busy.config = true;
            this.saveState = "saving";
            let error = null;
            try {
              this.assertSuccessful(
                await this.api("/api/config", {
                  method: "PUT",
                  body: JSON.stringify(entry.snapshot),
                }),
              );
              this._lastConfigSaveError = null;
              if (!this._queuedConfig.length) {
                this.saveState = "saved";
                if (this.currentPage === "models") {
                  await this.loadModels(this.modelBackend);
                }
              }
            } catch (caught) {
              error = caught;
              this._lastConfigSaveError = caught;
              entry.onFailure?.();
              if (!this._queuedConfig.length) {
                this.saveState = "error";
                this.showToast("Could not save settings.", "error");
              }
            }
            for (const done of entry.resolvers) done({ error });
          }
        })().finally(() => {
          this.busy.config = false;
          this._savingConfig = false;
          this._configSavePromise = null;
        });
      }

      return result.then(({ error }) => {
        if (error && throwOnError) throw error;
        return !error;
      });
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

    async downloadModel(
      name,
      backend = this.modelBackend,
      { throwOnError = false } = {},
    ) {
      const key = this.modelOperationKey(backend, name);
      let operation = this._modelOperationPromises[key];
      if (!operation) {
        this._modelOperations[key] = "downloading";
        operation = (async () => {
          try {
            this.assertSuccessful(
              await this.api(
                `/api/models/${encodeURIComponent(name)}/download?backend=${encodeURIComponent(backend)}`,
                { method: "POST" },
              ),
            );
            this.showToast("Model downloaded.");
            await Promise.all([this.loadModels(backend), this.loadDiskUsage()]);
            return true;
          } catch (error) {
            this.showToast("Could not download model.", "error");
            throw error;
          } finally {
            if (this._modelOperations[key] === "downloading") {
              delete this._modelOperations[key];
            }
            delete this._modelOperationPromises[key];
          }
        })();
        this._modelOperationPromises[key] = operation;
      }

      try {
        return await operation;
      } catch (error) {
        if (throwOnError) throw error;
        return false;
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
