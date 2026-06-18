#!/bin/bash

# --- Configuration ---
# Using $HOME makes this safe for any user/machine
VAULT="$HOME/.local/share/Cryptomator/mnt/Vault"
TEMP_DIR="takeout_temp"

# --- Safety Checks ---

# 1. Check if the Vault is actually mounted
if [ ! -d "$VAULT" ] || [ -z "$(ls -A "$VAULT")" ]; then
  echo "ERROR: Vault is not mounted at $VAULT"
  echo "Please unlock your Cryptomator vault and try again."
  exit 1
fi

# 2. Check if there are actually any zip files to process
shopt -s nullglob
zips=(*takeout*.zip)
if [ ${#zips[@]} -eq 0 ]; then
  echo "No takeout zip files found in the current directory."
  exit 0
fi

# --- Execution ---

# 3. Create temporary directory
echo "--- Step 1: Creating temp directory ---"
mkdir -p "$TEMP_DIR"

# 4. Unzip all takeout zips into the temp directory
echo "--- Step 2: Extracting zip files ---"
for zip in "${zips[@]}"; do
  unzip -o "$zip" -d "$TEMP_DIR/"
done

# 5. Find and move all MP4s using the CameraID/Date structure
echo "--- Step 3: Organizing and moving files to Vault ---"

# Using -iname to catch .mp4 and .MP4
find "$TEMP_DIR" -type f -iname "*.mp4" | while read -r filepath; do

  # Extract Camera ID (4th level up from the file in Nest structure)
  # filepath: takeout_temp/Takeout/Nest/camera/.../CAM_ID/video/YYYY-MM-DD/FILE.mp4
  camera_id=$(echo "$filepath" | awk -F'/' '{print $(NF-3)}')

  # Get filename for date parsing
  filename=$(basename "$filepath")

  # Extract date parts (YYYY_MM_DD_...)
  year=$(echo "$filename" | cut -d'_' -f1)
  month=$(echo "$filename" | cut -d'_' -f2)
  day=$(echo "$filename" | cut -d'_' -f3)

  # Define final destination: VAULT/CameraID/MM-DD-YYYY
  target_dir="$VAULT/$camera_id/${month}-${day}-${year}"

  # Create the directory structure in the vault
  mkdir -p "$target_dir"

  # Move the file (-v verbose, -n no-overwrite)
  mv -v -n "$filepath" "$target_dir/"
done

echo "--- Process Complete ---"
echo "Monitor sync with: watch -n 1 'rclone rc vfs/stats --rc-no-auth'"
