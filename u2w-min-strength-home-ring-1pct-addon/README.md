# Home Ring 1% add-on for `u2w-min-strength`

This add-on is intended specifically for:

- Repository: `craigmdennis/8bitdo-ultimate-2c-toolkit`
- Branch: `u2w-min-strength`
- Base commit: `69357753e2f51f86f8f6c597863329990040e3f8`
- Device firmware: 8BitDo Ultimate 2 Wireless, firmware 1.10

It does **not** replace or reimplement the branch. First build the normal Xbox/rumbIe image using the branch's own patcher. Then apply this Home Ring add-on to that Bank A image.

## Why the ring helper is relocated

The earlier PR #15-era image placed the 172-byte Home Ring helper at `0x1c7f0`, immediately after an older Xbox report cave. That address cannot be reused in the current branch: `u2w-min-strength` uses `0x1c780` for its minimum-strength rumble table and `0x1c880` for the larger 38-byte Xbox report cave.

In the current branch, the rumble routine occupies `0x1c940..0x1c98b`. The add-on relocates the 172-byte ring helper to `0x1c990..0x1ca3b`, leaving the Bank A integrity words at `0x1ca60` untouched until they are recomputed. The add-on checks that this full destination is zero-filled before writing it.

## Build

Run `build.sh` from the repository root (or copy this folder into the repository first). It uses the TC32 toolchain from the prior build session at `/tmp/tc32/bin`. Override `TC32_AS`, `TC32_LD`, `TC32_OBJCOPY`, and `TC32_NM` if yours is elsewhere.

1. Build the branch's normal Bank A image from your own full-flash backup:

   ```sh
   BACKUP="$HOME/Documents/Ultimate 2 Wireless Backup/backup-20261118-211833.bin"
   BASE="$HOME/Documents/Ultimate 2 Wireless Backup/u2w-min-strength-bankA.bin"
   python3.15 -m u2w_xbox.patch "$BACKUP" "$BASE"
   ```

2. Assemble the relocated Home Ring helper and its five hooks:

   ```sh
   ./u2w-min-strength-home-ring-1pct-addon/build.sh
   ```

3. Create the combined image:

   ```sh
   OUT="$HOME/Documents/Ultimate 2 Wireless Backup/u2w-min-strength-home-ring-1pct-bankA.bin"
   python3.15 u2w-min-strength-home-ring-1pct-addon/apply_home_ring.py \
     "$BASE" "$OUT" --asm-dir /tmp/u2w-ring-asm
   ```

4. Dry-run the writer; do not add `--write` yet:

   ```sh
   python3.15 -m u2w_xbox.write "$OUT"
   ```

The add-on writes a new Bank A image only. It does not write to a controller. It refuses unexpected base bytes, occupied ring space, wrong assembler output sizes, wrong PWM5 constants, unexpected hook bytes, or any changed byte outside the ring helper, five hooks, and the two integrity words.

## What the add-on changes

- PB5 is muxed to PWM5 during the existing PWM initialization.
- PWM5 period is 10000; the steady ON compare value is 100, i.e. 1% duty.
- OFF compare value is 0.
- Pairing blink and steady on/off paths are hooked with return-address preservation so the original pairing loop can continue.
- The add-on does not change Xbox PnP ID, HID report map/cave, motion-byte forwarding, rumble routine, minimum-strength table, output report ID, bootloader, or Bank B.

## Validation status

The base branch layout and the candidate free region were checked against the supplied stock 1.10 backup and the current branch patch source. The 1% ring helper itself was previously assembled for the older base address `0x1c7f0`; this add-on deliberately reassembles it at `0x1c990` so linker-relative branches are recalculated. **The relocated output must pass the script checks and then be tested on the controller, especially the pairing blink, before it is treated as hardware-validated.**
