# Changelog – PixxelSpool

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versions follow [SemVer](https://semver.org/)
(MAJOR.MINOR.PATCH: MAJOR = rework with data migration, MINOR = new feature, PATCH = bug fix).
Pre-releases are tagged `-alpha.N`, `-beta.N` and `-rc.N`; they are only offered to installations that already
run a pre-release. The Raspberry Pi, the Windows app and the Mac app share one version number. Fixes for the apps only
get the current version plus `-patch.N` (e.g. 1.0.0-patch.1); the Pi does not offer those.

The German changelog is [CHANGELOG.de.md](CHANGELOG.de.md).

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
