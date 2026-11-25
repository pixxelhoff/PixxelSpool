# Changelog – PixxelSpool

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versions follow [SemVer](https://semver.org/)
(MAJOR.MINOR.PATCH: MAJOR = rework with data migration, MINOR = new feature, PATCH = bug fix).
Pre-releases are tagged `-alpha.N`, `-beta.N` and `-rc.N`; they are only offered to installations that already
run a pre-release. The Raspberry Pi, the Windows app and the Mac app share one version number. Fixes for the apps only
get the current version plus `-patch.N` (e.g. 1.0.0-patch.1); the Pi does not offer those.

The German changelog is [CHANGELOG.de.md](CHANGELOG.de.md).

## [1.0.0-beta.4] – 2026-11-25

Third bundled release, plus a Docker version.

### Fixed
- Labels: Safari no longer cuts off rows at the page break. A hint explains how to turn off Safari's page header and footer.
- Labels without a QR code: the text now fills the label instead of shrinking to a tiny size.
- Labels: the info line above the sheet is translated.
- Check 3MF: large models (e.g. 50 MB) are read much faster and with a fraction of the memory. If a device still has too little memory, a clear message says so instead of crashing.
- Raspberry Pi without a clock chip: pulling the power plug is now detected reliably and shows the power-loss notice on the next start.

### Changed
- Check 3MF: the result is redesigned. A summary on top (weight, cost, colours in storage), one clear row per filament, and the explanation of the estimate folded away.

### Added
- Docker: PixxelSpool runs as a container (amd64 and arm64). See the README section "Docker".
- Labels: choose which address the QR code opens, including the `.local` name that keeps working when the router hands out a new IP address.
- Check 3MF: progress bar for upload and analysis, with a Cancel button.
- README: Waveshare PN532 HAT and PN532 V3 tested, with switch and jumper settings; Raspberry Pi 4 and 5 tested.

## [1.0.0-beta.3] – 2026-11-25

Second bundled release: everything reported on beta.2.

### Fixed
- A restart (e.g. after an update) no longer books the printer's last finished print a second time.
- If the print file can't be read from the printer, a notice says so and the print is marked, also after a restart.
- A spool on the external holder shows "External spool" (translated) instead of "in AMS: External spool".
- Catalog: the note on colours Bambu Lab no longer sells now reads "no longer available" and no longer runs into the next tile. The switch to show them moved from Options › Appearance into the catalog filters ("Show colors no longer available").
- No visible scrollbars; scrolling works as before.
- Check 3MF: the note now says to export the sliced plate (.gcode.3mf) from Bambu Studio for exact values.

### Changed
- Sorting storage by dragging was too easy to trigger by accident: it now only works after "Sort", and changes are only planned until "Apply".
- New loading screen: a spool winding up in Bambu colours instead of grey placeholder tiles.

### Added
- Recent prints: amounts of a print whose file couldn't be read can be added by hand or taken from the exported .gcode.3mf.
- Shopping list: choose how many spools of a color you want (− / +). The entry stays until that many new spools were added.
- Prices per delivery: mark a delivery as refills. The price history shows spools and refills as two lines; free spools (0) are left out.

## [1.0.0-beta.2] – 2026-11-25

First bundled release of the beta: all fixes reported since beta.1, plus a few small additions that make reporting
bugs and checking prints easier.

### Fixed
- External spool holder: "Assign spool" (β) now also works there; usage and cost of prints from the external holder are booked to the spool.
- Printers without AMS: the external spool is shown, print checks and statistics work.
- AMS spool without a Bambu chip and without a material set on the printer no longer counts as empty and can be assigned.
- External holders are named by their ID (254/255); grams from the print file go to the right holder.
- Audit: spools that were taken out (e.g. on the external holder) no longer count as "not found".
- Scanning a Bambu spool no longer attaches its tag to a same-coloured spool assigned to the AMS by hand.
- Storage tile: a spool on the external holder shows "Ext." instead of "AMS".
- Prices are always shown with two decimals (9 → 9.00 €), also right after typing them.
- Catalog: colours Bambu Lab no longer sells (PETG Basic 30404, 30504, 30701, 30702) no longer count as missing. They are hidden; Options › Appearance can show them with the note "no longer sold" and without a shop link.
- Catalog: PLA Basic Gradient and PLA Silk Multi-Color are their own lines instead of being listed under PLA Basic / PLA Silk. Prices and weights are taken over.
- List view on a PC: the left column (AMS, climate) scrolls on its own, so it no longer ends up below a long storage list.
- An opened spool no longer shows the Refill switch. When a refill shows up in the AMS, PixxelSpool now always asks whether an empty spool was used.
- Prints with free spools (0 €) show 0.00 € instead of "–"; prints recorded before a price was entered get their cost once the price exists.
- Check 3MF: sliced files no longer show "0 objects".
- Check 3MF: a colour that only exists as a hex code (e.g. #9C7149) shows the closest Bambu colour, with a note that it is only close.
- Check 3MF: painted, unsliced files show all painted filaments with their share, not only the base colour.
- Updates: releases marked "Security" are offered even when "Offer pre-releases" is Off.

### Added
- Check 3MF: cost of the print per filament and in total, from your stock price, the line price or, if neither exists, the price in the file (marked as an estimate). Clearer overview with Bambu colour names and amounts.
- Recent prints: a click shows usage and cost per filament. Prints can get a project name; Statistics shows a "Projects" card.
- Statistics: price history per line.
- Raspberry Pi: a notice after the power was cut without shutting down.
- Search: an X clears and closes the search. "/" opens it, arrow keys and Enter pick a result.
- "Empty" no longer asks first; an "Undo" button appears instead.
- "Today" bar on the start page; placeholders while the page loads.
- Spool details and the shopping list show roughly how long a colour lasts at your usage.
- Options › Backup: export spools and prints as CSV.
- Drag and drop in the AMS view: drop a spool on a free slot to move it, on an occupied slot to swap.
- Options › About and Log: "Report a bug" opens a GitHub issue with version, platform and device filled in. The log export starts with these facts (without tokens, passwords or access codes).

## [1.0.0-beta.1] – 2026-11-19

### First beta
- First beta of **PixxelSpool by pixxelhoff**: storage management for 3D filament (Bambu Lab) with NFC reader, printer and AMS connection, Home Assistant, backups, password and passkeys, remote access via Tailscale. Raspberry Pi, Windows app and Mac app share this version.
- From now on only bug fixes are collected and released in bundles; no new features before the final 1.0.0.
- Options › System › Updates: "Offer pre-releases" has the steps **Off**, **Beta** and **Alpha**.
- Developed privately before this; the earlier public versions were `1.0.0-alpha.1` to `1.0.0-alpha.97`.
