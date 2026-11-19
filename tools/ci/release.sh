#!/usr/bin/env bash
# Put the built files into the GitHub release of the tag (used by the Windows, the Mac and the Pi workflow), each
# with a SHA-256 checksum file next to it (<file>.sha256, the format of sha256sum).
# The workflows run at the same time for a tag: whoever comes first creates the release, the others add their files.
# A version whose changelog section has "### Security" is a security release: the title says so (the updater reads
# the same marker from CHANGELOG.md).
#   tools/ci/release.sh <tag> <version> <file>...      (needs GH_TOKEN)
set -euo pipefail
tag=$1; ver=$2; shift 2
notes="PixxelSpool $ver. Raspberry Pi: install it with the updater in PixxelSpool (Options › About). Windows: PixxelSpool-Setup-$ver.exe (or the portable zip). Mac (Apple silicon): PixxelSpool-$ver-macos.dmg. Changes: see CHANGELOG.md."
title="PixxelSpool $ver"
if awk -v h="## [$ver]" 'index($0, h) == 1 {on = 1; next} /^## \[/ {on = 0} on && /^### Security/ {f = 1} END {exit !f}' CHANGELOG.md; then
  title="$title (security update)"
  notes="Security update. $notes"
fi
command -v sha256sum >/dev/null 2>&1 || sha256sum() { shasum -a 256 "$@"; }     # macOS
sums=()
for f in "$@"; do
  (cd "$(dirname "$f")" && sha256sum "$(basename "$f")") > "$f.sha256"
  sums+=("$f.sha256")
done
pre=()
[[ $tag =~ -(alpha|beta|rc) ]] && pre=(--prerelease)     # -patch.N is a normal release
for i in 1 2 3 4 5 6; do
  if gh release view "$tag" >/dev/null 2>&1 || gh release create "$tag" --title "$title" --notes "$notes" ${pre[@]+"${pre[@]}"}; then
    gh release upload "$tag" "$@" "${sums[@]}" --clobber && exit 0
  fi
  sleep $((i * 10))
done
echo "release failed" >&2
exit 1
