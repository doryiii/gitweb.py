"""Side-agnostic extractors for the parity harness.

Each function pulls comparable *semantic data* out of a raw response
(bytes) from EITHER implementation.  The two gitwebs produce different
HTML, so we never compare markup -- only the extracted data (SHAs, ref
names, tree entries, diff bodies, archive listings, ...).
"""
import re
import html
import io
import tarfile
import zipfile


def text(raw: bytes) -> str:
    return raw.decode("utf-8", "replace")


def split_body(raw: bytes) -> bytes:
    """Return the message body (after the blank header separator).

    Upstream emits CRLF headers, ours LF; handle both, and the rare
    bare-CR case."""
    for sep in (b"\r\n\r\n", b"\n\n", b"\r\r"):
        i = raw.find(sep)
        if i != -1:
            return raw[i + len(sep):]
    return raw


_SHA40 = r"[0-9a-f]{40}"


def _dedup(items):
    seen, out = set(), []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def shortlog_shas(raw: bytes) -> list:
    """Ordered, de-duplicated commit SHAs linked from a shortlog/log page.

    Upstream links each commit several times per row (subject + 'commit'
    + ...); ours links it once.  De-dup so the comparison is on the set
    of commits shown, in rev-list order."""
    return _dedup(re.findall(rf"/commit/({_SHA40})", text(raw)))


def ref_marker_names(raw: bytes) -> list:
    """Sorted set of branch/tag labels shown next to commits (ref markers).

    Both implementations render markers as anchors pointing to a ref under
    /<action>/refs/... (e.g. /shortlog/refs/heads/main, /tag/refs/tags/v1.0).
    Those are the only /refs/ links on a log/shortlog page, so collecting
    their anchor texts sidesteps the nested <span class="refs"> markup, which
    differs between the two implementations."""
    names = re.findall(
        r'<a [^>]*href="[^"]*/(?:shortlog|log|tag|history)/refs/[^"]*"[^>]*>'
        r'([^<]*)</a>', text(raw))
    return sorted(set(names))


def tree_entries(raw: bytes) -> list:
    """List of (type, name) for tree rows, scoped to <table class="tree">.

    Type is taken from the link action (blob/tree) and name from the link
    text, so this is independent of the column layout (upstream has
    mode/size/name; we have mode/type/name) and of mode rendering
    (upstream symbolic, ours numeric).  Action-link texts and the '..'
    parent row upstream adds in subdirs are excluded."""
    m = re.search(r'<table class="tree">(.*?)</table>', text(raw), re.S)
    body = m.group(1) if m else ""
    action_words = {"blob", "tree", "history", "raw", "diff", "blame",
                    "commit", "commitdiff", "patch"}
    out = []
    for mm in re.finditer(
        r'<a [^>]*href="[^"]*/(blob|tree)/[^"]*"[^>]*>([^<]*)</a>', body):
        name = mm.group(2).strip()
        if name and name.lower() not in action_words and name != "..":
            out.append((mm.group(1), name))
    return out


def refs_names(raw: bytes) -> list:
    """Ref names from a heads/tags/remotes page (order preserved)."""
    return re.findall(r'class="list name"[^>]*>([^<]*)</a>', text(raw))


def tree_modes(raw: bytes) -> list:
    """Symbolic mode strings from the tree table's mode column, in row
    order.  Upstream renders symbolic modes via mode_str (e.g.
    '-rw-r--r--'); this lets the parity test confirm we match rather
    than diverging to numeric ('100644')."""
    m = re.search(r'<table class="tree">(.*?)</table>', text(raw), re.S)
    body = m.group(1) if m else ""
    return re.findall(r'class="mode">([^<]*)</td>', body)


def search_commit_shas(raw: bytes) -> list:
    """Commit SHAs matched by a commit/author/committer/pickaxe search.

    Upstream tags result subjects with class="list subject" (and also
    links the base commit in a header div); our port uses class="list".
    Prefer the subject links, then fall back to all commit links."""
    t = text(raw)
    shas = re.findall(
        r'class="list subject"[^>]*href="[^"]*?/commit/([0-9a-f]{40})"', t)
    if not shas:
        shas = re.findall(rf"/commit/({_SHA40})", t)
    return _dedup(shas)


def search_grep_files(raw: bytes) -> list:
    """File names matched by a grep search (sorted, unique)."""
    files = set()
    for m in re.finditer(r'/blob/[^"\' ]*', text(raw)):
        path = m.group(0)
        if ":" in path:
            f = path.rsplit(":", 1)[1].split("#", 1)[0].lstrip("/")
            if f:
                files.add(f)
    return sorted(files)


def feed_shas(raw: bytes) -> list:
    """Ordered, de-duplicated commit SHAs appearing in an rss/atom feed.

    Upstream appends a '...' more-commits item whose guid uses the
    all-zero SHA; filter it out."""
    zero = "0" * 40
    seen, out = set(), []
    for sha in re.findall(_SHA40, text(raw)):
        if sha == zero or sha in seen:
            continue
        seen.add(sha)
        out.append(sha)
    return out


def feed_item_titles(raw: bytes) -> list:
    """Item (commit) titles from a feed (parsed from <item>/<entry> blocks,
    so channel/image titles and the upstream 'more' item are excluded)."""
    t = text(raw)
    blocks = re.findall(r"<(?:item|entry)>(.*?)</(?:item|entry)>", t, re.S)
    titles = []
    for b in blocks:
        m = re.search(r"<title[^>]*>([^<]*)</title>", b)
        if m:
            titles.append(html.unescape(m.group(1)).strip())
    return titles


def blob_plain_body(raw: bytes) -> bytes:
    return split_body(raw)


def raw_text_body(raw: bytes) -> str:
    """Body of a text/plain raw endpoint (diff/patch), trailing ws stripped."""
    return text(split_body(raw)).rstrip()


def snapshot_listing(raw: bytes) -> list:
    """Sorted archive entry paths with the top-level prefix stripped.

    Only entries *under* the prefix are kept (the prefix dir itself is
    dropped), so the comparison is on archived content, not on the
    prefix naming."""
    body = split_body(raw)
    names = []
    if body[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(body)) as z:
            names = z.namelist()
    else:
        with tarfile.open(fileobj=io.BytesIO(body), mode="r:*") as t:
            names = t.getnames()
    stripped = []
    for n in names:
        if "/" not in n:
            continue                      # the prefix dir itself
        rem = n.split("/", 1)[1].rstrip("/")
        if rem:
            stripped.append(rem)
    return sorted(set(stripped))


def snapshot_filename(raw: bytes) -> str:
    """The Content-Disposition filename of a snapshot response.

    CGI.pm HTML-escapes the quoting around the value (the bytes for
    ampersand-quot-semicolon); our port uses a literal double quote.
    Accept either delimiter and capture the sanitized filename."""
    q = chr(38) + "quot;"  # CGI.pm's escaped double quote
    m = re.search(r'filename=(?:"|' + re.escape(q) + r')([\w.\-]+)',
                  text(raw), re.I)
    return m.group(1) if m else ""


def project_names(raw: bytes) -> list:
    """Project names from project_list or project_index."""
    t = text(raw)
    m = re.search(r'<table class="project_list">(.*?)</table>', t, re.S)
    if m:
        names = []
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", m.group(1), re.S):
            if "<th" in row:          # skip the sortable header row
                continue
            a = re.search(r"<a [^>]*>([^<]+)</a>", row)
            if a:
                names.append(a.group(1).strip())
        if names:
            return names
    # project_index: plain "path owner" lines
    names = []
    for ln in t.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith(("Status:", "Content")):
            continue
        names.append(ln.split()[0])
    return names


def commit_parents(raw: bytes) -> list:
    """Parent commit SHAs from a commit page (sorted)."""
    return sorted(set(re.findall(rf"/commit/({_SHA40})", text(raw))))


def commit_message(raw: bytes) -> str:
    """The commit log message text (upstream page_body, ours <pre>).

    Upstream escapes spaces as &nbsp; in the page body; unescape entities
    and collapse whitespace so the comparison is on the message content."""
    t = text(raw)
    m = re.search(r'<div class="page_body">(.*?)</div>', t, re.S)
    if not m:
        m = re.search(r"<pre[^>]*>(.*?)</pre>", t, re.S)
    if not m:
        return ""
    s = re.sub(r"<[^>]+>", "", m.group(1))
    return html.unescape(s).replace("\xa0", " ").strip()


def log_body_messages(raw: bytes) -> list:
    """Normalized message body of each commit on a log/shortlog page.

    Both implementations render the expanded `log` view with
    <div class="log_body">...</div> per commit (upstream prints the whole
    message, title included).  Strip tags, unescape entities, turn the
    &nbsp; gitweb uses back into spaces, and collapse to a single line so
    the comparison is on message content, not whitespace markup."""
    out = []
    for m in re.finditer(r'<div class="log_body">(.*?)</div>',
                         text(raw), re.S):
        s = re.sub(r"<[^>]+>", "", m.group(1))
        s = html.unescape(s).replace("\xa0", " ")
        s = " ".join(s.split()).strip()
        if s:
            out.append(s)
    return out
