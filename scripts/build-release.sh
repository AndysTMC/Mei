#!/usr/bin/env bash
# Build a release: the production extension bundled into the mei-runtime wheel, plus an install.sh
# pinned to that wheel's version and sha256 and to uv's published checksums for its pinned uv.
# Output goes to release/ (or the given directory). MEI_RELEASE_OFFLINE=1 skips fetching uv's
# checksums (for tests; that install.sh then can't install uv itself).
# Usage: scripts/build-release.sh [out-dir]
set -euo pipefail

main() {
    local root out version wheel sha
    root=$(cd "$(dirname "$0")/.." && pwd)
    out=$(mkdir -p "${1:-$root/release}" && cd "${1:-$root/release}" && pwd)
    version=$(sed -n 's/^version = "\(.*\)"$/\1/p' "$root/runtime/pyproject.toml")
    wheel="mei_runtime-$version-py3-none-any.whl"

    (cd "$root" && npm run build >/dev/null && node scripts/check-bundle.js)
    local bundle="$root/runtime/src/mei/extension"
    rm -rf "$bundle"
    trap "rm -rf $(printf %q "$bundle")" EXIT  # never leave the copy in the source tree
    cp -a "$root/dist" "$bundle"
    rm -f "$out/$wheel"
    (cd "$root/runtime" && uv build --wheel --out-dir "$out" >/dev/null)

    sha=$(sha256sum "$out/$wheel" | cut -d' ' -f1)
    local uv_version uv_x86="" uv_arm=""
    uv_version=$(sed -n 's/^    local UV_VERSION=\([0-9.]*\)$/\1/p' "$root/install.sh")
    if [ "${MEI_RELEASE_OFFLINE:-}" != 1 ]; then
        uv_x86=$(uv_checksum "$uv_version" x86_64-unknown-linux-gnu)
        uv_arm=$(uv_checksum "$uv_version" aarch64-unknown-linux-gnu)
    fi
    sed -e "s/^    local MEI_VERSION=.*/    local MEI_VERSION=$version/" \
        -e "s/^    local MEI_WHEEL_SHA256=.*/    local MEI_WHEEL_SHA256=$sha/" \
        -e "s/^    local UV_SHA256_X86_64=.*/    local UV_SHA256_X86_64=$uv_x86/" \
        -e "s/^    local UV_SHA256_AARCH64=.*/    local UV_SHA256_AARCH64=$uv_arm/" \
        "$root/install.sh" > "$out/install.sh"
    chmod +x "$out/install.sh"
    (cd "$out" && sha256sum "$wheel" install.sh > SHA256SUMS)
    echo "built $out/$wheel ($sha)"
    echo "      $out/install.sh"
}

# The sha256 uv publishes next to its release archive for one target; fails unless it is 64 hex digits.
uv_checksum() {
    local sum
    sum=$(curl -fsSL --proto '=https' --tlsv1.2 \
        "https://github.com/astral-sh/uv/releases/download/$1/uv-$2.tar.gz.sha256" | cut -d' ' -f1)
    [[ $sum =~ ^[0-9a-f]{64}$ ]] || { echo "unexpected checksum for uv $1 ($2): $sum" >&2; return 1; }
    echo "$sum"
}

main "$@"
