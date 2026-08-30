package airplay

// RK-X40L compatibility path.
//
// The receiver advertises itself as AppleTV3,2 but differs from both a genuine
// Apple TV 3 and the UxPlay-style third-party receivers supported by the stock
// doubletake path. In testing, pairing + FairPlay succeed, the first legacy
// media SETUP succeeds, then the receiver closes the RTSP connection on the
// second (video) SETUP. Captures from genuine AppleTV3-era senders use a
// different order: session SETUP -> RECORD -> compact video SETUP.
//
// This file adds that order without changing the normal AirPlay path.

import (
	"context"
	"fmt"
	"net"
	"strconv"
	"strings"
	"time"

	"golang.org/x/crypto/chacha20poly1305"
	"howett.net/plist"
)

// SetupMirrorRKX40 negotiates video without creating an audio stream.
// profile selects a bounded compatibility strategy:
//
//	1 = session SETUP -> RECORD -> compact video SETUP (preferred)
//	2 = session SETUP -> compact video SETUP -> RECORD
//	3 = combined session+video SETUP -> RECORD
func (c *AirPlayClient) SetupMirrorRKX40(ctx context.Context, cfg StreamConfig, profile int) (*MirrorSession, error) {
	if profile < 1 || profile > 3 {
		profile = 1
	}
	return c.setupMirrorRKX40(ctx, cfg, profile)
}

func (c *AirPlayClient) setupMirrorRKX40(ctx context.Context, cfg StreamConfig, profile int) (*MirrorSession, error) {
	sessionUUID := generateUUID()
	deviceID := uuidToMAC(c.sessionID)
	senderName := pairingClientName()

	// This receiver behaves like an older AirPlay screen-mirroring sink even
	// though it accepts the newer pairing/FairPlay preparation done by the app.
	// Use NTP, not the modern PTP control session.
	timingConns, err := allocateConsecutiveUDPPorts(1)
	if err != nil {
		return nil, fmt.Errorf("rkx40 allocate timing port: %w", err)
	}
	timingConn := timingConns[0]
	timingPort := timingConn.LocalAddr().(*net.UDPAddr).Port

	sessionCtx, cancelSession := context.WithCancel(ctx)
	setupOK := false
	var dataConn net.Conn
	var eventConn net.Conn
	defer func() {
		if setupOK {
			return
		}
		cancelSession()
		_ = timingConn.Close()
		if dataConn != nil {
			_ = dataConn.Close()
		}
		if eventConn != nil {
			_ = eventConn.Close()
		}
	}()
	go ntpTimingResponder(sessionCtx, timingConn)

	// Keep control and video URIs separate, matching real Apple senders.
	controlID := int64(time.Now().UnixNano() & 0x7FFFFFFFFFFFFFFF)
	videoID := int64((time.Now().UnixNano() + 1) & 0x7FFFFFFFFFFFFFFF)
	controlURI := fmt.Sprintf("rtsp://%s:%d/%d", c.host, c.port, controlID)
	videoURI := fmt.Sprintf("rtsp://%s:%d/%d", c.host, c.port, videoID)

	encKey, encIV, err := rkVideoKeyMaterial(c, cfg)
	if err != nil {
		return nil, err
	}

	sessionBody := map[string]interface{}{
		"deviceID":                 deviceID,
		"macAddress":               deviceID,
		"sessionUUID":              sessionUUID,
		"sourceVersion":            legacyAirPlaySourceVersion,
		"isScreenMirroringSession": true,
		"timingProtocol":           timingProtocolNTP,
		"timingPort":               int64(timingPort),
		"osBuildVersion":           "13F69",
		"model":                    "iPhone",
		"name":                     senderName,
	}
	// FairPlay's wrapped key belongs at the session root on this generation of
	// receiver. FpEkey is the wrapped value; fpKey is the local stream key.
	if c.FpEkey != nil && c.fpIV != nil {
		sessionBody["et"] = int64(32)
		sessionBody["ekey"] = c.FpEkey
		sessionBody["eiv"] = c.fpIV
	}

	videoStream := map[string]interface{}{
		"type":               int64(110),
		"streamConnectionID": videoID,
	}
	if encKey != nil {
		videoStream["shk"] = encKey
		videoStream["shiv"] = encIV
	}

	dbg("[RKX40] profile=%d timingPort=%d controlID=%d videoID=%d", profile, timingPort, controlID, videoID)

	var receiverEventPort int
	var dataPort int

	sendSessionOnly := func() error {
		resp, _, err := rkSetupRequest(c, controlURI, "rk session", sessionBody)
		if err != nil {
			return err
		}
		receiverEventPort = rkFirstPositive(receiverEventPort, rkPlistInt(resp["eventPort"]))
		// Apple senders establish the reverse event TCP channel as soon as the
		// session SETUP advertises it. Some embedded receivers stall later RTSP
		// requests until this callback path exists, so connect before RECORD.
		if receiverEventPort > 0 && eventConn == nil {
			ec, eventErr := c.connectEventChannel(sessionCtx, receiverEventPort)
			if eventErr != nil {
				return fmt.Errorf("rkx40 event channel %d: %w", receiverEventPort, eventErr)
			}
			eventConn = ec
			dbg("[RKX40] event channel connected before RECORD: %d", receiverEventPort)
		}
		return nil
	}

	sendVideoCompact := func(fullSession bool) error {
		var body map[string]interface{}
		if fullSession {
			body = rkCloneMap(sessionBody)
			body["streams"] = []interface{}{videoStream}
		} else {
			body = map[string]interface{}{"streams": []interface{}{videoStream}}
		}
		resp, headers, err := rkSetupRequest(c, videoURI, "rk video", body)
		if err != nil {
			return err
		}
		receiverEventPort = rkFirstPositive(receiverEventPort, rkPlistInt(resp["eventPort"]))
		dataPort = rkVideoDataPort(resp, headers)
		if dataPort == 0 {
			return fmt.Errorf("rkx40 video SETUP returned no data port (headers=%v response=%v)", headers, resp)
		}
		return nil
	}

	record := func(uri string) error {
		headers := map[string]string{
			"Session":  sessionUUID,
			"Range":    "npt=0-",
			"RTP-Info": "seq=0;rtptime=0",
		}
		_, _, err := c.rtspRequest("RECORD", uri, "", nil, headers)
		if err != nil {
			return fmt.Errorf("rkx40 RECORD: %w", err)
		}
		return nil
	}

	switch profile {
	case 1:
		// Capture-derived AppleTV3-era order.
		if err := sendSessionOnly(); err != nil {
			return nil, err
		}
		if err := record(controlURI); err != nil {
			return nil, err
		}
		if err := sendVideoCompact(false); err != nil {
			return nil, err
		}
	case 2:
		if err := sendSessionOnly(); err != nil {
			return nil, err
		}
		if err := sendVideoCompact(false); err != nil {
			return nil, err
		}
		if err := record(controlURI); err != nil {
			return nil, err
		}
	case 3:
		if err := sendVideoCompact(true); err != nil {
			return nil, err
		}
		if err := record(videoURI); err != nil {
			return nil, err
		}
	}

	dataAddr := net.JoinHostPort(c.host, strconv.Itoa(dataPort))
	dataConn, err = net.DialTimeout("tcp", dataAddr, 5*time.Second)
	if err != nil {
		return nil, fmt.Errorf("rkx40 connect video data port %s: %w", dataAddr, err)
	}
	if tc, ok := dataConn.(*net.TCPConn); ok {
		_ = tc.SetNoDelay(true)
		_ = tc.SetWriteBuffer(64 * 1024)
	}
	dbg("[RKX40] video data channel connected: %s", dataAddr)

	// Event traffic is optional on cheap third-party receivers. Try it only if a
	// port was actually advertised, and do not fail an otherwise valid video
	// session if the event channel is absent/broken.
	if receiverEventPort > 0 && eventConn == nil {
		if ec, eventErr := c.connectEventChannel(sessionCtx, receiverEventPort); eventErr != nil {
			dbg("[RKX40] event channel %d unavailable (continuing): %v", receiverEventPort, eventErr)
		} else {
			eventConn = ec
		}
	}

	session := &MirrorSession{
		client:         c,
		dataConn:       dataConn,
		eventConn:      eventConn,
		timingConn:     timingConn,
		cancel:         cancelSession,
		DataPort:       dataPort,
		firstFrameSent: make(chan struct{}),
		noAudio:        true,
		sessionURI:     controlURI,
		timestampBias:  TargetLatency(),
	}
	if dw, dh := c.info.DisplaySize(); dw > 0 && dh > 0 {
		session.displayWidth = dw
		session.displayHeight = dh
	}
	if err := rkConfigureCipher(c, session, cfg, encKey, encIV, videoID); err != nil {
		return nil, err
	}

	// Drain receiver->sender data channel traffic so a chatty receiver cannot
	// fill its TCP send buffer and stall mirroring.
	go func(conn net.Conn) {
		buf := make([]byte, 4096)
		for {
			if _, err := conn.Read(buf); err != nil {
				return
			}
		}
	}(dataConn)

	session.startWorker(func() { session.dataHeartbeatLoop(sessionCtx) })
	session.startWorker(func() { session.feedbackLoop(sessionCtx) })
	setupOK = true
	return session, nil
}

func rkVideoKeyMaterial(c *AirPlayClient, cfg StreamConfig) ([]byte, []byte, error) {
	if cfg.NoEncrypt {
		return nil, nil, nil
	}
	encKey := c.fpKey
	encIV := c.fpIV
	if encKey == nil {
		if c.streamKey == nil {
			if err := c.deriveStreamKeys(); err != nil {
				return nil, nil, fmt.Errorf("rkx40 derive stream keys: %w", err)
			}
		}
		encKey = c.streamKey
		encIV = c.streamIV
	}
	return encKey, encIV, nil
}

func rkConfigureCipher(c *AirPlayClient, session *MirrorSession, cfg StreamConfig, encKey, encIV []byte, streamID int64) error {
	if encKey == nil {
		dbg("[RKX40] no video encryption")
		return nil
	}

	if c.encrypted && ((c.PairKeys != nil && len(c.PairKeys.SharedSecret) > 0) || c.fpAesKey != nil) {
		ikm := c.fpAesKey
		if c.PairKeys != nil && len(c.PairKeys.SharedSecret) > 0 {
			ikm = c.PairKeys.SharedSecret
		}
		key, err := deriveChaChaKey(ikm, streamID)
		if err != nil {
			return fmt.Errorf("rkx40 derive chacha key: %w", err)
		}
		aead, err := chacha20poly1305.New(key)
		if err != nil {
			return fmt.Errorf("rkx40 chacha20poly1305: %w", err)
		}
		session.chachaCipher = aead
		dbg("[RKX40] using ChaCha20-Poly1305 video")
		return nil
	}

	var key, iv []byte
	if cfg.DirectKey {
		key, iv = encKey, encIV
	} else {
		key, iv = deriveVideoKeys(encKey, streamID)
	}
	mc, err := newMirrorCipher(key, iv)
	if err != nil {
		return fmt.Errorf("rkx40 video cipher: %w", err)
	}
	session.streamCipher = mc.EncryptFrame
	dbg("[RKX40] using AES-CTR video")
	return nil
}

func rkSetupRequest(c *AirPlayClient, uri, phase string, request map[string]interface{}) (map[string]interface{}, map[string]string, error) {
	body, err := plist.Marshal(request, plist.BinaryFormat)
	if err != nil {
		return nil, nil, fmt.Errorf("%s marshal: %w", phase, err)
	}
	dbg("[RKX40] %s SETUP -> %s (%d bytes)", phase, uri, len(body))
	respBody, headers, err := c.rtspRequest("SETUP", uri, "application/x-apple-binary-plist", body, nil)
	if err != nil {
		return nil, headers, fmt.Errorf("%s SETUP: %w", phase, err)
	}
	resp := map[string]interface{}{}
	if len(respBody) > 0 {
		if _, err := plist.Unmarshal(respBody, &resp); err != nil {
			// Some inexpensive receivers return a successful SETUP with a non-plist
			// or empty body but put the negotiated port in Transport headers. Preserve
			// the headers rather than rejecting the whole session.
			dbg("[RKX40] %s response body is not plist (%v); using headers", phase, err)
		}
	}
	dbg("[RKX40] %s SETUP response headers=%v body=%v", phase, headers, resp)
	return resp, headers, nil
}

func rkVideoDataPort(resp map[string]interface{}, headers map[string]string) int {
	if streams, ok := resp["streams"].([]interface{}); ok {
		for _, item := range streams {
			stream, ok := item.(map[string]interface{})
			if !ok || rkPlistInt(stream["type"]) != 110 {
				continue
			}
			for _, k := range []string{"dataPort", "serverPort", "port"} {
				if p := rkPlistInt(stream[k]); p > 0 {
					return p
				}
			}
		}
	}
	for _, k := range []string{"dataPort", "serverPort", "port"} {
		if p := rkPlistInt(resp[k]); p > 0 {
			return p
		}
	}
	if p := rkTransportServerPort(headers); p > 0 {
		return p
	}
	for _, k := range []string{"x-apple-dataport", "x-apple-data-port", "dataport"} {
		if v := strings.TrimSpace(headers[k]); v != "" {
			if p, err := strconv.Atoi(v); err == nil && p > 0 {
				return p
			}
		}
	}
	return 0
}

func rkPlistInt(v interface{}) int {
	switch n := v.(type) {
	case int:
		return n
	case int8:
		return int(n)
	case int16:
		return int(n)
	case int32:
		return int(n)
	case int64:
		return int(n)
	case uint:
		return int(n)
	case uint8:
		return int(n)
	case uint16:
		return int(n)
	case uint32:
		return int(n)
	case uint64:
		return int(n)
	case float64:
		return int(n)
	case string:
		i, _ := strconv.Atoi(strings.TrimSpace(n))
		return i
	default:
		return 0
	}
}

func rkTransportServerPort(headers map[string]string) int {
	var transport string
	for k, v := range headers {
		if strings.EqualFold(k, "Transport") {
			transport = v
			break
		}
	}
	for _, part := range strings.Split(transport, ";") {
		part = strings.TrimSpace(part)
		if !strings.HasPrefix(strings.ToLower(part), "server_port=") {
			continue
		}
		v := strings.TrimSpace(strings.SplitN(part, "=", 2)[1])
		if dash := strings.IndexByte(v, '-'); dash >= 0 {
			v = v[:dash]
		}
		p, _ := strconv.Atoi(v)
		if p > 0 {
			return p
		}
	}
	return 0
}

func rkCloneMap(src map[string]interface{}) map[string]interface{} {
	dst := make(map[string]interface{}, len(src)+1)
	for k, v := range src {
		dst[k] = v
	}
	return dst
}

func rkFirstPositive(a, b int) int {
	if a > 0 {
		return a
	}
	return b
}
