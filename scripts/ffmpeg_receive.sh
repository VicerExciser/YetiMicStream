#!/bin/bash
if [[ -f "audio.sdp" ]]; then
	ffplay -protocol_whitelist file,rtp,udp -i audio.sdp
else
	ffplay -protocol_whitelist file,rtp,udp -i rtp://234.5.5.5:1234
fi
