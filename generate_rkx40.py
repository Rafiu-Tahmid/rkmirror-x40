from pathlib import Path
import argparse, re

p = argparse.ArgumentParser()
p.add_argument('--repo', required=True)
p.add_argument('--profile', required=True, type=int, choices=(1,2,3))
a = p.parse_args()
root = Path(a.repo).resolve()
outer = root / 'doubletake'
inner_air = outer / 'doubletake' / 'internal' / 'airplay'
if not inner_air.is_dir():
    raise SystemExit(f'inner AirPlay source not found: {inner_air}')
all_go = '\n'.join(x.read_text(encoding='utf-8', errors='replace') for x in sorted(inner_air.glob('*.go')))
mirror = (inner_air / 'mirror.go').read_text(encoding='utf-8', errors='replace')

# Detect the exact pinned API instead of assuming a moving doubletake shape.
has_cancel = bool(re.search(r'\bcancel\s+context\.CancelFunc\b', all_go))

def sig(name):
    m = re.search(rf'func\s*\(s\s+\*MirrorSession\)\s*{name}\s*\(([^)]*)\)', all_go, re.S)
    return re.sub(r'\s+', ' ', m.group(1)).strip() if m else ''

hb_sig = sig('heartbeatLoop')
data_sig = sig('dataHeartbeatLoop')
fb_sig = sig('feedbackLoop')

# Reuse the sourceVersion already used by this exact source snapshot.
sv = re.search(r'"sourceVersion"\s*:\s*"([^"]+)"', mirror)
source_version = sv.group(1) if sv else '280.33'

calls = []
if hb_sig:
    # Current source: ctx, controlURI, sessionUUID. Older trees may omit it.
    commas = hb_sig.count(',')
    if commas >= 2:
        calls.append('go session.heartbeatLoop(sessionCtx, controlURI, sessionUUID)')
    elif commas == 1:
        calls.append('go session.heartbeatLoop(sessionCtx, controlURI)')
    else:
        calls.append('go session.heartbeatLoop(sessionCtx)')
if data_sig:
    commas = data_sig.count(',')
    if commas == 0:
        calls.append('go session.dataHeartbeatLoop(sessionCtx)')
    else:
        # Extremely defensive: preserve the only stable argument and skip an
        # unknown future signature rather than generating uncompilable code.
        calls.append('// dataHeartbeatLoop signature is newer than this kit; intentionally skipped')
if fb_sig:
    commas = fb_sig.count(',')
    if commas >= 1:
        calls.append('go session.feedbackLoop(sessionCtx, controlURI)')
    else:
        calls.append('go session.feedbackLoop(sessionCtx)')

cancel_literal = '\n\t\tcancel:         cancelSession,' if has_cancel else ''
background = '\n\t'.join(calls) if calls else '// No compatible stock heartbeat helpers detected in this snapshot.'

code = r'''package airplay

// RK-X40L compatibility path generated against the exact pinned doubletake API.
// It is deliberately video-only and avoids unstable helper APIs used by older
// experimental versions of this patch.

import (
    "context"
    "crypto/rand"
    "fmt"
    "net"
    "strconv"
    "strings"
    "time"

    "howett.net/plist"
)

func (c *AirPlayClient) SetupMirrorRKX40(ctx context.Context, cfg StreamConfig, profile int) (*MirrorSession, error) {
    if profile < 1 || profile > 3 { profile = 1 }
    return c.setupMirrorRKX40(ctx, cfg, profile)
}

func (c *AirPlayClient) setupMirrorRKX40(ctx context.Context, cfg StreamConfig, profile int) (*MirrorSession, error) {
    sessionUUID := rkUUID()
    deviceID := rkDeviceID()

    timingConn, err := net.ListenUDP("udp4", &net.UDPAddr{IP: net.IPv4zero, Port: 0})
    if err != nil { return nil, fmt.Errorf("rkx40 timing socket: %w", err) }
    timingPort := timingConn.LocalAddr().(*net.UDPAddr).Port

    sessionCtx, cancelSession := context.WithCancel(ctx)
    setupOK := false
    var dataConn net.Conn
    var eventConn net.Conn
    defer func() {
        if setupOK { return }
        cancelSession()
        _ = timingConn.Close()
        if dataConn != nil { _ = dataConn.Close() }
        if eventConn != nil { _ = eventConn.Close() }
    }()
    go ntpTimingResponder(sessionCtx, timingConn)

    controlID := int64(time.Now().UnixNano() & 0x7fffffffffffffff)
    videoID := int64((time.Now().UnixNano()+1) & 0x7fffffffffffffff)
    controlURI := fmt.Sprintf("rtsp://%s:%d/%d", c.host, c.port, controlID)
    videoURI := fmt.Sprintf("rtsp://%s:%d/%d", c.host, c.port, videoID)

    encKey, encIV, err := rkVideoKeyMaterial(c, cfg)
    if err != nil { return nil, err }

    sessionBody := map[string]interface{}{
        "deviceID": deviceID,
        "macAddress": deviceID,
        "sessionUUID": sessionUUID,
        "sourceVersion": "__SOURCE_VERSION__",
        "isScreenMirroringSession": true,
        "timingProtocol": "NTP",
        "timingPort": int64(timingPort),
        "osBuildVersion": "13F69",
        "model": "iPhone10,6",
        "name": "RK Mirror",
    }
    if c.FpEkey != nil && encIV != nil {
        sessionBody["et"] = int64(32)
        sessionBody["ekey"] = c.FpEkey
        sessionBody["eiv"] = encIV
    }

    videoStream := map[string]interface{}{
        "type": int64(110),
        "streamConnectionID": videoID,
        "timestampInfo": []interface{}{
            map[string]interface{}{"name":"SubSu"},
            map[string]interface{}{"name":"BePxT"},
            map[string]interface{}{"name":"AfPxT"},
            map[string]interface{}{"name":"BefEn"},
            map[string]interface{}{"name":"EmEnc"},
        },
    }
    if encKey != nil {
        videoStream["shk"] = encKey
        videoStream["shiv"] = encIV
    }

    dbg("[RKX40] profile=%d sourceVersion=%s timingPort=%d controlID=%d videoID=%d", profile, "__SOURCE_VERSION__", timingPort, controlID, videoID)
    var receiverEventPort, dataPort int

    connectEvent := func() {
        if receiverEventPort <= 0 || eventConn != nil { return }
        addr := net.JoinHostPort(c.host, strconv.Itoa(receiverEventPort))
        ec, e := net.DialTimeout("tcp", addr, 3*time.Second)
        if e != nil {
            dbg("[RKX40] receiver event channel %s unavailable (continuing): %v", addr, e)
            return
        }
        eventConn = ec
        dbg("[RKX40] receiver event channel connected: %s", addr)
    }

    sendSession := func() error {
        resp, _, e := rkSetupRequest(c, controlURI, "rk session", sessionBody)
        if e != nil { return e }
        receiverEventPort = rkFirstPositive(receiverEventPort, rkPlistInt(resp["eventPort"]))
        connectEvent()
        return nil
    }

    sendVideo := func(full bool) error {
        body := map[string]interface{}{"streams": []interface{}{videoStream}}
        if full {
            body = rkCloneMap(sessionBody)
            body["streams"] = []interface{}{videoStream}
        }
        resp, headers, e := rkSetupRequest(c, videoURI, "rk video", body)
        if e != nil { return e }
        receiverEventPort = rkFirstPositive(receiverEventPort, rkPlistInt(resp["eventPort"]))
        connectEvent()
        dataPort = rkVideoDataPort(resp, headers)
        if dataPort == 0 { return fmt.Errorf("rkx40 video SETUP returned no data port (headers=%v response=%v)", headers, resp) }
        return nil
    }

    record := func(uri string) error {
        headers := map[string]string{"Session":sessionUUID, "Range":"npt=0-", "RTP-Info":"seq=0;rtptime=0"}
        _, _, e := c.rtspRequest("RECORD", uri, "", nil, headers)
        if e != nil { return fmt.Errorf("rkx40 RECORD: %w", e) }
        return nil
    }

    switch profile {
    case 1:
        if err := sendSession(); err != nil { return nil, err }
        if err := record(controlURI); err != nil { return nil, err }
        if err := sendVideo(false); err != nil { return nil, err }
    case 2:
        if err := sendSession(); err != nil { return nil, err }
        if err := sendVideo(false); err != nil { return nil, err }
        if err := record(controlURI); err != nil { return nil, err }
    case 3:
        if err := sendVideo(true); err != nil { return nil, err }
        if err := record(videoURI); err != nil { return nil, err }
    }

    addr := net.JoinHostPort(c.host, strconv.Itoa(dataPort))
    dataConn, err = net.DialTimeout("tcp", addr, 5*time.Second)
    if err != nil { return nil, fmt.Errorf("rkx40 connect video data port %s: %w", addr, err) }
    if tc, ok := dataConn.(*net.TCPConn); ok {
        _ = tc.SetNoDelay(true)
        _ = tc.SetWriteBuffer(64*1024)
    }
    dbg("[RKX40] video data channel connected: %s", addr)

    session := &MirrorSession{
        client: c,
        dataConn: dataConn,
        eventConn: eventConn,
        timingConn: timingConn,__CANCEL_LITERAL__
        DataPort: dataPort,
        firstFrameSent: make(chan struct{}),
        noAudio: true,
        sessionURI: controlURI,
        timestampBias: TargetLatency(),
    }
    if dw, dh := c.info.DisplaySize(); dw > 0 && dh > 0 {
        session.displayWidth, session.displayHeight = dw, dh
    }
    if err := rkConfigureCipher(c, session, cfg, encKey, encIV, videoID); err != nil { return nil, err }

    // Drain receiver chatter so its send buffer cannot block the media TCP path.
    go func(conn net.Conn) {
        buf := make([]byte,4096)
        for { if _, e := conn.Read(buf); e != nil { return } }
    }(dataConn)

    __BACKGROUND__
    setupOK = true
    return session, nil
}

func rkVideoKeyMaterial(c *AirPlayClient, cfg StreamConfig) ([]byte, []byte, error) {
    if cfg.NoEncrypt { return nil, nil, nil }
    encKey, encIV := c.fpKey, c.fpIV
    if encKey == nil {
        if c.streamKey == nil {
            if err := c.deriveStreamKeys(); err != nil { return nil,nil,fmt.Errorf("rkx40 derive stream keys: %w", err) }
        }
        encKey, encIV = c.streamKey, c.streamIV
    }
    return encKey, encIV, nil
}

// RK-X40 advertises an AppleTV3-era identity. Use the stable legacy AES-CTR
// mirroring path rather than depending on moving PairKeys/ChaCha internals.
func rkConfigureCipher(c *AirPlayClient, session *MirrorSession, cfg StreamConfig, encKey, encIV []byte, streamID int64) error {
    if encKey == nil { dbg("[RKX40] no video encryption"); return nil }
    key, iv := encKey, encIV
    if !cfg.DirectKey { key, iv = deriveVideoKeys(encKey, streamID) }
    mc, err := newMirrorCipher(key, iv)
    if err != nil { return fmt.Errorf("rkx40 video cipher: %w", err) }
    session.streamCipher = mc.EncryptFrame
    dbg("[RKX40] using AES-CTR video")
    return nil
}

func rkSetupRequest(c *AirPlayClient, uri, phase string, request map[string]interface{}) (map[string]interface{}, map[string]string, error) {
    body, err := plist.Marshal(request, plist.BinaryFormat)
    if err != nil { return nil,nil,fmt.Errorf("%s marshal: %w", phase, err) }
    dbg("[RKX40] %s SETUP -> %s (%d bytes)", phase, uri, len(body))
    respBody, headers, err := c.rtspRequest("SETUP", uri, "application/x-apple-binary-plist", body, nil)
    if err != nil { return nil,headers,fmt.Errorf("%s SETUP: %w", phase, err) }
    resp := map[string]interface{}{}
    if len(respBody) > 0 {
        if _, e := plist.Unmarshal(respBody, &resp); e != nil { dbg("[RKX40] %s non-plist response body: %v", phase, e) }
    }
    dbg("[RKX40] %s SETUP response headers=%v body=%v", phase, headers, resp)
    return resp, headers, nil
}

func rkVideoDataPort(resp map[string]interface{}, headers map[string]string) int {
    if streams, ok := resp["streams"].([]interface{}); ok {
        for _, item := range streams {
            stream, ok := item.(map[string]interface{}); if !ok || rkPlistInt(stream["type"]) != 110 { continue }
            for _, k := range []string{"dataPort","serverPort","port"} { if p:=rkPlistInt(stream[k]); p>0 { return p } }
        }
    }
    for _, k := range []string{"dataPort","serverPort","port"} { if p:=rkPlistInt(resp[k]); p>0 { return p } }
    if p:=rkTransportServerPort(headers); p>0 { return p }
    for k,v := range headers {
        if strings.EqualFold(k,"x-apple-dataport") || strings.EqualFold(k,"x-apple-data-port") || strings.EqualFold(k,"dataport") {
            if p,e:=strconv.Atoi(strings.TrimSpace(v)); e==nil && p>0 { return p }
        }
    }
    return 0
}

func rkPlistInt(v interface{}) int {
    switch n := v.(type) {
    case int: return n
    case int8: return int(n)
    case int16: return int(n)
    case int32: return int(n)
    case int64: return int(n)
    case uint: return int(n)
    case uint8: return int(n)
    case uint16: return int(n)
    case uint32: return int(n)
    case uint64: return int(n)
    case float64: return int(n)
    case string: i,_:=strconv.Atoi(strings.TrimSpace(n)); return i
    default: return 0
    }
}

func rkTransportServerPort(headers map[string]string) int {
    transport := ""
    for k,v := range headers { if strings.EqualFold(k,"Transport") { transport=v; break } }
    for _, part := range strings.Split(transport,";") {
        part=strings.TrimSpace(part)
        if !strings.HasPrefix(strings.ToLower(part),"server_port=") { continue }
        v:=strings.TrimSpace(strings.SplitN(part,"=",2)[1]); if i:=strings.IndexByte(v,'-'); i>=0 { v=v[:i] }
        if p,e:=strconv.Atoi(v); e==nil && p>0 { return p }
    }
    return 0
}
func rkCloneMap(src map[string]interface{}) map[string]interface{} { dst:=make(map[string]interface{},len(src)+1); for k,v:=range src { dst[k]=v }; return dst }
func rkFirstPositive(a,b int) int { if a>0 { return a }; return b }

func rkUUID() string {
    b:=make([]byte,16); if _,e:=rand.Read(b); e!=nil { return fmt.Sprintf("%08x-%04x-%04x-%04x-%012x",uint32(time.Now().UnixNano()),0,0,0,uint64(time.Now().UnixNano())&0xffffffffffff) }
    b[6]=(b[6]&0x0f)|0x40; b[8]=(b[8]&0x3f)|0x80
    return fmt.Sprintf("%08x-%04x-%04x-%04x-%012x", b[0:4], b[4:6], b[6:8], b[8:10], b[10:16])
}
func rkDeviceID() string {
    b:=make([]byte,6); if _,e:=rand.Read(b); e!=nil { n:=time.Now().UnixNano(); for i:=range b { b[i]=byte(n>>uint(i*8)) } }
    b[0]=(b[0]|0x02)&0xfe
    return fmt.Sprintf("%02X:%02X:%02X:%02X:%02X:%02X",b[0],b[1],b[2],b[3],b[4],b[5])
}
'''
code = code.replace('__SOURCE_VERSION__', source_version)
code = code.replace('__CANCEL_LITERAL__', cancel_literal)
code = code.replace('__BACKGROUND__', background)
out = outer / 'rkx40.go'
out.write_text(code, encoding='utf-8', newline='\n')
print('Generated', out)
print('Detected API:', {'cancel_field':has_cancel,'heartbeat':hb_sig,'dataHeartbeat':data_sig,'feedback':fb_sig,'sourceVersion':source_version})
