"""Curated, opt-in vocabulary packs for dictation correction.

The entries here are bundled application data, not user dictionary entries.  They
are deliberately conservative: aliases express only high-confidence spoken or
segmented variants, while terms without aliases contribute recognition hints.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PackTerm:
    """One canonical word or product name and its explicit spoken aliases."""

    word: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class DictionaryPack:
    """A selectable collection of domain vocabulary."""

    id: str
    name: str
    description: str
    terms: tuple[PackTerm, ...]
    sources: tuple[tuple[str, str], ...]


_WISPER_DEVELOPER = (
    "Wisper developer profile (inspiration)",
    "https://github.com/taraksh01/wisper/blob/main/src-tauri/resources/profiles/developer.json",
)
_WISPER_EMAIL = (
    "Wisper email profile (inspiration)",
    "https://github.com/taraksh01/wisper/blob/main/src-tauri/resources/profiles/email.json",
)
_VOXTYPE_MANUAL = (
    "Voxtype user manual (context-hint inspiration)",
    "https://github.com/peteonrails/voxtype/blob/main/docs/USER_MANUAL.md",
)
_DUDEN_EMAIL = (
    "Duden: E-Mail (German spelling reference)",
    "https://www.duden.de/rechtschreibung/E_Mail",
)
_DUDEN_CONTACT = (
    "Duden: Ansprechpartner (German spelling reference)",
    "https://www.duden.de/rechtschreibung/Ansprechpartner",
)


BUNDLED_PACKS: tuple[DictionaryPack, ...] = (
    DictionaryPack(
        id="coding",
        name="Coding",
        description="Programming languages, frameworks, databases, and developer tools.",
        terms=(
            PackTerm("Python"),
            PackTerm("JavaScript", ("java script",)),
            PackTerm("TypeScript", ("type script",)),
            PackTerm("Go"),
            PackTerm("Rust"),
            PackTerm("React"),
            PackTerm("FastAPI", ("fast a p i", "fast api")),
            PackTerm("Django"),
            PackTerm("Flask"),
            PackTerm("Next.js", ("next js",)),
            PackTerm("Node.js", ("node js",)),
            PackTerm("npm", ("n p m",)),
            PackTerm("pnpm", ("p n p m",)),
            PackTerm("pip"),
            PackTerm("PyPI", ("pie p i",)),
            PackTerm("VS Code", ("v s code",)),
            PackTerm("GitHub", ("git hub",)),
            PackTerm("GitLab", ("git lab",)),
            PackTerm("Stack Overflow", ("stack overflow",)),
            PackTerm("PostgreSQL", ("post gres", "postgress")),
            PackTerm("MySQL", ("my sequel",)),
            PackTerm("SQLite", ("s q l lite", "sql lite")),
            PackTerm("MongoDB", ("mongo d b",)),
            PackTerm("Redis"),
            PackTerm("GraphQL", ("graph q l",)),
            PackTerm("REST API", ("rest a p i",)),
            PackTerm("JSON", ("j s o n",)),
            PackTerm("YAML", ("yamel",)),
            PackTerm("XML", ("x m l",)),
            PackTerm("HTML", ("h t m l",)),
            PackTerm("CSS", ("c s s",)),
            PackTerm("HTTP", ("h t t p",)),
            PackTerm("HTTPS", ("h t t p s",)),
            PackTerm("OAuth", ("o auth",)),
            PackTerm("WebSocket", ("web socket",)),
            PackTerm("Linux"),
            PackTerm("macOS", ("mac o s",)),
            PackTerm("API", ("a p i",)),
            PackTerm("CLI", ("c l i",)),
            PackTerm("C++", ("c plus plus",)),
            PackTerm("C#", ("c sharp",)),
            PackTerm("regex"),
        ),
        sources=(_WISPER_DEVELOPER,),
    ),
    DictionaryPack(
        id="devops",
        name="DevOps",
        description="Infrastructure, deployment, observability, and operations vocabulary.",
        terms=(
            PackTerm("Docker"),
            PackTerm("Dockerfile", ("docker file",)),
            PackTerm("Docker Compose", ("docker compose",)),
            PackTerm("kubectl", ("cube control", "cube ctl")),
            PackTerm("Kubernetes", ("kubernates", "koobernetes")),
            PackTerm("Terraform", ("terra form",)),
            PackTerm("Ansible"),
            PackTerm("systemd"),
            PackTerm("CI/CD", ("c i slash c d",)),
            PackTerm("GitHub Actions"),
            PackTerm("GitLab CI"),
            PackTerm("Jenkins"),
            PackTerm("Nginx", ("engine x",)),
            PackTerm("Apache"),
            PackTerm("Helm"),
            PackTerm("Kustomize"),
            PackTerm("Prometheus"),
            PackTerm("Grafana"),
            PackTerm("ELK Stack"),
            PackTerm("Elasticsearch"),
            PackTerm("Logstash"),
            PackTerm("Kibana"),
            PackTerm("AWS", ("a w s",)),
            PackTerm("Azure"),
            PackTerm("Google Cloud"),
            PackTerm("Cloudflare", ("cloud flare",)),
            PackTerm("S3", ("s three",)),
            PackTerm("SSH", ("s s h",)),
            PackTerm("TLS", ("t l s",)),
            PackTerm("VPN", ("v p n",)),
            PackTerm("Bash"),
        ),
        sources=(_WISPER_DEVELOPER,),
    ),
    DictionaryPack(
        id="ai",
        name="AI",
        description="Machine-learning models, tools, and retrieval terminology.",
        terms=(
            PackTerm("OpenAI", ("open a i", "open ai")),
            PackTerm("Ollama", ("ol lama", "ollama")),
            PackTerm("ChatGPT", ("chat g p t", "chat gpt")),
            PackTerm("GPT", ("g p t",)),
            PackTerm("LLM", ("l l m",)),
            PackTerm("RAG", ("r a g",)),
            PackTerm("PyTorch", ("pie torch", "py torch")),
            PackTerm("TensorFlow", ("tensor flow",)),
            PackTerm("Hugging Face", ("huggingface",)),
            PackTerm("LangChain", ("lang chain",)),
            PackTerm("Transformers"),
            PackTerm("embeddings"),
            PackTerm("fine-tuning", ("fine tuning",)),
            PackTerm("inference"),
            PackTerm("tokenizer"),
            PackTerm("tokenization"),
            PackTerm("vector database"),
            PackTerm("Qdrant"),
            PackTerm("Chroma"),
            PackTerm("Milvus"),
            PackTerm("Mistral AI"),
            PackTerm("Anthropic"),
            PackTerm("Claude"),
            PackTerm("Gemini"),
            PackTerm("Llama"),
            PackTerm("LoRA", ("l o r a",)),
            PackTerm("vLLM", ("v l l m",)),
            PackTerm("CUDA", ("c u d a",)),
        ),
        sources=(_VOXTYPE_MANUAL,),
    ),
    DictionaryPack(
        id="email",
        name="Email and office",
        description="Email clients, office applications, attachments, and common formats.",
        terms=(
            PackTerm("Microsoft Outlook", ("microsoft outlook",)),
            PackTerm("Thunderbird"),
            PackTerm("Gmail", ("g mail",)),
            PackTerm("Google Workspace"),
            PackTerm("PowerPoint", ("power point",)),
            PackTerm("SharePoint", ("share point",)),
            PackTerm("Microsoft Teams", ("microsoft teams",)),
            PackTerm("OneDrive", ("one drive",)),
            PackTerm("Microsoft 365", ("microsoft three sixty five",)),
            PackTerm("CC", ("c c",)),
            PackTerm("BCC", ("b c c",)),
            PackTerm("SMTP", ("s m t p",)),
            PackTerm("IMAP", ("i m a p",)),
            PackTerm("POP3", ("p o p three",)),
            PackTerm("PDF", ("p d f",)),
            PackTerm("DOCX", ("d o c x",)),
            PackTerm("XLSX", ("x l s x",)),
            PackTerm("PPTX", ("p p t x",)),
            PackTerm("iCalendar", ("i calendar",)),
            PackTerm("ICS", ("i c s",)),
            PackTerm("RSVP", ("r s v p",)),
            PackTerm("attachment", ("attachement",)),
            PackTerm("subject line"),
            PackTerm("recipient", ("recipent",)),
            PackTerm("signature"),
            PackTerm("calendar"),
            PackTerm("address", ("adress",)),
            PackTerm("receive", ("recieve",)),
        ),
        sources=(_WISPER_EMAIL,),
    ),
    DictionaryPack(
        id="de-business",
        name="German business",
        description="German business compounds and formal correspondence vocabulary.",
        terms=(
            PackTerm("E-Mail-Adresse", ("e mail adresse",)),
            PackTerm("E-Mail", ("e mail",)),
            PackTerm("Rückmeldung", ("rück meldung",)),
            PackTerm("Ansprechpartner", ("ansprech partner",)),
            PackTerm("Terminbestätigung", ("termin bestätigung",)),
            PackTerm("Besprechungsprotokoll", ("besprechungs protokoll",)),
            PackTerm("Projektleitung", ("projekt leitung",)),
            PackTerm("Geschäftsführung", ("geschäfts führung",)),
            PackTerm("Geschäftsbericht", ("geschäfts bericht",)),
            PackTerm("Zahlungsbedingungen", ("zahlungs bedingungen",)),
            PackTerm("Liefertermin", ("liefer termin",)),
            PackTerm("Angebotsnummer", ("angebots nummer",)),
            PackTerm("Rechnungsnummer", ("rechnungs nummer",)),
            PackTerm("Kundennummer", ("kunden nummer",)),
            PackTerm("Auftragsbestätigung", ("auftrags bestätigung",)),
            PackTerm("Datenschutzerklärung", ("datenschutz erklärung",)),
            PackTerm("Vertragsunterlagen", ("vertrags unterlagen",)),
            PackTerm("Zielvereinbarung", ("ziel vereinbarung",)),
            PackTerm("Prozessbeschreibung", ("prozess beschreibung",)),
            PackTerm("Qualitätsmanagement", ("qualitäts management",)),
            PackTerm("Unternehmensberatung", ("unternehmens beratung",)),
            PackTerm("Weiterbildungsmaßnahme", ("weiterbildungs maßnahme",)),
        ),
        sources=(_DUDEN_EMAIL, _DUDEN_CONTACT),
    ),
)
