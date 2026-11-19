#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Build the Ultimate 2 Wireless Backup prototype (ad-hoc signature) and its zip, for one architecture:
#   macos/u2w/build.sh [arm64|x86_64]  ->  dist/u2w/<arch>/Ultimate 2 Wireless Backup.app, dist/u2w-backup-X.Y.Z-macos-<arch>.zip
# It reuses the Python that macos/build.sh downloads, and bundles only the transport from u2c_customfw.
set -euo pipefail
root=$(cd "$(dirname "$0")/../.." && pwd)
cd "$root"
arch=${1:-arm64}
version=$(python3 -c "import re; print(re.search(r'__version__ = \"(.+?)\"', open('u2w_backup/__init__.py').read()).group(1))")
PBS=https://github.com/astral-sh/python-build-standalone/releases/download/20261026/cpython-3.12.16%2B20261026
case "$arch" in
  arm64) pbs_arch=aarch64; PBS_SHA256="fbf4afef53c2a6b72bb741bc06d5671a9dfaf87bd84e5aa73ac9b3d0d589f14e" ;;
  x86_64) pbs_arch=x86_64; PBS_SHA256="a962e47df522889eaa7ff0d6a56203f1079f68aabb65ffdbe8455f362bc769f3" ;;
  *) echo "architecture: arm64 or x86_64" >&2; exit 2 ;;
esac
out=dist/u2w/$arch
mkdir -p dist/cache "$out"
tarball=dist/cache/python-$pbs_arch.tar.gz
[ -f "$tarball" ] || curl -fsSL -o "$tarball" "$PBS-$pbs_arch-apple-darwin-install_only.tar.gz"
echo "$PBS_SHA256  $tarball" | shasum -a 256 -c -

name="Ultimate 2 Wireless Backup"
app="$out/$name.app"
rm -rf "$app"
mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources/app/u2c_customfw"
tar xzf "$tarball" -C "$app/Contents/Resources"
# What the backup never uses, so the zip fits GitHub's 25 MB limit for files attached to an issue
py="$app/Contents/Resources/python"
rm -rf "$py/include" "$py/share" "$py"/lib/{tcl,tk,itcl,thread}* "$py"/lib/libtcl* "$py"/lib/libtk* "$py"/bin/{idle,pip,pydoc,2to3}* \
  "$py"/lib/python3.12/{site-packages,ensurepip,idlelib,tkinter,turtledemo,lib2to3,pydoc_data,test,unittest/test} \
  "$py"/lib/python3.12/config-3.12-darwin "$py"/lib/python3.12/lib-dynload/_tkinter*
rsync -a --exclude __pycache__ --exclude sim.py u2w_backup "$app/Contents/Resources/app/"
cp u2c_customfw/__init__.py "$app/Contents/Resources/app/u2c_customfw/"
rsync -a --exclude __pycache__ u2c_customfw/transport "$app/Contents/Resources/app/u2c_customfw/"
cp LICENSE "$app/Contents/Resources/app/"
cp macos/AppIcon.icns "$app/Contents/Resources/"
sed "s/@VERSION@/$version/g" macos/u2w/Info.plist > "$app/Contents/Info.plist"
swiftc -O -target "$arch-apple-macos13.0" -o "$app/Contents/MacOS/u2w-backup" macos/u2w/main.swift -framework AppKit -framework IOKit
codesign --force --deep -s - "$app"
zip="u2w-backup-$version-macos-$arch.zip"
(cd "$out" && rm -f "$root/dist/$zip" && ditto -c -k --keepParent "$name.app" "$root/dist/$zip")
ls -lh "dist/$zip"
