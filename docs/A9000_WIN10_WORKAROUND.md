# Netgear A9000 (BE6500) on Windows 10 — forced-driver workaround

Task for a Claude Code session running ON THE RAZER (local filesystem access). Goal: stage a
USB thumb drive with a Win10-installable driver for the Netgear Nighthawk A9000, then hand the
owner a short on-screen checklist for the offline desktop. Time-box: 20 minutes. If it does
not come up, the owner returns the adapter and buys the TP-Link BE3500 (officially Win10).

## Facts already established
- Adapter: Netgear Nighthawk A9000, BE6500 Wi-Fi 7 USB 3.0. Hardware ID `USB\VID_0846&PID_9072`.
- Target PC: Windows 10 (unactivated), no internet, no Wi-Fi. Device Manager shows
  "Wireless_Device", Code 28, no compatible driver.
- Netgear's installer runs and "completes" on Win10 but installs nothing usable: the driver INF
  is gated to Windows 11 builds. Netgear lists the A9000 as Windows 11 only.
- The Netgear driver zip ("A9000 Windows Installer...zip") is already on the thumb drive and on
  the desktop PC's desktop. The thumb drive itself works (it ran the installer).

## Step 1 — extract and inspect the Netgear package (on the Razer)
1. Plug in the Netgear thumb drive. Copy the zip to `%USERPROFILE%\Desktop\A9000work\`, extract.
2. Find every `*.inf` in the extracted tree: `Get-ChildItem -Recurse -Filter *.inf`.
3. For each INF, read and report:
   - `[Version]` block: `Provider`, `Class` (expect `Net`), `CatalogFile`, `DriverVer`.
   - `[Manufacturer]` line. Win11 gating looks like `NTamd64.10.0...22000` (or `...22621`).
   - Whether `VID_0846&PID_9072` appears in a `[*.NTamd64...]` models section.
   - The `.sys` filename(s) referenced (tells us the chipset vendor: MediaTek `mtk*`/`mt79*`,
     Realtek `rtwlan*`/`rtl*`, Qualcomm `qcwlan*`).
4. Note the list of `.sys`/`.dll`/`.cat` files beside the INF — the whole folder must be copied.

## Step 2 — make the Win10 variant
1. Copy the driver folder to `A9000work\A9000_Win10\`. Never edit the original.
2. In the copied INF, change the `[Manufacturer]` decoration from `NTamd64.10.0...22000`
   (whatever build it names) to plain `NTamd64`. Rename the matching models section header
   `[<name>.NTamd64.10.0...22000]` to `[<name>.NTamd64]`. Leave everything else alone.
3. Make sure `USB\VID_0846&PID_9072` is listed in that models section. If it only appears
   with `&REV_0100`, add a second line without the REV so a plain match works.
4. Sanity check: no other section still references the old decorated name.
5. The edit breaks the catalog signature. That is expected; the desktop will boot with
   signature enforcement disabled (Step 4). Do NOT try to re-sign.

## Step 3 — plan B: generic chipset driver (do this too, costs nothing)
Based on the `.sys` names from Step 1, download the vendor's generic Windows 10 driver for that
chipset (Station-Drivers or the vendor's site). Put it in `A9000work\Generic_Win10\`. Check its
INF lists our `VID_0846&PID_9072`; if not, add a model line pointing at the same install section
the vendor's own USB IDs use. This is the fallback if Plan A loads but yellow-bangs (Code 10/39).

## Step 4 — stage the thumb drive
Copy `A9000_Win10\` and `Generic_Win10\` to the root of the thumb drive. Also drop a
`README_DESKTOP.txt` on it with the desktop checklist below, so the owner has it offline.

## Desktop checklist (offline PC, owner does this by hand)
1. Plug the A9000 into a rear USB 3.0 port (blue). Avoid front-panel ports and hubs.
2. Disable driver signature enforcement for this boot: Start > Power > hold Shift + Restart >
   Troubleshoot > Advanced options > Startup Settings > Restart > press 7.
3. Device Manager > Other devices > Wireless_Device > Update Driver > Browse my computer >
   Let me pick > Have Disk > Browse to the thumb drive `A9000_Win10\<file>.inf` > Next.
4. Accept the "unsigned driver" warning (Install anyway).
5. Result: adapter appears under Network adapters with no yellow mark, Wi-Fi icon shows in tray.
   - Code 10 / 39 / 52 after install: repeat step 3 with `Generic_Win10\`.
   - Still dead after both: stop. Return the adapter, buy TP-Link BE3500.
6. If it works: the unsigned driver stays loaded across normal reboots, but a major Windows
   update may reset it. Keep the thumb drive.

## Report back to the owner (10 bullets or fewer)
- Chipset vendor found, INF edited yes/no, generic driver found yes/no, files staged on USB,
  go / no-go recommendation.

## Honest odds
Roughly a coin flip. The build gate is often the only blocker and the edit alone works. If the
driver binary itself depends on Win11-only kernel APIs, it will fail to start and no INF edit
helps; the generic chipset driver is the only remaining shot. Ethernet is still the right
answer for a machine that runs backtests.
