#!/bin/bash

# Dotfiles cleanup script - undoes the installation script
# WARNING: This will remove packages and configurations!

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to confirm dangerous operations
confirm() {
    while true; do
        read -p "$(echo -e "${YELLOW}$1 (y/N): ${NC}")" yn
        case $yn in
            [Yy]* ) return 0;;
            [Nn]* | "" ) return 1;;
            * ) echo "Please answer yes or no.";;
        esac
    done
}

print_warning "This script will UNDO the dotfiles installation!"
echo "It will:"
echo "  - Remove installed pacman packages"
echo "  - Remove installed AUR packages" 
echo "  - Unstow all dotfiles configurations"
echo "  - Remove the dotfiles directory"
echo "  - Optionally remove yay"
echo

if ! confirm "Are you sure you want to proceed?"; then
    print_status "Cleanup cancelled."
    exit 0
fi

# Extend sudo timeout
print_status "Extending sudo timeout..."
sudo -v
echo "Defaults timestamp_timeout=15" | sudo tee -a /etc/sudoers.d/temp-cleanup > /dev/null

# Keep sudo alive
while true; do sudo -n true; sleep 60; kill -0 "$$" || exit; done 2>/dev/null &

print_status "Starting cleanup process..."

# Step 1: Unstow dotfiles
if [ -d "$HOME/dotfiles" ]; then
    print_status "Unstowing dotfiles..."
    cd "$HOME/dotfiles"
    
    # Try bulk unstow first
    if stow -D */ 2>/dev/null; then
        print_success "All dotfiles unstowed successfully"
    else
        print_warning "Bulk unstow failed. Trying individual directories..."
        
        # Unstow each directory individually
        for dir in */; do
            if [ -d "$dir" ]; then
                dir_name=$(basename "$dir")
                print_status "Unstowing $dir_name..."
                
                if stow -D "$dir_name" 2>/dev/null; then
                    print_success "Successfully unstowed $dir_name"
                else
                    print_warning "Failed to unstow $dir_name (may not have been stowed)"
                fi
            fi
        done
    fi
else
    print_warning "Dotfiles directory not found - skipping unstow"
fi

# Step 2: Remove AUR packages
if [ -f "$HOME/dotfiles/aur-packages.txt" ] && command -v yay &> /dev/null; then
    print_status "Removing AUR packages..."
    
    # Create a list of installed AUR packages from the list
    aur_installed=()
    while IFS= read -r package || [ -n "$package" ]; do
        # Skip empty lines and comments
        [[ -z "$package" || "$package" =~ ^[[:space:]]*# ]] && continue
        
        # Clean package name (remove whitespace)
        package=$(echo "$package" | xargs)
        
        # Check if package is installed
        if yay -Qi "$package" &>/dev/null; then
            aur_installed+=("$package")
        fi
    done < "$HOME/dotfiles/aur-packages.txt"
    
    if [ ${#aur_installed[@]} -gt 0 ]; then
        print_status "Found ${#aur_installed[@]} AUR packages to remove: ${aur_installed[*]}"
        if confirm "Remove these AUR packages?"; then
            yay -Rns --noconfirm "${aur_installed[@]}"
            print_success "AUR packages removed"
        else
            print_warning "Skipping AUR package removal"
        fi
    else
        print_status "No AUR packages from the list are currently installed"
    fi
else
    print_warning "AUR packages list not found or yay not installed - skipping AUR cleanup"
fi

# Step 3: Remove pacman packages
if [ -f "$HOME/dotfiles/pacman-packages.txt" ]; then
    print_status "Removing pacman packages..."
    
    # Create a list of installed pacman packages from the list
    pacman_installed=()
    while IFS= read -r package || [ -n "$package" ]; do
        # Skip empty lines and comments
        [[ -z "$package" || "$package" =~ ^[[:space:]]*# ]] && continue
        
        # Clean package name (remove whitespace)
        package=$(echo "$package" | xargs)
        
        # Check if package is installed
        if pacman -Qi "$package" &>/dev/null; then
            pacman_installed+=("$package")
        fi
    done < "$HOME/dotfiles/pacman-packages.txt"
    
    if [ ${#pacman_installed[@]} -gt 0 ]; then
        print_status "Found ${#pacman_installed[@]} pacman packages to remove: ${pacman_installed[*]}"
        if confirm "Remove these pacman packages?"; then
            sudo pacman -Rns --noconfirm "${pacman_installed[@]}"
            print_success "Pacman packages removed"
        else
            print_warning "Skipping pacman package removal"
        fi
    else
        print_status "No pacman packages from the list are currently installed"
    fi
else
    print_warning "Pacman packages list not found - skipping pacman cleanup"
fi

# Step 4: Remove yay (optional)
if command -v yay &> /dev/null; then
    if confirm "Remove yay AUR helper?"; then
        sudo pacman -Rns --noconfirm yay
        print_success "yay removed"
    else
        print_status "Keeping yay installed"
    fi
fi

# Step 5: Remove dotfiles directory
if [ -d "$HOME/dotfiles" ]; then
    if confirm "Remove the entire dotfiles directory?"; then
        rm -rf "$HOME/dotfiles"
        print_success "Dotfiles directory removed"
    else
        print_warning "Keeping dotfiles directory"
    fi
fi

# Step 6: Restore any backup
if ls "$HOME"/dotfiles.backup.* 1> /dev/null 2>&1; then
    latest_backup=$(ls -t "$HOME"/dotfiles.backup.* | head -n1)
    if confirm "Restore backup from $latest_backup?"; then
        mv "$latest_backup" "$HOME/dotfiles"
        print_success "Backup restored"
    fi
fi

# Step 7: Clean up orphaned packages
if confirm "Remove orphaned packages (packages no longer needed)?"; then
    if pacman -Qtdq &>/dev/null; then
        sudo pacman -Rns --noconfirm $(pacman -Qtdq)
        print_success "Orphaned packages removed"
    else
        print_status "No orphaned packages found"
    fi
fi

# Clean up sudo configuration
print_status "Cleaning up temporary sudo configuration..."
sudo rm -f /etc/sudoers.d/temp-cleanup

print_success "Cleanup completed!"
print_status "Your system should now be in a similar state to before running the installation script."
print_warning "NOTE: Some configuration files in your home directory may still exist."
print_warning "You may want to restart your shell or logout/login to fully reset your environment."
