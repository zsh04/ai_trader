#!/usr/bin/env zsh
set -euo pipefail

# -------- Vars --------
RG="${RG:-ai-trader-rg}"
LOC="${LOC:-westus2}"
VNET="${VNET:-ai-trader-vnet}"

SNET_ACA_INF="${SNET_ACA_INF:-snet-aca-infra}"
SNET_PROBE="${SNET_PROBE:-snet-probe}"          # optional attach for egress test

NAT_NAME="${NAT_NAME:-aca-egress-nat}"
PIP_NAME="${PIP_NAME:-aca-egress-pip}"

echo "Using RG=$RG LOC=$LOC VNET=$VNET"
echo "Target subnets: infra=$SNET_ACA_INF (required), probe=$SNET_PROBE (optional test)"

# -------- Create static Public IP (Standard, static) --------
if ! az network public-ip show -g "$RG" -n "$PIP_NAME" >/dev/null 2>&1; then
  echo "Creating Public IP: $PIP_NAME..."
  az network public-ip create -g "$RG" -n "$PIP_NAME" -l "$LOC" \
    --sku Standard --allocation-method Static --version IPv4 >/dev/null
else
  echo "Public IP $PIP_NAME already exists."
fi
PIP_ID="$(az network public-ip show -g "$RG" -n "$PIP_NAME" --query id -o tsv)"
PIP_IP="$(az network public-ip show -g "$RG" -n "$PIP_NAME" --query ipAddress -o tsv)"

# -------- Create NAT Gateway --------
if ! az network nat gateway show -g "$RG" -n "$NAT_NAME" >/dev/null 2>&1; then
  echo "Creating NAT Gateway: $NAT_NAME..."
  az network nat gateway create -g "$RG" -n "$NAT_NAME" -l "$LOC" \
    --public-ip-addresses "$PIP_ID" --idle-timeout 10 >/dev/null
else
  echo "NAT Gateway $NAT_NAME already exists."
fi
NAT_ID="$(az network nat gateway show -g "$RG" -n "$NAT_NAME" --query id -o tsv)"

# -------- Attach NAT to ACA infra subnet --------
echo "Associating NAT with subnet $SNET_ACA_INF..."
az network vnet subnet update \
  -g "$RG" --vnet-name "$VNET" -n "$SNET_ACA_INF" \
  --nat-gateway "$NAT_ID" >/dev/null

# -------- (Optional) also attach to snet-probe for egress testing --------
if az network vnet subnet show -g "$RG" --vnet-name "$VNET" -n "$SNET_PROBE" >/dev/null 2>&1; then
  echo "Associating NAT with subnet $SNET_PROBE (for egress test)..."
  az network vnet subnet update \
    -g "$RG" --vnet-name "$VNET" -n "$SNET_PROBE" \
    --nat-gateway "$NAT_ID" >/dev/null
else
  echo "Subnet $SNET_PROBE not found; skipping optional probe association."
fi

# -------- Summaries --------
echo "\n==== Summary ===="
echo "Public Egress IP      : $PIP_IP"
echo "NAT Gateway           : $NAT_NAME"
echo "Attached to subnets   :"
az network vnet subnet list -g "$RG" --vnet-name "$VNET" \
  --query "[].{name:name, nat:id.contains(@.natGateway.id, '$NAT_NAME')}" -o table

echo "\nIf you attached NAT to $SNET_PROBE and have the ACI 'netprobe' running there,"
echo "you can confirm the egress IP is $PIP_IP with:"
echo "  az container exec -g \"$RG\" -n netprobe --exec-command 'curl -s https://ifconfig.me; echo'"