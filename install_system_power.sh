#!/bin/bash

# --- 1. Hardware Automation (udev) ---
echo "⚡ Deploying udev Power Rules..."
# This copies 50-goodix, 50-usb, and your new 99-power-management rules
sudo cp ~/dotfiles/system/etc/udev/rules.d/*.rules /etc/udev/rules.d/

# Reload the kernel event system
sudo udevadm control --reload-rules
sudo udevadm trigger
echo "✅ udev rules active (CPU will now auto-switch on Battery)."

# --- 2. Manual GRUB Instructions ---
echo ""
echo "------------------------------------------------------------"
echo "⚠️  MANUAL ACTION REQUIRED: Update GRUB Power Parameters"
echo "------------------------------------------------------------"
echo "To finish the 'Turing' optimization, follow these steps:"
echo ""
echo "1. Open your GRUB config:"
echo "   sudo nvim /etc/default/grub"
echo ""
echo "2. Find the 'GRUB_CMDLINE_LINUX_DEFAULT' line."
echo "   Replace it with the template from your dotfiles:"
echo "   ~/dotfiles/system/etc/default/grub.template"
echo ""
echo "3. IMPORTANT: Replace 'PUT_LUKS_ID_HERE' with the real UUID"
echo "   of your encrypted drive (check your original file for reference)."
echo ""
echo "4. Save and exit, then run the update command:"
echo "   sudo grub-mkconfig -o /boot/grub/grub.cfg"
echo "------------------------------------------------------------"
