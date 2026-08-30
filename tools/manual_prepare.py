from pathlib import Path
import argparse,re,shutil
p=argparse.ArgumentParser(); p.add_argument('--repo',required=True); a=p.parse_args(); root=Path(a.repo).resolve()
outer=root/'doubletake'; inner=outer/'doubletake'; air=inner/'internal'/'airplay'

def r(path): return path.read_text(encoding='utf-8-sig').replace('\r\n','\n')
def w(path,s): path.write_text(s,encoding='utf-8',newline='\n')
def lit(path,old,new,label,required=False):
    s=r(path)
    if old not in s:
        if required: raise RuntimeError(f'missing required anchor {label}: {path}')
        print('manual fallback: optional patch not needed:',label); return
    w(path,s.replace(old,new,1)); print('manual fallback patched:',label)
def regex(path,pat,repl,label):
    s=r(path); n,c=re.subn(pat,repl,s,count=1,flags=re.S)
    if c: w(path,n); print('manual fallback patched:',label)
    else: print('manual fallback: optional regex not needed:',label)

# Copy Android wrapper and compatibility sources into the nested module.
dst=inner/'airplaylib'
if dst.exists() or dst.is_symlink():
    if dst.is_dir() and not dst.is_symlink(): shutil.rmtree(dst)
    else: dst.unlink()
shutil.copytree(outer/'airplaylib',dst)
for name in ('patches.go','airplay1.go','rkx40.go'):
    shutil.copy2(outer/name,air/name)

mirror=air/'mirror.go'; client=air/'client.go'; fair=air/'fairplay.go'
lit(mirror,'*ScreenCapture','io.Reader','Android capture reader')
regex(client,r'if err != nil \{\s*return nil, nil, err', 'if err != nil {\n\t\treturn nil, respHeaders, err','preserve RTSP response headers')
lit(fair,'deriveStreamMasterKey(c.fpAesKey, sharedSecret(c.PairKeys), c.encrypted)','deriveStreamMasterKey(c.fpAesKey, sharedSecret(c.PairKeys), true)','FairPlay shared-secret derivation')
lit(fair,'if c.encrypted && len(sharedSecret(c.PairKeys)) > 0 {','if len(sharedSecret(c.PairKeys)) > 0 {','FairPlay shared-secret gate')
anchor='audioSetupBody, err2 := plist.Marshal(audioSetupPlist, plist.BinaryFormat)'
insert='if ep, err0 := c.SetupSession(audioURI, clientDeviceID, sessionUUID, timingPort); err0 != nil {audioCtrlConn.Close(); audioDataConn.Close(); return nil, fmt.Errorf("SETUP phase 0 (session): %w", err0)} else if ep > 0 {receiverEventPort = ep}\n'+anchor
lit(mirror,anchor,insert,'legacy session phase 0')
# gomobile binding compatibility; named wrapper types are provided by outer patches.go.
regex(client,r'\[\]byte\s+`plist','pkBytes `plist','plist byte wrapper')
regex(client,r'(?<![A-Za-z0-9_])int\s+`plist','plistNum `plist','plist int wrapper')
regex(client,r'(?<![A-Za-z0-9_])bool\s+`plist','plistBool `plist','plist bool wrapper')
lit(client,'return w, h','return int(w), int(h)','DisplaySize int conversion')
print('manual fallback source preparation complete')
