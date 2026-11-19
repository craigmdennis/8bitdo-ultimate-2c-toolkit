#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Build the Ultimate 2 Wireless Controller Test prototype (one Swift file, no Python) as an app with an ad-hoc signature:
#   macos/u2w/build-test.sh   ->   dist/u2w/Ultimate 2 Wireless Controller Test.app
# Needs swiftc (the Xcode command line tools). Then: open "dist/u2w/Ultimate 2 Wireless Controller Test.app"
set -euo pipefail
root=$(cd "$(dirname "$0")/../.." && pwd)
cd "$root"
app="dist/u2w/Ultimate 2 Wireless Controller Test.app"
rm -rf "$app"
mkdir -p "$app/Contents/MacOS"
cat > "$app/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Ultimate 2 Wireless Controller Test</string>
  <key>CFBundleIdentifier</key><string>org.u2c-customfw.u2w-test</string>
  <key>CFBundleExecutable</key><string>u2w-test</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>0.1</string>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
  <key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST
swiftc -O -o "$app/Contents/MacOS/u2w-test" macos/u2w/test.swift -framework AppKit -framework GameController -framework CoreHaptics -framework IOKit
codesign --force -s - "$app"
echo "Built $app"
