#!/usr/bin/env bash
# One-time setup for the parity test harness.
#
# Installs the Perl CGI module into parity/perllocal WITHOUT sudo (the
# module was dropped from the Perl core in 5.22).  The HTML::Entities
# stub and the substituted upstream gitweb.pl are committed alongside
# this script, so no network access is needed for them.
#
# After running, the pytest harness finds everything via PERL5LIB and
# GITWEB_CONFIG set in parity/conftest.py.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PERLLOCAL="$DIR/perllocal"
PERL5LIB_DIR="$PERLLOCAL/lib/perl5"

if PERL5LIB="$PERL5LIB_DIR" perl -MCGI -MCGI::Carp -e 'exit 0' 2>/dev/null; then
  echo "[parity] CGI already available under $PERL5LIB_DIR"
  exit 0
fi

echo "[parity] Installing CGI into $PERLLOCAL (no sudo; tests skipped) ..."
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cd "$TMP"

# Pinned to 4.72 (matches the Arch extra/perl-cgi package).  Fetch from CPAN.
curl -fsSL -o cgi.tar.gz \
  "https://cpan.metacpan.org/authors/id/L/LE/LEEJO/CGI-4.72.tar.gz"
tar xzf cgi.tar.gz
cd CGI-4.72

# Build and install, deliberately skipping the test suite (it pulls in
# optional test-only deps like HTML::Entities::real, Test::NoWarnings).
perl Makefile.PL INSTALL_BASE="$PERLLOCAL"
make
make install

if PERL5LIB="$PERL5LIB_DIR" perl -MCGI -e 'print "CGI $CGI::VERSION ok\n"'; then
  echo "[parity] Done.  PERL5LIB=$PERL5LIB_DIR"
else
  echo "[parity] ERROR: CGI did not load after install" >&2
  exit 1
fi
