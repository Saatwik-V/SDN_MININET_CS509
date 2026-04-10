#!/usr/bin/env bash
# SDN_MININET_ORANGE - run.sh
# CS509 - Software Defined Networking
#
# Starts the RYU controller and the Mininet Orange topology.
# Usage:
#   ./run.sh [learning|firewall]
#
# Arguments:
#   learning   Use the L2 learning switch controller (default).
#   firewall   Use the firewall/ACL controller.
#
# Requirements:
#   sudo apt-get install -y mininet
#   pip install ryu

set -euo pipefail

MODE="${1:-learning}"
CONTROLLER_PORT=6633

case "$MODE" in
  learning)
    CONTROLLER_APP="orange_controller.py"
    ;;
  firewall)
    CONTROLLER_APP="firewall_controller.py"
    ;;
  *)
    echo "Unknown mode '$MODE'. Use 'learning' or 'firewall'." >&2
    exit 1
    ;;
esac

echo "=== SDN_MININET_ORANGE ==="
echo "Mode       : $MODE"
echo "Controller : $CONTROLLER_APP"
echo "OFP port   : $CONTROLLER_PORT"
echo ""

# Start RYU controller in the background
echo "[*] Starting RYU controller..."
ryu-manager "$CONTROLLER_APP" \
  --ofp-tcp-listen-port "$CONTROLLER_PORT" \
  --verbose &
RYU_PID=$!

# Give RYU a moment to bind its port
sleep 2

echo "[*] Starting Mininet topology..."
sudo python3 orange_topo.py

# Clean up controller when Mininet exits
echo "[*] Stopping RYU controller (PID $RYU_PID)..."
kill "$RYU_PID" 2>/dev/null || true

echo "[*] Done."
