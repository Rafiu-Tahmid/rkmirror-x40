# RK Mirror X40 — Cloud Build Kit

## Why this replaces the Windows installer

The local installer reached Android's NDK installation and Windows reported **not enough disk space**. Building locally also duplicates several large SDK/NDK/Gradle/Go caches. This kit moves the entire compilation to a fresh GitHub Actions Linux machine, so your PC does **not** need Android Studio, Android SDK, NDK, Gradle, or free space for the Android toolchain.

Your PC only needs the Git installation you already have.

## One-time setup

1. Sign in to GitHub in your browser.
2. Create a **new empty repository** (private is fine). Do NOT add README, .gitignore, or license when GitHub asks.
3. Extract this ZIP normally.
4. Double-click **PUSH-TO-GITHUB.bat**.
5. Paste the new repository's HTTPS URL, for example `https://github.com/YOURNAME/rkmirror-x40.git`.
6. If Windows opens Git Credential Manager/browser login, approve it.
7. When the script says SUCCESS, open that GitHub repository.
8. Click **Actions** → **Build RK Mirror APKs** → **Run workflow** → **Run workflow**.

GitHub will build P1, P2, and P3 independently in the cloud. A failure in one profile does not cancel the others.

## Downloading the APKs

When the workflow is finished:

1. Open the completed workflow run.
2. Scroll to **Artifacts**.
3. Download `RK-Mirror-X40-P1` first. It contains the APK and SHA-256 file.
4. Extract it and install `RK-Mirror-X40-P1-debug.apk` on the Pixel.

Before installing, uninstall the Play Store/F-Droid copy of Mirror because the custom debug APK has a different signing key.

## First hardware test

1. Power the RK-X40L OFF for ~20 seconds, then ON.
2. Connect Pixel Wi-Fi to `RK-X40L Ultra-e787` and choose Stay connected despite no internet.
3. For the first test, turn mobile data OFF.
4. Open `RK Mirror X40 P1`.
5. Keep **Support for legacy 3rd party receivers OFF**.
6. Select `RK-X40L Ultra-e787_itv` and Connect.
7. Approve Android's screen-capture prompt.

If P1 fails, power-cycle the RK before testing P2. Do the same before P3.

## Why this workflow is harder to break

- exact upstream tag v0.0.33 and exact commit are verified before patching;
- every required source anchor is checked and the build aborts immediately if upstream source differs;
- each profile is built on its own fresh runner;
- Java, Go, Android 36, Build Tools 36.0.0, and NDK 27.0.12077973 are pinned;
- the runner frees large unrelated preinstalled toolchains before Android installation;
- the AirPlay AAR is checked before Gradle runs;
- the APK is checked before artifact upload;
- each APK is accompanied by a SHA-256 checksum;
- local disk space is no longer relevant to compilation.

## Important limitation

The cloud build can prove the source compiles and produces valid APK files. Only your physical RK-X40L can prove which handshake profile its undocumented firmware accepts. That hardware test cannot be performed in GitHub Actions.
