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

  def run_cgi(self, query_string="", path_info="", text=True):
    """Run gitweb.py as a CGI script and return the output."""
    env = os.environ.copy()
    env["GITWEB_PROJECTROOT"] = self.project_root
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


if __name__ == "__main__":
  unittest.main(verbosity=2)
