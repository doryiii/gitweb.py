package HTML::Entities;
# Minimal pure-Perl stub used only by the parity test harness.
#
# CGI::escapeHTML does `eval { require HTML::Entities }` and, on failure,
# warns (which CGI::Carp splices into stdout, corrupting the page) before
# falling back to its internal escaper.  Providing this stub makes the
# require succeed so output is clean, and escapes the same character set
# CGI's fallback does -- enough for differential testing.  Do NOT use this
# as a real HTML::Entities; it has none of the real API.
use strict;
use warnings;
our $VERSION = '1.00';

sub encode_entities {
  my $str = shift;
  return '' unless defined $str;
  $str =~ s/&/&/g;
  $str =~ s/</</g;
  $str =~ s/>/>/g;
  $str =~ s/"/"/g;
  $str =~ s/'/&#39;/g;
  return $str;
}

sub encode_entities_numeric { goto &encode_entities; }

sub decode_entities {
  my $str = shift;
  return '' unless defined $str;
  $str =~ s/&#(\d+);/chr($1)/ge;
  $str =~ s/&#x([0-9a-fA-F]+);/chr(hex($1))/ge;
  $str =~ s/</</g;
  $str =~ s/>/>/g;
  $str =~ s/"/"/g;
  $str =~ s/'/'/g;
  $str =~ s/&#39;/'/g;
  $str =~ s/&/&/g;    # must be last
  return $str;
}

1;
