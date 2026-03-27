#!/bin/bash

# ==============================================================================
# KNAUGHT'S POST-INSTALL SYSTEM OPTIMIZER
# Run this AFTER setup.sh to apply system-level power & service configs.
# ==============================================================================

# --- 1. Sudo Check ---
if [[ $EUID -ne 0 ]]; then
  echo "❌ Error: This script must be run with sudo to modify system files."
  exit 1
fi

# Store the real user to handle user-level services/configs later
REAL_USER=$SUDO_USER
DOTFILES_DIR="/home/$REAL_USER/dotfiles"

echo "⚙️  Starting System Optimization..."

# --- 2. Sync Custom System Files (keyd, udev, systemd) ---
echo "📂 Syncing /etc configurations..."
sudo mkdir -p /etc/systemd/system /etc/udev/rules.d /etc/keyd

if [ -d "$DOTFILES_DIR/system/etc" ]; then
  # Copy custom service units (like enable-usb-wake)
  sudo cp -r "$DOTFILES_DIR/system/etc/systemd/system/." /etc/systemd/system/
  # Copy udev rules (50-goodix, 99-power-management, etc.)
  sudo cp -r "$DOTFILES_DIR/system/etc/udev/rules.d/." /etc/udev/rules.d/
  # Copy keyd configs
  sudo cp -r "$DOTFILES_DIR/system/etc/keyd/." /etc/keyd/

  sudo systemctl daemon-reload
  echo "✅ System files synced."
fi

# --- 3. Hydrate System Services ---
echo "🚀 Enabling System Services from services.txt..."
if [ -f "$DOTFILES_DIR/services.txt" ]; then
  while read -r service; do
    [[ "$service" =~ ^#.*$ ]] || [[ -z "$service" ]] && continue
    if systemctl list-unit-files "$service.service" &>/dev/null; then
      sudo systemctl enable --now "$service"
    fi
  done <"$DOTFILES_DIR/services.txt"
fi

# --- 4. Hydrate User Services ---
echo "👤 Enabling User Services from user_services.txt..."
if [ -f "$DOTFILES_DIR/user_services.txt" ]; then
  while read -r service; do
    [[ "$service" =~ ^#.*$ ]] || [[ -z "$service" ]] && continue
    # Run as the actual user, not root
    sudo -u "$REAL_USER" systemctl --user enable --now "$service"
  done <"$DOTFILES_DIR/user_services.txt"
fi

# --- 5. Crontab Setup ---
if [ -f "$DOTFILES_DIR/crontab_knaught" ]; then
  echo "⏰ Loading Crontab for $REAL_USER..."
  sudo -u "$REAL_USER" crontab "$DOTFILES_DIR/crontab_knaught"
fi

# --- 6. Turing (Framework 13) Hardware Optimizations ---
if grep -q "Framework" /sys/class/dmi/id/board_vendor 2>/dev/null; then
  echo "✨ Framework 13 detected. Applying 6.4W power tuning..."

  # Trigger udev for CPU auto-switching (Energy Performance Preference)
  sudo udevadm control --reload-rules && sudo udevadm trigger

  # Resolve Power Manager Conflicts
  sudo systemctl disable --now tlp auto-cpufreq 2>/dev/null || true
  sudo systemctl enable --now power-profiles-daemon

  echo ""
  echo "------------------------------------------------------------"
  echo "⚠️  MANUAL ACTION REQUIRED: GRUB POWER FLAGS"
  echo "------------------------------------------------------------"
  echo "To hit sub-7W idle, append these to GRUB_CMDLINE_LINUX_DEFAULT"
  echo "in /etc/default/grub:"
  echo ""
  echo "amdgpu.dcfeaturemask=0x8 nvme_core.default_ps_max_latency_us=5500 amdgpu.abmlevel=0 pcie_aspm=powersupersave"
  echo ""
  echo "Then run: sudo grub-mkconfig -o /boot/grub/grub.cfg"
  echo "------------------------------------------------------------"
else
  echo "💻 Generic hardware detected. Laptop-specific power tweaks skipped."
fi

echo "🏁 Post-install optimization complete. Highly recommend a REBOOT now."
