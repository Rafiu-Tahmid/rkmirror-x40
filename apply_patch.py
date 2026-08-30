from pathlib import Path
import argparse, re, sys

p = argparse.ArgumentParser()
p.add_argument('--repo', required=True)
p.add_argument('--profile', type=int, choices=[1,2,3], required=True)
a = p.parse_args()
root = Path(a.repo).resolve()
profile = a.profile

def read(path):
    return Path(path).read_text(encoding='utf-8-sig').replace('\r\n','\n')

def write(path, text):
    Path(path).write_text(text, encoding='utf-8', newline='\n')

def replace_required(path, old, new, label):
    text = read(path)
    if old not in text:
        raise RuntimeError(f'Patch anchor missing for {label}: {path}')
    write(path, text.replace(old, new, 1))
    print(f'patched: {label}')

print(f'Applying RK-X40 profile {profile} to {root}')
# Custom source used by patched upstream build.sh
src = Path(__file__).resolve().parent / 'patches' / 'rkx40.go'
dst = root / 'doubletake' / 'rkx40.go'
dst.write_bytes(src.read_bytes())

build = root / 'build.sh'
replace_required(
    build,
    'ln -sf ../../../airplay1.go internal/airplay/airplay1.go',
    'ln -sf ../../../airplay1.go internal/airplay/airplay1.go\nln -sf ../../../rkx40.go internal/airplay/rkx40.go',
    'build.sh RK source link')

ap = root / 'doubletake' / 'airplaylib' / 'airplaylib.go'
replace_required(
    ap,
    '\t\t// match the receiver\'s display; airplay1 keeps caller dims + clamp\n\t\tif airplay.AirPlay1Mode {',
    '\t\t// RK-X40L Ultra direct hotspot observed on this hardware.\n'
    '\t\t// Keep this deliberately narrow so all other receivers stay stock.\n'
    '\t\trkCompat := !airplay.AirPlay1Mode && host == "192.168.68.1" && port == 5000\n'
    '\t\tif rkCompat {\n'
    '\t\t\ts.logf("[RKX40] detected direct hotspot receiver at %s:%d; enabling video-only compatibility path", host, port)\n'
    '\t\t}\n\n'
    '\t\t// match the receiver\'s display; airplay1 keeps caller dims + clamp\n'
    '\t\tif airplay.AirPlay1Mode {',
    'airplaylib RK detection')

old = ('\t\tif airplay.AirPlay1Mode {\n'
       '\t\t\tmirror, setupErr = client.SetupMirrorAirPlay1(ctx)\n'
       '\t\t} else {\n'
       '\t\t\tmirror, setupErr = client.SetupMirror(ctx, airplay.StreamConfig{FPS: fps})\n'
       '\t\t}')
new = ('\t\tif airplay.AirPlay1Mode {\n'
       '\t\t\tmirror, setupErr = client.SetupMirrorAirPlay1(ctx)\n'
       '\t\t} else if rkCompat {\n'
       f'\t\t\tmirror, setupErr = client.SetupMirrorRKX40(ctx, airplay.StreamConfig{{FPS: fps, NoAudio: true}}, {profile})\n'
       '\t\t} else {\n'
       '\t\t\tmirror, setupErr = client.SetupMirror(ctx, airplay.StreamConfig{FPS: fps})\n'
       '\t\t}')
replace_required(ap, old, new, 'airplaylib RK routing')

strings = root / 'app' / 'src' / 'main' / 'res' / 'values' / 'strings.xml'
text = read(strings)
newtext, n = re.subn(r'<string name="mirror_app_name">[^<]*</string>', f'<string name="mirror_app_name">RK Mirror X40 P{profile}</string>', text, count=1)
if n != 1:
    raise RuntimeError('App-name patch anchor missing')
write(strings, newtext)

gradle = root / 'app' / 'build.gradle'
text = read(gradle)
newtext, n = re.subn(r'versionName\s+"[^"]+"', f'versionName "0.0.33-rkx40.p{profile}"', text, count=1)
if n != 1:
    raise RuntimeError('versionName patch anchor missing')
write(gradle, newtext)

# Sanity checks before expensive build.
for f in [build, ap, strings, gradle, dst]:
    if not f.exists() or f.stat().st_size == 0:
        raise RuntimeError(f'Patched file missing/empty: {f}')
print('Patch completed and sanity-checked.')
