#!/usr/bin/env bash
set -euo pipefail
[[ $EUID == 0 && $# == 1 ]] || exit 2
repo=$1
# Minimal Arch installations do not create this directory.
install -d -m 755 /var/backups
backup=$(mktemp -d /var/backups/dotfiles.XXXXXXXX)
chmod 700 "$backup"
copy() {
  local source=$1 target=$2
  if [[ -e $target || -L $target ]]; then
    mkdir -p "$backup$(dirname "$target")"
    cp -a "$target" "$backup$target"
    # install follows symlinks; remove the old link only after backing it up.
    [[ ! -L $target ]] || rm "$target"
  fi
  install -D -m "$3" "$source" "$target"
}
for name in automatic-timezoned geoclue-agent; do
  copy "$repo/system/etc/systemd/system/$name.service" "/etc/systemd/system/$name.service" 644
done
for source in "$repo"/root-etc/etc/keyd/*.conf; do copy "$source" "/etc/keyd/$(basename "$source")" 644; done
copy "$repo/system/etc/udev/rules.d/99-power-management.rules" /etc/udev/rules.d/99-power-management.rules 644
copy "$repo/system/usr/local/bin/opencode-disable-alt-menu" /usr/local/bin/opencode-disable-alt-menu 755
copy "$repo/system/etc/pacman.d/hooks/opencode-disable-alt-menu.hook" /etc/pacman.d/hooks/opencode-disable-alt-menu.hook 644
if [[ -f /usr/lib/opencode-desktop/main.mjs ]]; then /usr/local/bin/opencode-disable-alt-menu; fi
if grep -qi Framework /sys/class/dmi/id/sys_vendor; then
  for name in charge-threshold powertop; do
    copy "$repo/system/etc/systemd/system/$name.service" "/etc/systemd/system/$name.service" 644
  done
  systemctl daemon-reload
  systemctl enable charge-threshold.service powertop.service
fi
systemctl daemon-reload
for unit in tlp.service auto-cpufreq.service; do
  if systemctl is-enabled "$unit" >/dev/null 2>&1; then systemctl disable --now "$unit"; fi
done
while read -r unit; do
  [[ -n $unit && $unit != \#* ]] || continue
  systemctl enable "$unit"
done < "$repo/bootstrap/system-services.txt"
# Only one display manager owns tty2. Activation is deferred to reboot.
for unit in sddm.service ly.service; do
  if systemctl is-enabled "$unit" >/dev/null 2>&1; then systemctl disable "$unit"; fi
done
systemctl enable ly@tty2.service
systemctl mask getty@tty2.service
systemctl set-default graphical.target
udevadm control --reload-rules
echo "System file backups: $backup"
