#!/usr/bin/env bash
# Builds YAHT from source with PyInstaller and installs it for the
# current user only (no sudo needed): app files under
# ~/.local/share/yaht, a `yaht` launcher on ~/.local/bin, and an
# application-menu entry. If a previous install is found, asks before
# touching it.
set -e
cd "$(dirname "$0")/.."

APP_NAME="YAHT"
INSTALL_DIR="$HOME/.local/share/yaht"
BIN_LINK="$HOME/.local/bin/yaht"
DESKTOP_FILE="$HOME/.local/share/applications/yaht.desktop"

if [ -d "$INSTALL_DIR" ]; then
    echo "An existing $APP_NAME installation was found at $INSTALL_DIR."
    read -r -p "Uninstall it and continue installing? [y/N] " reply
    case "$reply" in
        [yY]*)
            echo "Removing previous installation..."
            rm -rf "$INSTALL_DIR"
            rm -f "$BIN_LINK"
            rm -f "$DESKTOP_FILE"
            ;;
        *)
            echo "Aborting install. Nothing was changed."
            exit 1
            ;;
    esac
fi

echo "Setting up build environment..."
if [ ! -d .venv ]; then
    python3 -m venv .venv
fi
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -r requirements-build.txt -q

echo "Building $APP_NAME..."
rm -rf build dist
.venv/bin/pyinstaller packaging/yaht.spec --noconfirm

echo "Installing to $INSTALL_DIR..."
mkdir -p "$(dirname "$INSTALL_DIR")"
cp -r dist/YAHT "$INSTALL_DIR"
rm -rf build dist

mkdir -p "$(dirname "$BIN_LINK")"
cat > "$BIN_LINK" <<LAUNCHER
#!/usr/bin/env bash
exec "$INSTALL_DIR/YAHT" "\$@"
LAUNCHER
chmod +x "$BIN_LINK"

mkdir -p "$(dirname "$DESKTOP_FILE")"
cat > "$DESKTOP_FILE" <<DESKTOP
[Desktop Entry]
Type=Application
Name=$APP_NAME
Comment=Yet Another Hdf5 Tool -- HDF5 file viewer
Exec=$INSTALL_DIR/YAHT %f
Terminal=false
Categories=Utility;Science;
DESKTOP

# A standalone uninstaller inside the install dir -- the source repo
# (and this script) don't need to still be around to uninstall later.
cat > "$INSTALL_DIR/uninstall.sh" <<UNINSTALLER
#!/usr/bin/env bash
rm -rf "$INSTALL_DIR"
rm -f "$BIN_LINK"
rm -f "$DESKTOP_FILE"
echo "$APP_NAME uninstalled."
UNINSTALLER
chmod +x "$INSTALL_DIR/uninstall.sh"

echo
echo "$APP_NAME installed."
echo "Launch it from your application menu, or run: yaht"
echo "(if 'yaht' isn't found, ~/.local/bin may not be on PATH yet -- restart your terminal or log back in)"
echo "To uninstall later: $INSTALL_DIR/uninstall.sh"
