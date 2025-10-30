#!/bin/bash

# Get selected network
selected=$(nmcli -t -f SSID,SECURITY device wifi list | \
    sed 's/\\:/COLON/g' | \
    awk -F: '{if($2=="") printf "🔓 %s\n", $1; else printf "🔒 %s\n", $1}' | \
    wofi --dmenu -p "Select WiFi Network")

if [ -z "$selected" ]; then
    exit 0
fi

# Extract SSID (remove the lock emoji and space)
ssid=$(echo "$selected" | sed 's/^🔓 //;s/^🔒 //')

# Check if network requires password
security=$(nmcli -t -f SSID,SECURITY device wifi list | grep "^$ssid:" | cut -d: -f2)

if [ -n "$security" ] && [ "$security" != "--" ]; then
    # Network is secured, prompt for password
    while true; do
        password=$(echo "" | wofi --dmenu --password -p "🔑 Password for $ssid" --prompt "🔑 Password: ")
        
        if [ -z "$password" ]; then
            # User cancelled
            exit 0
        fi
        
        # Try to connect
        result=$(nmcli device wifi connect "$ssid" password "$password" 2>&1)
        
        if echo "$result" | grep -q "successfully activated"; then
            notify-send "WiFi Connected" "Successfully connected to $ssid" -i network-wireless
            break
        else
            # Show error and ask again
            echo "❌ Wrong password. Try again?" | wofi --dmenu -p "Connection failed" > /dev/null
            if [ $? -ne 0 ]; then
                exit 1
            fi
        fi
    done
else
    # Open network
    result=$(nmcli device wifi connect "$ssid" 2>&1)
    if echo "$result" | grep -q "successfully activated"; then
        notify-send "WiFi Connected" "Successfully connected to $ssid" -i network-wireless
    else
        notify-send "WiFi Error" "Failed to connect to $ssid" -i network-error
    fi
fi
