#!/usr/bin/env bash
# Build a release: the production extension bundled into the mei-runtime wheel, plus an install.sh
# pinned to that wheel's version and sha256. Output goes to release/ (or the given directory).
# Usage: scripts/build-release.sh [out-dir]
set -euo pipefail

main() {
    local root out version wheel sha
    root=$(cd "$(dirname "$0")/.." && pwd)
    out=$(mkdir -p "${1:-$root/release}" && cd "${1:-$root/release}" && pwd)
    version=$(sed -n 's/^version = "\(.*\)"$/\1/p' "$root/runtime/pyproject.toml")
    wheel="mei_runtime-$version-py3-none-any.whl"

    (cd "$root" && npm run build >/dev/null && node scripts/check-bundle.js)
    rm -rf "$root/runtime/src/mei/extension"
    cp -a "$root/dist" "$root/runtime/src/mei/extension"
    rm -f "$out/$wheel"
    (cd "$root/runtime" && uv build --wheel --out-dir "$out" >/dev/null)
    rm -rf "$root/runtime/src/mei/extension"

    sha=$(sha256sum "$out/$wheel" | cut -d' ' -f1)
    sed -e "s/^    local MEI_VERSION=.*/    local MEI_VERSION=$version/" \
        -e "s/^    local MEI_WHEEL_SHA256=.*/    local MEI_WHEEL_SHA256=$sha/" \
        "$root/install.sh" > "$out/install.sh"
    chmod +x "$out/install.sh"
    (cd "$out" && sha256sum "$wheel" install.sh > SHA256SUMS)
    echo "built $out/$wheel ($sha)"
    echo "      $out/install.sh"
}

main "$@"
