import os
import sys
import tempfile
import subprocess
import unittest
from pathlib import Path

# Provide path to the gitweb.py script
GITWEB_SCRIPT = Path(__file__).parent / "gitweb.py"


class TestGitweb(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    # Create a temporary directory to act as the PROJECT_ROOT
    cls.temp_dir = tempfile.TemporaryDirectory()
    cls.project_root = cls.temp_dir.name

    # Initialize a test git repository
    cls.repo_name = "testrepo.git"
    cls.repo_path = Path(cls.project_root) / cls.repo_name
    cls.repo_path.mkdir()

    # Helper to run git commands in the test repo
    def run_git(*args):
      subprocess.run(["git", *args], cwd=cls.repo_path,
                     check=True, capture_output=True)

    run_git("init")
    run_git("config", "user.name", "Test User")
    run_git("config", "user.email", "test@example.com")

    # Set Gitweb metadata
    run_git("config", "gitweb.owner", "Tester McTestface")
    run_git("config", "gitweb.description",
            "A repository for testing gitweb.py")
    run_git("config", "gitweb.url", "https://example.com/testrepo.git")

    # Commit 1: Initial commit with a README
    (cls.repo_path / "README.md").write_text("# Test Repo\n\nThis is a test repository.", encoding="utf-8")
    run_git("add", "README.md")
    run_git("commit", "-m", "Initial commit: Add README.md")

    # Commit 2: Add a python script
    code = "def hello():\n    print('Hello, world!')\n"
    (cls.repo_path / "main.py").write_text(code, encoding="utf-8")
    run_git("add", "main.py")
    run_git("commit", "-m", "Add main.py script")

    # Commit 3: Modify the python script to test diffs
    code_v2 = "def hello(name='world'):\n    print(f'Hello, {name}!')\n"
    (cls.repo_path / "main.py").write_text(code_v2, encoding="utf-8")
    run_git("add", "main.py")
    run_git("commit", "-m", "Update main.py script to use f-strings")

    # Create a tag
    run_git("tag", "-a", "v1.0", "-m", "Release version 1.0")

    # Create a branch
    run_git("branch", "feature-branch")

  @classmethod
  def tearDownClass(cls):
    cls.temp_dir.cleanup()

  def run_cgi(self, query_string="", path_info="", text=True,
              project_root=None, extra_env=None):
    """Run gitweb.py as a CGI script and return the output."""
    env = os.environ.copy()
    env["GITWEB_PROJECTROOT"] = project_root or self.project_root
    env["SCRIPT_NAME"] = "gitweb.py"
    env["QUERY_STRING"] = query_string
    env["PATH_INFO"] = path_info
    if extra_env:
      env.update(extra_env)

    result = subprocess.run(
        [sys.executable, str(GITWEB_SCRIPT)],
        env=env,
        capture_output=True,
        text=text
    )
    return result.stdout, result.returncode

  @staticmethod
  def _make_repo(path):
    """Create a throwaway repo at *path* and return it for ad-hoc tests."""
    path = Path(path)
    path.mkdir(parents=True)

    def run_git(*args):
      subprocess.run(["git", *args], cwd=path, check=True, capture_output=True)

    run_git("init")
    run_git("config", "user.name", "Test User")
    run_git("config", "user.email", "test@example.com")
    return path, run_git

  def assertResponseOK(self, output):
    if isinstance(output, bytes):
      self.assertIn(b"Status: 200 OK", output)
    else:
      self.assertIn("Status: 200 OK", output)

  # --- Tests ---

  def test_project_list(self):
    out, code = self.run_cgi()
    self.assertEqual(code, 0)
    self.assertResponseOK(out)
    self.assertIn("testrepo.git", out)
    self.assertIn("Tester McTestface", out)
    self.assertIn("A repository for testing gitweb.py", out)

  def test_summary(self):
    out, code = self.run_cgi(query_string=f"p={self.repo_name}&a=summary")
    self.assertEqual(code, 0)
    self.assertResponseOK(out)
    self.assertIn("Summary for testrepo.git", out)
    self.assertIn("A repository for testing gitweb.py", out)
    self.assertIn("https://example.com/testrepo.git", out)
    self.assertIn("Recent commits", out)
    self.assertIn("Update main.py script to use f-strings", out)
    self.assertIn("v1.0", out)  # Tag teaser

  def test_log(self):
    out, code = self.run_cgi(query_string=f"p={self.repo_name}&a=log")
    self.assertEqual(code, 0)
    self.assertResponseOK(out)
    self.assertIn("Initial commit: Add README.md", out)
    self.assertIn("Add main.py script", out)
    self.assertIn("Update main.py script to use f-strings", out)

  def test_tree(self):
    out, code = self.run_cgi(query_string=f"p={self.repo_name}&a=tree")
    self.assertEqual(code, 0)
    self.assertResponseOK(out)
    self.assertIn("README.md", out)
    self.assertIn("main.py", out)
    self.assertIn("blob", out)  # File type

  def test_blob(self):
    out, code = self.run_cgi(
        query_string=f"p={self.repo_name}&a=blob&f=main.py")
    self.assertEqual(code, 0)
    self.assertResponseOK(out)
    self.assertIn("hello", out)
    self.assertIn("class=\"pre\"", out)

  def test_blob_plain(self):
    out, code = self.run_cgi(
        query_string=f"p={self.repo_name}&a=blob_plain&f=README.md")
    self.assertEqual(code, 0)
    self.assertResponseOK(out)
    self.assertIn("Content-Type: text/markdown", out)  # Guessed MIME
    self.assertIn("# Test Repo", out)

  def test_commitdiff(self):
    out, code = self.run_cgi(
        query_string=f"p={self.repo_name}&a=commitdiff&h=HEAD")
    self.assertEqual(code, 0)
    self.assertResponseOK(out)
    self.assertIn("Commit diff for HEAD", out)
    self.assertIn('class="add"', out)
    self.assertIn('class="rem"', out)
    self.assertIn('+def hello(name=&#x27;world&#x27;):', out)

  def test_commitdiff_sidebyside(self):
    out, code = self.run_cgi(
        query_string=f"p={self.repo_name}&a=commitdiff&h=HEAD&ds=sidebyside")
    self.assertEqual(code, 0)
    self.assertResponseOK(out)
    self.assertIn('class="chunk_block chg"', out)
    self.assertIn('class="old"', out)
    self.assertIn('class="new"', out)

  def test_patch(self):
    out, code = self.run_cgi(query_string=f"p={self.repo_name}&a=patch&h=HEAD")
    self.assertEqual(code, 0)
    self.assertResponseOK(out)
    self.assertIn(
        "Subject: [PATCH] Update main.py script to use f-strings", out)
    self.assertIn("diff --git a/main.py b/main.py", out)

  def test_patches(self):
    out, code = self.run_cgi(
        query_string=f"p={self.repo_name}&a=patches&h=HEAD")
    self.assertEqual(code, 0)
    self.assertResponseOK(out)
    self.assertIn("Subject: [PATCH 1/3] Initial commit: Add README.md", out)
    self.assertIn("Subject: [PATCH 2/3] Add main.py script", out)
    self.assertIn(
        "Subject: [PATCH 3/3] Update main.py script to use f-strings", out)

  def test_snapshot(self):
    # We test the HTTP headers for a raw tgz response
    out, code = self.run_cgi(
        query_string=f"p={self.repo_name}&a=snapshot&sf=tgz", text=False)
    self.assertEqual(code, 0)
    self.assertResponseOK(out)
    self.assertIn(b"Content-Type: application/x-gzip", out)
    self.assertIn(
        b"Content-Disposition: inline; filename=\"testrepo.git-HEAD.tar.gz\"", out)

  def test_path_info_routing(self):
    # Using PATH_INFO instead of QUERY_STRING
    out, code = self.run_cgi(path_info=f"/{self.repo_name}/summary")
    self.assertEqual(code, 0)
    self.assertResponseOK(out)
    self.assertIn("Summary for testrepo.git", out)

    # Test object dispatcher via PATH_INFO
    out, code = self.run_cgi(path_info=f"/{self.repo_name}/object/HEAD")
    self.assertEqual(code, 0)
    self.assertResponseOK(out)
    self.assertIn("<h1>Commit", out)

    # Test shortlog alias via PATH_INFO
    out, code = self.run_cgi(path_info=f"/{self.repo_name}/shortlog")
    self.assertEqual(code, 0)
    self.assertResponseOK(out)
    self.assertIn("Update main.py script to use f-strings", out)

  def test_rss_feed(self):
    out, code = self.run_cgi(query_string=f"p={self.repo_name}&a=rss")
    self.assertEqual(code, 0)
    self.assertResponseOK(out)
    self.assertIn("<rss version=\"2.0\">", out)
    self.assertIn("<title>Update main.py script to use f-strings</title>", out)

  def test_project_index(self):
    out, code = self.run_cgi(query_string="a=project_index")
    self.assertEqual(code, 0)
    self.assertResponseOK(out)
    self.assertIn("Content-Type: text/plain", out)
    # Expected format: "path owner"
    self.assertIn("testrepo.git Tester+McTestface", out)

  def test_object_dispatch_commit(self):
    # Dispatching a commit hash to 'object' should render the commit view
    out, code = self.run_cgi(
        query_string=f"p={self.repo_name}&a=object&h=HEAD")
    self.assertEqual(code, 0)
    self.assertResponseOK(out)
    self.assertIn("<h1>Commit", out)

  def test_object_dispatch_blob(self):
    # Get a blob hash first
    blob_hash = subprocess.run(
        ["git", "rev-parse", "HEAD:main.py"],
        cwd=self.repo_path, capture_output=True, text=True
    ).stdout.strip()

    out, code = self.run_cgi(
        query_string=f"p={self.repo_name}&a=object&h={blob_hash}")
    self.assertEqual(code, 0)
    self.assertResponseOK(out)
    self.assertIn("<h1>Blob", out)

  def test_search_commit(self):
    out, code = self.run_cgi(
        query_string=f"p={self.repo_name}&a=search&h=HEAD&st=commit&s=Initial")
    self.assertEqual(code, 0)
    self.assertResponseOK(out)
    self.assertIn("Initial commit: Add README.md", out)
    self.assertNotIn("Update main.py", out)

  def test_search_pickaxe(self):
    # We search for "Hello" which was added in the second commit.
    # Note: -S only matches if the number of occurrences changes.
    # Since commit 3 changes "Hello, world!" to "f'Hello, {name}!'",
    # the count of "Hello" stays the same, so commit 3 is NOT returned by -S.
    out, code = self.run_cgi(
        query_string=f"p={self.repo_name}&a=search&h=HEAD&st=pickaxe&s=Hello")
    self.assertEqual(code, 0)
    self.assertResponseOK(out)
    self.assertIn("Add main.py script", out)
    self.assertNotIn("Update main.py script to use f-strings", out)
    self.assertNotIn("Initial commit", out)

  def test_search_pickaxe_regex(self):
    # We search for regex "Hello, .*"
    out, code = self.run_cgi(
        query_string=f"p={self.repo_name}&a=search&h=HEAD&st=pickaxe&sr=1&s=Hello,%20.*")
    self.assertEqual(code, 0)
    self.assertResponseOK(out)
    self.assertIn("Add main.py script", out)

  def test_invalid_action(self):
    out, code = self.run_cgi(
        query_string=f"p={self.repo_name}&a=does_not_exist")
    self.assertEqual(code, 0)
    self.assertIn("Status: 404 Not Found", out)
    self.assertIn("Unknown action", out)

  def test_invalid_project(self):
    # If the project doesn't exist, we fallback to project list if not provided, or might fail.
    # Let's test providing a non-existent project and viewing its summary.
    # Actually gitweb.py sets git_dir = path if .git doesn't exist, then run_git will return "Error running git..."
    # So we just ensure it doesn't crash in a weird way
    out, code = self.run_cgi(query_string=f"p=nonexistent.git&a=summary")
    self.assertEqual(code, 0)
    self.assertResponseOK(out)
    self.assertIn("Summary for nonexistent.git", out)

  def test_invalid_hash_object(self):
    # Trying to view an object that doesn't exist
    out, code = self.run_cgi(
        query_string=f"p={self.repo_name}&a=object&h=badc0ffee")
    self.assertEqual(code, 0)
    self.assertIn("Status: 404 Not Found", out)
    self.assertIn("Object badc0ffee not found", out)

  # --- Regression tests for correctness fixes ---

  def test_no_nul_in_commit_and_feeds(self):
    # rev-list --header terminates commits with NUL; it must not leak
    # into HTML or the XML feeds (NUL is illegal in XML 1.0).
    for qs in [f"p={self.repo_name}&a=commit&h=HEAD",
               f"p={self.repo_name}&a=rss",
               f"p={self.repo_name}&a=atom"]:
      out, _ = self.run_cgi(query_string=qs, text=False)
      self.assertNotIn(b"\x00", out, f"NUL byte present in {qs} output")

  def test_merge_commitdiff_shows_changes(self):
    # A merge that resolves a conflict must show the resolution. With
    # '--root' (used when parents aren't detected) git suppresses merge
    # diffs entirely; '--cc' shows the combined diff.
    with tempfile.TemporaryDirectory() as tmp:
      root = Path(tmp)
      repo, run_git = self._make_repo(root / "merge.git")
      (repo / "f.txt").write_text("base\n")
      run_git("add", "f.txt")
      run_git("commit", "-m", "base")
      default_branch = subprocess.run(
          ["git", "symbolic-ref", "--short", "HEAD"],
          cwd=repo, capture_output=True, text=True).stdout.strip()
      run_git("checkout", "-b", "feat")
      (repo / "f.txt").write_text("feat-change\n")
      run_git("commit", "-am", "feat")
      run_git("checkout", default_branch)
      (repo / "f.txt").write_text("main-change\n")
      run_git("commit", "-am", "master change")
      # Merge, resolve the conflict, and commit.
      subprocess.run(["git", "merge", "--no-ff", "feat"],
                     cwd=repo, capture_output=True)
      (repo / "f.txt").write_text("resolved-line\n")
      run_git("add", "f.txt")
      run_git("commit", "-m", "merge feat resolved")

      out, code = self.run_cgi(
          query_string="p=merge.git&a=commitdiff&h=HEAD",
          project_root=str(root))
      self.assertEqual(code, 0)
      self.assertResponseOK(out)
      # The conflict resolution must appear (empty under the old --root).
      self.assertIn("resolved-line", out)
      self.assertIn('class="add"', out)

  def test_search_grep_leading_dash(self):
    # A grep pattern beginning with '-' must be treated as a literal
    # pattern, not parsed as a git flag.
    with tempfile.TemporaryDirectory() as tmp:
      root = Path(tmp)
      repo, run_git = self._make_repo(root / "dash.git")
      (repo / "nums.txt").write_text("value = -42\nother line\n")
      run_git("add", "nums.txt")
      run_git("commit", "-m", "add nums")

      out, code = self.run_cgi(
          query_string="p=dash.git&a=search&st=grep&s=-42",
          project_root=str(root))
      self.assertEqual(code, 0)
      self.assertResponseOK(out)
      self.assertIn("nums.txt", out)
      self.assertIn("-42", out)

  def test_path_traversal_rejected(self):
    # A project name that escapes PROJECT_ROOT must be refused.
    out, code = self.run_cgi(
        query_string="p=../../etc&a=summary")
    self.assertEqual(code, 0)
    self.assertIn("Status: 404 Not Found", out)
    self.assertIn("Invalid project", out)

    # And via PATH_INFO routing: place a real repo *above* the project
    # root so the router would otherwise resolve '..' to it.
    with tempfile.TemporaryDirectory() as tmp:
      root = Path(tmp) / "projects"
      root.mkdir()
      subprocess.run(["git", "init"], cwd=tmp, check=True,
                     capture_output=True)
      out, code = self.run_cgi(path_info="/../summary",
                               project_root=str(root))
      self.assertEqual(code, 0)
      self.assertIn("Status: 404 Not Found", out)
      self.assertIn("Invalid project", out)

  def test_error_sentinel_in_content_not_misclassified(self):
    # Git output containing the old error sentinel string must not be
    # treated as a failure. Previously parse_tree/parse_commit grepped
    # stdout for 'Error running git' and returned empty/None.
    with tempfile.TemporaryDirectory() as tmp:
      root = Path(tmp)
      repo, run_git = self._make_repo(root / "sentinel.git")
      # A file whose name contains the old sentinel.
      (repo / "Error running git.txt").write_text("hi\n")
      # A commit whose message contains the old sentinel.
      (repo / "f.txt").write_text("x\n")
      run_git("add", "f.txt")
      run_git("commit", "-m", "Fix Error running git handling")
      run_git("add", "Error running git.txt")
      run_git("commit", "-m", "add sentinel-named file")

      # Tree view must list the sentinel-named file.
      out, code = self.run_cgi(query_string="p=sentinel.git&a=tree",
                               project_root=str(root))
      self.assertEqual(code, 0)
      self.assertResponseOK(out)
      self.assertIn("Error running git.txt", out)

      # Log view must list the commit whose message has the sentinel.
      out, code = self.run_cgi(query_string="p=sentinel.git&a=log",
                               project_root=str(root))
      self.assertEqual(code, 0)
      self.assertResponseOK(out)
      self.assertIn("Fix Error running git handling", out)

  def test_blob_view_handles_binary(self):
    # A binary blob (containing NUL) must render in the HTML blob view,
    # not crash into a UnicodeDecodeError-turned-generic-error. The old
    # text-mode read swallowed the decode error and rendered the error
    # message into the page instead of the blob.
    with tempfile.TemporaryDirectory() as tmp:
      root = Path(tmp)
      repo, run_git = self._make_repo(root / "bin.git")
      (repo / "blob.bin").write_bytes(b"\x00\x01\x02 BINARY \xff\xfe\n")
      run_git("add", "blob.bin")
      run_git("commit", "-m", "add binary")

      out, code = self.run_cgi(query_string="p=bin.git&a=blob&f=blob.bin",
                               project_root=str(root))
      self.assertEqual(code, 0)
      self.assertResponseOK(out)
      self.assertIn('id="blob"', out)
      # No swallowed decode-error text should leak into the page.
      self.assertNotIn("codec", out)
      self.assertNotIn("can&#x27;t decode", out)

  # --- Minor / fidelity fixes ---

  def test_commit_date_uses_commit_timezone(self):
    # 03:30+0500 == 2019-12-31 22:30 UTC. The commit-local date is
    # 2020-01-01; rendering in the server's TZ (forced to UTC here)
    # would show 2019-12-31.
    with tempfile.TemporaryDirectory() as tmp:
      root = Path(tmp)
      repo, run_git = self._make_repo(root / "tz.git")
      (repo / "f.txt").write_text("x\n")
      subprocess.run(["git", "add", "f.txt"], cwd=repo,
                     check=True, capture_output=True)
      env = os.environ.copy()
      env["GIT_AUTHOR_DATE"] = "2020-01-01T03:30:00+0500"
      env["GIT_COMMITTER_DATE"] = "2020-01-01T03:30:00+0500"
      subprocess.run(["git", "commit", "-m", "tz commit"], cwd=repo,
                     check=True, capture_output=True, env=env)

      out, code = self.run_cgi(query_string="p=tz.git&a=log",
                               project_root=str(root),
                               extra_env={"TZ": "UTC"})
      self.assertEqual(code, 0)
      self.assertResponseOK(out)
      self.assertIn("2020-01-01", out)
      self.assertNotIn("2019-12-31", out)

  def test_commit_message_indentation_preserved(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = Path(tmp)
      repo, run_git = self._make_repo(root / "indent.git")
      subprocess.run(["git", "commit", "--allow-empty",
                      "-m", "summary", "-m", "    indented code line"],
                     cwd=repo, check=True, capture_output=True)

      out, code = self.run_cgi(query_string="p=indent.git&a=commit&h=HEAD",
                               project_root=str(root))
      self.assertEqual(code, 0)
      self.assertResponseOK(out)
      # The four-space indent must survive (lstrip used to drop it).
      self.assertIn("    indented code line", out)

  def test_nested_project_listed(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = Path(tmp)
      # A nested repo: <root>/group/nested.git
      self._make_repo(root / "group" / "nested.git")
      out, code = self.run_cgi(project_root=str(root))
      self.assertEqual(code, 0)
      self.assertResponseOK(out)
      self.assertIn("group/nested.git", out)

  def test_blobdiff_rename_detection(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = Path(tmp)
      repo, run_git = self._make_repo(root / "ren.git")
      (repo / "old.txt").write_text("content\n")
      run_git("add", "old.txt")
      run_git("commit", "-m", "add old")
      run_git("mv", "old.txt", "new.txt")
      run_git("commit", "-m", "rename to new")
      parent = subprocess.run(["git", "rev-parse", "HEAD^"],
                              cwd=repo, capture_output=True,
                              text=True).stdout.strip()
      head = subprocess.run(["git", "rev-parse", "HEAD"],
                            cwd=repo, capture_output=True,
                            text=True).stdout.strip()

      out, code = self.run_cgi(
          query_string=f"p=ren.git&a=blobdiff&hpb={parent}&hb={head}"
                       f"&fp=old.txt&f=new.txt",
          project_root=str(root))
      self.assertEqual(code, 0)
      self.assertResponseOK(out)
      # With -M the diff is a single rename, not a delete + add.
      self.assertIn("rename from old.txt", out)
      self.assertIn("rename to new.txt", out)

  def test_rss_link_escapes_project_name(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = Path(tmp)
      # A project whose name contains a space.
      self._make_repo(root / "my repo.git")
      (root / "my repo.git" / "f.txt").write_text("x\n")
      subprocess.run(["git", "add", "f.txt"],
                     cwd=root / "my repo.git", check=True, capture_output=True)
      subprocess.run(["git", "commit", "-m", "c"],
                     cwd=root / "my repo.git", check=True, capture_output=True)

      out, code = self.run_cgi(
          query_string="p=my%20repo.git&a=rss",
          project_root=str(root))
      self.assertEqual(code, 0)
      self.assertResponseOK(out)
      # The project must be percent-encoded in the feed link.
      self.assertIn("p=my%20repo.git", out)
      self.assertNotIn("p=my repo.git", out)

  def test_patch_single_with_parent_is_single(self):
    # a=patch with an explicit hp must still yield exactly one patch,
    # not a numbered range.
    parent = subprocess.run(["git", "rev-parse", "HEAD^"],
                            cwd=self.repo_path, capture_output=True,
                            text=True).stdout.strip()
    out, code = self.run_cgi(
        query_string=f"p={self.repo_name}&a=patch&h=HEAD&hp={parent}")
    self.assertEqual(code, 0)
    self.assertResponseOK(out)
    self.assertIn("Subject: [PATCH]", out)
    self.assertNotIn("[PATCH 1/", out)

  # --- Regression tests for the second round of correctness fixes ---

  def test_header_injection_blocked_in_project(self):
    # CR/LF in a project name must be rejected, not printed into a header.
    out, code = self.run_cgi(
        query_string="p=x%0d%0aSet-Cookie:%20bad=1&a=snapshot&h=HEAD",
        text=False)
    self.assertEqual(code, 0)
    self.assertIn(b"Status: 404 Not Found", out)
    self.assertIn(b"Invalid project", out)
    # The injected header must not appear in the header block (it may be
    # reflected in the text/plain body, which a browser will not parse).
    headers = out.split(b"\n\n", 1)[0]
    self.assertNotIn(b"Set-Cookie:", headers)

  def test_header_injection_blocked_in_patch_hash(self):
    # A valid project but CR/LF in h must not split the Content-Disposition
    # header into an injected header line.
    out, code = self.run_cgi(
        query_string=f"p={self.repo_name}&a=patch&h=HEAD%0d%0aInjected:%20y",
        text=False)
    self.assertEqual(code, 0)
    self.assertNotIn(b"Injected:", out)
    # The filename must be on a single line (CR/LF stripped).
    self.assertNotIn(b"filename=\".-HEAD\r\n", out)
    self.assertNotIn(b"filename=\".-HEAD\n", out)

  def test_grep_result_blob_link_resolves(self):
    # grep results must link to a blob that actually resolves, not to
    # cat-file blob <rev> (which yields "Blob not found").
    with tempfile.TemporaryDirectory() as tmp:
      root = Path(tmp)
      repo, run_git = self._make_repo(root / "gr.git")
      (repo / "nums.txt").write_text("value = -42\n")
      run_git("add", "nums.txt")
      run_git("commit", "-m", "add nums")

      out, code = self.run_cgi(
          query_string="p=gr.git&a=search&st=grep&s=-42",
          project_root=str(root))
      self.assertEqual(code, 0)
      self.assertResponseOK(out)
      # New link form uses hash_base:file_name in the path, not h=<rev>?f=.
      self.assertIn("blob/HEAD:nums.txt", out)

      # Following that link must render the blob content.
      out, code = self.run_cgi(
          path_info="/gr.git/blob/HEAD:nums.txt",
          project_root=str(root))
      self.assertEqual(code, 0)
      self.assertResponseOK(out)
      self.assertNotIn("Blob not found", out)
      self.assertIn("value = -42", out)

  def test_grep_handles_colon_in_filename(self):
    # A file whose path contains a colon must not be mis-parsed.
    with tempfile.TemporaryDirectory() as tmp:
      root = Path(tmp)
      repo, run_git = self._make_repo(root / "colon.git")
      (repo / "we:rd.txt").write_text("needle here\n")
      run_git("add", "we:rd.txt")
      run_git("commit", "-m", "add colon file")

      out, code = self.run_cgi(
          query_string="p=colon.git&a=search&st=grep&s=needle",
          project_root=str(root))
      self.assertEqual(code, 0)
      self.assertResponseOK(out)
      self.assertIn("we:rd.txt", out)
      # The colon in the path must not shift the parsed fields: the link
      # keeps the full path and the line number renders after it.
      self.assertIn("blob/HEAD:we:rd.txt", out)
      self.assertIn("</a>:1", out)
      self.assertIn("needle here", out)

  def test_tree_with_commit_and_file_name(self):
    # a=tree&h=<commit>&f=<dir> must list the subdir, not the root tree.
    with tempfile.TemporaryDirectory() as tmp:
      root = Path(tmp)
      repo, run_git = self._make_repo(root / "t.git")
      (repo / "top.txt").write_text("top\n")
      (repo / "sub").mkdir()
      (repo / "sub" / "deep.txt").write_text("deep\n")
      run_git("add", ".")
      run_git("commit", "-m", "add tree")

      out, code = self.run_cgi(
          query_string="p=t.git&a=tree&h=HEAD&f=sub",
          project_root=str(root))
      self.assertEqual(code, 0)
      self.assertResponseOK(out)
      self.assertIn("deep.txt", out)
      # The root entry must not leak through with a mis-prefixed path.
      self.assertNotIn("sub/top.txt", out)

  def test_plain_diff_has_no_stray_commit_id(self):
    # commitdiff_plain must start the body with "diff --git", not a bare
    # commit hash line (missing --no-commit-id used to emit one).
    out, code = self.run_cgi(
        query_string=f"p={self.repo_name}&a=commitdiff_plain&h=HEAD")
    self.assertEqual(code, 0)
    self.assertResponseOK(out)
    body = out.split("\n\n", 1)[1] if "\n\n" in out else out
    self.assertTrue(body.lstrip().startswith("diff --git"),
                    f"plain diff body should start with diff --git, got: {body[:60]!r}")

  def test_commit_shows_parent_links(self):
    out, code = self.run_cgi(
        query_string=f"p={self.repo_name}&a=commit&h=HEAD")
    self.assertEqual(code, 0)
    self.assertResponseOK(out)
    self.assertIn("Parent:", out)
    # The parent link should point at a commit view.
    self.assertIn("/commit/", out)

  def test_snapshot_pathspec_is_not_parsed_as_option(self):
    # A leading-dash file_name must be passed as a pathspec, not a flag.
    with tempfile.TemporaryDirectory() as tmp:
      root = Path(tmp)
      repo, run_git = self._make_repo(root / "sp.git")
      (repo / "-dash.txt").write_text("x\n")
      run_git("add", "--", "-dash.txt")
      run_git("commit", "-m", "dash")
      out, code = self.run_cgi(
          query_string="p=sp.git&a=snapshot&h=HEAD&f=-dash.txt",
          project_root=str(root), text=False)
      self.assertEqual(code, 0)
      self.assertResponseOK(out)

  def test_error_body_does_not_reflect_crlf(self):
    # The 404 "Invalid project" body must not echo CR/LF from the input
    # (which could splice extra lines into the response).
    out, code = self.run_cgi(
        query_string="p=x%0d%0aSet-Cookie:%20bad=1&a=summary", text=False)
    self.assertEqual(code, 0)
    self.assertIn(b"Status: 404 Not Found", out)
    self.assertIn(b"Invalid project:", out)
    # CR/LF stripped from the reflected value; it stays on one line.
    self.assertNotIn(b"\r", out)
    self.assertIn(b"Invalid project: xSet-Cookie: bad=1", out)

    # Same for the "Unknown action" body.
    out, code = self.run_cgi(
        query_string=f"p={self.repo_name}&a=bad%0d%0aX:%20y", text=False)
    self.assertEqual(code, 0)
    self.assertIn(b"Status: 404 Not Found", out)
    self.assertIn(b"Unknown action:", out)
    self.assertNotIn(b"\r", out)

  # --- Parity fixes against gitweb.perl ---

  def test_search_form_has_regexp_checkbox(self):
    # The header search form must expose the 'sr' (re) checkbox, mirroring
    # gitweb's print_search_form.
    out, code = self.run_cgi(query_string=f"p={self.repo_name}&a=summary")
    self.assertEqual(code, 0)
    self.assertResponseOK(out)
    self.assertIn('name="sr"', out)
    self.assertIn(">re<", out)
    # And the hidden hash field the original includes.
    self.assertIn('name="h"', out)

  def test_search_commit_default_is_fixed_strings(self):
    # Without 're', the pattern is a literal: "f.strings" does not match
    # "f-strings".
    out, code = self.run_cgi(
        query_string=f"p={self.repo_name}&a=search&st=commit&s=f.strings")
    self.assertEqual(code, 0)
    self.assertResponseOK(out)
    self.assertIn("No commits found.", out)

  def test_search_commit_regexp_mode_matches(self):
    # With 're', "f.strings" is a regex (. matches '-') -> matches the
    # f-strings commit.
    out, code = self.run_cgi(
        query_string=f"p={self.repo_name}&a=search&st=commit&sr=1&s=f.strings")
    self.assertEqual(code, 0)
    self.assertResponseOK(out)
    self.assertIn("Update main.py script to use f-strings", out)

  def test_search_commit_is_case_insensitive(self):
    # gitweb always passes --regexp-ignore-case.
    out, code = self.run_cgi(
        query_string=f"p={self.repo_name}&a=search&st=commit&s=INITIAL")
    self.assertEqual(code, 0)
    self.assertResponseOK(out)
    self.assertIn("Initial commit: Add README.md", out)

  def test_search_grep_default_is_fixed_strings(self):
    # Without 're', grep uses -F: "Hello, .name" is literal and absent.
    out, code = self.run_cgi(
        query_string=f"p={self.repo_name}&a=search&st=grep&s=Hello,%20.name")
    self.assertEqual(code, 0)
    self.assertResponseOK(out)
    self.assertIn("No matches found.", out)

  def test_search_grep_regexp_mode_matches(self):
    # With 're', grep uses -E -i: "Hello, .name" matches "Hello, {name".
    out, code = self.run_cgi(
        query_string=f"p={self.repo_name}&a=search&st=grep&sr=1&s=Hello,%20.name")
    self.assertEqual(code, 0)
    self.assertResponseOK(out)
    self.assertIn("main.py", out)

  def test_search_pickaxe_regexp_uses_pickaxe_regex(self):
    # sr=1 pickaxe should still find the commit that introduced a regex
    # pattern (equivalent to gitweb's -S --pickaxe-regex).
    out, code = self.run_cgi(
        query_string=f"p={self.repo_name}&a=search&st=pickaxe&sr=1&s=Hello,%20.*")
    self.assertEqual(code, 0)
    self.assertResponseOK(out)
    self.assertIn("Add main.py script", out)

  def test_atom_author_has_name_and_email(self):
    # Atom <author> should split name and email, like gitweb.
    out, code = self.run_cgi(query_string=f"p={self.repo_name}&a=atom")
    self.assertEqual(code, 0)
    self.assertResponseOK(out)
    self.assertIn("<name>Test User</name>", out)
    self.assertIn("<email>test@example.com</email>", out)


if __name__ == "__main__":
  unittest.main(verbosity=2)
