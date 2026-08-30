from pathlib import Path
import argparse

parser = argparse.ArgumentParser(description="Apply the narrow RK-X40 compatibility patch")
parser.add_argument("--repo", required=True)
parser.add_argument("--profile", type=int, choices=(1, 2, 3), required=True)
args = parser.parse_args()

root = Path(args.repo).resolve()
profile = args.profile
kit_root = Path(__file__).resolve().parent


def read_text(path: Path) -> str:
    # utf-8-sig safely consumes a BOM if a checkout/editor ever introduced one.
    return path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")


def write_text(path: Path, text: str) -> None:
    # Explicit UTF-8 + LF keeps generated source deterministic on every runner.
    path.write_text(text, encoding="utf-8", newline="\n")


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = read_text(path)
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"Patch anchor for {label!r} must occur exactly once, found {count}: {path}"
        )
    write_text(path, text.replace(old, new, 1))
    print(f"patched: {label}")


print(f"Applying RK-X40 profile {profile} to {root}")

# 1) Add only our AirPlay compatibility source. Do not edit cosmetic Android
# resources/version metadata; those were unnecessary and made the patch brittle.
src = kit_root / "patches" / "rkx40.go"
dst = root / "doubletake" / "rkx40.go"
if not src.is_file() or src.stat().st_size == 0:
    raise RuntimeError(f"RK compatibility source missing/empty: {src}")
write_text(dst, read_text(src))
print("copied: RK-X40 compatibility source")

# 2) Make upstream build.sh expose rkx40.go inside the pinned nested doubletake
# tree when it creates its temporary build workspace.
build = root / "build.sh"
replace_once(
    build,
    "ln -sf ../../../airplay1.go internal/airplay/airplay1.go",
    "ln -sf ../../../airplay1.go internal/airplay/airplay1.go\n"
    "ln -sf ../../../rkx40.go internal/airplay/rkx40.go",
    "build.sh RK source link",
)

# 3) Keep receiver detection deliberately narrow: only the RK direct hotspot
# address observed on this hardware, and only while the app's legacy mode is off.
airplaylib = root / "doubletake" / "airplaylib" / "airplaylib.go"
replace_once(
    airplaylib,
    "\t\t// match the receiver's display; airplay1 keeps caller dims + clamp\n"
    "\t\tif airplay.AirPlay1Mode {",
    "\t\t// RK-X40L Ultra direct hotspot observed on this hardware.\n"
    "\t\t// Keep this deliberately narrow so all other receivers stay stock.\n"
    "\t\trkCompat := !airplay.AirPlay1Mode && host == \"192.168.68.1\" && port == 5000\n"
    "\t\tif rkCompat {\n"
    "\t\t\ts.logf(\"[RKX40] detected direct hotspot receiver at %s:%d; enabling video-only compatibility path\", host, port)\n"
    "\t\t}\n\n"
    "\t\t// match the receiver's display; airplay1 keeps caller dims + clamp\n"
    "\t\tif airplay.AirPlay1Mode {",
    "airplaylib RK detection",
)

stock_setup = (
    "\t\tif airplay.AirPlay1Mode {\n"
    "\t\t\tmirror, setupErr = client.SetupMirrorAirPlay1(ctx)\n"
    "\t\t} else {\n"
    "\t\t\tmirror, setupErr = client.SetupMirror(ctx, airplay.StreamConfig{FPS: fps})\n"
    "\t\t}"
)
rk_setup = (
    "\t\tif airplay.AirPlay1Mode {\n"
    "\t\t\tmirror, setupErr = client.SetupMirrorAirPlay1(ctx)\n"
    "\t\t} else if rkCompat {\n"
    f"\t\t\tmirror, setupErr = client.SetupMirrorRKX40(ctx, airplay.StreamConfig{{FPS: fps, NoAudio: true}}, {profile})\n"
    "\t\t} else {\n"
    "\t\t\tmirror, setupErr = client.SetupMirror(ctx, airplay.StreamConfig{FPS: fps})\n"
    "\t\t}"
)
replace_once(airplaylib, stock_setup, rk_setup, "airplaylib RK routing")

# 4) Hard post-patch assertions. These are intentionally about behavior only,
# not labels/version strings, so upstream UI-resource layout cannot break us.
build_text = read_text(build)
airplay_text = read_text(airplaylib)
rk_text = read_text(dst)

assert build_text.count("internal/airplay/rkx40.go") == 1
assert airplay_text.count("rkCompat :=") == 1
assert airplay_text.count("SetupMirrorRKX40") == 1
assert f"}}, {profile})" in airplay_text
assert "func (c *AirPlayClient) SetupMirrorRKX40" in rk_text
assert "[RKX40]" in rk_text

print(f"RK-X40 profile {profile} patch completed and behavior assertions passed.")
