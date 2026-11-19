#!/bin/bash
set -euo pipefail

# Run from the root of craigmdennis/8bitdo-ultimate-2c-toolkit,
# branch u2w-min-strength. The Mac TC32 toolchain is the one used in the
# previous reverse-engineering session.
ADDON_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_ROOT=$(git -C "$ADDON_DIR" rev-parse --show-toplevel)
cd "$REPO_ROOT"
EXPECTED_BRANCH=u2w-min-strength
EXPECTED_COMMIT=69357753e2f51f86f8f6c597863329990040e3f8
ACTUAL_BRANCH=$(git branch --show-current)
ACTUAL_COMMIT=$(git rev-parse HEAD)
[[ "$ACTUAL_BRANCH" == "$EXPECTED_BRANCH" ]] || { echo "Expected branch $EXPECTED_BRANCH, found $ACTUAL_BRANCH" >&2; exit 1; }
[[ "$ACTUAL_COMMIT" == "$EXPECTED_COMMIT" ]] || { echo "Expected commit $EXPECTED_COMMIT, found $ACTUAL_COMMIT" >&2; exit 1; }
AS=${TC32_AS:-/tmp/tc32/bin/tc32-elf-as}
LD=${TC32_LD:-/tmp/tc32/bin/tc32-elf-ld}
OC=${TC32_OBJCOPY:-/tmp/tc32/bin/tc32-elf-objcopy}
NM=${TC32_NM:-/tmp/tc32/bin/tc32-elf-nm}
ASM_DIR=${ASM_DIR:-/tmp/u2w-ring-asm}
mkdir -p "$ASM_DIR"

for f in "$AS" "$LD" "$OC" "$NM"; do
  [[ -x "$f" ]] || { echo "Missing TC32 tool: $f" >&2; exit 1; }
done

# The current u2w-min-strength image occupies:
# rumble table 0x1c780..0x1c7e4, Xbox report cave 0x1c880..0x1c925,
# rumble routine 0x1c940..0x1c98b. The 172-byte ring helper is relocated
# to the zero-filled 0x1c990..0x1ca3b gap before checksum words at 0x1ca60.
RING_BASE=0x1c990
$AS -o "$ASM_DIR/ring.o" "$ADDON_DIR/ring.s"
$LD -Ttext="$RING_BASE" --defsym=gpio_set_func=0x129cc -o "$ASM_DIR/ring.elf" "$ASM_DIR/ring.o"
$OC -O binary --only-section=.text "$ASM_DIR/ring.elf" "$ASM_DIR/ring.bin"

sym() {
  "$NM" "$ASM_DIR/ring.elf" | awk -v name="$1" '$3 == name { print "0x" $1; found=1 } END { if (!found) exit 1 }'
}
BLINK_GO=$(sym blink_go)
MAYBE_OFF=$(sym maybe_off)
MAYBE_ON=$(sym maybe_on)
SETUP=$(sym setup)

echo "ring base: $RING_BASE"
echo "blink_go: $BLINK_GO"
echo "maybe_off: $MAYBE_OFF"
echo "maybe_on: $MAYBE_ON"
echo "setup: $SETUP"
(( BLINK_GO == 0x1c9a0 )) || { echo "Unexpected blink_go address: $BLINK_GO" >&2; exit 1; }
(( MAYBE_OFF == 0x1c9ac )) || { echo "Unexpected maybe_off address: $MAYBE_OFF" >&2; exit 1; }
(( MAYBE_ON == 0x1c9c8 )) || { echo "Unexpected maybe_on address: $MAYBE_ON" >&2; exit 1; }
(( SETUP == 0x1c9e4 )) || { echo "Unexpected setup address: $SETUP" >&2; exit 1; }
echo "ring bytes: $(wc -c < "$ASM_DIR/ring.bin" | tr -d ' ')"

make_hook() {
  local name="$1" address="$2" source="$3"
  printf '%s\n' "$source" > "$ASM_DIR/$name.s"
  "$AS" -o "$ASM_DIR/$name.o" "$ASM_DIR/$name.s"
  "$LD" -Ttext="$address" \
    --defsym=blink_go="$BLINK_GO" \
    --defsym=maybe_off="$MAYBE_OFF" \
    --defsym=maybe_on="$MAYBE_ON" \
    --defsym=setup="$SETUP" \
    -o "$ASM_DIR/$name.elf" "$ASM_DIR/$name.o"
  "$OC" -O binary --only-section=.text "$ASM_DIR/$name.elf" "$ASM_DIR/$name.bin"
}

make_hook blink_off 0xf54a '.text
h:
    tpush {lr}
    tmovs r0, #0
    tjl blink_go
    .short 0x06c0
    .short 0x06c0'
make_hook blink_on 0xf566 '.text
h:
    tpush {lr}
    tmovs r0, #1
    tjl blink_go
    .short 0x06c0
    .short 0x06c0
    .short 0x06c0
    .short 0x06c0'
make_hook solid_off 0xf5ca '.text
h:
    tjl maybe_off'
make_hook solid_on 0xf5ea '.text
h:
    tjl maybe_on'
make_hook init 0xf71c '.text
h:
    tjl setup
    .short 0x06c0
    .short 0x06c0
    .short 0x06c0'

# Exact hook lengths are checked by apply_home_ring.py too.
for spec in 'ring:172' 'blink_off:12' 'blink_on:16' 'solid_off:4' 'solid_on:4' 'init:10'; do
  name=${spec%%:*}; expected=${spec##*:}; actual=$(wc -c < "$ASM_DIR/$name.bin" | tr -d ' ')
  [[ "$actual" == "$expected" ]] || { echo "$name size $actual != expected $expected" >&2; exit 1; }
done

echo "Assembled ring helper and five hooks in $ASM_DIR"
echo "Next: python3.15 addon/apply_home_ring.py BASE_BANK_A.bin COMBINED_BANK_A.bin --asm-dir $ASM_DIR"
