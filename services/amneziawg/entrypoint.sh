#!/bin/sh
# Build a wireproxy config from the AmneziaWG config + a [Socks5] section, then run it.
# Userspace netstack — no TUN device, no privileged caps.
set -e

SRC="${AWG_CONF_FILE:-/etc/amneziawg/awg0.conf}"
WORK=/tmp/wireproxy.conf

if [ -n "${AWG_CONFIG:-}" ]; then
    printf '%s' "$AWG_CONFIG" | (base64 -d 2>/dev/null || cat) > "$WORK"
elif [ -f "$SRC" ]; then
    cp "$SRC" "$WORK"
else
    echo "[amneziawg] no config (mount awg0.conf or set AWG_CONFIG)" >&2
    exit 1
fi

# wireproxy dislikes IPv6 AllowedIPs entries it can't route in netstack; keep IPv4 default.
sed -i 's#AllowedIPs *=.*#AllowedIPs = 0.0.0.0/0#' "$WORK"

# append the SOCKS5 inbound if not present
if ! grep -qi '^\[Socks5\]' "$WORK"; then
    {
        echo ""
        echo "[Socks5]"
        echo "BindAddress = 0.0.0.0:${SOCKS_PORT:-1080}"
    } >> "$WORK"
fi

echo "[amneziawg] starting wireproxy (userspace AmneziaWG -> SOCKS5 :${SOCKS_PORT:-1080})"
exec wireproxy -c "$WORK"
