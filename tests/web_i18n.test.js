"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const root = path.resolve(__dirname, "..");
const i18n = require(path.join(root, "src/linux_whispr/web/static/i18n.js"));

function appWithStorage(storage, globals = {}) {
  const { window: windowOverrides = {}, ...contextGlobals } = globals;
  const context = {
    WhisprI18n: i18n,
    window: {
      WhisprI18n: i18n,
      localStorage: storage,
      matchMedia: () => ({ matches: false }),
      location: { pathname: "/" },
      addEventListener() {},
      removeEventListener() {},
      ...windowOverrides,
    },
    localStorage: storage,
    document: {},
    HTMLElement: class HTMLElement {},
    navigator: {},
    clearTimeout() {},
    setTimeout() {
      return 1;
    },
    ...contextGlobals,
  };
  vm.createContext(context);
  vm.runInContext(
    fs.readFileSync(
      path.join(root, "src/linux_whispr/web/static/app.js"),
      "utf8",
    ),
    context,
  );
  return context.app();
}

function placeholders(value) {
  const text =
    typeof value === "string" ? value : Object.values(value).join(" ");
  return [...text.matchAll(/\{([A-Za-z0-9_]+)\}/g)]
    .map((match) => match[1])
    .sort();
}

test("English is the default and unsupported UI languages fall back safely", () => {
  assert.deepEqual(i18n.languages, [
    { code: "en", name: "English", tag: "en-US" },
    { code: "de", name: "Deutsch", tag: "de-DE" },
    { code: "es", name: "Español", tag: "es-ES" },
    { code: "pt", name: "Português", tag: "pt-BR" },
  ]);
  for (const value of [undefined, null, "", "de-DE", "EN", "fr", {}, 42]) {
    assert.equal(i18n.normalizeLanguage(value), "en");
  }
  assert.equal(i18n.localeTag("es"), "es-ES");
  assert.equal(i18n.translate("de", "Settings"), "Einstellungen");
  assert.equal(i18n.translate("es", "Settings"), "Configuración");
  assert.equal(i18n.translate("pt", "Settings"), "Configurações");
});

test("app restores a persisted UI locale and safely handles denied storage", () => {
  const values = new Map([
    ["uiLanguage", "es"],
    ["darkMode", "false"],
  ]);
  const stored = {
    getItem(key) {
      return values.get(key) ?? null;
    },
    setItem(key, value) {
      values.set(key, value);
    },
  };
  const app = appWithStorage(stored);
  assert.equal(app.uiLanguage, "es");
  assert.equal(app.localeTag, "es-ES");
  app.setLanguage("de");
  assert.equal(values.get("uiLanguage"), "de");

  const denied = {
    getItem() {
      throw new Error("storage denied");
    },
    setItem() {
      throw new Error("storage denied");
    },
  };
  const privateApp = appWithStorage(denied);
  assert.equal(privateApp.uiLanguage, "en");
  assert.doesNotThrow(() => privateApp.setLanguage("pt"));
  assert.equal(privateApp.uiLanguage, "pt");
});

test("changing UI language does not touch dictation settings, drafts, pages, or APIs", () => {
  const writes = [];
  const storage = {
    getItem() {
      return null;
    },
    setItem(key, value) {
      writes.push([key, value]);
    },
  };
  const app = appWithStorage(storage);
  app.config.stt.language = "de";
  app.currentPage = "dictionary";
  app.newWord = "Mnemopi";
  app.newSnippetTrigger = "my email";
  let apiCalls = 0;
  let saves = 0;
  app.api = async () => {
    apiCalls += 1;
  };
  app.saveConfig = async () => {
    saves += 1;
  };

  app.setLanguage("pt");

  assert.equal(app.uiLanguage, "pt");
  assert.equal(app.config.stt.language, "de");
  assert.equal(app.currentPage, "dictionary");
  assert.equal(app.newWord, "Mnemopi");
  assert.equal(app.newSnippetTrigger, "my email");
  assert.equal(apiCalls, 0);
  assert.equal(saves, 0);
  assert.deepEqual(writes, [["uiLanguage", "pt"]]);
});

test("catalogs have matching keys, placeholder parity, and complete plural forms", () => {
  const englishKeys = Object.keys(i18n.catalogs.en).sort();
  for (const language of i18n.languages.map(({ code }) => code)) {
    const catalog = i18n.catalogs[language];
    assert.deepEqual(Object.keys(catalog).sort(), englishKeys, language);
    for (const key of englishKeys) {
      assert.deepEqual(
        placeholders(catalog[key]),
        placeholders(i18n.catalogs.en[key]),
        `${language}: ${key}`,
      );
      if (typeof i18n.catalogs.en[key] === "object") {
        assert.equal(typeof catalog[key], "object", `${language}: ${key}`);
        assert.equal(
          typeof catalog[key].one,
          "string",
          `${language}: ${key}.one`,
        );
        assert.equal(
          typeof catalog[key].other,
          "string",
          `${language}: ${key}.other`,
        );
      }
    }
  }
});

test("translations select plural forms and localize count, date, numbers, and durations", () => {
  assert.equal(i18n.translate("en", "{count} words", { count: 0 }), "0 words");
  assert.equal(i18n.translate("en", "{count} words", { count: 1 }), "1 word");
  assert.equal(i18n.translate("en", "{count} words", { count: 2 }), "2 words");
  assert.equal(
    i18n.translate("de", "{count} words", { count: 1234 }),
    "1.234 Wörter",
  );
  assert.equal(i18n.formatNumber("de", 1234.5), "1.234,5");
  assert.equal(i18n.formatNumber("es", Infinity), "0");
  assert.equal(i18n.formatDuration("pt", 1.25), "1,3 s");
  assert.notEqual(i18n.formatDate("en", "2026-06-15T12:34:00"), "");
  assert.equal(i18n.formatDate("pt", "not a date"), "");
  const germanMinutes = i18n.translate("de", "{count} minutes", { count: 15 });
  assert.ok(germanMinutes.startsWith(i18n.formatNumber("de", 15)));
  assert.notEqual(
    germanMinutes,
    i18n.translate("en", "{count} minutes", { count: 15 }),
  );
  assert.equal(i18n.formatDate("de", 0), "");
});

test("dates render for every supported locale and reject invalid timestamps", () => {
  for (const { code } of i18n.languages) {
    const value = i18n.formatDate(code, "2026-06-15T12:34:00");
    assert.equal(typeof value, "string", code);
    assert.notEqual(value, "", code);
    assert.equal(i18n.formatDate(code, "not a date"), "", code);
    assert.equal(i18n.formatDate(code, 0), "", code);
  }
});

test("translation falls back defensively and interpolation stays plain text", () => {
  assert.equal(
    i18n.translate("de", "Unknown source key"),
    "Unknown source key",
  );
  assert.equal(i18n.translate("de", null), "");
  assert.equal(
    i18n.translate("de", "Original: {text}", {
      text: "<img src=x onerror=alert(1)>",
    }),
    "Original: <img src=x onerror=alert(1)>",
  );
  assert.equal(i18n.translate("en", "Page {page}"), "Page {page}");
});

test("model catalog requests stay scoped and stale results cannot replace a new format", async () => {
  const app = appWithStorage({ getItem: () => null, setItem() {} });
  const pending = [];
  app.api = (url) =>
    new Promise((resolve) => {
      pending.push({ url, resolve });
    });

  const faster = app.loadModels("faster-whisper");
  app.modelBackend = "whisper-cpp";
  const whisperCpp = app.loadModels("whisper-cpp");

  assert.deepEqual(
    pending.map(({ url }) => url),
    [
      "/api/models?backend=faster-whisper",
      "/api/models?backend=whisper-cpp",
    ],
  );

  pending[0].resolve({ models: [{ name: "base" }] });
  await faster;
  assert.equal(app.models.length, 0);

  pending[1].resolve({ models: [{ name: "tiny" }] });
  await whisperCpp;
  assert.equal(app.models.length, 1);
  assert.equal(app.models[0].name, "tiny");
  assert.equal(app.models[0].backend, "whisper-cpp");
});

test("model download and deletion keep their captured format", async () => {
  const app = appWithStorage({ getItem: () => null, setItem() {} });
  const urls = [];
  app.api = async (url) => {
    urls.push(url);
    if (url.startsWith("/api/models?")) return { models: [] };
    if (url === "/api/models/disk-usage") return { mb: 0 };
    return { status: "ok" };
  };

  await app.downloadModel("base", "whisper-cpp");
  await app.deleteModel("base", "whisper-cpp");

  assert.equal(
    urls[0],
    "/api/models/base/download?backend=whisper-cpp",
  );
  assert.ok(urls.includes("/api/models/base?backend=whisper-cpp"));
});

test("switching to whisper.cpp selects Vulkan and a compatible model", async () => {
  const app = appWithStorage({ getItem: () => null, setItem() {} });
  const saved = [];
  app.config.stt = {
    backend: "whisper-cpp",
    device: "cuda",
    compute_type: "float16",
    model: "distil-large-v3",
  };
  app.api = async (url, options = {}) => {
    if (url.startsWith("/api/models?")) return { models: [] };
    if (url === "/api/config") {
      saved.push(JSON.parse(options.body));
      return { status: "ok" };
    }
    throw new Error(`Unexpected request: ${url}`);
  };

  await app.selectSttBackend();

  assert.equal(app.config.stt.device, "vulkan");
  assert.equal(app.config.stt.compute_type, "auto");
  assert.equal(app.config.stt.model, "base");
  assert.equal(app.modelBackend, "whisper-cpp");
  assert.equal(saved.length, 1);
});

test("a completed settings save refreshes active models on the models page", async () => {
  const app = appWithStorage({ getItem: () => null, setItem() {} });
  const urls = [];
  app.currentPage = "models";
  app.modelBackend = "whisper-cpp";
  app.config.stt = {
    backend: "whisper-cpp",
    device: "vulkan",
    compute_type: "auto",
    model: "tiny",
  };
  app.models = [{ name: "base", active: true, backend: "whisper-cpp" }];
  app.api = async (url) => {
    urls.push(url);
    if (url === "/api/config") return { status: "ok" };
    if (url === "/api/models?backend=whisper-cpp") {
      return {
        models: [{ name: "tiny", active: true, downloaded: true }],
      };
    }
    throw new Error(`Unexpected request: ${url}`);
  };

  await app.saveConfig();

  assert.deepEqual(urls, ["/api/config", "/api/models?backend=whisper-cpp"]);
  assert.equal(app.models.length, 1);
  assert.equal(app.models[0].name, "tiny");
  assert.equal(app.models[0].active, true);
});

test("preload settings autosave with the selected residency duration", async () => {
  const app = appWithStorage({ getItem: () => null, setItem() {} });
  const saved = [];
  app.config = {
    stt: { model: "small" },
    audio: { silence_duration: 2.0 },
    preload_models: false,
    ai: { backend: "ollama", keep_alive_minutes: 30 },
  };
  app.api = async (url, options = {}) => {
    assert.equal(url, "/api/config");
    saved.push(JSON.parse(options.body));
    return { status: "ok" };
  };

  await app.saveConfig();

  assert.equal(saved[0].preload_models, false);
  assert.equal(saved[0].ai.keep_alive_minutes, 30);
  assert.equal(saved[0].stt.model, "small");
  assert.equal(saved[0].audio.silence_duration, 2.0);
});

test("Ollama keeps a separate model choice for each AI backend", async () => {
  const app = appWithStorage({ getItem: () => null, setItem() {} });
  const saved = [];
  app.config.ai = { backend: "openai", model: "gpt-4o-mini" };
  app.rememberCurrentAiModel();
  app.api = async (url, options = {}) => {
    if (url === "/api/ollama/models") {
      return {
        available: true,
        models: [{ name: "qwen3:8b", parameter_size: "8B" }],
        recommended: [
          {
            name: "qwen3:8b",
            installed: true,
            size_gb: 5.2,
            description:
              "Balanced multilingual refinement; recommended starting point.",
          },
        ],
        error: null,
        warnings: [],
      };
    }
    if (url === "/api/config") {
      saved.push(JSON.parse(options.body));
      return { status: "ok" };
    }
    throw new Error(`Unexpected request: ${url}`);
  };

  app.config.ai.backend = "ollama";
  await app.selectAiBackend();
  assert.equal(app.config.ai.model, "");
  assert.equal(saved[saved.length - 1].ai.model, "");

  await app.selectOllamaModel("qwen3:8b");
  assert.equal(app.config.ai.model, "qwen3:8b");

  app.config.ai.backend = "openai";
  await app.selectAiBackend();
  assert.equal(app.config.ai.model, "gpt-4o-mini");

  app.config.ai.backend = "ollama";
  await app.selectAiBackend();
  assert.equal(app.config.ai.model, "qwen3:8b");

  const savesBeforeUninstalledRecommendation = saved.length;
  await app.useOllamaRecommendation({ name: "gemma3:12b", installed: false });
  assert.equal(saved.length, savesBeforeUninstalledRecommendation);
  assert.equal(app.ollamaPullCommand("gemma3:12b"), "ollama pull gemma3:12b");
});

test("stale Ollama catalog responses cannot replace a later backend choice", async () => {
  const app = appWithStorage({ getItem: () => null, setItem() {} });
  let resolveCatalog;
  app.config.ai = { backend: "ollama", model: "configured-but-missing" };
  app.rememberCurrentAiModel();
  app.api = (url, options = {}) => {
    if (url === "/api/ollama/models") {
      return new Promise((resolve) => {
        resolveCatalog = resolve;
      });
    }
    if (url === "/api/config") {
      return Promise.resolve({ status: "ok", options });
    }
    throw new Error(`Unexpected request: ${url}`);
  };

  const catalogRequest = app.loadOllamaModels();
  app.config.ai.backend = "openai";
  await app.selectAiBackend();
  resolveCatalog({
    available: true,
    models: [{ name: "qwen3:8b" }],
    recommended: [],
    error: null,
    warnings: [],
  });
  await catalogRequest;

  assert.equal(app.config.ai.model, "");
  assert.equal(app.ollamaCatalog.models.length, 0);
});

test("Ollama keeps a configured model visible when discovery does not list it", () => {
  const app = appWithStorage({ getItem: () => null, setItem() {} });
  app.config.ai = { backend: "ollama", model: "configured-but-missing" };
  app.ollamaCatalog.models = [{ name: "qwen3:8b" }];

  assert.equal(app.hasUnavailableOllamaModel(), true);
  assert.equal(app.config.ai.model, "configured-but-missing");
});

test("Ollama picker filters metadata and only commits installed models or clear", async () => {
  const app = appWithStorage({ getItem: () => null, setItem() {} });
  let saves = 0;
  app.config.ai = { backend: "ollama", model: "configured-but-missing" };
  app.ollamaCatalog.models = [
    { name: "qwen3:8b", parameter_size: "8B", quantization_level: "Q4_K_M" },
    { name: "gemma3:12b", parameter_size: "12B", quantization_level: "Q8_0" },
  ];
  app.saveConfig = async () => {
    saves += 1;
  };

  app.ollamaModelQuery = "q8_0";
  assert.deepEqual(
    app.filteredOllamaInstalledModels().map((model) => model.name),
    ["gemma3:12b"],
  );
  assert.equal(app.ollamaModelDisplayValue(), "Unavailable model: configured-but-missing");

  app.openOllamaModelPicker();
  app.ollamaModelQuery = "12b";
  app.onOllamaModelSearchInput();
  app.moveOllamaModelPicker(1);
  await app.commitActiveOllamaModel();
  assert.equal(app.config.ai.model, "gemma3:12b");
  assert.equal(app.ollamaModelPickerOpen, false);
  assert.equal(saves, 1);

  await app.selectOllamaModel("not-installed");
  assert.equal(app.config.ai.model, "gemma3:12b");
  assert.equal(saves, 1);

  await app.commitOllamaModel("");
  assert.equal(app.config.ai.model, "");
  assert.equal(saves, 2);
});

test("dictation status distinguishes engine state from dashboard reachability", () => {
  const app = appWithStorage({ getItem: () => null, setItem() {} });
  app.status = {
    status: "running",
    runtime: { available: true, state: "idle", models_preparing: true },
  };
  assert.equal(app.dictationStatusLabel(), "Preparing models");
  app.status.runtime.state = "recording";
  assert.equal(app.dictationStatusLabel(), "Recording");
  app.status.runtime.state = "processing";
  assert.equal(app.dictationStatusLabel(), "Processing");
  app.status.runtime.state = "error";
  assert.equal(app.dictationStatusLabel(), "Dictation unavailable");
  app.errors.status = "Could not check the dashboard connection.";
  assert.equal(app.dictationStatusLabel(), "Panel unavailable");
});

test("status refresh serializes preparation transitions and releases its timer", async () => {
  const callbacks = [];
  const cleared = [];
  const app = appWithStorage(
    { getItem: () => null, setItem() {} },
    {
      window: {
        setInterval(callback) {
          callbacks.push(callback);
          return callback;
        },
        clearInterval(timer) {
          cleared.push(timer);
        },
      },
    },
  );
  const responses = [];
  app.api = () =>
    new Promise((resolve) => {
      responses.push(resolve);
    });

  const preparing = app.loadStatus();
  const duplicate = app.loadStatus();
  assert.equal(preparing, duplicate);
  assert.equal(responses.length, 1);
  responses.shift()({
    status: "running",
    runtime: { available: true, state: "idle", models_preparing: true },
  });
  await preparing;
  assert.equal(app.dictationStatusLabel(), "Preparing models");

  const ready = app.loadStatus();
  responses.shift()({
    status: "running",
    runtime: { available: true, state: "idle", models_preparing: false },
  });
  await ready;
  assert.equal(app.dictationStatusLabel(), "Dictation ready");

  app.startStatusRefresh();
  app.destroy();
  assert.equal(callbacks.length, 1);
  assert.equal(cleared.length, 1);
});

test("status refresh pauses while the dashboard tab is hidden", () => {
  const document = { visibilityState: "hidden" };
  const callbacks = [];
  const cleared = [];
  const app = appWithStorage(
    { getItem: () => null, setItem() {} },
    {
      document,
      window: {
        setInterval(callback) {
          callbacks.push(callback);
          return callback;
        },
        clearInterval(timer) {
          cleared.push(timer);
        },
      },
    },
  );
  app.api = async () => ({
    status: "running",
    runtime: { available: true, state: "idle", models_preparing: false },
  });

  app.startStatusRefresh();
  assert.equal(callbacks.length, 0);
  document.visibilityState = "visible";
  app.handleStatusVisibilityChange();
  assert.equal(callbacks.length, 1);
  document.visibilityState = "hidden";
  app.handleStatusVisibilityChange();
  assert.equal(cleared.length, 1);
});

test("dictionary pack save failure restores server state and ignores a duplicate toggle", async () => {
  const app = appWithStorage({ getItem: () => null, setItem() {} });
  app.dictionary = {
    entries: [],
    corrections: [],
    packs: [{ id: "coding", enabled: false }],
  };
  let saves = 0;
  let reloads = 0;
  app.api = async () => {
    saves += 1;
    throw new Error("request-failed");
  };
  app.loadDictionary = async () => {
    reloads += 1;
    app.dictionary = {
      entries: [],
      corrections: [],
      packs: [{ id: "coding", enabled: false }],
    };
    return app.dictionary;
  };

  const firstSave = app.setDictionaryPack(app.dictionary.packs[0], true);
  const duplicateSave = app.setDictionaryPack(app.dictionary.packs[0], true);
  await Promise.all([firstSave, duplicateSave]);

  assert.equal(saves, 1);
  assert.equal(reloads, 1);
  assert.equal(app.dictionary.packs[0].enabled, false);
  assert.equal(app.dictionaryPackBusy.coding, undefined);
  assert.equal(
    app.dictionaryPackErrors.coding,
    "Could not update dictionary pack.",
  );
});

test("dictionary imports show bounded server details and clear them on a new request", async () => {
  let detail = "x".repeat(501);
  let responseKind = "json";
  const app = appWithStorage(
    { getItem: () => null, setItem() {} },
    {
      fetch: async () => {
        if (responseKind === "connection") throw new Error("offline");
        return {
          ok: false,
          text: async () =>
            responseKind === "json" ? JSON.stringify({ detail }) : "not JSON",
        };
      },
    },
  );

  await assert.rejects(app.api("/api/dictionary/import/preview"), (error) => {
    assert.equal(error.message, "request-failed");
    assert.equal(error.detail, detail.slice(0, 500));
    return true;
  });

  detail = "Dictionary URLs must use a public hostname, not an IP address.";
  await app.requestDictionaryImportPreview(() =>
    app.api("/api/dictionary/import/preview"),
  );
  assert.equal(app.dictionaryImportError, "Could not preview dictionary.");
  assert.equal(app.dictionaryImportErrorDetail, detail);

  app.invalidateDictionaryImportPreview();
  assert.equal(app.dictionaryImportErrorDetail, "");

  responseKind = "connection";
  await app.requestDictionaryImportPreview(() =>
    app.api("/api/dictionary/import/preview"),
  );
  assert.equal(app.dictionaryImportError, "Could not preview dictionary.");
  assert.equal(app.dictionaryImportErrorDetail, "");

  responseKind = "json";
  detail = "Community dictionary preview is stale.";
  app.dictionaryImportToken = "preview-token";
  app.dictionaryImportPreview = {};
  await app.confirmDictionaryImport();
  assert.equal(app.dictionaryImportError, "Could not save community dictionary.");
  assert.equal(app.dictionaryImportErrorDetail, detail);
});

test("first-run detection is read-only and existing configurations do not auto-detect", async () => {
  const firstRun = appWithStorage({ getItem: () => null, setItem() {} });
  const calls = [];
  firstRun.pageForPath = () => "dashboard";
  firstRun.attachConfirmationDialogListener = () => {};
  firstRun.loadStatus = async () => {};
  firstRun.loadStats = async () => {};
  firstRun.loadConfig = async () => {
    firstRun.config = { first_run: true, stt: {} };
  };
  firstRun.loadHistory = async () => {};
  firstRun.loadRecentHistory = async () => {};
  firstRun.loadDictionary = async () => {};
  firstRun.loadSnippets = async () => {};
  firstRun.loadModels = async () => {};
  firstRun.loadDiskUsage = async () => {};
  firstRun.api = async (url) => {
    calls.push(url);
    return {
      status: "ok",
      hardware: { cpu_threads: 8, ram_total_mb: 8192, gpus: [] },
      recommendation: {
        backend: "faster-whisper",
        model: "small",
        device: "cpu",
        compute_type: "int8",
        downloaded: false,
      },
      warnings: [],
    };
  };
  await firstRun.init();
  assert.deepEqual(calls, ["/api/setup/detect"]);
  assert.equal(firstRun.config.first_run, true);

  const existing = appWithStorage({ getItem: () => null, setItem() {} });
  existing.pageForPath = () => "dashboard";
  existing.attachConfirmationDialogListener = () => {};
  existing.loadStatus = async () => {};
  existing.loadStats = async () => {};
  existing.loadConfig = async () => {
    existing.config = { first_run: false, stt: {} };
  };
  existing.loadHistory = async () => {};
  existing.loadRecentHistory = async () => {};
  existing.loadDictionary = async () => {};
  existing.loadSnippets = async () => {};
  existing.loadModels = async () => {};
  existing.loadDiskUsage = async () => {};
  existing.api = async () => {
    throw new Error("existing installations must not auto-detect");
  };
  await existing.init();

  const manualCalls = [];
  existing.api = async (url) => {
    manualCalls.push(url);
    return {
      status: "ok",
      hardware: { cpu_threads: 4, ram_total_mb: null, gpus: [] },
      recommendation: {
        backend: "faster-whisper",
        model: "base",
        device: "cpu",
        compute_type: "int8",
        downloaded: false,
      },
      warnings: ["ram_unknown"],
    };
  };
  await existing.detectOptimalSetup();
  assert.deepEqual(manualCalls, ["/api/setup/detect"]);
  assert.equal(existing.config.first_run, false);
});

test("a stale detection response cannot replace the newer recommendation", async () => {
  const app = appWithStorage({ getItem: () => null, setItem() {} });
  const pending = [];
  app.api = () =>
    new Promise((resolve) => {
      pending.push(resolve);
    });

  const first = app.detectOptimalSetup();
  const second = app.detectOptimalSetup();
  pending[1]({
    status: "ok",
    hardware: { cpu_threads: 8, gpus: [] },
    recommendation: { model: "small", downloaded: false },
    warnings: [],
  });
  await second;
  pending[0]({
    status: "ok",
    hardware: { cpu_threads: 1, gpus: [] },
    recommendation: { model: "tiny", downloaded: false },
    warnings: [],
  });
  await first;

  assert.equal(app.setup.detection.recommendation.model, "small");
  assert.equal(app.loading.setup, false);
});

test("a failed setup save restores only recommendation-owned settings", async () => {
  const app = appWithStorage({ getItem: () => null, setItem() {} });
  const original = {
    first_run: true,
    stt: {
      backend: "faster-whisper",
      model: "base",
      device: "cpu",
      compute_type: "int8",
      language: "pt",
    },
  };
  app.config = JSON.parse(JSON.stringify(original));
  app.setup.detection = {
    recommendation: {
      backend: "whisper-cpp",
      model: "base",
      device: "vulkan",
      compute_type: "auto",
      downloaded: true,
    },
  };
  app.loadModels = async () => {};
  app.loadDiskUsage = async () => {};
  const calls = [];
  app.api = async (url) => {
    calls.push(url);
    if (url.includes("/download?")) return { status: "ok" };
    throw new Error("save failed");
  };

  await app.applyOptimalSetup();

  assert.deepEqual(JSON.parse(JSON.stringify(app.config)), original);
  assert.deepEqual(calls, [
    "/api/models/base/download?backend=whisper-cpp",
    "/api/config",
  ]);
  assert.equal(app.errors.setup, "Could not apply the recommended setup.");
  assert.equal(app.setup.success, "");
});

test("a failed setup download leaves the current configuration untouched", async () => {
  const app = appWithStorage({ getItem: () => null, setItem() {} });
  const original = {
    first_run: true,
    stt: { backend: "faster-whisper", model: "base", language: "de" },
    audio: { vad_threshold: 0.4 },
  };
  app.config = JSON.parse(JSON.stringify(original));
  app.setup.detection = {
    recommendation: {
      backend: "whisper-cpp",
      model: "small",
      device: "vulkan",
      compute_type: "auto",
      downloaded: false,
    },
  };
  const calls = [];
  app.api = async (url) => {
    calls.push(url);
    throw new Error("download failed");
  };

  await app.applyOptimalSetup();

  assert.deepEqual(app.config, original);
  assert.deepEqual(calls, ["/api/models/small/download?backend=whisper-cpp"]);
  assert.equal(app.errors.setup, "Could not apply the recommended setup.");
});

test("setup download completes before it saves only recommended STT fields", async () => {
  const app = appWithStorage({ getItem: () => null, setItem() {} });
  app.config = {
    first_run: true,
    stt: {
      backend: "faster-whisper",
      model: "base",
      device: "cpu",
      compute_type: "int8",
      language: "de",
      prompt: "project terms",
    },
    audio: { vad_threshold: 0.4 },
    custom_setting: "preserved",
  };
  app.setup.detection = {
    recommendation: {
      backend: "whisper-cpp",
      model: "small",
      device: "vulkan",
      compute_type: "auto",
      downloaded: false,
    },
  };
  const calls = [];
  let saved;
  app.loadModels = async () => {};
  app.loadDiskUsage = async () => {};
  app.selectModelBackend = () => {};
  app.api = async (url, options = {}) => {
    calls.push(url);
    if (url.includes("/download?")) return { status: "ok" };
    if (url === "/api/config") {
      saved = JSON.parse(options.body);
      return { status: "ok" };
    }
    throw new Error(`Unexpected request: ${url}`);
  };

  await app.applyOptimalSetup();

  assert.deepEqual(calls, [
    "/api/models/small/download?backend=whisper-cpp",
    "/api/config",
  ]);
  assert.deepEqual(saved.stt, {
    backend: "whisper-cpp",
    model: "small",
    device: "vulkan",
    compute_type: "auto",
    language: "de",
    prompt: "project terms",
  });
  assert.equal(saved.first_run, false);
  assert.deepEqual(saved.audio, { vad_threshold: 0.4 });
  assert.equal(saved.custom_setting, "preserved");
  assert.equal(
    app.setup.success,
    "Setup saved. Restart LinuxWhispr to activate the recommendation.",
  );
});

test("a setup save queued behind an older draft persists the recommendation last", async () => {
  const app = appWithStorage({ getItem: () => null, setItem() {} });
  app.config = {
    first_run: true,
    stt: { backend: "faster-whisper", model: "base", language: "en" },
    audio: { gain: 1 },
  };
  const writes = [];
  let releaseFirstWrite;
  app.api = (url, options = {}) => {
    if (url.includes("/download?")) return Promise.resolve({ status: "ok" });
    assert.equal(url, "/api/config");
    writes.push(JSON.parse(options.body));
    if (writes.length === 1) {
      return new Promise((resolve) => {
        releaseFirstWrite = () => resolve({ status: "ok" });
      });
    }
    return Promise.resolve({ status: "ok" });
  };
  app.loadModels = async () => {};
  app.loadDiskUsage = async () => {};
  app.selectModelBackend = () => {};
  const oldSave = app.saveConfig();
  app.config.audio.gain = 2;
  app.setup.detection = {
    recommendation: {
      backend: "whisper-cpp",
      model: "base",
      device: "vulkan",
      compute_type: "auto",
      downloaded: true,
    },
  };
  const apply = app.applyOptimalSetup();
  releaseFirstWrite();
  await Promise.all([oldSave, apply]);

  assert.equal(writes.length, 2);
  assert.equal(writes[0].first_run, true);
  assert.equal(writes[1].first_run, false);
  assert.equal(writes[1].audio.gain, 2);
  assert.deepEqual(writes[1].stt, {
    backend: "whisper-cpp",
    model: "base",
    language: "en",
    device: "vulkan",
    compute_type: "auto",
  });
});

test("a later queued save failure does not undo a successful setup save", async () => {
  const app = appWithStorage({ getItem: () => null, setItem() {} });
  app.config = {
    first_run: true,
    stt: {
      backend: "faster-whisper",
      model: "base",
      device: "cpu",
      compute_type: "int8",
      language: "en",
    },
  };
  app.setup.detection = {
    recommendation: {
      backend: "whisper-cpp",
      model: "small",
      device: "vulkan",
      compute_type: "auto",
      downloaded: true,
    },
  };
  app.loadModels = async () => {};
  app.loadDiskUsage = async () => {};
  app.selectModelBackend = () => {};
  const writes = [];
  let releaseSetupWrite;
  let setupWriteStarted;
  const setupStarted = new Promise((resolve) => {
    setupWriteStarted = resolve;
  });
  app.api = (url, options = {}) => {
    if (url.includes("/download?")) return Promise.resolve({ status: "ok" });
    writes.push(JSON.parse(options.body));
    if (writes.length === 1) {
      setupWriteStarted();
      return new Promise((resolve) => {
        releaseSetupWrite = () => resolve({ status: "ok" });
      });
    }
    return Promise.reject(new Error("later settings save failed"));
  };

  const apply = app.applyOptimalSetup();
  await setupStarted;
  app.config.stt.language = "de";
  const laterSave = app.saveConfig();
  releaseSetupWrite();
  await Promise.all([apply, laterSave]);

  assert.equal(app.errors.setup, "");
  assert.equal(
    app.setup.success,
    "Setup saved. Restart LinuxWhispr to activate the recommendation.",
  );
  assert.equal(app.config.first_run, false);
  assert.deepEqual({ ...app.config.stt }, {
    backend: "whisper-cpp",
    model: "small",
    device: "vulkan",
    compute_type: "auto",
    language: "de",
  });
  assert.equal(writes.length, 2);
});

test("a failed setup save preserves a newer language draft in queued snapshots", async () => {
  const app = appWithStorage({ getItem: () => null, setItem() {} });
  app.config = {
    first_run: true,
    stt: {
      backend: "faster-whisper",
      model: "base",
      device: "cpu",
      compute_type: "int8",
      language: "en",
    },
    audio: { gain: 1 },
  };
  app.setup.detection = {
    recommendation: {
      backend: "whisper-cpp",
      model: "small",
      device: "vulkan",
      compute_type: "auto",
      downloaded: true,
    },
  };
  app.loadModels = async () => {};
  app.loadDiskUsage = async () => {};
  const writes = [];
  let rejectSetupWrite;
  let setupWriteStarted;
  const setupStarted = new Promise((resolve) => {
    setupWriteStarted = resolve;
  });
  app.api = (url, options = {}) => {
    if (url.includes("/download?")) return Promise.resolve({ status: "ok" });
    writes.push(JSON.parse(options.body));
    if (writes.length === 1) {
      setupWriteStarted();
      return new Promise((_, reject) => {
        rejectSetupWrite = () => reject(new Error("setup save failed"));
      });
    }
    return Promise.resolve({ status: "ok" });
  };

  const apply = app.applyOptimalSetup();
  await setupStarted;
  app.config.stt.language = "de";
  const laterSave = app.saveConfig();
  rejectSetupWrite();
  await Promise.all([apply, laterSave]);

  assert.equal(app.errors.setup, "Could not apply the recommended setup.");
  assert.equal(app.config.first_run, true);
  assert.deepEqual({ ...app.config.stt }, {
    backend: "faster-whisper",
    model: "base",
    device: "cpu",
    compute_type: "int8",
    language: "de",
  });
  assert.deepEqual(writes[1].stt, { ...app.config.stt });
  assert.equal(writes[1].first_run, true);
});

test("apply is ignored while a newer setup detection is pending", async () => {
  const app = appWithStorage({ getItem: () => null, setItem() {} });
  app.config = { first_run: true, stt: { backend: "faster-whisper" } };
  app.setup.detection = {
    recommendation: {
      backend: "whisper-cpp",
      model: "base",
      device: "vulkan",
      compute_type: "auto",
      downloaded: true,
    },
  };
  let resolveDetection;
  app.api = () =>
    new Promise((resolve) => {
      resolveDetection = resolve;
    });

  const detection = app.detectOptimalSetup();
  await app.applyOptimalSetup();
  resolveDetection({
    status: "ok",
    hardware: { cpu_threads: 8, gpus: [] },
    recommendation: {
      backend: "faster-whisper",
      model: "small",
      device: "cpu",
      compute_type: "int8",
      downloaded: false,
    },
    warnings: [],
  });
  await detection;

  assert.equal(app.config.first_run, true);
  assert.equal(app.config.stt.backend, "faster-whisper");
  assert.equal(app.setup.detection.recommendation.model, "small");
});

test("apply verifies a stale downloaded recommendation before saving", async () => {
  const app = appWithStorage({ getItem: () => null, setItem() {} });
  app.config = {
    first_run: true,
    stt: { backend: "faster-whisper", model: "base" },
  };
  app.setup.detection = {
    recommendation: {
      backend: "whisper-cpp",
      model: "small",
      device: "vulkan",
      compute_type: "auto",
      downloaded: true,
    },
  };
  app.loadModels = async () => {};
  app.loadDiskUsage = async () => {};
  app.selectModelBackend = () => {};
  const calls = [];
  app.api = async (url, options = {}) => {
    calls.push(url);
    if (url.includes("/download?")) return { status: "ok" };
    if (url === "/api/config") {
      assert.equal(JSON.parse(options.body).stt.model, "small");
      return { status: "ok" };
    }
    throw new Error(`Unexpected request: ${url}`);
  };

  await app.applyOptimalSetup();

  assert.deepEqual(calls, [
    "/api/models/small/download?backend=whisper-cpp",
    "/api/config",
  ]);
  assert.equal(app.errors.setup, "");
});

test("setup memory leaves unavailable values unknown and formats gigabytes", () => {
  const app = appWithStorage({ getItem: () => null, setItem() {} });

  assert.equal(app.setupMemory(null), "Unknown");
  assert.equal(app.setupMemory(undefined), "Unknown");
  assert.equal(app.setupMemory(0), "0.0 GB");
  assert.equal(app.setupMemory(96335), "101.0 GB");
  app.uiLanguage = "de";
  assert.equal(app.setupMemory(96335), "101,0 GB");
});
