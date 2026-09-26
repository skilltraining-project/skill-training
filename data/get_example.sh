#!/usr/bin/env bash
# Download the example screenplay: Valkaama (2010), CC BY-SA 3.0.
#
# Valkaama is an open source feature film. Tim Baumann wrote the screenplay from
# a novel by Hendrik Behnisch, and released it under Creative Commons BY-SA 3.0.
# The licence is printed on the title page of the PDF itself, so it travels with
# the file. See data/README.md for the full attribution.
#
# The PDF is not committed to this repository. It is CC BY-SA and the code is
# MIT, and keeping the two apart means neither licence has to reason about the
# other. Fetch it, use it, and note the licence if you redistribute anything
# derived from it.
#
#   bash data/get_example.sh

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/example"
OUT="$DIR/source.pdf"
SHA256="53fbfff56397803cf1259ce9798da071c07dc7bf9332d8ed7051286e370c1664"
PRIMARY="http://www.valkaama.com/media/script/Valkaama_v.2007-06-30(English-Final).pdf"
MIRROR="https://web.archive.org/web/20120422034219id_/http://www.valkaama.com/media/script/Valkaama_v.2007-06-30(English-Final).pdf"

mkdir -p "$DIR"

if [ -f "$OUT" ]; then
  echo "already downloaded: $OUT"
else
  for url in "$PRIMARY" "$MIRROR"; do
    echo "fetching $url"
    if curl -fsSL --retry 2 --max-time 120 -o "$OUT.part" "$url"; then
      mv "$OUT.part" "$OUT"
      break
    fi
    echo "  failed, trying the next source"
  done
  rm -f "$OUT.part"
fi

[ -f "$OUT" ] || { echo "could not download the screenplay from either source" >&2; exit 1; }

# Verify, because the pipeline downstream assumes this exact document.
if command -v shasum >/dev/null 2>&1; then
  got="$(shasum -a 256 "$OUT" | cut -d' ' -f1)"
elif command -v sha256sum >/dev/null 2>&1; then
  got="$(sha256sum "$OUT" | cut -d' ' -f1)"
else
  got="$SHA256"
  echo "note: no sha256 tool found, skipping the checksum"
fi
if [ "$got" != "$SHA256" ]; then
  echo "checksum mismatch for $OUT" >&2
  echo "  expected $SHA256" >&2
  echo "  got      $got" >&2
  exit 1
fi

echo "ok: $OUT"
echo
echo "next:"
echo "  python -m skilltrain prepare --pdf data/example/source.pdf --episodes 20"
