"""Shared fixtures and runners for the gitweb parity harness.

The harness drives upstream gitweb.perl (parity/gitweb.pl) and our
gitweb.py with identical inputs (same fixture repo, path-info routing,
query params) and the tests compare extracted semantic data -- never raw
HTML, since the two implementations deliberately produce different DOM.
"""
import os
import sys
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

PARITY = Path(__file__).resolve().parent
REPO = PARITY.parent
GITWEB_PY = REPO / "gitweb.py"
GITWEB_PL = PARITY / "gitweb.pl"
CONFIG = PARITY / "gitweb_config.perl"
# perllocal holds the CGI module (installed by setup.sh); lib/ holds the
# HTML::Entities stub.  Both must be on PERL5LIB.
PERL5LIB = os.pathsep.join([
    str(PARITY / "perllocal" / "lib" / "perl5"),
    str(PARITY / "lib"),
])


def upstream_ready():
    """True iff perl + CGI are available (run parity/setup.sh otherwise)."""
    if not GITWEB_PL.exists() or not (PARITY / "perllocal").exists():
        return False
    env = os.environ.copy()
    env["PERL5LIB"] = PERL5LIB
    try:
        r = subprocess.run(["perl", "-MCGI", "-MCGI::Carp", "-e", "exit 0"],
                           env=env, capture_output=True)
        return r.returncode == 0
    except FileNotFoundError:
        return False


UPSTREAM_OK = upstream_ready()
skip_no_upstream = pytest.mark.skipif(
    not UPSTREAM_OK,
    reason="parity: perl + CGI not available (run parity/setup.sh)")


def build_fixture():
    """Build a bare fixture repo and return (projectroot, project_name).

    SHAs are not pinned -- the comparison is differential at run time
    (both sides see the same repo), so determinism across machines is not
    needed.  Content is chosen to exercise trees, subdirs, diffs, tags
    (annotated + lightweight) and a branch.
    """
    root = tempfile.mkdtemp(prefix="parity_root_")
    work = Path(tempfile.mkdtemp(prefix="parity_work_"))

    def git(*a, cwd=work):
        subprocess.run(["git", *a], cwd=str(cwd), check=True,
                       capture_output=True)

    git("init", "-q")
    git("config", "user.name", "Parity Tester")
    git("config", "user.email", "parity@example.com")

    def commit(message, date):
        # Distinct committer dates so ref ordering by -committerdate is
        # deterministic across both implementations (no same-second ties).
        env = os.environ.copy()
        env["GIT_AUTHOR_DATE"] = date
        env["GIT_COMMITTER_DATE"] = date
        subprocess.run(["git", "commit", "-q", "-m", message],
                       cwd=str(work), check=True, capture_output=True, env=env)

    (work / "README.md").write_text("# Proj\n\nA project.\n", encoding="utf-8")
    git("add", "README.md")
    commit("Initial commit: Add README.md", "2020-01-01T10:00:00")

    (work / "src").mkdir()
    (work / "src" / "main.py").write_text(
        "def hello():\n    print('Hello, world!')\n", encoding="utf-8")
    git("add", "src/main.py")
    commit("Add src/main.py", "2020-01-02T10:00:00")

    (work / "docs").mkdir()
    (work / "docs" / "notes.txt").write_text("some notes\n", encoding="utf-8")
    git("add", "docs")
    commit("Add docs/notes.txt", "2020-01-03T10:00:00")

    (work / "src" / "main.py").write_text(
        "def hello(name='world'):\n    print(f'Hello, {name}!')\n",
        encoding="utf-8")
    git("add", "-A")
    commit("Use f-strings in main.py", "2020-01-04T10:00:00")

    git("tag", "v0.1")                       # lightweight tag
    git("tag", "-a", "v1.0", "-m", "Release 1.0")  # annotated tag
    # Branch from the previous commit so 'feature' and 'main' have distinct
    # committer dates -- otherwise ref ordering is a tie-break coin flip and
    # not a meaningful parity check.
    git("branch", "feature", "HEAD~1")

    subprocess.run(["git", "clone", "-q", "--bare", str(work),
                    str(Path(root) / "proj.git")],
                   check=True, capture_output=True)
    shutil.rmtree(work, ignore_errors=True)
    return Path(root), "proj.git"


@pytest.fixture(scope="session")
def fixture():
    root, name = build_fixture()
    yield root, name
    shutil.rmtree(root, ignore_errors=True)


def _env(projectroot, perl):
    env = os.environ.copy()
    env["GITWEB_PROJECTROOT"] = str(projectroot)
    env["GITWEB_GIT_TEMP"] = str(projectroot)
    env["SCRIPT_NAME"] = "gitweb"
    # CGI.pm needs REQUEST_METHOD to read QUERY_STRING params.
    env["REQUEST_METHOD"] = "GET"
    if perl:
        env["GITWEB_CONFIG"] = str(CONFIG)
        env["PERL5LIB"] = PERL5LIB
    return env


def run_upstream(root, path_info="", query=""):
    env = _env(root, perl=True)
    env["PATH_INFO"] = path_info
    env["QUERY_STRING"] = query
    r = subprocess.run(["perl", str(GITWEB_PL)], env=env,
                       capture_output=True)
    return r.stdout


def run_ours(root, path_info="", query=""):
    env = _env(root, perl=False)
    env["PATH_INFO"] = path_info
    env["QUERY_STRING"] = query
    r = subprocess.run([sys.executable, str(GITWEB_PY)], env=env,
                       capture_output=True)
    return r.stdout
