#!/usr/bin/env bash
# Freeze the daemon and wrap it in a user-domain .pkg. Run on arm64 macOS with
# requirements.txt + pyinstaller installed. No signing, no notarisation.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

VERSION="${1:-$(python3 -c 'import midi_pedald; print(midi_pedald.__version__)')}"
IDENT="pro.kyxap.midi-pedald"
OUT="dist/midi-pedald-${VERSION}.pkg"

rm -rf build dist

pyinstaller --clean --noconfirm packaging/midi-pedald.spec

# Smoke the frozen binary before wrapping a pkg around it: the rtmidi hidden
# import fails silently until a port is opened, so --version alone is not enough
# once hardware is present, but it does catch a broken freeze in CI.
./dist/midi-pedald/midi-pedald --version

mkdir -p build/pkg

pkgbuild \
    --identifier "$IDENT" \
    --version "$VERSION" \
    --install-location "Library/Application Support/midi-pedald/bin" \
    --root "dist/midi-pedald" \
    --component-plist packaging/component.plist \
    --scripts packaging/scripts \
    build/pkg/component.pkg

productbuild \
    --distribution packaging/distribution.xml \
    --package-path build/pkg \
    "$OUT"

echo "built $OUT"
