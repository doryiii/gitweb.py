# Gitweb-Python

A modernized, simplified Python 3 port of the original `gitweb.perl` CGI script. It provides a web interface for browsing Git repositories, focusing on core functionality and ease of deployment in Python environments without relying on deprecated standard libraries like `cgi`.

## Running

`gitweb.py` is a CGI script: it reads request information from environment variables (`GITWEB_PROJECTROOT`, `PATH_INFO`, `QUERY_STRING`, `SCRIPT_NAME`) and writes an HTTP response to stdout. You need a webserver to run it.

### Quick start — bundled dev server

The easiest way to browse a directory of repos locally:

```
python serve.py --root /path/to/repos
```

Then open the printed URL (http://127.0.0.1:8000 by default). Options:

- `--port` / `-p` — port (default `8000`)
- `--bind` / `-b` — interface (default `127.0.0.1`; use `0.0.0.0` to expose on your LAN)

This is a **development server**: it spawns one `gitweb.py` process per request, with no caching or HTTPS. It is intended for local browsing, not production.

### Styling

`static/gitweb.css` is vendored from git v2.54.0 (matching the parity oracle in `parity/`), so pages are styled out of the box. `static/git-logo.png` is bundled from the same upstream tree; the favicon (`static/git-favicon.png`) is not — drop it into `static/` from `git/git/static/` if you want it.

**JavaScript-free by design.** Unlike upstream `gitweb.perl`, this port ships and emits no JavaScript: there is no `gitweb.js`, no `<script>` tags, and no inline event handlers. Pages are pure server-rendered HTML + CSS. The upstream JS-powered UI (the timezone toggle, interactive AJAX blame) is intentionally omitted rather than reimplemented — see [Unsupported Features](#unsupported-features).

### Production CGI

Set `GITWEB_PROJECTROOT` to the directory containing your bare repos, then point a CGI-capable webserver at `gitweb.py`. A few options:

**lighttpd** (the canonical gitweb setup):
```ini
server.modules += ("mod_cgi", "mod_setenv")
setenv.add-environment = ("GITWEB_PROJECTROOT" => "/path/to/repos")
$HTTP["url"] =~ "^/" {
  cgi.assign = ( "" => "" )
  alias.url = ( "/" => "/path/to/gitweb.py" )
}
```

**Apache**:
```apache
SetEnv GITWEB_PROJECTROOT /path/to/repos
ScriptAlias /gitweb /path/to/gitweb.py
```

**nginx**: nginx has no CGI support; run `gitweb.py` behind `fcgiwrap` (or use the dev server / lighttpd instead).

**Python stdlib** (zero dependencies, fiddly): `python -m http.server --cgi 8000` with `gitweb.py` placed in a `cgi-bin/` directory and `GITWEB_PROJECTROOT` exported in the environment.

### Notes

- All routing is GET-based; the port does not read POST bodies.
- The port is JavaScript-free: no JS is shipped or emitted, so JS-dependent UI (the timezone toggle, AJAX blame) is absent by design rather than merely unshipped.
- The parity tests in `parity/` cover behavior; see `parity/README.md`.

## Supported Features

**Project & Repository Navigation**
- `project_list` (Home page listing available projects)
- `project_index` (Plain-text list for bots/scripts)
- `summary` (Project overview, description, owner, clone URLs)

**Browsing History & Commits**
- `log` (Expanded view: per-commit age + title, author/date, a commit|commitdiff|tree link row, and the full multi-line commit message inline)
- `shortlog` (Compact one-line-per-commit table)
- `history` (Commit history filtered for a specific file/directory)
- `commit` (Detailed view of a single commit, including its message and parent links)
- `object` (Automatic redirection based on whether a hash is a commit, tree, blob, or tag)

**Browsing Files**
- `tree` (Directory listing)
- `blob` (Syntax-highlighted file viewer)
- `blob_plain` (Raw file download/streaming with MIME-type guessing)
- `blame` (Basic line-by-line blame view; a simplified full-page rendering, not the AJAX-powered interactive UI)

**Diffs & Changes**
- `commitdiff` & `blobdiff` (HTML view of changes with support for both `inline` and `sidebyside` styles)
- `commitdiff_plain` & `blobdiff_plain` (Raw unified diff output)

**Exports & Feeds**
- `snapshot` (Download the repository tree as `.tar.gz`, `.tar.bz2`, or `.zip`)
- `patch` (Download a commit formatted as an email patch)
- `patches` (Download a series of commits as a single multi-patch file)
- `rss` & `atom` (XML syndication feeds for repository activity)

**References & Metadata**
- `heads` (Branches list)
- `tags` (Tags list)
- `tag` (View an annotated tag object)
- `remotes` (List of remote tracking branches)

**Search**
- `search` (Search by `commit` message, `author`, `committer`, or file contents via `grep`)
- **Pickaxe Search** (`-S` and `-G` to search through repository history for strings/regex added or removed in diffs)

**Core System Capabilities**
- Clean URLs (Path-info based routing)
- Breadcrumb navigation
- Ref markers (branch/tag labels next to commits)
- Syntax Highlighting (via the external `highlight` binary)

---

## Unsupported Features

This project aims to be a simplified port, so several of the more advanced or obscure features from the original `gitweb.perl` are currently missing:

**Missing Endpoints & Views**
- `blame_incremental` & `blame_data` (The backend endpoints required for the interactive, AJAX-powered, line-by-line blame view)
- `forks` (A dedicated page to list and navigate forks of a project)
- `opml` (An XML endpoint that aggregates all project RSS/Atom feeds into one outline)
- `search_help` (A static help page explaining the search syntax)

**Missing Core Functionality & UI Features**
- **Avatars:** Support for fetching and displaying Gravatars or Picons next to author names in the UI.
- **Submodule Links:** In the `tree` view, the original Gitweb detects submodules (mode 160000) and can render them as clickable links to external repositories.
- **Project Categories & Tags (CTags):** The main project list lacks the ability to group projects by category or generate a "tag cloud" of repository topics.
- **Rich Remotes:** Our `remotes` view is a simple list of branches. The Perl version groups them by the actual remote name (e.g., `origin`) and displays their Fetch/Push URLs.
- **Project Filtering:** The main `project_list` is missing the UI text box that allows users to quickly filter the list of projects by name/description.

---

## Testing

The unit suite (`test_gitweb.py`) covers the Python implementation directly. In addition, `parity/` holds a **differential parity harness** that runs upstream `gitweb.perl` (pinned to git v2.54.0) and this port against the same fixture repo and compares the extracted semantic data, catching drift from upstream. Passing tests assert real parity; tests marked `xfail` document known, intentional divergences and serve as the "what to work on next" list. See `parity/README.md` for setup and details.
