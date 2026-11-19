#!/bin/sh
# Pack dist/PixxelSpool.app into macos/Output/PixxelSpool-<version>-macos.dmg (with a shortcut to Applications,
# so the app can be dragged over). Run from the repository root on a Mac after the PyInstaller build.
set -e
v=$(tr -d '[:space:]' < VERSION)
stage=build/dmg
rm -rf "$stage" macos/Output
mkdir -p "$stage" macos/Output
ditto dist/PixxelSpool.app "$stage/PixxelSpool.app"
ln -s /Applications "$stage/Applications"
hdiutil create -volname "PixxelSpool $v" -srcfolder "$stage" -fs HFS+ -format UDZO -ov "macos/Output/PixxelSpool-$v-macos.dmg"
echo "macos/Output/PixxelSpool-$v-macos.dmg"
