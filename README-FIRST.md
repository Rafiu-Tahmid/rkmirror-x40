# RK Mirror X40 — Cloud Build Kit v1.3

This kit updates the existing GitHub repository and builds the three RK-X40 compatibility APK profiles entirely on GitHub Actions. The Windows updater requires only Git (already installed). It does not require Python, Android Studio, an Android SDK/NDK, Gradle, Java, or Go locally for compilation.

## Existing repository (recommended)

1. Extract this ZIP.
2. Double-click `UPDATE-EXISTING-REPO.bat`.
3. Press Enter to use the default repository `https://github.com/Rafiu-Tahmid/rkmirror-x40.git`.
4. Wait for `SUCCESS`.
5. In GitHub, open **Actions → Build RK Mirror APKs → Run workflow → Run workflow**.

## What v1.3 fixes

The v1.2 patcher tried to rename an Android string resource named `mirror_app_name`. The pinned upstream v0.0.33 source does not define that resource, so the patch step could exit before compilation. v1.3 removes all cosmetic app-name/version edits and patches only the three behavior-critical points: add `rkx40.go`, link it into the nested AirPlay build, and route the known RK hotspot through the requested profile.

The workflow also avoids `grep | head` while `pipefail` is enabled, performs patcher syntax checks before modifying source, verifies each behavior anchor exactly once, pins the exact upstream commits, and keeps profiles 1/2/3 independent.

## Successful result

The run should produce these artifacts:

- `RK-Mirror-X40-P1`
- `RK-Mirror-X40-P2`
- `RK-Mirror-X40-P3`

Test P1 first. If a profile fails at runtime, power-cycle the RK-X40 before testing the next profile.
