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

  def run_cgi(self, query_string="", path_info="", text=True, project_root=None):
    """Run gitweb.py as a CGI script and return the output."""
    env = os.environ.copy()
    env["GITWEB_PROJECTROOT"] = project_root or self.project_root
    env["SCRIPT_NAME"] = "gitweb.py"
    env["QUERY_STRING"] = query_string
    env["PATH_INFO"] = path_info

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


if __name__ == "__main__":
  unittest.main(verbosity=2)
