from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Scenario:
    id: str
    label: str
    ai_context: str
    categories: tuple[str, ...]
    keywords: tuple[str, ...]


SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        "personal",
        "Home / Personal",
        "A normal home computer. Prioritise familiar everyday software such as a browser, writing/office tools, photos, video/music, books/podcasts, casual games and file handling. Keep specialist tools such as torrent clients, programming tools and advanced media editors in a separate advanced group.",
        ("Network", "Office", "Game", "AudioVideo", "Graphics", "FileManager", "WebBrowser", "Email", "Chat"),
        ("browser", "internet", "mail", "chat", "office", "document", "pdf", "photo", "image", "video", "music", "player", "game", "gaming", "ebook", "epub", "podcast", "file manager"),
    ),
    Scenario(
        "business",
        "Office / Business",
        "A business or office workstation. Prefer productivity, communication, document, collaboration, support and managed-workflow software.",
        ("Office", "Network", "Utility", "Settings", "FileManager", "WebBrowser"),
        ("office", "document", "mail", "calendar", "meeting", "remote", "support", "pdf", "scanner", "printer", "browser"),
    ),
    Scenario(
        "development",
        "Development / Engineering",
        "A development or engineering workstation. Prefer editors, IDEs, terminals, compilers, build tools, version control, debugging and technical utilities.",
        ("Development", "TextEditor", "TerminalEmulator", "System", "Utility", "IDE"),
        ("editor", "terminal", "developer", "development", "compiler", "debug", "git", "code", "ide", "build", "programming"),
    ),
    Scenario(
        "production",
        "Production / Industrial",
        "A production or industrial system. Prefer stable operational, diagnostic, device, maintenance, monitoring, support and controlled engineering software.",
        ("System", "Utility", "Settings", "Network", "Development"),
        ("monitor", "diagnostic", "device", "maintenance", "industrial", "production", "remote", "support", "terminal", "network", "scanner"),
    ),
    Scenario(
        "education",
        "School / Education",
        "A school or education workstation. Prefer learning, teaching, classroom, document, communication and accessible educational software while keeping administration and development tools explicit.",
        ("Education", "Office", "Network", "Utility", "AudioVideo", "Graphics"),
        ("school", "education", "learning", "teacher", "student", "classroom", "lesson", "tutor", "study", "document", "browser"),
    ),
    Scenario(
        "gaming_team",
        "Gaming / Team",
        "A gaming, e-sports or team system. Prefer games, communication, media, streaming, graphics, team utilities and performance tools.",
        ("Game", "AudioVideo", "Graphics", "Network", "Utility"),
        ("game", "gaming", "steam", "lutris", "discord", "chat", "stream", "record", "obs", "team", "voice"),
    ),
    Scenario(
        "custom",
        "Custom",
        "A custom-purpose system. Do not assume a specific use case; follow the user's explicit application and role requirements.",
        (),
        (),
    ),
)


def scenario_by_id(scenario_id: str) -> Scenario:
    return next((s for s in SCENARIOS if s.id == scenario_id), SCENARIOS[0])


def relevance_score(app: dict, scenario_id: str) -> int:
    """Return a small relevance score used only for Quick-view prioritisation.

    This does not grant permissions, remove packages or change the image. A user
    can always choose Show all applications.
    """
    scenario = scenario_by_id(scenario_id)
    if scenario.id == "custom":
        return 1

    categories = {str(x).casefold() for x in app.get("categories", [])}
    text = " ".join(
        [
            str(app.get("application", "")),
            str(app.get("description", "")),
            str(app.get("package", "")),
        ]
    ).casefold()

    score = 0
    wanted_categories = {x.casefold() for x in scenario.categories}
    score += 3 * len(categories & wanted_categories)
    score += sum(2 for word in scenario.keywords if word.casefold() in text)

    # Keep basic desktop utilities discoverable in every scenario.
    common = {"utility", "settings", "filemanager", "terminalemulator", "network", "webbrowser"}
    if categories & common:
        score += 1
    return score


SECTION_ORDER: tuple[str, ...] = (
    "Internet & Communication",
    "Office & Documents",
    "Education & Learning",
    "Games",
    "Media & Graphics",
    "Development",
    "System & Utilities",
    "Other",
)

SCENARIO_SECTION_ORDER: dict[str, tuple[str, ...]] = {
    "personal": (
        "Internet & Communication", "Office & Documents", "Games",
        "Media & Graphics", "System & Utilities", "Education & Learning", "Development", "Other",
    ),
    "business": (
        "Office & Documents", "Internet & Communication", "System & Utilities",
        "Development", "Media & Graphics", "Education & Learning", "Other", "Games",
    ),
    "development": (
        "Development", "System & Utilities", "Internet & Communication",
        "Office & Documents", "Media & Graphics", "Education & Learning", "Other", "Games",
    ),
    "production": (
        "System & Utilities", "Development", "Internet & Communication",
        "Office & Documents", "Education & Learning", "Other", "Media & Graphics", "Games",
    ),
    "education": (
        "Education & Learning", "Office & Documents", "Internet & Communication",
        "Media & Graphics", "System & Utilities", "Development", "Games", "Other",
    ),
    "gaming_team": (
        "Games", "Internet & Communication", "Media & Graphics",
        "System & Utilities", "Office & Documents", "Education & Learning", "Development", "Other",
    ),
    "custom": SECTION_ORDER,
}


def application_section(app: dict) -> str:
    """Map desktop-entry categories to a small human-facing section.

    This is presentation only. It never changes package selection or permissions.
    """
    categories = {str(x).casefold() for x in app.get("categories", [])}
    text = " ".join([
        str(app.get("application", "")), str(app.get("description", "")),
        str(app.get("package", "")),
    ]).casefold()

    if "game" in categories or any(x in text for x in (" game", "chess", "mahjong", "mines", "solitaire")):
        return "Games"
    if "education" in categories or any(x in text for x in ("education", "learning", "classroom", "teacher", "student", "tutor")):
        return "Education & Learning"
    if categories & {"office", "wordprocessor", "spreadsheet", "presentation", "database"} or "libreoffice" in text:
        return "Office & Documents"
    if categories & {"network", "webbrowser", "email", "chat", "instantmessaging", "telephony"} or any(
        x in text for x in ("browser", "internet", "mail", "chat", "torrent", "remote desktop")
    ):
        return "Internet & Communication"
    if categories & {"audiovideo", "audio", "video", "graphics", "photography", "player", "recorder"}:
        return "Media & Graphics"
    if categories & {"development", "ide", "texteditor", "building", "debugger"} or any(
        x in text for x in ("compiler", "debugger", "development", "programming", "source code")
    ):
        return "Development"
    if categories & {"utility", "settings", "system", "filemanager", "terminalemulator", "archiving", "filesystem"}:
        return "System & Utilities"
    return "Other"


def suite_group(app: dict) -> str:
    """Return a recognizable application-suite parent for compact presentation."""
    name = str(app.get("application", "")).casefold()
    package = str(app.get("package", "")).casefold()
    if name.startswith("libreoffice") or package.startswith("libreoffice"):
        return "LibreOffice"
    return ""


def section_order_for_scenario(scenario_id: str) -> tuple[str, ...]:
    return SCENARIO_SECTION_ORDER.get(scenario_id, SECTION_ORDER)


def personal_home_group(app: dict) -> tuple[str, str]:
    """Return a compact Home/Personal presentation group.

    Empty strings mean the app is intentionally hidden from the Home quick view.
    Search and Show all applications can still reveal it. This is presentation
    only and never changes the image.
    """
    categories = {str(x).casefold() for x in app.get("categories", [])}
    name = str(app.get("application", "")).casefold()
    package = str(app.get("package", "")).casefold()
    description = str(app.get("description", "")).casefold()
    text = " ".join((name, package, description))

    # Specialist tools first so they do not leak into the everyday groups.
    # Home / Personal deliberately treats the full LibreOffice suite as an
    # advanced optional suite; the lightweight everyday writing recommendation
    # is AbiWord.  This is presentation/recommendation logic only and does not
    # silently remove LibreOffice from the image.
    if "libreoffice" in text:
        return ("Specialised / Advanced", "Full office suites")

    if any(x in text for x in ("torrent", "bittorrent", "transmission", "qbittorrent", "deluge")):
        return ("Specialised / Advanced", "Torrent & file sharing")

    if (
        categories & {"development", "ide", "building", "debugger"}
        or any(x in text for x in ("programming", "source code", "compiler", "debugger", "developer", "web development", "vim", "emacs", "visual studio code", "vscode"))
    ):
        return ("Specialised / Advanced", "Programming & web development")

    if any(x in text for x in ("audacity", "kdenlive", "openshot", "obs studio", "blender", "ardour", "audio editor", "video editor", "multitrack", "non-linear editor")):
        return ("Specialised / Advanced", "Advanced audio & video editing")

    # Familiar day-to-day groups.
    if categories & {"webbrowser", "email", "chat", "instantmessaging", "telephony"} or any(
        x in text for x in ("firefox", "chromium", "browser", "mail", "email", "chat", "messenger")
    ):
        return ("Everyday essentials", "Internet, browser & email")

    if categories & {"office", "wordprocessor", "spreadsheet", "presentation", "database"} or "libreoffice" in text:
        return ("Everyday essentials", "Writing & office")

    if categories & {"graphics", "photography"} or any(x in text for x in ("image viewer", "photo viewer", "image editor", "gimp", "drawing")):
        return ("Everyday essentials", "Photos & images")

    if any(x in text for x in ("ebook", "e-book", "epub", "calibre", "podcast")):
        return ("Everyday essentials", "Books & podcasts")

    if categories & {"game"} or any(x in text for x in ("game", "chess", "mahjong", "mines", "solitaire")):
        return ("Everyday essentials", "Casual games")

    if categories & {"audio", "video", "player"} or any(x in text for x in ("media player", "video player", "music player", "vlc", "mpv", "smplayer")):
        return ("Everyday essentials", "Video & music")

    if categories & {"filemanager", "archiving", "filesystem"} or any(x in text for x in ("file manager", "archive manager", "backup")):
        return ("Everyday essentials", "Files & everyday tools")

    # A small technical catch-all for recognisably advanced desktop tools.
    if categories & {"terminalemulator", "system", "settings"}:
        return ("Specialised / Advanced", "Technical tools")

    return ("", "")


HOME_GROUP_DESCRIPTIONS: dict[str, str] = {
    "Everyday essentials": "Familiar programs most people use regularly.",
    "Specialised / Advanced": "Optional specialist tools for advanced or technical use.",
    "Internet, browser & email": "Web browsing, email and everyday internet communication.",
    "Writing & office": "Writing, documents, spreadsheets, presentations and office work.",
    "Photos & images": "View, organise or edit photos and images.",
    "Video & music": "Play everyday video, music and other media.",
    "Books & podcasts": "Read e-books or listen to and manage podcasts.",
    "Casual games": "Everyday games and light entertainment.",
    "Files & everyday tools": "File handling, archives and familiar everyday utilities.",
    "Full office suites": "Full multi-application office suites kept as optional advanced software for Home / Personal.",
    "Torrent & file sharing": "Peer-to-peer and specialised file-sharing tools.",
    "Programming & web development": "Editors, IDEs and tools for software or web development.",
    "Advanced audio & video editing": "Specialist audio/video creation and editing tools, such as Audacity when installed.",
    "Technical tools": "System and technical tools that most home users do not need every day.",
}


HOME_EVERYDAY_SUBGROUPS: tuple[str, ...] = (
    "Internet, browser & email",
    "Writing & office",
    "Photos & images",
    "Video & music",
    "Books & podcasts",
    "Casual games",
    "Files & everyday tools",
)

HOME_SPECIALIST_SUBGROUPS: tuple[str, ...] = (
    "Full office suites",
    "Torrent & file sharing",
    "Programming & web development",
    "Advanced audio & video editing",
    "Technical tools",
)


@dataclass(frozen=True)
class HomeRecommendation:
    role: str
    subgroup: str
    application: str
    package: str
    description: str
    categories: tuple[str, ...] = ()
    manager: str = "apt"
    aliases: tuple[str, ...] = ()
    bundle_relpath: str = ""
    bundle_sha256: str = ""
    documentation_label: str = ""
    documentation_relpath: str = ""
    documentation_sha256: str = ""
    repository_component: str = ""


HOME_RECOMMENDATIONS: tuple[HomeRecommendation, ...] = (
    HomeRecommendation(
        "browser", "Internet, browser & email", "Falkon", "falkon",
        "Lightweight Qt web browser for everyday web use.", ("Network", "WebBrowser"),
    ),
    HomeRecommendation(
        "email", "Internet, browser & email", "Evolution", "evolution",
        "Email, calendar and contacts for everyday communication.", ("Network", "Email", "Office"),
    ),
    HomeRecommendation(
        "writing", "Writing & office", "AbiWord", "abiword",
        "Lightweight word processor for everyday documents without a full office suite.", ("Office", "WordProcessor"),
    ),
    HomeRecommendation(
        "image_editing", "Photos & images", "KolourPaint", "kolourpaint",
        "Simple image editing and drawing for common home tasks.", ("Graphics",),
    ),
    HomeRecommendation(
        "video", "Video & music", "Haruna", "haruna",
        "Lightweight Qt video player based on mpv.", ("AudioVideo", "Video", "Player"),
    ),
    HomeRecommendation(
        "music", "Video & music", "Audacious", "audacious",
        "Fast, lightweight music player.", ("AudioVideo", "Audio", "Player"),
    ),
    HomeRecommendation(
        "ebooks", "Books & podcasts", "Foliate", "foliate",
        "Simple e-book reader for EPUB and common reading formats.", ("Office",),
    ),
    HomeRecommendation(
        "podcasts", "Books & podcasts", "gPodder", "gpodder",
        "Lightweight podcast client for subscriptions and episodes.", ("AudioVideo",),
    ),
    HomeRecommendation(
        "games", "Casual games", "Aisleriot", "aisleriot",
        "Classic solitaire card games for light entertainment.", ("Game",),
    ),
    HomeRecommendation(
        "file_manager", "Files & everyday tools", "PCManFM-Qt", "pcmanfm-qt",
        "Lightweight Qt file manager for browsing and managing files and folders.", ("System", "FileManager"),
    ),
)


def home_recommendations_supported(source: dict) -> bool:
    """Return True only for the repository target validated for Alpha 13.

    Alpha 13 intentionally does not guess package names for other Linux
    distributions or releases. More targets can be added once their native
    repository catalogue has been verified.
    """
    distribution = str(source.get("distribution", "")).strip().casefold()
    version = str(source.get("version", "")).strip()
    return distribution in {"ubuntu", "lubuntu"} and version.startswith("26.04")


def home_roles_for_app(app: dict) -> set[str]:
    """Identify the everyday Home/Personal roles an installed launcher covers."""
    categories = {str(x).casefold() for x in app.get("categories", [])}
    name = str(app.get("application", "")).casefold()
    package = str(app.get("package", "")).casefold()
    description = str(app.get("description", "")).casefold()
    text = " ".join((name, package, description))
    roles: set[str] = set()

    if "webbrowser" in categories or any(x in text for x in (
        "web browser", "browser", "firefox", "chromium", "chrome", "falkon", "epiphany",
    )):
        roles.add("browser")

    if "email" in categories or any(x in text for x in (
        "email client", "e-mail client", "mail client", "thunderbird", "evolution", "kmail",
    )):
        roles.add("email")

    # In Home / Personal the locked lightweight writing role is AbiWord.
    # LibreOffice remains discoverable as an installed advanced suite, but it
    # does not suppress the AbiWord recommendation.
    if "libreoffice" not in text and (
        "wordprocessor" in categories or any(x in text for x in (
            "word processor", "abiword", "writer word processor", "document editor",
        ))
    ):
        roles.add("writing")

    if any(x in text for x in (
        "kolourpaint", "krita", "gimp", "pinta", "image editor", "photo editor", "paint program", "drawing program",
    )):
        roles.add("image_editing")

    video_markers = ("video player", "haruna", "vlc", "smplayer", "celluloid", "dragon player", "mpv media player")
    if "video" in categories and "player" in categories or any(x in text for x in video_markers):
        roles.add("video")

    music_markers = ("music player", "audio player", "audacious", "rhythmbox", "strawberry", "clementine", "vlc")
    if "audio" in categories and "player" in categories or any(x in text for x in music_markers):
        roles.add("music")

    if any(x in text for x in ("ebook", "e-book", "epub", "foliate", "calibre")):
        roles.add("ebooks")

    if "podcast" in text or "gpodder" in text:
        roles.add("podcasts")

    if "game" in categories or any(x in text for x in ("solitaire", "aisleriot", "chess", "mahjong", "mines")):
        roles.add("games")

    if "filemanager" in categories or any(x in text for x in (
        "file manager", "pcmanfm", "dolphin file manager", "thunar", "nautilus", "nemo file manager",
    )):
        roles.add("file_manager")

    return roles


def missing_home_recommendations(
    apps: list[dict], source: dict, removed_packages: set[str] | None = None
) -> tuple[HomeRecommendation, ...]:
    """Return safe repository recommendations for currently missing home roles.

    Staged removals are treated as absent so the UI can reveal a replacement
    before the image is ever mutated. A package explicitly staged for removal
    is not immediately recommended again; the row's Keep control is the direct
    way to undo that decision.
    """
    if not home_recommendations_supported(source):
        return ()

    removed = {str(x).strip() for x in (removed_packages or set()) if str(x).strip()}
    covered: set[str] = set()
    for app in apps:
        package = str(app.get("package", "")).strip()
        if package and package in removed:
            continue
        covered.update(home_roles_for_app(app))

    return tuple(
        recommendation
        for recommendation in HOME_RECOMMENDATIONS
        if recommendation.role not in covered and recommendation.package not in removed
    )

# Alpha 15 extends the same visible recommendation model to the remaining
# built-in scenarios.  Nothing is silently installed: every entry still uses
# Skip | Add and becomes a staged change first.  Repository names below are
# limited to the currently validated Ubuntu/Lubuntu 26.04 target.
SCENARIO_RECOMMENDATIONS: dict[str, tuple[HomeRecommendation, ...]] = {
    "business": (
        HomeRecommendation(
            "business_writing", "Documents & notes", "AbiWord", "abiword",
            "Lightweight word processor for everyday business documents.",
            ("Office", "WordProcessor"), aliases=("abiword",),
        ),
        HomeRecommendation(
            "business_notes", "Documents & notes", "Notepad++ Linux", "notepadplusplus",
            "Native Qt6 Notepad++-style editor from the Snap Store; no Wine layer.",
            ("Office", "TextEditor"), manager="snap",
            aliases=("notepad++", "notepadplusplus", "notepad-plus-plus", "notepad++ linux"),
        ),
    ),
    "development": (
        HomeRecommendation(
            "engineering_studio", "Engineering & code", "Refract Studio", "refract-studio",
            "ChromaPlex + PRISME development studio supplied with this ChromaPress build.",
            ("Development", "IDE"), manager="bundled",
            aliases=("refract studio", "refracteditor", "refract editor"),
            bundle_relpath="bundled_apps/refract-studio_0.1.0-1_all.deb",
            bundle_sha256="9f06a78ab3e75316c00dd71e876313d0d0475066e045de0025c176d3b61b8fdd",
        ),
        HomeRecommendation(
            "development_notes", "Engineering & code", "Notepad++ Linux", "notepadplusplus",
            "Native Qt6 Notepad++-style editor from the Snap Store for quick source and text edits.",
            ("Development", "TextEditor"), manager="snap",
            aliases=("notepad++", "notepadplusplus", "notepad-plus-plus", "notepad++ linux"),
        ),
        HomeRecommendation(
            "development_documents", "Office documents", "AbiWord", "abiword",
            "Lightweight word processor for specifications, notes and engineering documents.",
            ("Office", "WordProcessor"), aliases=("abiword",),
        ),
    ),
    "production": (
        HomeRecommendation(
            "production_studio", "Engineering & production", "Refract Studio", "refract-studio",
            "ChromaPlex + PRISME studio for controlled engineering and production workflows.",
            ("Development", "System"), manager="bundled",
            aliases=("refract studio", "refracteditor", "refract editor"),
            bundle_relpath="bundled_apps/refract-studio_0.1.0-1_all.deb",
            bundle_sha256="9f06a78ab3e75316c00dd71e876313d0d0475066e045de0025c176d3b61b8fdd",
        ),
    ),
    "education": (
        HomeRecommendation(
            "education_ai", "Education & Learning", "ChromaLearn AI", "chromalearn",
            "Open-source pedagogical AI layer for schools with RAM-only student sessions in v0.4.5. School evaluation documentation is included.",
            ("Education", "Office"), manager="bundled",
            aliases=("chromalearn", "chromalearn ai", "learning ai", "school ai", "education ai", "teaching ai"),
            bundle_relpath="bundled_apps/chromalearn_0.4.5_all.deb",
            bundle_sha256="024374666992d83df7ae6c9b0f488973e896beec80aeff18c997336d7dbe9fbc",
            documentation_label="School Evaluation Pack v1.2.1 DA",
            documentation_relpath="bundled_docs/ChromaLearn_Skoleevalueringspakke_v1.2.1_DA.zip",
            documentation_sha256="9fec49879412c056991e123c06d89b3ce99f64eff3ca19718891333fca6e67eb",
        ),
    ),
    "gaming_team": (
        HomeRecommendation(
            "gaming_overlay", "Performance & diagnostics", "MangoHud", "mangohud",
            "In-game Vulkan/OpenGL overlay for FPS, frame timing, temperatures and CPU/GPU load.",
            ("Game", "System"), aliases=("mangohud",), repository_component="universe",
        ),
        HomeRecommendation(
            "gaming_gpu", "Performance & diagnostics", "nvtop", "nvtop",
            "Lightweight live GPU utilisation and process monitor.",
            ("System", "Utility"), aliases=("nvtop", "videocard top"), repository_component="multiverse",
        ),
        HomeRecommendation(
            "gaming_network", "Performance & diagnostics", "Speedtest CLI", "speedtest-cli",
            "Simple internet bandwidth and latency measurement tool.",
            ("Network", "Utility"), aliases=("speedtest-cli", "speedtest cli"), repository_component="universe",
        ),
        HomeRecommendation(
            "gaming_benchmark", "Performance & diagnostics", "GLMark2", "glmark2-x11",
            "Small OpenGL benchmark for a quick graphics-performance baseline.",
            ("Game", "System"), aliases=("glmark2", "glmark2-x11"), repository_component="universe",
        ),
    ),
}


SCENARIO_RECOMMENDATION_DESCRIPTIONS: dict[str, str] = {
    "business": "Lightweight office and note-taking defaults for a business workstation.",
    "development": "Core engineering, source-editing and document tools for development work.",
    "production": "Controlled engineering software intended for production and industrial workflows.",
    "gaming_team": "Performance, GPU and network measurement tools for gaming and team systems.",
}


def scenario_recommendations_supported(source: dict, scenario_id: str) -> bool:
    if scenario_id not in SCENARIO_RECOMMENDATIONS:
        return False
    distribution = str(source.get("distribution", "")).strip().casefold()
    version = str(source.get("version", "")).strip()
    return distribution in {"ubuntu", "lubuntu"} and version.startswith("26.04")


def _recommendation_present(app: dict, recommendation: HomeRecommendation) -> bool:
    text = " ".join((
        str(app.get("application", "")),
        str(app.get("package", "")),
        str(app.get("description", "")),
    )).casefold()
    markers = recommendation.aliases or (recommendation.application, recommendation.package)
    return any(str(marker).casefold() in text for marker in markers if str(marker).strip())


def missing_scenario_recommendations(
    apps: list[dict], source: dict, scenario_id: str, removed_packages: set[str] | None = None
) -> tuple[HomeRecommendation, ...]:
    """Return visible missing recommendations for a non-Home scenario.

    This is still only a staging model.  The apply/build engine remains a later
    gate, and third-party/bundled sources carry their source manager explicitly
    in the staged payload.
    """
    if not scenario_recommendations_supported(source, scenario_id):
        return ()
    removed = {str(x).strip() for x in (removed_packages or set()) if str(x).strip()}
    visible_apps = [
        app for app in apps
        if not (str(app.get("package", "")).strip() and str(app.get("package", "")).strip() in removed)
    ]
    result = []
    for recommendation in SCENARIO_RECOMMENDATIONS.get(scenario_id, ()):
        if recommendation.package in removed:
            continue
        if any(_recommendation_present(app, recommendation) for app in visible_apps):
            continue
        result.append(recommendation)
    return tuple(result)

