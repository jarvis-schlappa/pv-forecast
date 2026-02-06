#!/bin/bash
# PV-Forecast One-Liner Installer
# Usage: curl -sSL https://raw.githubusercontent.com/jarvis-schlappa/pv-forecast/main/install.sh | bash
#
# This script:
# 1. Checks dependencies (git, python3, pip)
# 2. Clones the repository to ~/pv-forecast
# 3. Creates a virtual environment
# 4. Installs pvforecast
# 5. Creates a wrapper script in ~/.local/bin
# 6. Runs the setup wizard

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Installation paths
INSTALL_DIR="$HOME/pv-forecast"
WRAPPER_DIR="$HOME/.local/bin"
WRAPPER_PATH="$WRAPPER_DIR/pvforecast"
REPO_URL="https://github.com/jarvis-schlappa/pv-forecast.git"

# Minimum Python version
MIN_PYTHON_MAJOR=3
MIN_PYTHON_MINOR=9

#######################################
# Print functions
#######################################

print_header() {
    echo ""
    echo -e "${CYAN}🔆 PV-Forecast Installer${NC}"
    echo "════════════════════════════════════"
    echo ""
}

print_step() {
    echo -e "${CYAN}$1${NC}"
}

print_success() {
    echo -e " ${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e " ${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e " ${RED}✗${NC} $1"
}

print_info() {
    echo -e "   $1"
}

#######################################
# Dependency checks
#######################################

check_command() {
    if command -v "$1" &> /dev/null; then
        return 0
    else
        return 1
    fi
}

get_python_version() {
    python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')" 2>/dev/null
}

check_python_version() {
    local version
    version=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
    local major minor
    major=$(echo "$version" | cut -d. -f1)
    minor=$(echo "$version" | cut -d. -f2)
    
    if [[ "$major" -gt "$MIN_PYTHON_MAJOR" ]] || \
       [[ "$major" -eq "$MIN_PYTHON_MAJOR" && "$minor" -ge "$MIN_PYTHON_MINOR" ]]; then
        return 0
    else
        return 1
    fi
}

check_dependencies() {
    print_step "Prüfe Abhängigkeiten..."
    local missing=0
    
    # Check git
    if check_command git; then
        local git_version
        git_version=$(git --version | awk '{print $3}')
        print_success "git ($git_version)"
    else
        print_error "git (nicht gefunden)"
        missing=1
    fi
    
    # Check python3
    if check_command python3; then
        local py_version
        py_version=$(get_python_version)
        if check_python_version; then
            print_success "python3 ($py_version)"
        else
            print_error "python3 ($py_version) - Version $MIN_PYTHON_MAJOR.$MIN_PYTHON_MINOR+ benötigt"
            missing=1
        fi
    else
        print_error "python3 (nicht gefunden)"
        missing=1
    fi
    
    # Check pip
    if python3 -m pip --version &> /dev/null; then
        local pip_version
        pip_version=$(python3 -m pip --version | awk '{print $2}')
        print_success "pip ($pip_version)"
    else
        print_error "pip (nicht gefunden)"
        missing=1
    fi
    
    echo ""
    
    if [[ "$missing" -eq 1 ]]; then
        echo -e "${RED}❌ Fehlende Abhängigkeiten!${NC}"
        echo ""
        echo "Installation:"
        echo ""
        
        # Detect OS and show instructions
        if [[ "$OSTYPE" == "darwin"* ]]; then
            echo "  macOS (Homebrew):"
            echo "    brew install python@3.11 git"
        elif [[ -f /etc/debian_version ]]; then
            echo "  Ubuntu/Debian:"
            echo "    sudo apt update && sudo apt install python3.11 python3-pip git"
        elif [[ -f /etc/fedora-release ]]; then
            echo "  Fedora:"
            echo "    sudo dnf install python3.11 python3-pip git"
        elif [[ -f /etc/arch-release ]]; then
            echo "  Arch Linux:"
            echo "    sudo pacman -S python python-pip git"
        else
            echo "  Installiere python3 (>= 3.9), pip und git für dein System."
        fi
        
        echo ""
        echo "Dann erneut ausführen:"
        echo "  curl -sSL https://raw.githubusercontent.com/jarvis-schlappa/pv-forecast/main/install.sh | bash"
        echo ""
        exit 1
    fi
}

#######################################
# Installation
#######################################

check_existing_installation() {
    if [[ -d "$INSTALL_DIR" ]]; then
        print_warning "Verzeichnis $INSTALL_DIR existiert bereits."
        echo ""
        read -p "   Löschen und neu installieren? [j/N]: " -r response
        if [[ "$response" =~ ^[jJyY]$ ]]; then
            print_info "Lösche $INSTALL_DIR..."
            rm -rf "$INSTALL_DIR"
        else
            echo ""
            echo "Installation abgebrochen."
            echo "Lösche das Verzeichnis manuell oder wähle einen anderen Pfad."
            exit 1
        fi
    fi
}

clone_repository() {
    print_step "Klone Repository..."
    if git clone --quiet "$REPO_URL" "$INSTALL_DIR" 2>/dev/null; then
        print_success "$INSTALL_DIR"
    else
        print_error "Klonen fehlgeschlagen"
        exit 1
    fi
}

create_venv() {
    print_step "Erstelle Virtual Environment..."
    cd "$INSTALL_DIR"
    if python3 -m venv .venv 2>/dev/null; then
        print_success ".venv"
    else
        print_error "venv-Erstellung fehlgeschlagen"
        exit 1
    fi
}

install_package() {
    print_step "Installiere pvforecast..."
    cd "$INSTALL_DIR"
    
    # Upgrade pip first (required for PEP 517 editable installs)
    .venv/bin/pip install --quiet --upgrade pip 2>/dev/null
    
    # Install package
    if .venv/bin/pip install --quiet -e . 2>/dev/null; then
        print_success "pip install"
    else
        print_error "Installation fehlgeschlagen"
        exit 1
    fi
}

create_wrapper() {
    print_step "Erstelle Wrapper-Script..."
    
    # Create directory if needed
    mkdir -p "$WRAPPER_DIR"
    
    # Create wrapper script
    cat > "$WRAPPER_PATH" << 'WRAPPER'
#!/bin/bash
# pvforecast wrapper - runs pvforecast from venv without activation
exec "$HOME/pv-forecast/.venv/bin/python" -m pvforecast "$@"
WRAPPER
    
    chmod +x "$WRAPPER_PATH"
    print_success "$WRAPPER_PATH"
}

check_path() {
    # Check if ~/.local/bin is in PATH
    if [[ ":$PATH:" != *":$WRAPPER_DIR:"* ]]; then
        print_warning "$WRAPPER_DIR ist nicht im PATH"
        echo ""
        
        # Detect shell and config file
        local shell_config=""
        local shell_name=""
        
        if [[ -n "$ZSH_VERSION" ]] || [[ "$SHELL" == *"zsh"* ]]; then
            shell_config="$HOME/.zshrc"
            shell_name="zsh"
        elif [[ -n "$BASH_VERSION" ]] || [[ "$SHELL" == *"bash"* ]]; then
            shell_config="$HOME/.bashrc"
            shell_name="bash"
        fi
        
        if [[ -n "$shell_config" ]]; then
            echo "   Füge zu $shell_config hinzu..."
            echo "" >> "$shell_config"
            echo "# Added by pvforecast installer" >> "$shell_config"
            echo "export PATH=\"\$HOME/.local/bin:\$PATH\"" >> "$shell_config"
            print_success "PATH erweitert"
            echo ""
            print_warning "Terminal neu öffnen oder ausführen:"
            echo "         source $shell_config"
        else
            print_warning "Füge manuell zu deiner Shell-Config hinzu:"
            echo "         export PATH=\"\$HOME/.local/bin:\$PATH\""
        fi
        echo ""
    fi
}

run_setup() {
    echo "────────────────────────────────────"
    print_step "Starte Einrichtung..."
    echo ""
    
    # Run setup wizard with stdin from terminal (not from pipe)
    # This is required when running via: curl ... | bash
    # The wizard shows its own completion message, so we don't need print_completion
    if "$INSTALL_DIR/.venv/bin/python" -m pvforecast setup < /dev/tty; then
        # Wizard erfolgreich, zeigt eigene Meldung
        :
    else
        echo ""
        echo -e "${YELLOW}⚠️  Setup nicht abgeschlossen.${NC}"
        echo "   Später nachholen: pvforecast setup"
    fi
}

#######################################
# Main
#######################################

main() {
    print_header
    check_dependencies
    check_existing_installation
    clone_repository
    create_venv
    install_package
    create_wrapper
    check_path
    run_setup
}

# Run main
main
