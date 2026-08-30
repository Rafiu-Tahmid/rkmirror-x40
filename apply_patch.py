from pathlib import Path
import argparse, subprocess, sys

p=argparse.ArgumentParser(); p.add_argument('--repo',required=True); p.add_argument('--profile',required=True,type=int,choices=(1,2,3)); a=p.parse_args()
root=Path(a.repo).resolve(); here=Path(__file__).resolve().parent

def read(path): return path.read_text(encoding='utf-8-sig').replace('\r\n','\n')
def write(path,s): path.write_text(s,encoding='utf-8',newline='\n')
def replace_once(path,old,new,label):
    s=read(path); n=s.count(old)
    if n!=1: raise RuntimeError(f'{label}: expected exactly one anchor, found {n}: {path}')
    write(path,s.replace(old,new,1)); print('patched:',label)

# Generate against the exact nested submodule API first.
subprocess.run([sys.executable,str(here/'generate_rkx40.py'),'--repo',str(root),'--profile',str(a.profile)],check=True)

# Make the upstream builder include our generated source.
build=root/'build.sh'
replace_once(build,
    'ln -sf ../../../airplay1.go internal/airplay/airplay1.go',
    'ln -sf ../../../airplay1.go internal/airplay/airplay1.go\nln -sf ../../../rkx40.go internal/airplay/rkx40.go',
    'build.sh RK source link')

# Route only the observed RK direct-hotspot endpoint through the compatibility path.
air=root/'doubletake'/'airplaylib'/'airplaylib.go'
replace_once(air,
    '\t\t// match the receiver\'s display; airplay1 keeps caller dims + clamp\n\t\tif airplay.AirPlay1Mode {',
    '\t\t// RK-X40L Ultra direct hotspot; leave all other receivers stock.\n\t\trkCompat := !airplay.AirPlay1Mode && host == "192.168.68.1" && port == 5000\n\t\tif rkCompat { s.logf("[RKX40] detected direct hotspot receiver at %s:%d", host, port) }\n\n\t\t// match the receiver\'s display; airplay1 keeps caller dims + clamp\n\t\tif airplay.AirPlay1Mode {',
    'airplaylib RK detection')
stock='\t\tif airplay.AirPlay1Mode {\n\t\t\tmirror, setupErr = client.SetupMirrorAirPlay1(ctx)\n\t\t} else {\n\t\t\tmirror, setupErr = client.SetupMirror(ctx, airplay.StreamConfig{FPS: fps})\n\t\t}'
rk='\t\tif airplay.AirPlay1Mode {\n\t\t\tmirror, setupErr = client.SetupMirrorAirPlay1(ctx)\n\t\t} else if rkCompat {\n\t\t\tmirror, setupErr = client.SetupMirrorRKX40(ctx, airplay.StreamConfig{FPS: fps, NoAudio: true}, %d)\n\t\t} else {\n\t\t\tmirror, setupErr = client.SetupMirror(ctx, airplay.StreamConfig{FPS: fps})\n\t\t}'%a.profile
replace_once(air,stock,rk,'airplaylib RK routing')

# Format the generated Go now; fail immediately on syntax errors.
subprocess.run(['gofmt','-w',str(root/'doubletake'/'rkx40.go')],check=True)
print('RK profile patch complete.')
