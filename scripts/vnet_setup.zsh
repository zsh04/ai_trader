#!/usr/bin/env zsh
set -e
set -u
set -o pipefail

# ---------- INPUTS ----------
RG="ai-trader-rg"                                # existing resource group
LOC="$(az group show -n "$RG" --query location -o tsv)"  # reuse RG location

VNET="ai-trader-vnet"
VNET_CIDR="10.242.0.0/16"

SNET_WEBAPPS="snet-webapps-int"   # App Service VNet Integration (outbound only)
SNET_WEBAPPS_CIDR="10.242.1.0/24"

SNET_ACA_INFRA="snet-aca-infra"   # Container Apps Environment
SNET_ACA_INFRA_CIDR="10.242.2.0/23"

SNET_ACA_APPS="snet-aca-apps"     # Optional separation for workloads
SNET_ACA_APPS_CIDR="10.242.4.0/23"

SNET_PE="snet-pe"                  # Private Endpoints only
SNET_PE_CIDR="10.242.10.0/24"

typeset -a PDNS_ZONES
PDNS_ZONES=(
  "privatelink.blob.core.windows.net"
  "privatelink.servicebus.windows.net"
  "privatelink.postgres.database.azure.com"
  "privatelink.vaultcore.azure.net"
)

echo "Using RG=$RG LOC=$LOC"

# ---------- NETWORK FABRIC ----------
# VNet (idempotent)
if ! az network vnet show -g "$RG" -n "$VNET" &>/dev/null; then
  echo "Creating VNet $VNET..."
  az network vnet create \
    -g "$RG" -n "$VNET" \
    --location "$LOC" \
    --address-prefixes "$VNET_CIDR" \
    >/dev/null
else
  echo "VNet $VNET exists; ensuring address space includes $VNET_CIDR"
  az network vnet update -g "$RG" -n "$VNET" --address-prefixes "$VNET_CIDR" >/dev/null
fi

ensure_subnet() {
  local name="$1" cidr="$2" delegation="${3:-}" disable_pe_np="${4:-false}"

  if ! az network vnet subnet show -g "$RG" --vnet-name "$VNET" -n "$name" &>/dev/null; then
    echo "Creating subnet $name ($cidr)..."
    az network vnet subnet create \
      -g "$RG" --vnet-name "$VNET" -n "$name" \
      --address-prefixes "$cidr" \
      >/dev/null
  else
    echo "Subnet $name exists; updating…"
  fi

  if [[ -n "$delegation" ]]; then
    az network vnet subnet update \
      -g "$RG" --vnet-name "$VNET" -n "$name" \
      --delegations "$delegation" \
      >/dev/null
  fi

  if [[ "$disable_pe_np" == "true" ]]; then
    az network vnet subnet update \
      -g "$RG" --vnet-name "$VNET" -n "$name" \
      --disable-private-endpoint-network-policies true \
      >/dev/null
  fi
}

# Subnets + delegations
ensure_subnet "$SNET_WEBAPPS"   "$SNET_WEBAPPS_CIDR"   "Microsoft.Web/serverFarms"      "false"
ensure_subnet "$SNET_ACA_INFRA" "$SNET_ACA_INFRA_CIDR" "Microsoft.App/environments"     "false"
ensure_subnet "$SNET_ACA_APPS"  "$SNET_ACA_APPS_CIDR"  "Microsoft.App/environments"     "false"
ensure_subnet "$SNET_PE"        "$SNET_PE_CIDR"        ""                                "true"

# ---------- PRIVATE DNS ----------
VNET_ID="$(az network vnet show -g "$RG" -n "$VNET" --query id -o tsv)"

for zone in "${PDNS_ZONES[@]}"; do
  if ! az network private-dns zone show -g "$RG" -n "$zone" &>/dev/null; then
    echo "Creating Private DNS zone: $zone"
    az network private-dns zone create -g "$RG" -n "$zone" >/dev/null
  else
    echo "Private DNS zone $zone already exists"
  fi

  link_name="${zone//./-}-link"
  if ! az network private-dns link vnet show -g "$RG" -z "$zone" -n "$link_name" &>/dev/null; then
    echo "Linking VNet to zone $zone"
    az network private-dns link vnet create \
      -g "$RG" -z "$zone" -n "$link_name" \
      --virtual-network "$VNET_ID" \
      --registration-enabled false \
      >/dev/null
  else
    echo "VNet already linked to $zone"
  fi
done

# ---------- OUTPUTS ----------
echo
echo "==== Summary ===="
az network vnet show -g "$RG" -n "$VNET" --query "{name:name,location:location,addressSpace:addressSpace.addressPrefixes}" -o jsonc
echo
az network vnet subnet list -g "$RG" --vnet-name "$VNET" \
  --query "[].{name:name,prefix:addressPrefix,delegations:delegations[].serviceName,peNP:privateEndpointNetworkPolicies}" -o table
echo
for zone in "${PDNS_ZONES[@]}"; do
  echo "Zone: $zone"
  az network private-dns link vnet list -g "$RG" -z "$zone" --query "[].{link:name,vnet:id}" -o table
done