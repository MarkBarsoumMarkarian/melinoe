#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="2.6.1"
FINGERPRINT="FFF3E01444FED7C316A3545A895F5BC123A02740"
BASE_URL="https://github.com/rfjakob/gocryptfs/releases/download/v${VERSION}"
ARCHIVE="gocryptfs_v${VERSION}_linux-static_amd64.tar.gz"
DOWNLOAD_DIR="$PROJECT_DIR/.tools/downloads"
BIN_DIR="$PROJECT_DIR/.tools/bin"
GPG_DIR="$PROJECT_DIR/.tools/gnupg"
KEY_FILE="$DOWNLOAD_DIR/gocryptfs-signing-key.pub"

mkdir -p "$DOWNLOAD_DIR" "$BIN_DIR" "$GPG_DIR"
chmod 700 "$GPG_DIR"

printf 'Fetching the official gocryptfs signing key...\n'
curl --fail --location --retry 3 --progress-bar \
    --output "$KEY_FILE" https://nuetzlich.net/gocryptfs-signing-key.pub

actual_fingerprint="$(
    gpg --homedir "$GPG_DIR" --with-colons --import-options show-only \
        --import "$KEY_FILE" 2>/dev/null \
        | awk -F: '$1 == "fpr" {print $10; exit}'
)"
if [[ "$actual_fingerprint" != "$FINGERPRINT" ]]; then
    printf 'Signing-key fingerprint mismatch. Refusing installation.\n' >&2
    exit 1
fi
gpg --homedir "$GPG_DIR" --batch --import "$KEY_FILE" >/dev/null 2>&1

printf 'Downloading gocryptfs %s...\n' "$VERSION"
curl --fail --location --retry 3 --progress-bar \
    --output "$DOWNLOAD_DIR/$ARCHIVE" "$BASE_URL/$ARCHIVE"
curl --fail --location --retry 3 --progress-bar \
    --output "$DOWNLOAD_DIR/$ARCHIVE.asc" "$BASE_URL/$ARCHIVE.asc"

printf 'Verifying the signed release...\n'
gpg --homedir "$GPG_DIR" --batch --verify \
    "$DOWNLOAD_DIR/$ARCHIVE.asc" "$DOWNLOAD_DIR/$ARCHIVE"

temporary_dir="$(mktemp -d)"
trap 'rm -rf "$temporary_dir"' EXIT
tar --extract --gzip --file "$DOWNLOAD_DIR/$ARCHIVE" --directory "$temporary_dir"
install -m 0755 "$temporary_dir/gocryptfs" "$BIN_DIR/gocryptfs"
install -m 0755 "$temporary_dir/gocryptfs-xray" "$BIN_DIR/gocryptfs-xray"

"$BIN_DIR/gocryptfs" -version
printf 'Project Vault engine is ready.\n'
