#!/bin/bash

# Dotfiles installation script for Arch Linux
set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
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

# Function to display ASCII art
show_ascii_art() {
    echo -e "${BLUE}"
    cat << "EOF"
    ╔═══════════════════════════════════════════════════════════════╗
    ║                                                               ║
    ║        ██╗  ██╗██████╗                                        ║
    ║        ██║ ██╔╝╚════██╗                                       ║
    ║        █████╔╝  █████╔╝                                       ║
    ║        ██╔═██╗ ██╔═══╝                                        ║
    ║        ██║  ██╗███████╗                                       ║
    ║        ╚═╝  ╚═╝╚══════╝                                       ║
    ║                                                               ║
    ║    ██████╗  ██████╗ ████████╗███████╗██╗██╗     ███████╗███████╗
    ║    ██╔══██╗██╔═══██╗╚══██╔══╝██╔════╝██║██║     ██╔════╝██╔════╝
    ║    ██║  ██║██║   ██║   ██║   █████╗  ██║██║     █████╗  ███████╗
    ║    ██║  ██║██║   ██║   ██║   ██╔══╝  ██║██║     ██╔══╝  ╚════██║
    ║    ██████╔╝╚██████╔╝   ██║   ██║     ██║███████╗███████╗███████║
    ║    ╚═════╝  ╚═════╝    ╚═╝   ╚═╝     ╚═╝╚══════╝╚══════╝╚══════╝
    ║                                                               ║
    ║                 🐧 arch linux setup script 🐧                 ║
    ║                                                               ║
    ║           install your dotfiles and packages                  ║
    ║              (press Ctrl+C to cancel anytime)                 ║
    ║                                                               ║
    ╚═══════════════════════════════════════════════════════════════╝
EOF
    echo -e "${NC}"
}

# Function to show countdown
show_countdown() {
    echo
    print_status "Starting in:"
    for i in {5..1}; do
        echo -ne "${YELLOW}   $i ${NC}"
        sleep 1
        echo -ne "\r   "
    done
    echo -e "${GREEN}🚀 Let's go!${NC}"
    echo
}

# Show ASCII art and countdown
clear
show_ascii_art
show_countdown

# Ensure we're NOT running as root
if [ "$EUID" -eq 0 ]; then
    print_error "This script should not be run as root! Run as your regular user."
    exit 1
fi

# Step 1: Add current user to sudoers with NOPASSWD temporarily
print_status "Setting up temporary passwordless sudo..."
echo "$(whoami) ALL=(ALL) NOPASSWD: ALL" | sudo tee /etc/sudoers.d/temp-nopasswd

# Get the actual user info before we start
ACTUAL_USER="$(whoami)"
ACTUAL_HOME="$HOME"

print_status "Running as user: $ACTUAL_USER"
print_status "Home directory: $ACTUAL_HOME"

# Step 2: Install git first (required for cloning dotfiles)
print_status "Installing git..."
if sudo pacman -S --needed --noconfirm git; then
    print_success "Git installed successfully"
else
    print_error "Failed to install git"
    sudo rm /etc/sudoers.d/temp-nopasswd
    exit 1
fi

# Installation summary variables
PACMAN_SUCCESS=false
PACMAN_COUNT=0
AUR_SUCCESS=false
AUR_COUNT=0
YAY_INSTALLED=false
STOW_SUCCESS=false
STOW_FAILED=()
SOFTWARE_DIR_SUCCESS=false
LY_SERVICE_SUCCESS=false

# Function to print installation summary
print_summary() {
    echo
    echo "=================================="
    echo -e "${BLUE}INSTALLATION SUMMARY${NC}"
    echo "=================================="
    
    # Git clone status
    if [ -d "$ACTUAL_HOME/dotfiles/.git" ]; then
        print_success "✅ Dotfiles repository cloned"
    else
        print_error "❌ Dotfiles repository failed"
    fi
    
    # Pacman packages
    if [ "$PACMAN_SUCCESS" = true ]; then
        print_success "✅ Pacman packages installed ($PACMAN_COUNT packages)"
    else
        print_error "❌ Pacman packages failed"
    fi
    
    # Yay installation
    if [ "$YAY_INSTALLED" = true ]; then
        print_success "✅ yay AUR helper installed"
    fi
    
    # AUR packages
    if [ "$AUR_SUCCESS" = true ]; then
        print_success "✅ AUR packages installed ($AUR_COUNT packages)"
    else
        print_error "❌ AUR packages failed"
    fi
    
    # Stow status
    if [ "$STOW_SUCCESS" = true ]; then
        print_success "✅ All dotfiles stowed successfully"
    else
        if [ ${#STOW_FAILED[@]} -eq 0 ]; then
            print_success "✅ Dotfiles stowed (some individual directories)"
        else
            print_warning "⚠️ Some stow operations failed: ${STOW_FAILED[*]}"
        fi
    fi
    
    # Software directory
    if [ "$SOFTWARE_DIR_SUCCESS" = true ]; then
        print_success "✅ Software directory created"
    else
        print_error "❌ Software directory creation failed"
    fi
    
    # Ly service
    if [ "$LY_SERVICE_SUCCESS" = true ]; then
        print_success "✅ Ly display manager enabled"
    else
        print_error "❌ Ly display manager enable failed"
    fi
    
    echo "=================================="
    
    if [ "$PACMAN_SUCCESS" = true ] && [ "$AUR_SUCCESS" = true ]; then
        print_success "Installation completed successfully! 🎉"
        echo -e "${GREEN}You may need to restart your shell or source your configuration files.${NC}"
    else
        print_warning "Installation completed with some issues. Check the summary above."
    fi
}

# Start installation process
print_status "Starting dotfiles installation..."

# Step 3: Clone dotfiles repo
print_status "Cloning dotfiles repository..."
if [ -d "$ACTUAL_HOME/dotfiles" ]; then
    print_warning "Dotfiles directory already exists. Backing it up..."
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    BACKUP_NAME="dotfiles.backup.$TIMESTAMP"
    mv "$ACTUAL_HOME/dotfiles" "$ACTUAL_HOME/$BACKUP_NAME"
fi

git clone https://github.com/kdn251/dotfiles "$ACTUAL_HOME/dotfiles"
print_success "Dotfiles repository cloned successfully"

# Step 4: Install pacman packages
print_status "Installing pacman packages..."
cd "$ACTUAL_HOME/dotfiles"

if [ -f "pacman-packages.txt" ]; then
    # Trim whitespace from package list
    sed -i 's/[[:space:]]*$//' pacman-packages.txt
    
    # Count packages for display purposes
    TEMP_COUNT=$(grep -v '^#' pacman-packages.txt | grep -v '^$' | wc -l)
    PACMAN_COUNT="$TEMP_COUNT"
    print_status "Found $PACMAN_COUNT packages to install"
    
    # Handle known conflicts: iptables vs iptables-nft
    if grep -q "iptables" pacman-packages.txt && grep -q "iptables-nft" pacman-packages.txt; then
        print_warning "Detected iptables conflict. Removing iptables-nft to avoid conflicts..."
        sudo pacman -Rdd --noconfirm iptables-nft 2>/dev/null || true
    elif grep -q "iptables-nft" pacman-packages.txt; then
        print_warning "Detected iptables-nft. Removing iptables to avoid conflicts..."
        sudo pacman -Rdd --noconfirm iptables 2>/dev/null || true
    fi
    
    # Install packages with --noconfirm for automatic yes
    if sudo pacman -S --needed --noconfirm --overwrite "*" - < pacman-packages.txt; then
        PACMAN_SUCCESS=true
        print_success "Pacman packages installed successfully"
    else
        print_warning "Some pacman packages failed, trying individual installation..."
        PACMAN_SUCCESS=false
        
        # Try installing packages individually
        while IFS= read -r package || [ -n "$package" ]; do
            # Skip empty lines and comments
            if [[ -z "$package" ]] || [[ "$package" =~ ^[[:space:]]*# ]]; then
                continue
            fi
            
            # Clean package name
            package=$(echo "$package" | xargs)
            
            print_status "Installing $package..."
            if sudo pacman -S --needed --noconfirm --overwrite "*" "$package"; then
                print_success "✅ $package installed"
            else
                print_error "❌ Failed to install $package"
            fi
        done < pacman-packages.txt
        
        # Check if we got most packages installed
        INSTALLED_COUNT=$(pacman -Qq | wc -l)
        if [ "$INSTALLED_COUNT" -gt 100 ]; then
            PACMAN_SUCCESS=true
            print_success "Individual package installation completed"
        fi
    fi
else
    print_error "pacman-packages.txt not found in dotfiles directory"
    # Clean up and exit
    sudo rm /etc/sudoers.d/temp-nopasswd
    exit 1
fi

# Step 5: Install AUR packages with yay
print_status "Installing AUR packages with yay..."

# Check if yay is installed
if ! command -v yay &> /dev/null; then
    print_warning "yay not found. Installing yay first..."
    
    # Install yay as the actual user (makepkg cannot run as root)
    TEMP_DIR="/tmp/yay-install-$$"
    mkdir -p "$TEMP_DIR"
    cd "$TEMP_DIR"
    git clone https://aur.archlinux.org/yay.git .
    makepkg -si --noconfirm --needed
    cd "$ACTUAL_HOME/dotfiles"
    rm -rf "$TEMP_DIR"
    
    YAY_INSTALLED=true
    print_success "yay installed successfully"
fi

if [ -f "aur-packages.txt" ]; then
    # Trim whitespace from package list
    sed -i 's/[[:space:]]*$//' aur-packages.txt
    
    # Count packages for display purposes
    TEMP_COUNT=$(grep -v '^#' aur-packages.txt | grep -v '^$' | wc -l)
    AUR_COUNT="$TEMP_COUNT"
    print_status "Found $AUR_COUNT AUR packages to install"
    
    # Configure yay for non-interactive operation
    yay --save --answerclean All --answerdiff None --removemake
    
    # Install AUR packages
    if yay -S --needed --noconfirm - < aur-packages.txt; then
        AUR_SUCCESS=true
        print_success "AUR packages installed successfully"
    else
        print_error "Some AUR packages failed to install"
        AUR_SUCCESS=false
    fi
else
    print_error "aur-packages.txt not found in dotfiles directory"
    # Clean up and exit
    sudo rm /etc/sudoers.d/temp-nopasswd
    exit 1
fi

# Step 6: Stow directories
print_status "Setting up dotfiles with stow..."

# Check if stow is installed
if ! command -v stow &> /dev/null; then
    print_warning "stow not found. Installing stow..."
    sudo pacman -S --noconfirm stow
fi

# Remove conflicting config files before stowing
print_status "Removing conflicting config files..."
rm -f "$ACTUAL_HOME/.config/hypr/hyprland.conf"

# Try to stow all directories
if stow */ 2>/dev/null; then
    STOW_SUCCESS=true
    print_success "All dotfiles stowed successfully"
else
    print_warning "Bulk stow failed. Attempting to stow directories individually..."
    
    # Stow each directory individually
    for dir in */; do
        if [ -d "$dir" ]; then
            DIR_BASENAME=$(basename "$dir")
            print_status "Stowing $DIR_BASENAME..."
            
            if stow "$DIR_BASENAME" 2>/dev/null; then
                print_success "Successfully stowed $DIR_BASENAME"
            else
                print_warning "Failed to stow $DIR_BASENAME - you may need to handle this manually"
                STOW_FAILED+=("$DIR_BASENAME")
            fi
        fi
    done
fi

# Step 7: Create software directory
print_status "Creating software directory..."
if mkdir -p "$ACTUAL_HOME/software"; then
    SOFTWARE_DIR_SUCCESS=true
    print_success "Software directory created at $ACTUAL_HOME/software"
else
    SOFTWARE_DIR_SUCCESS=false
    print_error "Failed to create software directory"
fi

# Step 8: Enable ly display manager service
print_status "Enabling ly display manager service..."
if sudo systemctl enable ly; then
    LY_SERVICE_SUCCESS=true
    print_success "Ly display manager service enabled"
else
    LY_SERVICE_SUCCESS=false
    print_error "Failed to enable ly display manager service"
fi

# Print installation summary
print_summary

# Clean up - remove the temporary sudoers rule
print_status "Cleaning up temporary sudo permissions..."
sudo rm /etc/sudoers.d/temp-nopasswd
print_success "Setup complete!"
