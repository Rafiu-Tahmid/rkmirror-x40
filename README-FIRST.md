# RK Mirror X40 Cloud Builder v1.4

This version is designed so you only run one Windows file.

## Run

Double-click **UPDATE-AND-BUILD.bat** and press Enter at the repository prompt.
It updates the existing `Rafiu-Tahmid/rkmirror-x40` repository, pushes one commit, and the push automatically starts GitHub Actions.

No Android Studio, Android SDK, NDK, Gradle, Go build, or APK compilation happens on your PC.

## Why v1.4 is different

The previous static RK source assumed a particular `doubletake` internal API. The pinned v0.0.33 submodule can have different `MirrorSession` fields and heartbeat method signatures. v1.4 reads the exact pinned source during the GitHub run and generates an RK compatibility file that matches that API.

The AirPlay library also has two independent build paths:
1. exact upstream `build.sh`;
2. automatic deterministic fallback that reproduces the required Android/gomobile patches if the upstream script exits non-zero.

The workflow only fails if both AirPlay builders fail. In that case it automatically uploads full compiler/build logs and the exact generated source as `diagnostics-P1/P2/P3`; you do not have to manually copy hidden log lines.

## Success

When a profile is green, open that workflow run and download the `RK-Mirror-X40-P1` artifact first. It contains the APK and SHA-256 checksum.
