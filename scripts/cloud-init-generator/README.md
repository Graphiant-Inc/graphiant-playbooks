# Cloud-Init Interactive Generator

This Bash script is an interactive tool for generating a valid `cloud-init` configuration (`user-data` and `meta-data`) and outputting it in a supported image format such as `cloud.iso`.

The script is designed to onboard network devices using parameters required by Graphiant's onboarding system and is compatible with both DHCP and static IP environments.

---

## 📦 What It Does

- Prompts the user step-by-step to enter relevant onboarding and networking configuration values.
- Supports default or custom local management and WAN interfaces.
- Allows use of DHCP or static IPs for the WAN interface.
- Can optionally include an onboarding token.
- Outputs a cloud-init ISO.

---

## 🛠️ Requirements

- Bash shell (Linux/macOS)
- `mkisofs` installed and available in your system path

---

## ▶️ How to Run

- install required packages
    - Linux/macOS: run "brew install cdrtools"

- start cloud init generation script
chmod +x generate-cloud-init.sh
./generate-cloud-init.sh

## ▶️ Example Run
```commandline
./generate-cloud-init.sh 

=== Cloud-Init local management and ztp Configurator ===
Enter onboarding environment [prod,test, default: prod]: test
Enter device role [cpe,gateway,core, default: cpe]: core
Do you want to include an onboarding token? [y,n, default: n]: y
Enter onboarding token [default: ]: hjfdhjklfdhjklfdahjklfda
Do you want to change the default local management interface from GigabitEthernet2? [y,n, default: n]: y
Enter custom local management interface name [default: GigabitEthernet2]: GigabitEthernet2/0/0
Do you want to change the default onboarding WAN interface from GigabitEthernet1? [y,n, default: n]: 1
Invalid option. Please choose one of: y,n
Do you want to change the default onboarding WAN interface from GigabitEthernet1? [y,n, default: n]: y
Enter custom onboarding WAN interface name [default: GigabitEthernet1]: GigabitEthernet1/0/0
Do you want to use DHCP for GigabitEthernet1/0/0? [y,n, default: n]: n
Enter WAN IP address (CIDR) for GigabitEthernet1/0/0 [default: ]: 123.123.123.2/24
Enter WAN Gateway for GigabitEthernet1/0/0 [default: ]: 123.123.123.1
Do you want to customize DNS servers? [y,n, default: n]: 
Enter local web server password [default: ]: 1234qwerasdf
Enter custom hostname [default: ]: 
Enter output disk file name (e.g., cloud.iso, myimage.qcow2) [default: cloud.iso]: ccccloud.iso
Generating cloud image...
Total translation table size: 0
Total rockridge attributes bytes: 363
Total directory bytes: 0
Path table size(bytes): 10
Max brk space used 0
183 extents written (0 MB)
✅ Cloud-init image created: ccccloud.iso
```
