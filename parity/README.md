# Parity test harness

Differential tests that run **upstream `gitweb.perl`** and **our `gitweb.py`**
against the same fixture repo and the same requests, then compare *extracted
semantic data* -- never raw HTML, since the two implementations deliberately
produce different markup.

## What it's for

- **Regression detection:** a previously-passing parity test turning into a
  hard failure means we drifted from upstream.
- **The parity backlog:** tests marked `xfail` document known, intentional
  divergences.  The list of xfails *is* the "what to work on next" list.

## One-time setup

Perl dropped `CGI` from the core in 5.22, so it must be installed (no sudo;
skips the test-only deps):

```
./parity/setup.sh
```

This installs `CGI` into `parity/perllocal/` (gitignored).  The
`HTML::Entities` stub (`parity/lib/`), the substituted upstream oracle
(`parity/gitweb.pl`, pinned to git v2.54.0), and the gitweb config
(`parity/gitweb_config.perl`) are committed, so no further network access is
needed.

If perl + CGI are not available, the whole suite **skips** gracefully (it does
not fail) -- so this harness never breaks a perl-less CI.

## Running

```
python -m pytest parity/test_parity.py
# or, with the unit suite:
python -m pytest test_gitweb.py parity/test_parity.py
```

## How it works

- `conftest.py` builds a session-scoped bare fixture repo (commits, annotated
  + lightweight tags, a branch, a subdir) and exposes `run_upstream` /
  `run_ours`, driving both via `&`-separated query strings with
  `REQUEST_METHOD=GET` and `GITWEB_PROJECTROOT` pointed at the fixture.
- `extract.py` holds side-agnostic extractors (SHAs, ref names, tree entries,
  diff bodies, archive listings, ...).  Each pulls comparable data out of
  *either* implementation's output.
- `test_parity.py` has one granular test per (endpoint, aspect).  Passing
  tests assert real parity; `xfail` tests document known divergences.

## Known divergences (xfail / not yet at parity)

- `commitdiff_plain` -- upstream emits mbox-style `From:`/`Subject:` headers
  (format-patch-like); we emit a raw `diff-tree` diff.
- Tree *mode* rendering -- upstream symbolic (`-rw-r--r--`), ours numeric
  (`100644`).  `tree_entries` drops mode so the entry test passes; the gap is
  documented by `test_tree_mode_rendering_diverges`.
- Snapshot *filename/prefix* -- upstream `proj-HEAD-<short>`, ours
  `proj.git-HEAD`.  The listing test strips the prefix and compares only
  archived content.

## Regenerating the upstream oracle

`parity/gitweb.pl` is `gitweb/gitweb.perl` from git v2.54.0 with the build-time
`@VAR@` placeholders substituted (the Makefile normally does this at build
time; the raw file is not runnable).  To repin to another version, fetch the
raw file, substitute the placeholders (see `setup.sh`'s logic / git history),
and replace `parity/gitweb.pl`.
