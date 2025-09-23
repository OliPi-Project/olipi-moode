#!/bin/bash
set -e

DRY_RUN=false
if [ "$1" == "--dry-run" ]; then
    DRY_RUN=true
    echo "=== DRY-RUN mode enabled: no actual deletion will be performed ==="
fi

run_cmd() {
    if $DRY_RUN; then
        echo "[DRY-RUN] $*"
    else
        eval "$@"
    fi
}

echo "=== OliPi-Moode Uninstallation Script ==="

# --- Detect user ---
if [ -n "$SUDO_USER" ]; then
    REAL_USER="$SUDO_USER"
else
    REAL_USER="$USER"
fi
USER_HOME=$(eval echo "~$REAL_USER")
echo "Detected user: $REAL_USER"

# --- List of services ---
SERVICES=("olipi-ui-playing" "olipi-ui-browser" "olipi-ui-queue" "olipi-ui-off" "olipi-starting-wait")

PROJECT_DIR=""
VENV_DIR=""
FOUND_SERVICES=()

# --- 1. Parse services to detect paths ---
for svc in "${SERVICES[@]}"; do
    SERVICE_FILE="/etc/systemd/system/${svc}.service"
    if [ -f "$SERVICE_FILE" ]; then
        FOUND_SERVICES+=("$SERVICE_FILE")
        line=$(grep -m1 "^ExecStart=" "$SERVICE_FILE" | sed 's/^ExecStart=//')
        if [ -n "$line" ]; then
            EXE_PATH=$(echo "$line" | awk '{print $1}')
            SCRIPT_PATH=$(echo "$line" | awk '{print $2}')
            if [ -n "$EXE_PATH" ] && [ -n "$SCRIPT_PATH" ]; then
                if [ -z "$VENV_DIR" ]; then
                    VENV_DIR=$(dirname "$(dirname "$EXE_PATH")")
                fi
                if [ -z "$PROJECT_DIR" ]; then
                    PROJECT_DIR=$(dirname "$SCRIPT_PATH")
                fi
            fi
        fi
    fi
done

# --- Summary of detected items ---
echo "--------------------------"
echo "Detected project directory: ${PROJECT_DIR:-NOT FOUND}"
echo "Detected virtualenv directory: ${VENV_DIR:-NOT FOUND}"
echo "Detected services:"
if [ ${#FOUND_SERVICES[@]} -eq 0 ]; then
    echo "  None of the expected services found."
else
    for svc in "${FOUND_SERVICES[@]}"; do
        echo "  $svc"
    done
fi

# --- Detect what actually exists ---
MISSING_ELEMENTS=()
if [ -z "$PROJECT_DIR" ] || [ ! -d "$PROJECT_DIR" ]; then
    MISSING_ELEMENTS+=("project directory")
fi
if [ -z "$VENV_DIR" ] || [ ! -d "$VENV_DIR" ]; then
    MISSING_ELEMENTS+=("virtual environment")
fi
if [ ${#FOUND_SERVICES[@]} -eq 0 ]; then
    MISSING_ELEMENTS+=("all expected services")
fi

echo "--------------------------"
if [ ${#MISSING_ELEMENTS[@]} -gt 0 ]; then
    echo "WARNING: Some expected elements are already missing: ${MISSING_ELEMENTS[*]}"
    echo "The script will attempt to clean whatever remains."
else
    echo "All expected elements detected. Ready to proceed."
fi

# --- Confirmation prompt ---
echo ""
PROMPT_MSG="Do you want to continue and remove the detected elements? [y/N] "
read -p "$PROMPT_MSG" CONFIRM
case "$CONFIRM" in
    [yY]|[yY][eE][sS]) echo "Proceeding with uninstallation..." ;;
    *) echo "Aborted by user."; exit 0 ;;
esac

# --- 3. Stop and disable services ---
if [ ${#FOUND_SERVICES[@]} -gt 0 ]; then
    echo ">> Stopping and disabling OliPi-Moode services"
    for svc in "${SERVICES[@]}"; do
        if systemctl list-unit-files | grep -q "${svc}.service"; then
            run_cmd "sudo systemctl stop $svc || true"
            run_cmd "sudo systemctl disable $svc || true"
            run_cmd "sudo rm -f /etc/systemd/system/${svc}.service"
        fi
    done
    run_cmd "sudo systemctl daemon-reload"
    run_cmd "sudo systemctl reset-failed"
fi

# --- 4. Clean ~/.profile ---
PROFILE_FILE="$USER_HOME/.profile"
if [ -f "$PROFILE_FILE" ]; then
    echo ">> Cleaning $PROFILE_FILE"
    run_cmd "sudo -u $REAL_USER sed -i '/install_lirc_remote.py/d' $PROFILE_FILE"
fi

# --- 5. Remove Python virtual environment ---
if [ -n "$VENV_DIR" ] && [ -d "$VENV_DIR" ]; then
    echo ">> Removing Python virtual environment"
    run_cmd "sudo rm -rf $VENV_DIR"
fi

# --- 6. Clean Moode ready-script (if present) ---
READY_SCRIPT="/var/local/www/commandw/ready-script.sh"
if [ -f "$READY_SCRIPT" ]; then
    echo ">> Cleaning Moode ready-script"
    run_cmd "sudo sed -i '/# Start the OliPi service/,/systemctl start olipi-ui-playing/d' $READY_SCRIPT"
fi

# --- 7. Clean /boot/firmware/config.txt ---
CONFIG_FILE="/boot/firmware/config.txt"
if [ -f "$CONFIG_FILE" ]; then
    echo ">> Removing Olipi section from config.txt"
    run_cmd "sudo sed -i '/^# --- Olipi-moode START ---/,/^# --- Olipi-moode END ---/d' $CONFIG_FILE"
    # Clean multiple empty lines
    run_cmd "sudo sed -i '/^$/N;/^\n$/D' $CONFIG_FILE"
fi

# --- 8. Remove old backups ---
echo ">> Cleaning old backups"
for path in "/boot/firmware" "/etc/lirc"; do
    if [ -d "$path" ]; then
        backups=( $(ls -t "$path" 2>/dev/null | grep '\.olipi-' || true) )
        if [ ${#backups[@]} -gt 1 ]; then
            echo "   - Removing old backups in $path"
            for file in "${backups[@]:1}"; do
                run_cmd "sudo rm -rf $path/$file"
            done
        fi
    fi
done
if [ -f "/var/local/www/commandw/ready-script.sh.bak" ]; then
    echo "   - Removing ready-script.sh.bak"
    run_cmd "sudo rm -f /var/local/www/commandw/ready-script.sh.bak"
fi

# --- 9. Remove main project directory ---
if [ -n "$PROJECT_DIR" ] && [ -d "$PROJECT_DIR" ]; then
    echo ">> Removing OliPi-Moode directory"
    run_cmd "sudo rm -rf $PROJECT_DIR"
fi

echo ""
echo "=== Uninstallation complete ==="
echo "You need to reboot your Raspberry!"
if $DRY_RUN; then
    echo ">> (no modifications were applied, because --dry-run was active)"
fi
