# Ultimate 2 Wireless: Xbox identity with rumble (prototype)

`u2w_xbox` patches firmware 1.10 of the 8BitDo Ultimate 2 Wireless. Over Bluetooth, the patched controller reports the identity of an Xbox Elite controller. Apple's GameController framework then loads its Xbox driver for the controller, and that driver offers haptics, the battery level and the four Elite paddles. With stock firmware, tvOS and macOS classify the controller as a generic HID gamepad with neither haptics nor battery level.

On an Apple TV 4K (3rd generation) with tvOS 27.2.1, GameController reports the category `Xbox One` for the patched controller. It lists the haptic localities `All, Default, Handles, Left Handle, Right Handle, Left Trigger, Right Trigger, Triggers`, the battery level and `Paddle 1`–`4`. Core Haptics drives the motors. Every input maps to its Xbox element, and the four back buttons press the paddles. On macOS 27.2.1, GameController lists the same category, localities and paddles, every input except Home reaches apps, and Core Haptics drives the motors from every locality.

Only Apple devices are tested. The patched controller reports product ID `045e:0b05`, the Xbox Elite Series 2 over Bluetooth Classic, with a 39-byte input report. Windows, Linux drivers such as xpadneo and hid-microsoft, and SDL games through Steam have their own handling for `0x0b05`, and may read the inputs wrongly.

| Procedure | Tested on hardware |
|---|---|
| Back up, build and write the patched image | Yes |
| Write the controller's own bank back | Yes |
| Return to stock firmware with `restore-original --write` | Partly. The writer is tested. The download of 1.09 has not run on a patched controller. |
| Return to stock firmware with 8BitDo's software | No |

## Terms

- **Stock firmware.** 8BitDo's unmodified firmware.
- **Backup.** The whole flash of one controller, read by `u2w_backup`. It contains that controller's Bluetooth pairings and calibration. Keep it private.
- **The controller's own bank.** Bank A as it is in the backup.
- **Patched image.** Bank A with the edits in this package, built from the controller's own bank.
- **Writer.** `u2w_backup.restore.run`, the code behind `restore-original`. `u2w_xbox.write` runs it with the patched image in place of 1.09.
- **Update mode.** The bootloader's USB mode for reading and writing the flash. The controller appears as `2dc8:3208`, "8BitDo Boot".

## Requirements

- A Mac with Python 3.12 or later. Run every command from the root of this repository.
- Input Monitoring permission for the terminal app, in System Settings › Privacy & Security › Input Monitoring. After adding the permission, quit and reopen the terminal.
- A USB data cable. Unplug the 2.4 GHz adapter from every computer.
- Firmware 1.10 on the controller. 8BitDo's Ultimate Software V2 installs it. The patch compares every byte it changes with the 1.10 bytes, and it refuses any other version.

## Flash a controller

Each controller needs its own backup.

1. Update the controller to 1.10 with 8BitDo's Ultimate Software V2.
2. Turn the controller off and connect it to the Mac with the cable.
3. Back up the whole flash. This command only reads.

   ```sh
   python3 -m u2w_backup --trace sent.txt
   ```

   The command saves the backup and a report in `~/Documents/Ultimate 2 Wireless Backup/`. In the report, `firmware_version` must be `1.1`.
4. Build the patched image from the backup:

   ```sh
   python3 -m u2w_xbox.patch ~/Documents/"Ultimate 2 Wireless Backup"/backup-<date>.bin xbox.bin
   ```

   If the backup does not contain stock 1.10, the command stops with `Nothing written` and names the first address that differs.
5. Check the controller without writing. This command only reads.

   ```sh
   python3 -m u2w_xbox.write xbox.bin
   ```

   Expected output: `Check passed: it would rewrite bank A (36 sectors, 0x5000-0x29000) ...`.
6. Write the patched image. Keep the cable connected. The write takes about 1 minute.

   ```sh
   python3 -m u2w_xbox.write xbox.bin --write --trace sent.txt
   ```

   Expected output at the end: `Back after ... s as 2dc8:310b; by cable its firmware reads as ...`, then `done`. These messages name 1.09, because the writer's wording names 1.09. The bytes written come from `xbox.bin`.
7. Unplug the cable and set the mode switch to BT.
8. On every device that the controller was paired with, forget the controller in the Bluetooth settings. A device that keeps the old pairing can also keep the old description of the controller.
9. Hold Pair for 3 seconds, and pair the controller again. The controller name does not change.
10. Check the result with the controller test app on a Mac (`macos/u2w/build-test.sh`), or with any app that lists a controller's GameController details. The category must be `Xbox One`, and the haptic localities must be listed.

## Return to stock firmware

`restore-original` downloads stock firmware from 8BitDo's update server, checks its SHA-256 and writes it. The server offers 1.09 for this controller. The writer compares the controller's bootloader with the backup from step 3 of "Flash a controller", so that backup must exist.

1. Connect the controller to the Mac with the cable. The controller can be on or off.
2. Check without writing:

   ```sh
   python3 -m u2w_backup restore-original
   ```

3. Write stock firmware. Keep the cable connected.

   ```sh
   python3 -m u2w_backup restore-original --write --trace sent.txt
   ```

   Expected output at the end: `done 8BitDo's firmware 1.09 restored`.
4. To install 1.10 again, update the controller with 8BitDo's Ultimate Software V2.
5. On every device that the controller was paired with, forget the controller, then pair it again.

### Recovery when the controller does not start or does not answer by cable

1. Turn the controller fully off: unplug the cable, then hold Home for about 12 seconds.
2. Hold LB + RB, and plug the cable in. The controller enters update mode. Update mode is part of the bootloader, and no command in this repository writes the bootloader.
3. Run step 3 of "Return to stock firmware". The writer detects update mode and writes from there.

To leave update mode without writing, run `python3 -m u2w_backup leave-update-mode`, or unplug the cable and hold Home for about 12 seconds. `leave-update-mode` restarts the controller only when bank A contains a whole firmware.

### Write back the controller's own bank

The same writer writes the controller's own bank back from the backup:

```sh
python3 -m u2w_xbox.patch --stock ~/Documents/"Ultimate 2 Wireless Backup"/backup-<date>.bin stock.bin
python3 -m u2w_xbox.write stock.bin --write --trace sent.txt
```

## What the patch changes

The patch changes only the Bluetooth interface. USB mode, 2.4 GHz mode and the rest of the firmware are unchanged.

| Edit | Address | Stock firmware | Patched image |
|---|---|---|---|
| PnP ID | `0x1b54c` | `2dc8:6012` | `045e:0b05`, Xbox Elite Series 2 |
| HID report map | `0x1b4d8` | 113 bytes: input report 1 of 33 bytes, output report 5 | 98 bytes: input report 1 of 38 bytes, output report 3 |
| Report map length in the GATT table | `0x1b92c` | `0x71` | `0x62` |
| Input report notify | `0xe458` | `notify(0x40, 0x1d, payload, 33)` | call to the cave |
| Cave | `0x1c880` | zero padding with no references | `cave.s`: builds the Xbox input report, with the paddles and the motion data, and sends it with length 38 |
| Rumble callback | `0xd53e` | motors from value bytes 0 and 1 | call to the rumble routine |
| Rumble routine | `0x1c940` | zero padding with no references | `rumble.s`: motor strengths from the Xbox packet, converted to 0-255 |
| Rumble table | `0x1c780` | zero padding with no references | 101 bytes: `28 + 227 × √(x / 100)` for strengths from GameController |
| Output report reference | `0x1c6f0` | `05 02` | `03 02` |
| CRC and start-up sum | `0x1ca60` | | recomputed |

**Input report.** The first 9 bytes of the stock input report have the same layout as on the Ultimate 2C: hat (0-7, 15 when released), LX, LY, RX, RY, RT, LT, then the button bits. The cave writes the 38-byte Xbox Elite input report: sticks as 16-bit values, triggers as 10-bit values, the hat as 1-8 with 0 when released, and the buttons at the Xbox bit positions. Each trigger value is `v << 2 | v >> 6`, so 255 gives 1023.

**Paddles.** Two checks in Apple's code decide whether the back buttons reach apps:

- GameController creates `Paddle 1`–`4` only for product IDs `0x0b02` and `0x0b05`. For `0x0b22`, the ID of the Elite Series 2 over Bluetooth LE, it creates none.
- `XboxOneHIDServicePlugin`, which parses the reports of Bluetooth Xbox controllers, reads the paddles from bits 0-3 of byte 17 of a 39-byte report (38 bytes and the report ID). It reads them only while bits 0-2 of byte 19, the Elite profile, are 0.

The patch therefore uses product ID `0x0b05`, and the report map gives input report 1 a 23-byte vendor field, so the report is 38 bytes. The cave writes the paddles to byte 16 of the payload, the motion data to bytes 22-33, and 0 to the other bytes of the vendor field. The back buttons map to the paddles at the same positions on an Elite:

| Back button | Bit in the stock input report | Elite paddle |
|---|---|---|
| R4, upper right | byte 9, `0x02` | P1 |
| PR, lower right | byte 7, `0x04` | P2 |
| L4, upper left | byte 9, `0x01` | P3 |
| PL, lower left | byte 7, `0x20` | P4 |

**Rumble path.** Stock firmware drives the motors from output report 5, through the write callback at `0xd534` and the motor routine at `0x12220`. The motor routine takes strengths from 0 to 255. The output routine at `0x12114` sets a PWM duty of `20 + strength × 80 / 255` percent.

The patch changes the report ID to 3, and the callback calls the rumble routine, `rumble.s`. The routine reads the Xbox packet `[0f LT RT LOW HIGH ff 00 eb]`, where each strength runs from 0 to 100. The controller has motors in the handles only. The left motor gets the larger of LT and LOW, and the right motor gets the larger of RT and HIGH. The routine then converts each strength to 0-255 in one of two ways, by the last byte of the packet:

- **GameController's packets** end with loop count `00`: `03 0f LT RT LOW HIGH 0a 00 00`. GameController sends a Core Haptics intensity `p` as strength `100 × p²`, so 30 % arrives as 9. The routine caps the strength at 100 and looks it up in the rumble table, where entry `x` is `28 + 227 × √(x / 100)` and entry 0 is 0. The motors then run at `28 + 227 × p`.
- **Packets from SDL's Xbox driver** end with loop count `0xeb`, and carry the strength linearly. The routine multiplies each strength by 164, shifts it right by 6 and caps it at 255, so 100 becomes 255.

The motors start to turn at strength 28, about 29 % PWM duty, so the table starts at 28 for the smallest strength above 0. SDL's packets keep the plain linear conversion, with no minimum.

GameController's plugin, `XboxOneHIDServicePlugin`, cuts off the fraction when it multiplies by 100, so a Core Haptics intensity below about 10 % arrives as 0. No firmware can recover that rumble. A real Xbox controller receives the same packets from GameController, with the same squared strength and the same loss below 10 %.

**Integrity checks.** Bank A contains two checks over its first `hsize - 4` bytes, where `hsize` is the header word at `+0x18`: a Telink CRC at `hsize - 4`, and the start-up sum at `hsize`. The patch recomputes both. At start-up, the bootloader runs bank A only when the sum matches. According to the bootloader code, a failed sum makes the bootloader copy bank B, the second firmware copy at `0x32000`, over bank A. No test has shown that copy yet.

**Motion data.** Bytes 14-25 of the stock input report carry the gyroscope and the accelerometer. The cave copies them unchanged to bytes 23-34 of the patched report, counting the report ID. GameController offers no motion data for a controller in the Xbox category, and SDL reads no motion data from an Xbox controller, so neither passes these bytes to games. Only an app that reads the raw HID report, and knows this layout, sees them. On tvOS, apps cannot read raw HID reports.

**Not included.** The patched image drops the digital trigger bits. On tvOS, the system handles Home and does not pass it to apps. On macOS, Home does not reach apps either.

## Rebuild the cave and the rumble routine

The Telink tc32 toolchain assembles `cave.s`. Use the `macos` branch of flyskywhy/tc32. Its binaries are x86_64 and run under Rosetta. Link the cave at its address, with the two firmware addresses that it calls:

```sh
tc32-elf-as -o cave.o cave.s
tc32-elf-ld -Ttext=0x1c880 --defsym=notify=0x188d0 --defsym=back=0xe464 -o cave.elf cave.o
tc32-elf-objcopy -O binary --only-section=.text cave.elf cave.bin
```

Build the rumble routine the same way, linked at its own address:

```sh
tc32-elf-as -o rumble.o rumble.s
tc32-elf-ld -Ttext=0x1c940 --defsym=table=0x1c780 -o rumble.elf rumble.o
tc32-elf-objcopy -O binary --only-section=.text rumble.elf rumble.bin
```

`CAVE` and `RUMBLE_ROUTINE` in `patch.py` hold the resulting bytes. `patch.py` computes `RUMBLE_TABLE`. After any change, disassemble the patched bank with `tc32-elf-objdump -D -b binary -m tc32 --adjust-vma=0x5000`, and check that every branch target is the intended address.
