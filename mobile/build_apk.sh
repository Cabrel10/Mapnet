#!/usr/bin/env bash
# =============================================================================
# MAPNET MOBILE — Script de compilation de l'APK Android (release)
# Cible : Android 10+ (API 29-34), Flutter 3.24, JDK 17
# =============================================================================
set -euo pipefail

export PATH="$PATH:/opt/flutter/bin:/opt/android-sdk/platform-tools:/opt/android-sdk/cmdline-tools/latest/bin"
export JAVA_HOME="$(dirname "$(dirname "$(readlink -f "$(which java)")")")"
export ANDROID_SDK_ROOT=/opt/android-sdk
export ANDROID_HOME=/opt/android-sdk

PROJECT_DIR="/home/ubuntu/webapp/MORNINGSTAR/MAPNET/mobile"
cd "$PROJECT_DIR"

echo "==============================================================="
echo " MAPNET APK BUILD"
echo " Flutter : $(flutter --version | head -1)"
echo " Java    : $(java -version 2>&1 | head -1)"
echo " Date    : $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "==============================================================="

echo "[1/3] flutter pub get..."
flutter pub get

echo "[2/3] flutter build apk --release (universel + split-per-abi)..."
flutter build apk --release
flutter build apk --release --split-per-abi

echo "[3/3] Artefacts générés :"
find build/app/outputs/flutter-apk -name "*.apk" -exec ls -lh {} \;

echo "==============================================================="
echo " APK principal : $PROJECT_DIR/build/app/outputs/flutter-apk/app-release.apk"
echo "==============================================================="
