#!/usr/bin/env bash
# systemd provides singleton ownership and persistent crash recovery.
exec systemctl --user start --no-block hyprlock-recover.service
