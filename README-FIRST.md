# RK Mirror X40 — Cloud Build Kit v1.2

This version is designed for the existing GitHub repository and avoids local Android build tooling completely.

## Why v1.2 exists

The first cloud workflow called `sdkmanager` as though it were guaranteed to be on the runner PATH. On the current GitHub-hosted image it was not, so all three matrix jobs stopped with exit code 127 before source compilation. v1.2 resolves the SDK root explicitly and calls the canonical `cmdline-tools/.../bin/sdkmanager` path. It also verifies API 36, Build Tools 36.0.0, and NDK 27.0.12077973 before cloning or compiling anything.

The workflow now uses current Node-24-capable official GitHub actions (`checkout@v7`, `setup-java@v6`, `setup-go@v7`, `upload-artifact@v6`) to remove the Node 20/deprecation warnings shown by the previous run.

## Existing repository: easiest route

1. Extract this ZIP.
2. Double-click `UPDATE-EXISTING-REPO.bat`.
3. Press Enter to use `https://github.com/Rafiu-Tahmid/rkmirror-x40.git`.
4. Let it push the fixed workflow.
5. GitHub should open automatically.
6. Go to **Actions → Build RK Mirror APKs → Run workflow → Run workflow**.

You do not need a new repository and do not need to install anything else on Windows.

## What a healthy run looks like

Each Profile job should pass these gates in order:

1. `Locate and verify Android SDK` → ends with `Android SDK/NDK verification passed.`
2. `Clone exact upstream release`
3. `Apply RK-X40 compatibility profile`
4. `Preflight patched sources`
5. `Build AirPlay library`
6. `Build Android APK`
7. `Upload APK and checksum`

When finished, the run's **Artifacts** section should contain:

- `RK-Mirror-X40-P1`
- `RK-Mirror-X40-P2`
- `RK-Mirror-X40-P3`

Test P1 first.

## If a source-level failure still appears

Do not rerun repeatedly. Open the failed job and send the first failing step's final 30–50 lines. At that point the failure is no longer a Windows installer/SDK-discovery problem; the workflow's preflight gates make the failing layer explicit.
