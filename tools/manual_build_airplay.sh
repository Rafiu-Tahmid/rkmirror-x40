#!/usr/bin/env bash
set -euo pipefail
REPO="${1:?repo path required}"
KIT="${2:?kit path required}"
PROFILE="${3:?profile required}"
cd "$REPO"
mkdir -p app/libs
python3 "$KIT/tools/manual_prepare.py" --repo "$PWD"
cd doubletake/doubletake
GOMOBILE_VERSION='v0.0.0-20260611195102-4dd8f1dbf5d2'
go install "golang.org/x/mobile/cmd/gomobile@$GOMOBILE_VERSION"
go install "golang.org/x/mobile/cmd/gobind@$GOMOBILE_VERSION"
export PATH="$(go env GOPATH)/bin:$PATH"
export GOTOOLCHAIN=go1.25.10
# Remove any BOM a Windows checkout/editor could ever have introduced.
python3 - <<'PY'
from pathlib import Path
for p in Path('.').rglob('*'):
    if p.is_file() and (p.suffix=='.go' or p.name in ('go.mod','go.sum')):
        b=p.read_bytes()
        if b.startswith(b'\xef\xbb\xbf'): p.write_bytes(b[3:])
PY
gofmt -w internal/airplay/rkx40.go internal/airplay/patches.go internal/airplay/airplay1.go airplaylib/*.go
# A real compile preflight, not just text assertions.
go test ./internal/airplay
go get golang.org/x/mobile/bind
gomobile bind -v -trimpath '-ldflags=-buildid= -extldflags=-Wl,-z,max-page-size=16384' \
  -target android -androidapi 26 -o "$REPO/app/libs/airplaylib.aar" ./airplaylib/
test -s "$REPO/app/libs/airplaylib.aar"
ls -lh "$REPO/app/libs/airplaylib.aar"
