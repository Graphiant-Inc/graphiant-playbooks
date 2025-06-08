#!/bin/bash -e

function prompt() {
    local var_name=$1
    local prompt_text=$2
    local default_value=$3
    local allow_empty=${4:-false}

    while true; do
        read -rp "$prompt_text [default: $default_value]: " input
        input="${input:-$default_value}"

        if [[ -z "$input" && "$allow_empty" == "false" ]]; then
            echo "This field cannot be empty."
        else
            eval "$var_name='$input'"
            break
        fi
    done
}

function prompt_choice() {
    local var_name=$1
    local prompt_text=$2
    local valid_options=$3
    local default_value=$4

    local input
    local IFS=','
    read -r -a options <<< "$valid_options"

    while true; do
        read -rp "$prompt_text [$valid_options]: " input
        input="${input:-$default_value}"
        for opt in "${options[@]}"; do
            if [[ "$input" == "$opt" ]]; then
                eval "$var_name='$input'"
                return
            fi
        done
        echo "Invalid option. Please choose one of: $valid_options"
    done
}

echo "=== Cloud-Init local management and ztp Configurator ==="

prompt_choice role "Enter device role" "cpe,gateway,core" "cpe"
# Map 'gateway' to 'cpe' internally
if [[ "$role" == "gateway" ]]; then
    role="cpe"
fi

prompt_choice use_token "Do you want to include an onboarding token?" "y,n" "n"
include_token="false"

if [[ "$use_token" == "y" ]]; then
    prompt token "Enter onboarding token" "your-default-token"
    include_token="true"
fi

# Local management interface (ask if they want to change the default interface name)
default_mgmt_iface="GigabitEthernet2"
prompt_choice change_mgmt_iface "Do you want to change the default local management interface from $default_mgmt_iface?" "y,n" "n"

if [[ "$change_mgmt_iface" == "y" ]]; then
    prompt local_mgmt_iface "Enter custom local management interface name" "$default_mgmt_iface"
else
    local_mgmt_iface="$default_mgmt_iface"
fi

default_wan_iface="GigabitEthernet1"
prompt_choice change_wan_iface "Do you want to change the default onboarding WAN interface from $default_wan_iface?" "y,n" "n"
if [[ "$change_wan_iface" == "y" ]]; then
    prompt wan_iface "Enter custom onboarding WAN interface name" "$default_wan_iface"
else
    wan_iface="$default_wan_iface"
fi

prompt_choice use_dhcp "Do you want to use DHCP for $wan_iface?" "y,n" "n"
wan_use_dhcp="false"

if [[ "$use_dhcp" == "y" ]]; then
    wan_use_dhcp="true"
else
    # No default values shown, and empty input not allowed
    prompt wan_ip "Enter WAN IP address (CIDR) for $wan_iface" "" false
    prompt wan_gateway "Enter WAN Gateway for $wan_iface" "" false
fi

prompt_choice use_custom_dns "Do you want to customize DNS servers?" "y,n" "n"

if [[ "$use_custom_dns" == "y" ]]; then
    read -rp "Enter primary DNS server (or press enter to skip): " dns1
    read -rp "Enter secondary DNS server (or press enter to skip): " dns2
else
    dns1="8.8.8.8"
    dns2="1.1.1.1"
fi

prompt disk "Enter output disk file name (e.g., cloud.iso, myimage.qcow2)" "cloud.iso"

format="${disk##*.}"
userdata='userdata'
metadata='metadata'
[[ "$format" == "iso" ]] && { userdata='user-data'; metadata='meta-data'; }

cat > "$userdata" <<EOF
#cloud-config
graphnos:
  role: $role
  devtest-port-enabled: true
  onboarding-auth-url: https://api.test.graphiant.io/v1/devices/oauth
  onboarding-gw: onboarding-gateway.test.graphiant.io:16000
EOF

if [[ "$include_token" == "true" ]]; then
    echo "  token: \"$token\"" >> "$userdata"
fi

cat >> "$userdata" <<EOF

graphnos-network:
  local-management-interface:
    name: "$local_mgmt_iface"
    ipv4:
      address: "192.168.1.1/24"
  wan-interfaces:
    "$wan_iface":
      ipv4:
EOF

if [[ "$wan_use_dhcp" == "true" ]]; then
    echo "        address: dhcp" >> "$userdata"
else
    echo "        address: \"$wan_ip\"" >> "$userdata"
    echo "        gateway: \"$wan_gateway\"" >> "$userdata"
fi

if [[ -n "$dns1" || -n "$dns2" ]]; then
    echo "      dns-servers: [${dns1:+\"$dns1\"}${dns1:+, }${dns2:+\"$dns2\"}]" >> "$userdata"
fi

cat >> "$userdata" <<'EOF'

  local-web-password: ""

  start-service:
EOF

echo -e "local-hostname: gnos\ninstance-id: gnos" > "$metadata"

if [[ "$disk" == "nodisk" ]]; then
    echo "No disk image created."
    exit 0
fi

echo "Generating cloud image..."
if [[ "$format" == "iso" ]]; then
    mkisofs -output "$disk" -volid cidata -joliet -rock "$userdata" "$metadata"
elif [[ "$format" == "qcow2" || "$format" == "vdi" ]]; then
    cloud-localds --disk-format "$format" "$disk" "$userdata" "$metadata"
else
    echo "Unsupported disk format: $format"
    exit 1
fi

echo "✅ Cloud-init image created: $disk"
