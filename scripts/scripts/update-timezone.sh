#!/bin/bash
# Try to update timezone
if sudo tzupdate; then
    # Restart waybar if update succeeds
    killall -SIGUSR2 waybar
else
    # Log error if it fails
    echo "Timezone update failed: $(date)" >> ~/.tz-error.log
fi
