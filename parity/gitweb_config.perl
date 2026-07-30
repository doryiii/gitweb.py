# gitweb configuration for the parity test harness.
# The harness sets GITWEB_PROJECTROOT (and GITWEB_GIT_TEMP) to the shared
# fixture directory before invoking gitweb.pl, so this config just wires
# those env vars in and enables the features under test.

our $projectroot = $ENV{GITWEB_PROJECTROOT} || $projectroot;
our $git_temp    = $ENV{GITWEB_GIT_TEMP}    || $git_temp;

# Route warnings to stderr so CGI::Carp cannot splice them into stdout.
$SIG{__WARN__} = sub { print STDERR @_ };

# Enable the features the parity suite exercises.
$feature{'pathinfo'}{'default'}  = [1];
$feature{'search'}{'default'}    = [1];
$feature{'pickaxe'}{'default'}   = [1];
$feature{'grep'}{'default'}      = [1];
$feature{'snapshot'}{'default'}  = ['tgz', 'tbz2', 'zip'];
# Highlighting would make blob HTML diverge across implementations; the
# harness compares raw blob_plain bytes instead, so disable it to keep
# upstream deterministic.
$feature{'highlight'}{'default'} = [0];

1;
