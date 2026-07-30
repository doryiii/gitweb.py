#!/usr/bin/env python3
import pwd
import os
import sys
import time
import re
import subprocess
import urllib.parse
import html
from datetime import datetime, timedelta, timezone

# Enable basic error reporting


def enable_error_reporting():
  import traceback
  sys.excepthook = lambda t, v, tb: print(
      "Status: 500 Internal Server Error\nContent-Type: text/plain\n\n" + "".join(traceback.format_exception(t, v, tb)))


enable_error_reporting()

# --- Configuration (from gitweb/Makefile defaults) ---
GIT = "git"
PROJECT_ROOT = os.environ.get("GITWEB_PROJECTROOT", "/home/dory/tmp")
PROJECT_MAX_DEPTH = 2007
SITE_NAME = os.environ.get('SERVER_NAME', 'Untitled') + " Git"
HOME_LINK_STR = "projects"
VERSION = "2.x.python"  # Placeholder
STRICT_EXPORT = False
EXPORT_OK = ""
LOGO_URL = "https://git-scm.com/"
LOGO_LABEL = "git homepage"
STYLESHEETS = ["static/gitweb.css"]
LOGO = "static/git-logo.png"
FAVICON = "static/git-favicon.png"
JAVASCRIPT = "static/gitweb.js"

USE_HIGHLIGHT = True
HIGHLIGHT_BIN = "/usr/bin/highlight"

PATCHES_LIMIT = 16  # Default limit for 'patches' action

# --- Global State ---
project = None
action = None
hash_id = None
hash_base = None
file_name = None
page = 1
git_dir = None
my_url = ""
my_uri = ""
base_url = ""
path_info = ""
params = {}

# CGI parameters mapping
CGI_PARAM_MAPPING = [
    ('project', 'p'),
    ('action', 'a'),
    ('hash', 'h'),
    ('hash_base', 'hb'),
    ('hash_parent', 'hp'),
    ('file_name', 'f'),
    ('file_parent', 'fp'),
    ('page', 'pg'),
    ('order', 'o'),
    ('searchtext', 's'),
    ('searchtype', 'st'),
    ('search_use_regexp', 'sr'),
    ('diff_style', 'ds'),
    ('project_filter', 'pf'),
    ('extra_options', 'opt'),
    ('snapshot_format', 'sf'),
]

# --- Utilities ---


def to_utf8(s):
  if isinstance(s, bytes):
    return s.decode('utf-8', 'replace')
  return str(s)


def esc_html(s):
  return html.escape(to_utf8(s))


def esc_url(s):
  return urllib.parse.quote(to_utf8(s), safe='/:?@&=+$,#')


def esc_param(s):
  return urllib.parse.quote(to_utf8(s))


def esc_path_info(s):
  return urllib.parse.quote(to_utf8(s), safe='/')


def esc_header(s):
  """Sanitize a value for use in an HTTP header field.

  CR/LF/NUL in a user-controlled param (project, hash, file name) would
  otherwise let an attacker inject extra header lines (HTTP response
  splitting) via Content-Disposition filenames."""
  return to_utf8(s).replace("\r", "").replace("\n", "").replace("\0", "")


def _parse_tz_offset(tz):
  """Parse a git timezone string like '+0000' or '-0730' into a timedelta."""
  try:
    return datetime.strptime(tz, '%z').utcoffset()
  except (ValueError, TypeError):
    return timedelta()


def commit_datetime(co, who='committer'):
  """Return the author/committer date as a tz-aware datetime in the
  commit's own timezone (not the server's local time)."""
  epoch = co.get(f'{who}_epoch')
  if epoch is None:
    return datetime.fromtimestamp(0, tz=timezone.utc)
  offset = _parse_tz_offset(co.get(f'{who}_tz', '+0000'))
  return datetime.fromtimestamp(epoch, tz=timezone(offset))


def href(**kwargs):
  global my_url, my_uri, project, params

  p = kwargs.copy()

  # Handle replay
  if p.get('replay'):
    del p['replay']
    for name, symbol in CGI_PARAM_MAPPING:
      if name not in p and name in params:
        val = params[name]
        if isinstance(val, list):
          p[name] = val[0]
        else:
          p[name] = val

  if 'project' not in p and project:
    p['project'] = project

  url = my_uri
  if USE_PATHINFO and 'project' in p and p['project'] is not None:
    url += f"/{esc_url(p['project'])}"
    if 'action' in p and p['action'] is not None:
      url += f"/{esc_url(p['action'])}"

      if 'hash_base' in p and p['hash_base'] is not None and 'file_name' in p and p['file_name'] is not None:
        url += f"/{esc_url(p['hash_base'])}:{esc_url(p['file_name'])}"
        del p['hash_base']
        del p['file_name']
      elif 'hash' in p and p['hash'] is not None:
        url += f"/{esc_url(p['hash'])}"
        del p['hash']

    del p['project']
    if 'action' in p:
      del p['action']

  query = []
  for name, symbol in CGI_PARAM_MAPPING:
    if name in p and p[name] is not None:
      query.append(f"{symbol}={esc_param(str(p[name]))}")

  if query:
    url += "?" + "&".join(query)
  return url


def git_cmd():
  cmd = [GIT]
  if git_dir:
    cmd.extend(["--git-dir", git_dir])
  return cmd


def is_valid_project(name):
  """Reject project names that could escape PROJECT_ROOT.

  Gitweb receives the project path from the request (query string or
  PATH_INFO); without validation a value like '../private' would point
  --git-dir at a repository outside the project root."""
  if not name or '\0' in name or '\r' in name or '\n' in name or os.path.isabs(name):
    return False
  parts = name.split('/')
  if '..' in parts:
    return False
  return True


def run_git(*args):
  """Run git, returning decoded stdout on success or None on failure.

  Returning None (rather than an error string) lets callers distinguish
  failure from legitimate output by truthiness/identity, instead of
  grepping stdout for a sentinel substring that real output could
  contain (e.g. a commit message or tree entry named 'Error running git')."""
  full_cmd = git_cmd() + list(args)
  try:
    process = subprocess.Popen(
        full_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        encoding="utf-8", errors="replace")
    stdout, _ = process.communicate()
    if process.returncode != 0:
      return None
    return stdout
  except Exception:
    return None


def run_git_bin(*args):
  full_cmd = git_cmd() + list(args)
  try:
    process = subprocess.Popen(
        full_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    if process.returncode != 0:
      return None
    return stdout
  except Exception as e:
    return None

# --- HTML Generation ---


def git_header_html(status="200 OK"):
  title = f"{SITE_NAME}"
  if project:
    title += f" :: {project}"

  print(f"Status: {status}")
  print("Content-Type: text/html; charset=utf-8")
  print()

  print(f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html [
	<!ENTITY nbsp "&#xA0;">
	<!ENTITY sdot "&#x22C5;">
]>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en-US" lang="en-US">
<head>
<meta name="generator" content="gitweb-python"/>
<meta name="robots" content="index, nofollow"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{esc_html(title)}</title>
""")
  for ss in STYLESHEETS:
    print(f'<link rel="stylesheet" type="text/css" href="{esc_url(ss)}"/>')
  if FAVICON:
    print(
        f'<link rel="shortcut icon" href="{esc_url(FAVICON)}" type="image/png"/>')
  print("</head><body>")

  print('<div class="page_header">')
  if LOGO:
    print(f'<a href="{esc_url(LOGO_URL)}" title="{esc_html(LOGO_LABEL)}">')
    print(
        f'<img src="{esc_url(LOGO)}" width="72" height="27" alt="git" class="logo"/></a>')

  # Breadcrumbs
  home_link = href(project=None, action=None)
  print(f'<a href="{esc_url(home_link)}">{esc_html(HOME_LINK_STR)}</a>')
  if project:
    print(
        f' / <a href="{esc_url(href(action="summary"))}">{esc_html(project)}</a>')

    # Navigation
    print('<div class="page_nav">')
    print(f'<a href="{esc_url(href(action="summary"))}">summary</a> | ')
    print(f'<a href="{esc_url(href(action="log"))}">log</a> | ')
    print(f'<a href="{esc_url(href(action="tree"))}">tree</a> | ')
    print(f'<a href="{esc_url(href(action="tags"))}">tags</a> | ')
    print(f'<a href="{esc_url(href(action="heads"))}">heads</a> | ')
    print(f'<a href="{esc_url(href(action="remotes"))}">remotes</a>')
    print('</div>')

    # Search form
    print('<div class="search">')
    print(f'<form method="get" action="{esc_url(my_url)}">')
    print(f'<input type="hidden" name="p" value="{esc_html(project)}"/>')
    print('<input type="hidden" name="a" value="search"/>')
    print('<input type="hidden" name="h" value="HEAD"/>')
    print('<select name="st">')
    print('<option value="commit">commit</option>')
    print('<option value="grep">grep</option>')
    print('<option value="author">author</option>')
    print('<option value="committer">committer</option>')
    print('<option value="pickaxe">pickaxe</option>')
    print('</select>')
    print(' search: ')
    print('<input type="text" name="s" placeholder="search..." />')
    print('<span title="Extended regular expression">')
    print('<input type="checkbox" name="sr" value="1" id="sr"/>')
    print('<label for="sr">re</label>')
    print('</span>')
    print('</form>')
    print('</div>')

  print('</div>')


def git_footer_html():
  print('<div class="page_footer">')
  if project:
    print(f'<div class="page_footer_text">{esc_html(project)}</div>')
  print('</div>')
  print("</body></html>")

# --- Data Parsing ---


def get_project_owner(proj_git_dir):
  global git_dir
  old_git_dir = git_dir
  git_dir = proj_git_dir

  owner = run_git("config", "gitweb.owner")
  if owner:
    git_dir = old_git_dir
    return owner.strip()

  git_dir = old_git_dir
  try:
    stat_info = os.stat(proj_git_dir)
    return pwd.getpwuid(stat_info.st_uid).pw_name
  except Exception:
    return ""


def get_project_description(proj_git_dir):
  global git_dir
  old_git_dir = git_dir
  git_dir = proj_git_dir

  desc = run_git("config", "gitweb.description")
  if desc:
    git_dir = old_git_dir
    return desc.strip()

  git_dir = old_git_dir
  desc_file = os.path.join(proj_git_dir, "description")
  if os.path.exists(desc_file):
    with open(desc_file, 'r', encoding='utf-8') as f:
      content = f.read().strip()
      if content and not content.startswith("Unnamed repository"):
        return content
  return ""


def get_project_cloneurls(proj_git_dir):
  global git_dir
  old_git_dir = git_dir
  git_dir = proj_git_dir

  urls = []
  url_config = run_git("config", "--get-all", "gitweb.url")
  if url_config:
    urls.extend([u.strip() for u in url_config.split("\n") if u.strip()])

  git_dir = old_git_dir
  cloneurl_file = os.path.join(proj_git_dir, "cloneurl")
  if os.path.exists(cloneurl_file):
    with open(cloneurl_file, 'r', encoding='utf-8') as f:
      for line in f:
        line = line.strip()
        if line and line not in urls:
          urls.append(line)
  return urls


def parse_refs(ref_space, max_count=None):
  # Match gitweb's sort keys: tags by -creatordate (annotated tags have a
  # tagger date, not a committer date, so -committerdate would leave them
  # unordered); heads/remotes by -HEAD then -committerdate (current branch
  # first).
  if ref_space == "refs/tags":
    cmd = ["for-each-ref", "--sort=-creatordate"]
  else:
    cmd = ["for-each-ref", "--sort=-HEAD", "--sort=-committerdate"]
  if max_count:
    cmd.append(f"--count={max_count}")
  cmd.extend(
      ["--format=%(objectname)\t%(refname:short)\t%(*objectname)\t%(objecttype)", ref_space])

  raw = run_git(*cmd)
  refs = []
  if raw is None:
    return refs

  for line in raw.strip().split('\n'):
    if not line:
      continue
    parts = line.split('\t')
    if len(parts) >= 4:
      refs.append({
          "id": parts[0],
          "name": parts[1],
          "peeled": parts[2] if parts[2] else parts[0],
          "type": parts[3]
      })
  return refs


def parse_tag(tag_id):
  raw = run_git("cat-file", "tag", tag_id)
  if raw is None:
    return None

  lines = raw.strip().split('\n')
  tag_info = {'id': tag_id, 'object': '', 'type': '',
              'tag': '', 'tagger': '', 'comment': []}
  idx = 0
  while idx < len(lines):
    line = lines[idx]
    if not line:
      idx += 1
      break
    if line.startswith('object '):
      tag_info['object'] = line.removeprefix('object ')
    elif line.startswith('type '):
      tag_info['type'] = line.removeprefix('type ')
    elif line.startswith('tag '):
      tag_info['tag'] = line.removeprefix('tag ')
    elif line.startswith('tagger '):
      tag_info['tagger'] = line.removeprefix('tagger ')
    idx += 1

  tag_info['comment'] = lines[idx:]
  return tag_info


def _split_ident(ident):
  """Split a "Name <email>" ident into (name, email), mirroring gitweb.

  Falls back to (ident, "") when there is no angle-bracket address."""
  m = re.match(r"([^<]+) <([^>]*)>", ident)
  if m:
    return m.group(1), m.group(2)
  return ident, ""


def parse_commit(commit_id):
  # Get raw commit data with git rev-list --header --max-count=1
  raw = run_git("rev-list", "--header", "--max-count=1", commit_id)
  if not raw:
    return None

  # rev-list --header terminates each commit with a NUL byte. Commit
  # objects cannot contain NUL, so it is safe to strip it entirely;
  # otherwise it would leak into co['comment'] (and thus into feeds as
  # an illegal XML character).
  lines = raw.replace("\0", "").strip().split("\n")
  if not lines:
    return None

  co = {}
  # First line is the commit hash (parents come on 'parent ' lines).
  header = lines[0]
  parts = header.split()
  co['id'] = parts[0]
  co['parents'] = []

  i = 1
  while i < len(lines) and lines[i]:
    line = lines[i]
    if line.startswith("tree "):
      co['tree'] = line.removeprefix('tree ')
    elif line.startswith("parent "):
      co['parents'].append(line.removeprefix('parent '))
    elif line.startswith("author "):
      match = re.match(r"author (.*) ([0-9]+) (.*)", line)
      if match:
        co['author'] = match.group(1)
        co['author_epoch'] = int(match.group(2))
        co['author_tz'] = match.group(3)
        co['author_name'], co['author_email'] = _split_ident(co['author'])
    elif line.startswith("committer "):
      match = re.match(r"committer (.*) ([0-9]+) (.*)", line)
      if match:
        co['committer'] = match.group(1)
        co['committer_epoch'] = int(match.group(2))
        co['committer_tz'] = match.group(3)
        co['committer_name'], co['committer_email'] = _split_ident(
            co['committer'])
    i += 1

  # Commit message. rev-list --header indents every message line by
  # exactly four spaces (blank lines become four spaces); strip only
  # that prefix so intentional indentation in the message is preserved.
  co['comment'] = []
  i += 1  # Skip empty line
  while i < len(lines):
    line = lines[i]
    co['comment'].append(line.removeprefix('    '))
    i += 1

  if co['comment']:
    co['title'] = co['comment'][0]
  else:
    co['title'] = "(no commit message)"

  return co


def parse_tree(tree_id):
  raw = run_git("ls-tree", "-z", tree_id)
  if raw is None:
    return []

  entries = []
  for entry in raw.split('\0'):
    if not entry:
      continue
    # mode type hash name
    match = re.match(r"([0-7]+)\s+(\w+)\s+([0-9a-f]{40,64})\s+(.*)", entry)
    if match:
      entries.append({
          'mode': match.group(1),
          'type': match.group(2),
          'hash': match.group(3),
          'name': match.group(4)
      })
  return entries

# --- Actions ---


def _repo_git_dir(path):
  """Return the .git dir if *path* is a git repository, else None.

  Recognizes both bare repos (objects/ at top level) and working repos
  (.git/objects)."""
  if os.path.exists(os.path.join(path, "objects")):
    return path
  if os.path.exists(os.path.join(path, ".git", "objects")):
    return os.path.join(path, ".git")
  return None


def get_projects():
  projects = []
  if not os.path.isdir(PROJECT_ROOT):
    return projects

  # Walk PROJECT_ROOT looking for git repositories, descending into
  # non-repo directories so nested projects (e.g. group/sub.git) are
  # listed too. A directory that is itself a repo is recorded and not
  # descended into.
  for dirpath, dirnames, _ in os.walk(PROJECT_ROOT):
    # Skip dot-directories (e.g. .git) and don't descend into them.
    dirnames[:] = sorted(d for d in dirnames if not d.startswith('.'))
    proj_git_dir = _repo_git_dir(dirpath)
    if proj_git_dir:
      rel = os.path.relpath(dirpath, PROJECT_ROOT)
      desc = get_project_description(proj_git_dir)
      owner = get_project_owner(proj_git_dir)
      projects.append({
          'path': rel,
          'git_dir': proj_git_dir,
          'description': desc,
          'owner': owner
      })
      dirnames[:] = []  # don't descend into a repository
  projects.sort(key=lambda p: p['path'])
  return projects


def git_project_list():
  git_header_html()
  print('<div class="projlib">')
  print('<h1>Projects</h1>')
  print('<table class="project_list">')
  print('<tr><th>Project</th><th>Description</th><th>Owner</th></tr>')

  projects = get_projects()
  for pr in projects:
    url = href(project=pr['path'], action="summary")
    print(
        f'<tr><td><a href="{esc_url(url)}" class="project">{esc_html(pr["path"])}</a></td>')
    print(
        f'<td>{esc_html(pr["description"])}</td><td>{esc_html(pr["owner"])}</td></tr>')

  print('</table>')
  print('</div>')
  git_footer_html()


def git_project_index():
  projects = get_projects()
  print("Status: 200 OK")
  print("Content-Type: text/plain; charset=utf-8")
  print('Content-Disposition: inline; filename="index.aux"')
  print()
  for pr in projects:
    # Simple escaping for space as per gitweb.perl. Strip CR/LF/NUL so a
    # project path or owner containing them can't splice extra entries
    # into this machine-readable index.
    path = esc_header(pr['path']).replace(' ', '+')
    owner = esc_header(pr['owner']).replace(' ', '+')
    print(f"{path} {owner}")


def git_summary():
  global git_dir
  path = os.path.join(PROJECT_ROOT, project)
  if os.path.exists(os.path.join(path, ".git")):
    git_dir = os.path.join(path, ".git")
  else:
    git_dir = path

  git_header_html()
  print(f'<h1>Summary for {esc_html(project)}</h1>')

  desc = get_project_description(git_dir)
  owner = get_project_owner(git_dir)
  urls = get_project_cloneurls(git_dir)

  print('<table class="projects_list">')
  if desc:
    print(f'<tr><td>description</td><td>{esc_html(desc)}</td></tr>')
  if owner:
    print(f'<tr><td>owner</td><td>{esc_html(owner)}</td></tr>')
  print('</table>')

  if urls:
    print('<p>Clone urls:</p>')
    print('<table class="cloneurls">')
    for url in urls:
      print(f'<tr><td><a href="{esc_url(url)}">{esc_html(url)}</a></td></tr>')
    print('</table>')

  # Show last few commits as a teaser
  print('<h2>Recent commits</h2>')
  log_raw = run_git("rev-list", "--max-count=5", "HEAD")
  if log_raw:
    print('<table class="shortlog">')
    for commit_id in log_raw.strip().split("\n"):
      co = parse_commit(commit_id)
      if co:
        url = href(project=project, action="commit", hash=commit_id)
        dt = commit_datetime(co).strftime("%Y-%m-%d")
        print(
            f'<tr><td>{dt}</td><td><a href="{esc_url(url)}" class="list">{esc_html(co.get("author", ""))}</a></td>')
        print(
            f'<td><a href="{esc_url(url)}" class="list">{esc_html(co["title"])}</a></td>')
        diff_url = href(project=project, action="commitdiff", hash=commit_id)
        patch_url = href(project=project, action="patch", hash=commit_id)
        tree_url = href(project=project, action="tree", hash=commit_id)
        snapshot_url = href(project=project, action="snapshot",
                            hash=commit_id, snapshot_format="tgz")
        print(f'<td class="link"><a href="{esc_url(url)}">commit</a> | <a href="{esc_url(diff_url)}">commitdiff</a> | <a href="{esc_url(patch_url)}">patch</a> | <a href="{esc_url(tree_url)}">tree</a> | <a href="{esc_url(snapshot_url)}">snapshot</a></td></tr>')
    print('</table>')

  # Teaser for tags
  tags = parse_refs("refs/tags", max_count=10)
  if tags:
    print('<h2>Tags</h2>')
    _print_refs_table(tags, 'tags')

  # Teaser for heads
  heads = parse_refs("refs/heads", max_count=10)
  if heads:
    print('<h2>Heads</h2>')
    _print_refs_table(heads, 'heads')

  git_footer_html()


def _print_refs_table(refs, ref_type):
  if not refs:
    print('<p>No refs found.</p>')
    return

  print(f'<table class="{ref_type}">')
  for ref in refs:
    co = parse_commit(ref['peeled'])
    if not co:
      continue

    dt = commit_datetime(co).strftime("%Y-%m-%d")
    name = ref['name']

    log_url = href(project=project, action="log", hash=name)
    patch_url = href(project=project, action="patch", hash=name)
    tree_url = href(project=project, action="tree", hash=name)
    snapshot_url = href(project=project, action="snapshot",
                        hash=name, snapshot_format="tgz")

    print(f'<tr><td>{dt}</td>')

    if ref_type == 'tags' and ref['type'] == 'tag':
      tag_url = href(project=project, action="tag", hash=name)
      print(
          f'<td><a href="{esc_url(tag_url)}" class="list name">{esc_html(name)}</a></td>')
      print(f'<td class="link"><a href="{esc_url(log_url)}">log</a> | <a href="{esc_url(tag_url)}">tag</a> | <a href="{esc_url(patch_url)}">patch</a> | <a href="{esc_url(snapshot_url)}">snapshot</a></td></tr>')
    elif ref_type == 'tags':
      commit_url = href(project=project, action="commit", hash=ref['id'])
      print(
          f'<td><a href="{esc_url(commit_url)}" class="list name">{esc_html(name)}</a></td>')
      print(f'<td class="link"><a href="{esc_url(log_url)}">log</a> | <a href="{esc_url(commit_url)}">commit</a> | <a href="{esc_url(patch_url)}">patch</a> | <a href="{esc_url(snapshot_url)}">snapshot</a></td></tr>')
    else:
      print(
          f'<td><a href="{esc_url(log_url)}" class="list name">{esc_html(name)}</a></td>')
      print(f'<td class="link"><a href="{esc_url(log_url)}">log</a> | <a href="{esc_url(tree_url)}">tree</a> | <a href="{esc_url(patch_url)}">patch</a> | <a href="{esc_url(snapshot_url)}">snapshot</a></td></tr>')
  print('</table>')


def git_heads():
  global git_dir
  path = os.path.join(PROJECT_ROOT, project)
  git_dir = os.path.join(path, ".git") if os.path.exists(
      os.path.join(path, ".git")) else path

  git_header_html()
  print('<h1>Heads</h1>')
  refs = parse_refs('refs/heads')
  _print_refs_table(refs, 'heads')
  git_footer_html()


def git_tags():
  global git_dir
  path = os.path.join(PROJECT_ROOT, project)
  git_dir = os.path.join(path, ".git") if os.path.exists(
      os.path.join(path, ".git")) else path

  git_header_html()
  print('<h1>Tags</h1>')
  refs = parse_refs('refs/tags')
  _print_refs_table(refs, 'tags')
  git_footer_html()


def git_remotes():
  global git_dir
  path = os.path.join(PROJECT_ROOT, project)
  git_dir = os.path.join(path, ".git") if os.path.exists(
      os.path.join(path, ".git")) else path

  git_header_html()
  print('<h1>Remotes</h1>')
  refs = parse_refs('refs/remotes')
  _print_refs_table(refs, 'remotes')
  git_footer_html()


def git_tag():
  global git_dir, hash_id
  path = os.path.join(PROJECT_ROOT, project)
  git_dir = os.path.join(path, ".git") if os.path.exists(
      os.path.join(path, ".git")) else path

  if not hash_id:
    hash_id = params.get('h', [''])[0]

  tag_info = parse_tag(hash_id)
  git_header_html()

  if not tag_info or not tag_info.get('tag'):
    print(f"<h1>Tag not found or invalid</h1>")
    git_footer_html()
    return

  print(f'<h1>Tag {esc_html(tag_info["tag"])}</h1>')
  print('<table class="object_header">')
  print(
      f'<tr><td>object</td><td><a href="{esc_url(href(project=project, action=tag_info["type"], hash=tag_info["object"]))}">{esc_html(tag_info["object"])}</a></td></tr>')
  print(f'<tr><td>author</td><td>{esc_html(tag_info["tagger"])}</td></tr>')
  print('</table>')
  print('<div class="page_body">')
  for line in tag_info['comment']:
    print(f'{esc_html(line)}<br/>')
  print('</div>')
  git_footer_html()


def git_log():
  global git_dir, hash_id
  path = os.path.join(PROJECT_ROOT, project)
  git_dir = os.path.join(path, ".git") if os.path.exists(
      os.path.join(path, ".git")) else path

  if not hash_id:
    hash_id = params.get('h', ['HEAD'])[0]

  file_name = params.get('f', [None])[0]

  try:
    pg = int(params.get('pg', ['0'])[0])
  except ValueError:
    pg = 0

  page_size = 100
  skip = pg * page_size

  git_header_html()

  title = f'Log for {esc_html(hash_id)}'
  if file_name:
    title += f' : {esc_html(file_name)}'
  print(f'<h1>{title}</h1>')

  cmd = ["rev-list", f"--skip={skip}", f"--max-count={page_size + 1}", hash_id]
  if file_name:
    cmd.extend(["--", file_name])

  log_raw = run_git(*cmd)

  commits = []
  if log_raw:
    commits = [c for c in log_raw.strip().split("\n") if c]

  has_next = len(commits) > page_size
  commits = commits[:page_size]

  # Pagination UI
  print('<div class="page_nav">')
  if pg > 0:
    prev_url = href(project=project, action=params.get("a", ["log"])[
                    0], hash=hash_id, file_name=file_name, page=pg-1)
    print(f'<a href="{esc_url(prev_url)}">prev</a> | ')
  else:
    print('prev | ')

  if has_next:
    next_url = href(project=project, action=params.get("a", ["log"])[
                    0], hash=hash_id, file_name=file_name, page=pg+1)
    print(f'<a href="{esc_url(next_url)}">next</a>')
  else:
    print('next')
  print('</div>')

  if not commits:
    print('<p>No commits found.</p>')
  else:
    print('<table class="shortlog">')
    for commit_id in commits:
      co = parse_commit(commit_id)
      if co:
        url = href(project=project, action="commit", hash=commit_id)
        dt = commit_datetime(co).strftime("%Y-%m-%d")
        print(f'<tr><td>{dt}</td><td>{esc_html(co.get("author", ""))}</td>')
        print(
            f'<td><a href="{esc_url(url)}" class="list">{esc_html(co["title"])}</a></td>')
        diff_url = href(project=project, action="commitdiff", hash=commit_id)
        patch_url = href(project=project, action="patch", hash=commit_id)
        print(
            f'<td class="link"><a href="{esc_url(diff_url)}">commitdiff</a> | <a href="{esc_url(patch_url)}">patch</a></td></tr>')
    print('</table>')

  git_footer_html()


def git_tree():
  global git_dir, hash_id
  path = os.path.join(PROJECT_ROOT, project)
  git_dir = os.path.join(path, ".git") if os.path.exists(
      os.path.join(path, ".git")) else path

  if not hash_id:
    hash_id = "HEAD"

  hash_base = params.get('hb', [hash_id])[0]
  file_name = params.get('f', [''])[0]

  git_header_html()

  print('<div class="page_nav">')
  print(f'<a href="{esc_url(href(project=project, action="history", hash=hash_base, file_name=file_name))}">history</a> | ')
  print(f'<a href="{esc_url(href(project=project, action="snapshot", hash=hash_base, file_name=file_name, snapshot_format="tgz"))}">snapshot</a>')
  print('</div>')

  title = f'Tree for {esc_html(project)} at {esc_html(hash_base)}'
  if file_name:
    title += f' : {esc_html(file_name)}'
  print(f'<h1>{title}</h1>')

  # Resolve the tree to list. hash_id may be a commit (use its tree, or
  # the subtree at file_name), a tree hash (subtree navigation via the
  # UI threads the subtree hash here), or fall back to hash_id itself.
  co = parse_commit(hash_id)
  if co and 'tree' in co:
    if file_name:
      tree_id = _resolve_tree_hash(hash_base, file_name) or co['tree']
    else:
      tree_id = co['tree']
  else:
    tree_id = hash_id

  entries = parse_tree(tree_id)
  print('<table class="tree">')
  for entry in entries:
    f_name = entry['name']
    f_path = f"{file_name}/{f_name}" if file_name else f_name

    if entry['type'] == 'blob':
      url = href(project=project, action="blob",
                 hash=entry['hash'], file_name=f_path, hash_base=hash_base)
      hist_url = href(project=project, action="history",
                      hash=hash_base, file_name=f_path)
      raw_url = href(project=project, action="blob_plain",
                     hash=entry['hash'], file_name=f_path)
      diff_url = href(project=project, action="blobdiff",
                      hash_base=hash_base, file_name=f_path)

      print(
          f'<tr><td class="mode">{esc_html(entry["mode"])}</td><td class="type">{esc_html(entry["type"])}</td>')
      print(
          f'<td><a href="{esc_url(url)}" class="list">{esc_html(f_name)}</a></td>')
      print(
          f'<td class="link"><a href="{esc_url(url)}">blob</a> | <a href="{esc_url(hist_url)}">history</a> | <a href="{esc_url(raw_url)}">raw</a> | <a href="{esc_url(diff_url)}">diff</a></td></tr>')
    else:
      url = href(project=project, action="tree",
                 hash=entry['hash'], file_name=f_path, hash_base=hash_base)
      hist_url = href(project=project, action="history",
                      hash=hash_base, file_name=f_path)

      print(
          f'<tr><td class="mode">{esc_html(entry["mode"])}</td><td class="type">{esc_html(entry["type"])}</td>')
      print(
          f'<td><a href="{esc_url(url)}" class="list">{esc_html(f_name)}</a></td>')
      print(
          f'<td class="link"><a href="{esc_url(url)}">tree</a> | <a href="{esc_url(hist_url)}">history</a></td></tr>')
  print('</table>')

  git_footer_html()


def _resolve_blob_hash(hash_base, file_name):
  if not hash_base or not file_name:
    return None
  raw = run_git("ls-tree", hash_base, "--", file_name)
  if not raw or not raw.strip():
    return None
  parts = raw.split()
  if len(parts) >= 3:
    return parts[2]
  return None


def _resolve_tree_hash(hash_base, file_name):
  """Return the tree hash of *file_name* within *hash_base*, or None.

  Used when git_tree is given a commit plus a path (h=<commit>&f=<dir>)
  so the subtree -- not the root tree -- is listed."""
  if not hash_base or not file_name:
    return None
  raw = run_git("ls-tree", hash_base, "--", file_name)
  if not raw or not raw.strip():
    return None
  parts = raw.split()
  # mode type hash name -- hash is always the third whitespace token
  if len(parts) >= 3 and parts[1] == 'tree':
    return parts[2]
  return None


def git_blob():
  global git_dir, hash_id
  path = os.path.join(PROJECT_ROOT, project)
  git_dir = os.path.join(path, ".git") if os.path.exists(
      os.path.join(path, ".git")) else path

  hash_base = params.get('hb', ['HEAD'])[0]
  file_name = params.get('f', [''])[0]

  if not hash_id and hash_base and file_name:
    hash_id = _resolve_blob_hash(hash_base, file_name)

  git_header_html()

  print('<div class="page_nav">')
  print(f'<a href="{esc_url(href(project=project, action="history", hash=hash_base, file_name=file_name))}">history</a> | ')
  print(f'<a href="{esc_url(href(project=project, action="blob_plain", hash=hash_id, file_name=file_name))}">raw</a> | ')
  print(f'<a href="{esc_url(href(project=project, action="blame", hash_base=hash_base, file_name=file_name))}">blame</a>')
  print('</div>')

  title = f'Blob {esc_html(hash_id)}'
  if file_name:
    title += f' : {esc_html(file_name)}'
  print(f'<h1>{title}</h1>')

  if not hash_id:
    print("<p>Blob not found</p>")
    git_footer_html()
    return

  # Read the blob as bytes so binary files don't raise UnicodeDecodeError
  # (the text-mode run_git would swallow that into a generic error and
  # render nothing). We decode with 'replace' only for display.
  blob_data = run_git_bin("cat-file", "blob", hash_id)
  if blob_data is None:
    print("<p>Blob not found</p>")
    git_footer_html()
    return

  print('<div class="page_body">')
  highlighted = None
  if USE_HIGHLIGHT and os.path.exists(HIGHLIGHT_BIN) and file_name:
    try:
      cmd = [HIGHLIGHT_BIN, "-f", "-O", "html",
             "--inline-css", f"--syntax-by-name={file_name}"]
      p = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
      stdout, _ = p.communicate(input=blob_data)
      if p.returncode == 0:
        highlighted = stdout.decode('utf-8', 'replace')
    except Exception:
      pass

  if highlighted is None:
    highlighted = esc_html(blob_data)

  print('<table class="code" id="blob">')
  for i, line in enumerate(highlighted.splitlines(), start=1):
    print(
        f'<tr><td class="num"><a id="l{i}" href="#l{i}" class="linenr">{i:4}</a></td><td class="code"><div class="pre">{line}</div></td></tr>')
  print('</table>')
  print('</div>')

  git_footer_html()


def git_blob_plain():
  global git_dir, hash_id
  path = os.path.join(PROJECT_ROOT, project)
  git_dir = os.path.join(path, ".git") if os.path.exists(
      os.path.join(path, ".git")) else path

  file_name = params.get('f', [''])[0]
  hash_base = params.get('hb', ['HEAD'])[0]
  if not hash_id:
    hash_id = params.get('h', [''])[0]

  if not hash_id and hash_base and file_name:
    hash_id = _resolve_blob_hash(hash_base, file_name)

  if not hash_id:
    print("Status: 400 Bad Request")
    print("Content-Type: text/plain\n")
    print("Missing hash parameter")
    return

  blob_data = run_git_bin("cat-file", "blob", hash_id)
  if blob_data is None:
    print("Status: 404 Not Found")
    print("Content-Type: text/plain\n")
    print("Blob not found")
    return

  import mimetypes
  import sys

  mime_type, _ = mimetypes.guess_type(file_name) if file_name else (None, None)
  if not mime_type:
    if b'\0' in blob_data[:8000]:
      mime_type = "application/octet-stream"
    else:
      mime_type = "text/plain"

  print("Status: 200 OK")
  print(f"Content-Type: {mime_type}")
  if file_name:
    print(f'Content-Disposition: inline; filename="{esc_header(file_name)}"')
  print()
  sys.stdout.flush()
  sys.stdout.buffer.write(blob_data)
  sys.stdout.buffer.flush()


def git_history():
  git_log()


def git_commit():
  global git_dir, hash_id
  path = os.path.join(PROJECT_ROOT, project)
  git_dir = os.path.join(path, ".git") if os.path.exists(
      os.path.join(path, ".git")) else path

  co = parse_commit(hash_id)
  git_header_html()
  if co:
    print(f'<h1>Commit {esc_html(hash_id)}</h1>')
    print(f'<p>Author: {esc_html(co.get("author", ""))}</p>')
    print(f'<p>Committer: {esc_html(co.get("committer", ""))}</p>')
    print('<pre>')
    print(esc_html("\n".join(co["comment"])))
    print('</pre>')

    # Parent links
    parents = co.get('parents', [])
    if parents:
      links = []
      for parent_id in parents:
        p_url = href(project=project, action="commit", hash=parent_id)
        links.append(f'<a href="{esc_url(p_url)}">{esc_html(parent_id)}</a>')
      print(f'<p>Parent: {" | ".join(links)}</p>')

    # Link to tree
    tree_url = href(project=project, action="tree", hash=co['tree'])
    print(f'<p><a href="{esc_url(tree_url)}">Browse Tree</a></p>')

    # Link to diff
    diff_url = href(project=project, action="commitdiff", hash=hash_id)
    print(f'<p><a href="{esc_url(diff_url)}">View Diff</a></p>')

    # Link to snapshot
    snapshot_url = href(project=project, action="snapshot",
                        hash=hash_id, snapshot_format="tgz")
    print(
        f'<p><a href="{esc_url(snapshot_url)}">Download Snapshot (tar.gz)</a></p>')
  else:
    print("Commit not found")
  git_footer_html()


def git_blobdiff_plain():
  git_commitdiff(format='plain')


def git_commitdiff_plain():
  git_commitdiff(format='plain')


def git_patch():
  git_commitdiff(format='patch', single=True)


def git_patches():
  git_commitdiff(format='patch', single=False)


def print_diff_lines(ctx, rem, add, diff_style):
  if diff_style == 'sidebyside':
    if ctx:
      print('<div class="chunk_block ctx">')
      print('<div class="old">')
      for line in ctx:
        print(f'<div class="diff ctx">{esc_html(line)}</div>')
      print('</div><div class="new">')
      for line in ctx:
        print(f'<div class="diff ctx">{esc_html(line)}</div>')
      print('</div></div>')

    if rem or add:
      if not add:
        print('<div class="chunk_block rem"><div class="old">')
        for line in rem:
          print(f'<div class="diff rem">{esc_html(line)}</div>')
        print('</div></div>')
      elif not rem:
        print('<div class="chunk_block add"><div class="new">')
        for line in add:
          print(f'<div class="diff add">{esc_html(line)}</div>')
        print('</div></div>')
      else:
        print('<div class="chunk_block chg"><div class="old">')
        for line in rem:
          print(f'<div class="diff rem">{esc_html(line)}</div>')
        print('</div><div class="new">')
        for line in add:
          print(f'<div class="diff add">{esc_html(line)}</div>')
        print('</div></div>')
  else:
    for line in ctx:
      print(f'<div class="ctx">{esc_html(line)}</div>')
    for line in rem:
      print(f'<div class="rem">{esc_html(line)}</div>')
    for line in add:
      print(f'<div class="add">{esc_html(line)}</div>')


def git_commitdiff(format='html', single=False):
  global git_dir, hash_id, params
  path = os.path.join(PROJECT_ROOT, project)
  git_dir = os.path.join(path, ".git") if os.path.exists(
      os.path.join(path, ".git")) else path

  hash_parent = params.get('hp', [None])[0]
  hash_base = params.get('hb', [None])[0]
  hash_parent_base = params.get('hpb', [None])[0]
  file_name = params.get('f', [None])[0]
  file_parent = params.get('fp', [None])[0]
  diff_style = params.get('ds', ['inline'])[0]

  if not hash_id:
    hash_id = hash_base or "HEAD"

  co = parse_commit(hash_id)
  if format != 'patch' and not hash_parent and not (hash_parent_base and hash_base):
    if co:
      if len(co.get('parents', [])) > 1:
        hash_parent = "--cc"
      elif co.get('parents', []):
        hash_parent = co['parents'][0]
      else:
        hash_parent = "--root"

  if format == 'patch':
    if single:
      # A single commit's patch: always exactly one, against its parent
      # (--root is a no-op for non-root commits). An explicit hp is not
      # honored here because format-patch has no way to select a parent
      # for a single commit.
      commit_spec = ["-1", "--root", hash_id]
    else:
      commit_spec = []
      if hash_parent:
        commit_spec.extend(["-n", f"{hash_parent}..{hash_id}"])
      else:
        commit_spec.append("-n")
        commit_spec.extend(["--root", hash_id])
      if PATCHES_LIMIT > 0:
        commit_spec.insert(0, f"-{PATCHES_LIMIT}")

    filename = f"{os.path.basename(project)}-{hash_id[:7]}.patch"
    print("Status: 200 OK")
    print("Content-Type: text/plain; charset=utf-8")
    print(f'Content-Disposition: inline; filename="{esc_header(filename)}"')
    print()

    raw = run_git_bin("format-patch", "--stdout", *commit_spec)
    if raw:
      sys.stdout.flush()
      sys.stdout.buffer.write(raw)
      sys.stdout.buffer.flush()
    return

  if format == 'plain':
    cmd = ["diff-tree", "-r", "-p", "--full-index", "--no-commit-id"]
    # Enable rename detection when comparing an old path to a new one
    # (blobdiff with file_parent), so the result is a single rename diff
    # rather than a separate delete+add.
    if file_parent and file_parent != file_name:
      cmd.append("-M")
    if hash_parent:
      if hash_parent == "--root":
        cmd.extend(["--root", hash_id])
      else:
        cmd.extend([hash_parent, hash_id])
    elif hash_parent_base and hash_base:
      cmd.extend([hash_parent_base, hash_base])
    else:
      cmd.extend(["--root", hash_id])

    if file_name:
      if "--" not in cmd:
        cmd.append("--")
      if file_parent:
        cmd.append(file_parent)
      cmd.append(file_name)

    diff = run_git(*cmd)
    print("Status: 200 OK")
    print("Content-Type: text/plain; charset=utf-8")
    print()
    if diff:
      print(diff)
    return

  # HTML format
  git_header_html()

  title = f'Commit diff for {esc_html(hash_id)}'
  if file_name:
    title = f'Blob diff for {esc_html(file_name)}'
  print(f'<h1>{title}</h1>')

  # Navigation for formats and styles
  print('<div class="page_nav">')
  print(
      f'<a href="{esc_url(href(action="commitdiff_plain", replay=True))}">raw</a> | ')
  print(f'<a href="{esc_url(href(action="patch", replay=True))}">patch</a> | ')

  styles = [('inline', 'inline'), ('sidebyside', 'side by side')]
  style_nav = []
  for s_id, s_label in styles:
    if s_id == diff_style:
      style_nav.append(s_label)
    else:
      style_nav.append(
          f'<a href="{esc_url(href(diff_style=s_id, replay=True))}">{s_label}</a>')
  print(" | ".join(style_nav))
  print('</div>')

  cmd = ["diff-tree", "-r", "-p", "--full-index", "--no-commit-id"]
  if file_parent and file_parent != file_name:
    cmd.append("-M")
  if hash_parent:
    if hash_parent == "--root":
      cmd.extend(["--root", hash_id])
    else:
      cmd.extend([hash_parent, hash_id])
  elif hash_parent_base and hash_base:
    cmd.extend([hash_parent_base, hash_base])
  else:
    cmd.extend(["--root", hash_id])

  if file_name:
    if "--" not in cmd:
      cmd.append("--")
    if file_parent:
      cmd.append(file_parent)
    cmd.append(file_name)

  diff_raw = run_git(*cmd) or ""

  print('<div class="patchset">')

  ctx, rem, add = [], [], []

  for line in diff_raw.split('\n'):
    if line.startswith('diff --git'):
      if ctx or rem or add:
        print_diff_lines(ctx, rem, add, diff_style)
        ctx, rem, add = [], [], []
      print(f'<div class="diff header">{esc_html(line)}</div>')
    elif line.startswith('--- ') or line.startswith('+++ ') or line.startswith('index '):
      print(f'<div class="diff extended_header">{esc_html(line)}</div>')
    elif line.startswith('@@ '):
      if ctx or rem or add:
        print_diff_lines(ctx, rem, add, diff_style)
        ctx, rem, add = [], [], []
      print(f'<div class="diff chunk_header">{esc_html(line)}</div>')
    elif line.startswith('+'):
      add.append(line)
    elif line.startswith('-'):
      rem.append(line)
    elif line.startswith(' '):
      if rem or add:
        print_diff_lines(ctx, rem, add, diff_style)
        ctx, rem, add = [], [], []
      ctx.append(line)
    else:
      # Other header lines
      if line.strip():
        print(f'<div class="diff ctx">{esc_html(line)}</div>')

  if ctx or rem or add:
    print_diff_lines(ctx, rem, add, diff_style)

  print('</div>')
  git_footer_html()


def git_blame():
  global git_dir, hash_id
  path = os.path.join(PROJECT_ROOT, project)
  git_dir = os.path.join(path, ".git") if os.path.exists(
      os.path.join(path, ".git")) else path

  file_name = params.get('f', [None])[0]
  hash_base = params.get('hb', ['HEAD'])[0]

  git_header_html()
  print(f'<h1>Blame {esc_html(file_name)} at {esc_html(hash_base)}</h1>')

  if file_name:
    blame_raw = run_git("blame", "-c", hash_base, "--", file_name)
    if blame_raw is not None:
      print('<table class="blame">')
      for line in blame_raw.split('\n'):
        if not line:
          continue
        # Simple parsing of `git blame -c`
        parts = line.split('\t')
        if len(parts) >= 3:
          print(f'<tr><td class="sha1">{esc_html(parts[0][:8])}</td>')
          print(f'<td class="author">{esc_html(parts[1])}</td>')
          print(f'<td class="content">{esc_html(parts[-1])}</td></tr>')
      print('</table>')
    else:
      print('<p>Error running blame.</p>')
  else:
    print('<p>No file specified for blame.</p>')

  git_footer_html()


def git_search():
  global git_dir, hash_id
  path = os.path.join(PROJECT_ROOT, project)
  git_dir = os.path.join(path, ".git") if os.path.exists(
      os.path.join(path, ".git")) else path

  searchtext = params.get('s', [None])[0]
  searchtype = params.get('st', ['commit'])[0]

  if not hash_id:
    hash_id = "HEAD"

  git_header_html()
  print(
      f'<h1>Search results for "{esc_html(searchtext)}" in {esc_html(project)}</h1>')

  if not searchtext:
    print('<p>No search text specified.</p>')
  elif searchtype in ['commit', 'author', 'committer', 'pickaxe']:
    # search_use_regexp ('sr') is honored by every type, matching gitweb:
    # commit/author/committer use --fixed-strings vs --extended-regexp
    # (with --regexp-ignore-case always on); pickaxe uses -S with
    # --pickaxe-regex.
    use_regexp = params.get('sr', ['0'])[0] == '1'
    if searchtype in ('commit', 'author', 'committer'):
      flag = {'commit': '--grep', 'author': '--author',
              'committer': '--committer'}[searchtype]
      cmd = ["rev-list", f"{flag}={searchtext}", "--max-count=100",
             "--regexp-ignore-case",
             "--extended-regexp" if use_regexp else "--fixed-strings",
             hash_id]
      log_raw = run_git(*cmd)
    else:  # pickaxe
      cmd = ["log", "--format=%H", f"-S{searchtext}", "--max-count=100"]
      if use_regexp:
        cmd.append("--pickaxe-regex")
      cmd.append(hash_id)
      log_raw = run_git(*cmd)

    if log_raw and log_raw.strip():
      print('<table class="shortlog">')
      for commit_id in log_raw.strip().split("\n"):
        co = parse_commit(commit_id)
        if co:
          url = href(project=project, action="commit", hash=commit_id)
          dt = commit_datetime(co).strftime("%Y-%m-%d")
          print(f'<tr><td>{dt}</td><td>{esc_html(co.get("author", ""))}</td>')
          print(
              f'<td><a href="{esc_url(url)}" class="list">{esc_html(co["title"])}</a></td></tr>')
      print('</table>')
    else:
      print('<p>No commits found.</p>')
  elif searchtype == 'grep':
    # '-e' marks the pattern as a pattern even if it begins with '-',
    # preventing the user's search text from being parsed as a git flag.
    # '-z' NUL-separates the path/line/match fields so file paths that
    # contain colons parse correctly (the default ':' delimiter does not).
    # search_use_regexp selects extended-regex (case-insensitive) vs fixed
    # strings, matching gitweb.
    use_regexp = params.get('sr', ['0'])[0] == '1'
    if use_regexp:
      grep_cmd = ["grep", "-n", "-z", "-E", "-i", "-e", searchtext, hash_id]
    else:
      grep_cmd = ["grep", "-n", "-z", "-F", "-e", searchtext, hash_id]
    grep_raw = run_git(*grep_cmd)
    if grep_raw and grep_raw.strip("\n\0"):
      print('<table class="grep_results">')
      # Each record is "<rev>:<path>\0<line>\0<match>\n"; the rev prefix
      # is exactly hash_id, so strip it rather than guessing where the
      # path begins.
      prefix = f"{hash_id}:"
      for record in grep_raw.split("\n"):
        if not record:
          continue
        fields = record.split("\0")
        if len(fields) < 3:
          continue
        revpath, f_line, text = fields[0], fields[1], fields[2]
        f_name = revpath[len(prefix):] if revpath.startswith(prefix) else revpath

        # Link via hash_base so git_blob resolves the blob from the rev
        # (the grep output carries a rev, not a blob hash).
        url = href(project=project, action="blob",
                   hash_base=hash_id, file_name=f_name)
        print(
            f'<tr><td><a href="{esc_url(url)}">{esc_html(f_name)}</a>:{esc_html(f_line)}</td>')
        print(f'<td>{esc_html(text)}</td></tr>')
      print('</table>')
    else:
      print('<p>No matches found.</p>')

  git_footer_html()


def _generate_feed(feed_type):
  global git_dir, hash_id
  path = os.path.join(PROJECT_ROOT, project)
  git_dir = os.path.join(path, ".git") if os.path.exists(
      os.path.join(path, ".git")) else path

  if not hash_id:
    hash_id = "HEAD"

  print("Status: 200 OK")
  if feed_type == 'rss':
    print("Content-Type: text/xml; charset=utf-8")
  else:
    print("Content-Type: application/atom+xml; charset=utf-8")
  print()

  log_raw = run_git("rev-list", "--max-count=15", hash_id)
  if not log_raw:
    return

  commits = []
  for commit_id in log_raw.strip().split("\n"):
    co = parse_commit(commit_id)
    if co:
      commits.append(co)

  if not commits:
    return

  title = f"{SITE_NAME} - {project}"
  link = f"{my_url}?p={esc_param(project)}&a=summary"
  desc = f"Recent changes in {project}"

  if feed_type == 'rss':
    print('<?xml version="1.0" encoding="utf-8"?>')
    print('<rss version="2.0">')
    print('<channel>')
    print(f'<title>{esc_html(title)}</title>')
    print(f'<link>{esc_html(link)}</link>')
    print(f'<description>{esc_html(desc)}</description>')
    print('<language>en</language>')

    for co in commits:
      commit_link = f"{my_url}?p={esc_param(project)}&a=commit&h={co['id']}"
      # RFC 822 date in the commit's own timezone.
      dt = commit_datetime(co).strftime("%a, %d %b %Y %H:%M:%S %z")
      print('<item>')
      print(f'<title>{esc_html(co["title"])}</title>')
      print(f'<link>{esc_html(commit_link)}</link>')
      print(f'<guid isPermaLink="true">{esc_html(commit_link)}</guid>')
      print(f'<pubDate>{dt}</pubDate>')
      print(f'<author>{esc_html(co.get("author", ""))}</author>')
      print(f'<description>{esc_html(" ".join(co["comment"]))}</description>')
      print('</item>')

    print('</channel>')
    print('</rss>')
  else:
    print('<?xml version="1.0" encoding="utf-8"?>')
    print('<feed xmlns="http://www.w3.org/2005/Atom">')
    print(f'<title>{esc_html(title)}</title>')
    print(f'<link rel="alternate" type="text/html" href="{esc_html(link)}" />')
    print(f'<id>{esc_html(link)}</id>')
    print(
        f'<updated>{commit_datetime(commits[0]).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}</updated>')

    for co in commits:
      commit_link = f"{my_url}?p={esc_param(project)}&a=commit&h={co['id']}"
      # Atom requires UTC; convert from the commit's timezone.
      dt = commit_datetime(co).astimezone(
          timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
      print('<entry>')
      print(f'<title>{esc_html(co["title"])}</title>')
      print(
          f'<link rel="alternate" type="text/html" href="{esc_html(commit_link)}" />')
      print(f'<id>{esc_html(commit_link)}</id>')
      print(f'<updated>{dt}</updated>')
      print('<author>')
      print(
          f'<name>{esc_html(co.get("author_name", co.get("author", "")))}</name>')
      if co.get("author_email"):
        print(f'<email>{esc_html(co["author_email"])}</email>')
      print('</author>')
      print(
          f'<content type="text">{esc_html("\n".join(co["comment"]))}</content>')
      print('</entry>')

    print('</feed>')


def git_rss():
  _generate_feed('rss')


def git_atom():
  _generate_feed('atom')


def git_object():
  global git_dir, hash_id
  path = os.path.join(PROJECT_ROOT, project)
  git_dir = os.path.join(path, ".git") if os.path.exists(
      os.path.join(path, ".git")) else path

  if not hash_id:
    hash_id = 'HEAD'

  out = run_git("cat-file", "-t", hash_id)
  out = out.strip() if out else ""

  if out == "commit":
    git_commit()
  elif out == "tree":
    git_tree()
  elif out == "blob":
    git_blob()
  elif out == "tag":
    git_tag()
  else:
    print("Status: 404 Not Found")
    print("Content-Type: text/plain")
    print()
    print(f"Object {esc_header(hash_id)} not found or unknown type: {esc_header(out)}")


def git_snapshot():
  global git_dir, hash_id
  path = os.path.join(PROJECT_ROOT, project)
  git_dir = os.path.join(path, ".git") if os.path.exists(
      os.path.join(path, ".git")) else path

  sf = params.get('sf', ['tgz'])[0]
  formats = {
      'tgz': {'format': 'tgz', 'suffix': '.tar.gz', 'mimetype': 'application/x-gzip'},
      'tbz2': {'format': 'tar', 'compressor': ['bzip2'], 'suffix': '.tar.bz2', 'mimetype': 'application/x-bzip2'},
      'zip': {'format': 'zip', 'suffix': '.zip', 'mimetype': 'application/x-zip'},
  }

  if sf not in formats:
    sf = 'tgz'
  fmt = formats[sf]

  if not hash_id:
    hash_id = params.get('hb', ['HEAD'])[0]

  file_name = params.get('f', [''])[0]

  name = project
  if hash_id != 'HEAD':
    co = parse_commit(hash_id)
    if co:
      name += "-" + hash_id[:7]
    else:
      name += "-" + hash_id
  else:
    name += "-HEAD"

  if file_name:
    name += "-" + file_name.replace('/', '-')

  # name flows into both the archive --prefix and the Content-Disposition
  # filename; strip CR/LF/NUL so user-controlled hash/file values cannot
  # inject headers (response splitting).
  name = esc_header(name)
  filename = name + fmt['suffix']

  cmd = git_cmd() + ["archive",
                     f"--format={fmt['format']}", f"--prefix={name}/", hash_id]
  if file_name:
    cmd.extend(["--", file_name])

  print("Status: 200 OK")
  print(f"Content-Type: {fmt['mimetype']}")
  print(f"Content-Disposition: inline; filename=\"{esc_header(filename)}\"")
  print()
  sys.stdout.flush()

  try:
    subprocess.run(cmd, stdout=sys.stdout.buffer, stderr=subprocess.DEVNULL)
  except Exception:
    pass


ACTIONS = {
    "project_list": git_project_list,
    "summary": git_summary,
    "log": git_log,
    "tree": git_tree,
    "blob": git_blob,
    "commit": git_commit,
    "commitdiff": git_commitdiff,
    "blobdiff": git_commitdiff,
    "blobdiff_plain": git_commitdiff_plain,
    "commitdiff_plain": git_commitdiff_plain,
    "blame": git_blame,
    "search": git_search,
    "rss": git_rss,
    "atom": git_atom,
    "heads": git_heads,
    "tags": git_tags,
    "remotes": git_remotes,
    "tag": git_tag,
    "history": git_history,
    "blob_plain": git_blob_plain,
    "snapshot": git_snapshot,
    "patch": git_patch,
    "patches": git_patches,
    "shortlog": git_log,
    "object": git_object,
    "project_index": git_project_index,
}

# --- Main Flow ---

USE_PATHINFO = True


def evaluate_path_info():
  global project, action, hash_id, params
  path_info = os.environ.get("PATH_INFO", "").strip("/")
  if not path_info or 'p' in params:
    return

  parts = path_info.split("/")

  # 1. Find project
  project_cand = ""
  rest = []
  for i in range(len(parts), 0, -1):
    cand = "/".join(parts[:i])
    path = os.path.join(PROJECT_ROOT, cand)
    if os.path.isdir(path) and (os.path.exists(os.path.join(path, "objects")) or os.path.exists(os.path.join(path, ".git", "objects"))):
      project_cand = cand
      rest = parts[i:]
      break

  if not project_cand:
    return

  params['p'] = [project_cand]
  project = project_cand

  if not rest:
    return

  # 2. Find action
  action_cand = rest[0]
  if action_cand in ACTIONS:
    params['a'] = [action_cand]
    action = action_cand
    rest = rest[1:]

  if not rest:
    return

  # 3. Find hash / hash_base:file_name
  ref_path = "/".join(rest)
  if ":" in ref_path:
    hash_base_cand, file_name_cand = ref_path.split(":", 1)
    params['hb'] = [hash_base_cand]
    params['f'] = [file_name_cand]
    if 'a' not in params:
      params['a'] = ['blob_plain']
      action = 'blob_plain'
  else:
    params['h'] = [ref_path]
    hash_id = ref_path
    if 'a' not in params:
      params['a'] = ['shortlog']
      action = 'shortlog'


def run_request():
  global project, action, hash_id, my_uri, my_url, base_url, path_info, params

  # Parse query parameters manually
  query_string = os.environ.get('QUERY_STRING', '')
  if not query_string and len(sys.argv) > 1:
    # Allow testing from command line with key=value args
    query_string = "&".join(sys.argv[1:])

  params = urllib.parse.parse_qs(query_string)
  project = params.get('p', [None])[0]
  action = params.get('a', [None])[0]
  hash_id = params.get('h', [None])[0]

  my_url = os.environ.get('SCRIPT_NAME', 'gitweb.py')
  my_uri = my_url

  evaluate_path_info()

  if project and not is_valid_project(project):
    print("Status: 404 Not Found")
    print("Content-Type: text/plain")
    print()
    # esc_header strips CR/LF/NUL so a crafted project name can't splice
    # extra lines into this text/plain body.
    print(f"Invalid project: {esc_header(project)}")
    return

  if not action:
    if project:
      action = "summary"
    else:
      action = "project_list"

  if action in ACTIONS:
    ACTIONS[action]()
  else:
    print("Status: 404 Not Found")
    print("Content-Type: text/plain")
    print()
    print(f"Unknown action: {esc_header(action)}")


if __name__ == "__main__":
  run_request()
