# Gitweb-Python

A modernized, simplified Python 3 port of the original `gitweb.perl` CGI script. It provides a web interface for browsing Git repositories, focusing on core functionality and ease of deployment in Python environments without relying on deprecated standard libraries like `cgi`.

## Supported Features

**Project & Repository Navigation**
- `project_list` (Home page listing available projects)
- `project_index` (Plain-text list for bots/scripts)
- `summary` (Project overview, description, owner, clone URLs)

**Browsing History & Commits**
- `log` / `shortlog` (List of recent commits)
- `history` (Commit history filtered for a specific file/directory)
- `commit` (Detailed view of a single commit, including its message and parent links)
- `object` (Automatic redirection based on whether a hash is a commit, tree, blob, or tag)

**Browsing Files**
- `tree` (Directory listing)
- `blob` (Syntax-highlighted file viewer)
- `blob_plain` (Raw file download/streaming with MIME-type guessing)

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
- Syntax Highlighting (via the external `highlight` binary)

---

## Unsupported Features

This project aims to be a simplified port, so several of the more advanced or obscure features from the original `gitweb.perl` are currently missing:

**Missing Endpoints & Views**
- **Full `log` View:** Currently, our `log` endpoint acts as a `shortlog` (listing just the commit titles). We are missing the "expanded" log view that shows the full, multi-line commit messages inline.
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

