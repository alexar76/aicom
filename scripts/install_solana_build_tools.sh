#!/usr/bin/env bash
# Install checksum-pinned build tools only. Does not change rustup or deploy.
set -euo pipefail
DEST="${1:?Usage: install_solana_build_tools.sh ABSOLUTE_DESTINATION}"
[[ "$DEST" = /* ]] || { echo 'Destination must be absolute' >&2; exit 2; }
case "$(uname -s)-$(uname -m)" in
  Darwin-arm64)
    AGAVE_TARGET=aarch64-apple-darwin
    AGAVE_SHA=51a44318e6fb8be0cfa69cdfdb3252f4c76a5eb2866740694e91de3d2fc5a75b
    TOOLS_TARGET=osx-aarch64
    TOOLS_SHA=1c8b3af5e8614e1c459393a95c5b19bfbcc8ed13822a1cb539fae68471f9bfbb ;;
  Darwin-x86_64)
    AGAVE_TARGET=x86_64-apple-darwin
    AGAVE_SHA=eb678fe505ca470d4b474a0a92a1d6dd6c00c95df47ee4d8ca0712fe7a97efa1
    TOOLS_TARGET=osx-x86_64
    TOOLS_SHA=d1cb7165892007d11ad72fded16c76926e5dfa9ff286fe3d999440c1af34a758 ;;
  Linux-x86_64)
    AGAVE_TARGET=x86_64-unknown-linux-gnu
    AGAVE_SHA=5991d027a686eb419a709a479178b33eb83501e8a2bfbf599a81a286bfcbf770
    TOOLS_TARGET=linux-x86_64
    TOOLS_SHA=fcc41631c7f77561bf5412218bf297501dccf0305ea280f338f0ace2aab9f31e ;;
  *) echo 'Unsupported build host; see anza-xyz release assets' >&2; exit 2 ;;
esac
verify() {
  if command -v sha256sum >/dev/null 2>&1; then
    echo "$2  $1" | sha256sum -c -
  else
    echo "$2  $1" | shasum -a 256 -c -
  fi
}
mkdir -p "$DEST"
curl --proto '=https' --tlsv1.2 -fsSL --retry 3 \
  "https://github.com/anza-xyz/agave/releases/download/v4.1.2/solana-release-$AGAVE_TARGET.tar.bz2" \
  -o "$DEST/agave.tar.bz2"
verify "$DEST/agave.tar.bz2" "$AGAVE_SHA"
tar -xjf "$DEST/agave.tar.bz2" -C "$DEST"

# cargo-build-sbf 4.1 uses this location for LLVM postprocessing even with
# --no-rustup-override. Never replace an existing operator toolchain silently.
TOOLS_DIR="$HOME/.cache/solana/v1.54/platform-tools"
if [[ -e "$TOOLS_DIR" || -L "$TOOLS_DIR" ]]; then
  [[ -f "$TOOLS_DIR/.aicom-verified-sha256" ]] && \
    [[ "$(cat "$TOOLS_DIR/.aicom-verified-sha256")" = "$TOOLS_SHA" ]] || {
      echo "Existing SBF tools at $TOOLS_DIR; use them explicitly or choose a clean build host" >&2
      exit 1
    }
else
  curl --proto '=https' --tlsv1.2 -fsSL --retry 3 \
    "https://github.com/anza-xyz/platform-tools/releases/download/v1.54/platform-tools-$TOOLS_TARGET.tar.bz2" \
    -o "$DEST/platform-tools.tar.bz2"
  verify "$DEST/platform-tools.tar.bz2" "$TOOLS_SHA"
  mkdir -p "$TOOLS_DIR"
  tar -xjf "$DEST/platform-tools.tar.bz2" -C "$TOOLS_DIR"
  printf '%s\n' "$TOOLS_SHA" > "$TOOLS_DIR/.aicom-verified-sha256"
fi
{
  printf 'export RUSTC=%q\n' "$TOOLS_DIR/rust/bin/rustc"
  printf 'export PATH=%q:$PATH\n' "$TOOLS_DIR/rust/bin:$DEST/solana-release/bin"
} > "$DEST/env.sh"
echo "Build environment: source $DEST/env.sh"
