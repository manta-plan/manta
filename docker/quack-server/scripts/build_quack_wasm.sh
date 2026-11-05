#!/usr/bin/env bash
# Build Quack for DuckDB-Wasm (wasm_eh) from duckdb-quack's main, which has the
# fix for single-threaded Wasm that the published build lacks. Follows Quack's
# CI (extension-ci-tools): Emscripten 3.1.71, vcpkg for OpenSSL.
#
#     scripts/build_quack_wasm.sh [WORKDIR]    # default: ./build/quack-wasm
#     uv run python scripts/prepare_wasm.py --quack <the path it prints>
#
# Takes a while on first run (Emscripten, vcpkg's OpenSSL, DuckDB's sources).
set -euo pipefail

WORK=$(mkdir -p "${1:-build/quack-wasm}" && cd "${1:-build/quack-wasm}" && pwd)
EMSDK_VERSION=3.1.71
VCPKG_COMMIT=cd61e1e26a038e82d6550a3ebbe0fbbfe7da78e3 # extension-ci-tools' default
QUACK_REF=main

cd "$WORK"
[ -d emsdk ] || git clone -q --depth 1 https://github.com/emscripten-core/emsdk.git
emsdk/emsdk install "$EMSDK_VERSION" >/dev/null
emsdk/emsdk activate "$EMSDK_VERSION" >/dev/null
# shellcheck disable=SC1091
source emsdk/emsdk_env.sh >/dev/null 2>&1

if [ ! -d vcpkg ]; then
  git clone -q https://github.com/microsoft/vcpkg.git
  git -C vcpkg checkout -q "$VCPKG_COMMIT"
  vcpkg/bootstrap-vcpkg.sh -disableMetrics >/dev/null
fi

[ -d duckdb-quack ] || git clone -q --depth 1 --branch "$QUACK_REF" https://github.com/duckdb/duckdb-quack.git
cd duckdb-quack
git submodule update --init --depth 1

# The duckdb submodule is cloned without tags; name the version as CI would.
export OVERRIDE_GIT_DESCRIBE="v2.0.0-0-g$(git -C duckdb rev-parse --short=10 HEAD)"
export VCPKG_TOOLCHAIN_PATH="$WORK/vcpkg/scripts/buildsystems/vcpkg.cmake"
export VCPKG_TARGET_TRIPLET=wasm32-emscripten
export VCPKG_HOST_TRIPLET=$( [ "$(uname -m)" = arm64 ] && echo arm64-osx || echo x64-linux )
export VCPKG_OVERLAY_PORTS="$PWD/extension-ci-tools/vcpkg_ports"
export WASM_EXTENSIONS=1 DUCKDB_PLATFORM=wasm_eh

# The configure step only; its compile step runs `make` on what may be Ninja files.
make wasm_eh GEN=ninja || true
emmake ninja -C build/wasm_eh

# Link again with WASM_BIGINT: DuckDB-Wasm passes 64-bit values whole, and
# without it Emscripten 3.1.71 splits each into two i32s, so loading fails with
# "imported function does not match the expected type".
link=$(grep -m1 'POST_BUILD = cd .*extension/quack && emcc' build/wasm_eh/build.ninja \
  | sed 's/^ *POST_BUILD = //; s/-sSIDE_MODULE=2/-sSIDE_MODULE=2 -sWASM_BIGINT/')
bash -c "$link"

echo "$PWD/build/wasm_eh/extension/quack/quack.duckdb_extension.wasm"
