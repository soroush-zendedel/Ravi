#!/bin/sh
#
# fetch-debs.sh
# Download the .deb packages needed to build the offline Ravi Ollama image.
#
# Works on Ubuntu hosts by isolating apt from the host package database.
#
# Usage:
#   ./scripts/fetch-debs.sh --mirror http://mirror.arvancloud.ir/debian
#   ./scripts/fetch-debs.sh --mirror http://mirror.arvancloud.ir/debian --suite trixie
#   ./scripts/fetch-debs.sh --mirror http://mirror.arvancloud.ir/debian --suite bookworm --no-security
#   ./scripts/fetch-debs.sh --mirror http://ftp.de.debian.org/debian --security-mirror http://security.debian.org/debian-security
#   ./scripts/fetch-debs.sh --clean
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DEST_DIR="$PROJECT_ROOT/local/debs"
TMP_DIR="/tmp/ravi-debs-$$"

# Packages required by the Dockerfile (runtime + C++ llama server)
REQUIRED_PACKAGES="ca-certificates curl libstdc++6"

MIRROR=""
SECURITY_MIRROR=""
SUITE="resolute"
CLEAN=0
NO_SECURITY=0

info()  { echo "[*] $*"; }
warn()  { echo "[!] $*" >&2; }
error() { echo "[ERROR] $*" >&2; exit 1; }
step()  { echo; echo "==> $*"; }

usage() {
    cat << EOF
Usage: $(basename "$0") [OPTIONS]

Options:
  --mirror URL              Main Debian mirror (required)
  --security-mirror URL     Security mirror (optional, auto-derived if omitted)
  --suite NAME              Suite / codename (default: plucky (Ubuntu 25.04))
  --no-security             Do not use security repository
  --clean                   Delete old .deb files first
  -h, --help                Show this help
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --mirror)
            [ -n "$2" ] || error "--mirror needs a URL"
            MIRROR="$2"
            shift 2
            ;;
        --security-mirror)
            [ -n "$2" ] || error "--security-mirror needs a URL"
            SECURITY_MIRROR="$2"
            shift 2
            ;;
        --suite)
            [ -n "$2" ] || error "--suite needs a name"
            SUITE="$2"
            shift 2
            ;;
        --no-security)
            NO_SECURITY=1
            shift
            ;;
        --clean)
            CLEAN=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            error "Unknown option: $1"
            ;;
    esac
done

command -v apt-get  >/dev/null || error "apt-get not found"
command -v apt-cache >/dev/null || error "apt-cache not found"

mkdir -p "$DEST_DIR"

if [ "$CLEAN" -eq 1 ]; then
    step "Cleaning old packages"
    rm -f "$DEST_DIR"/*.deb
fi

rm -rf "$TMP_DIR"
mkdir -p "$TMP_DIR"
cd "$TMP_DIR"

if [ -z "$MIRROR" ]; then
    error "Please provide --mirror (this script is intended for Debian mirrors)"
fi

step "Configuring mirrors"
info "Main mirror : $MIRROR"
info "Suite       : $SUITE"

cat > "$TMP_DIR/sources.list" << EOF
deb $MIRROR $SUITE main
deb $MIRROR $SUITE-updates main
EOF

if [ "$NO_SECURITY" -eq 0 ]; then
    if [ -z "$SECURITY_MIRROR" ]; then
        # Try to derive a security mirror from the main mirror path
        SECURITY_MIRROR=$(echo "$MIRROR" | sed 's|/debian/*$|/debian-security|')
    fi
    info "Security    : $SECURITY_MIRROR"
    echo "deb $SECURITY_MIRROR $SUITE-security main" >> "$TMP_DIR/sources.list"
else
    info "Security repository disabled"
fi

echo
info "sources.list:"
cat "$TMP_DIR/sources.list"
echo

# ------------------------------------------------------------------
# Critical isolation options (the part that makes it work on Ubuntu hosts)
#
# - Dir::State::Status=/dev/null
#     Ignore the host dpkg status database (which contains Ubuntu packages).
# - Dir::Etc::SourceParts=/dev/null
#     Ignore any extra sources under /etc/apt/sources.list.d/
# - Dir::State::Lists and Dir::Cache point to our private directories
# - APT::Default-Release + explicit -t $SUITE
#     Force the solver to pick packages from the chosen Debian suite only.
# ------------------------------------------------------------------
APT_OPTS="
    -o Dir::Etc::SourceList=$TMP_DIR/sources.list
    -o Dir::Etc::SourceParts=/dev/null
    -o Dir::State::Lists=$TMP_DIR/lists
    -o Dir::Cache=$TMP_DIR/cache
    -o Dir::State::Status=/dev/null
    -o APT::Default-Release=$SUITE
    -o APT::Get::AllowUnauthenticated=true
    -o Acquire::AllowInsecureRepositories=true
    -o Acquire::ForceIPv4=true
    -o Acquire::Retries=2
    -o Acquire::http::Timeout=25
    -o Acquire::Languages=none
    -o Acquire::IndexTargets::deb::Contents-deb::DefaultEnabled=false
"

mkdir -p "$TMP_DIR/lists" "$TMP_DIR/cache"

step "Updating package lists"
info "Please wait..."
echo

if ! apt-get $APT_OPTS update; then
    warn "Retrying with sudo..."
    sudo apt-get $APT_OPTS update || error "apt-get update failed"
fi

info "Update finished."

# ------------------------------------------------------------------
step "Resolving dependencies (target: $SUITE)"
info "Packages: $REQUIRED_PACKAGES"

# -t $SUITE forces the solver to use only that suite (ignores Ubuntu versions)
DEPS=$(apt-cache $APT_OPTS -t "$SUITE" depends --recurse --no-recommends --no-suggests \
    --no-conflicts --no-breaks --no-replaces --no-enhances \
    --no-pre-depends \
    $REQUIRED_PACKAGES 2>/dev/null \
    | grep '^\w' | sort -u)

[ -n "$DEPS" ] || error "Could not resolve dependencies for suite $SUITE"

info "Will download:"
echo "$DEPS" | sed 's/^/    /'
echo

# ------------------------------------------------------------------
step "Downloading (suite: $SUITE)"
# Explicitly request the suite so Ubuntu host versions are ignored
apt-get $APT_OPTS -t "$SUITE" download $REQUIRED_PACKAGES $DEPS
info "Download finished."

# ------------------------------------------------------------------
step "Filtering architecture"
ARCH=$(dpkg --print-architecture 2>/dev/null || echo "amd64")

for f in *.deb; do
    [ -f "$f" ] || continue
    case "$f" in
        *_${ARCH}.deb|*_all.deb) ;;
        *)
            warn "Removing $f"
            rm -f "$f"
            ;;
    esac
done

COUNT=$(ls *.deb 2>/dev/null | wc -l)
[ "$COUNT" -gt 0 ] || error "No .deb files left"

# ------------------------------------------------------------------
step "Copying to project"
info "$COUNT packages → $DEST_DIR"
cp -v *.deb "$DEST_DIR/"

step "Cleanup"
cd /
rm -rf "$TMP_DIR"

echo
echo "============================================================"
info "Done. Packages are in: $DEST_DIR"
echo
info "Next step:"
echo "  docker build -t ravi-ollama:cpu -f docker/Dockerfile.ollama-cpu ."
echo "============================================================"
echo
