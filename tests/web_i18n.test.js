"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const root = path.resolve(__dirname, "..");
const i18n = require(path.join(root, "src/linux_whispr/web/static/i18n.js"));

function appWithStorage(storage) {
  const context = {
    WhisprI18n: i18n,
    window: {
      WhisprI18n: i18n,
      localStorage: storage,
      matchMedia: () => ({ matches: false }),
    },
    localStorage: storage,
    document: {},
    HTMLElement: class HTMLElement {},
    navigator: {},
    clearTimeout() {},
    setTimeout() {
      return 1;
    },
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
  app.status = { status: "running", runtime: { available: true, state: "idle" } };
  assert.equal(app.dictationStatusLabel(), "Dictation ready");
  app.status.runtime.state = "recording";
  assert.equal(app.dictationStatusLabel(), "Recording");
  app.status.runtime.state = "processing";
  assert.equal(app.dictationStatusLabel(), "Processing");
  app.status.runtime.state = "error";
  assert.equal(app.dictationStatusLabel(), "Dictation unavailable");
  app.errors.status = "Could not check the dashboard connection.";
  assert.equal(app.dictationStatusLabel(), "Panel unavailable");
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
