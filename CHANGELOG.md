# Changelog – PixxelSpool

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versions follow [SemVer](https://semver.org/)
(MAJOR.MINOR.PATCH: MAJOR = rework with data migration, MINOR = new feature, PATCH = bug fix).
Pre-releases are tagged `-alpha.N`, `-beta.N` and `-rc.N`; they are only offered to installations that already
run a pre-release. The Raspberry Pi, the Windows app and the Mac app share one version number. Fixes for the apps only
get the current version plus `-patch.N` (e.g. 1.0.0-patch.1); the Pi does not offer those.

The German changelog is [CHANGELOG.de.md](CHANGELOG.de.md).

## [1.0.0-beta.1] – 2026-11-19

### First beta
- First beta of **PixxelSpool by pixxelhoff**: storage management for 3D filament (Bambu Lab) with NFC reader, printer and AMS connection, Home Assistant, backups, password and passkeys, remote access via Tailscale. Raspberry Pi, Windows app and Mac app share this version.
- From now on only bug fixes are collected and released in bundles; no new features before the final 1.0.0.
- Options › System › Updates: "Offer pre-releases" has the steps **Off**, **Beta** and **Alpha**.
- Developed privately before this; the earlier public versions were `1.0.0-alpha.1` to `1.0.0-alpha.97`.
