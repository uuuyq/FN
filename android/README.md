# FNote Android

Android 8.0+ WebView client for https://uuuf.online/.

## Build

Install JDK 17, Android SDK Platform 35 and Build Tools 35.0.0. Set JAVA_HOME and ANDROID_HOME to their installation directories. Run `./build.ps1` from PowerShell. The Gradle wrapper downloads Gradle 8.11.1. Android Studio can also open this directory.

The signed APK is `app/build/outputs/apk/release/app-release.apk`. First build generates a private release key and password in `../runtime/android-signing/`. Back up both files securely. Future builds must use the same key and a higher versionCode for installation over existing releases. Never commit signing files.

Install the APK on the phone after allowing installation from the chosen file app. Sign in using the existing website account.

## Device acceptance

Verify login survives force-stop and restart, logout, training edits and calendar, catalogs, streamed AI replies, keyboard layout, gesture and three-button navigation, dialog dismissal with Back, external links, airplane mode and retry. During an AI reply, lock/unlock and switch networks, then use the existing recovery control if streaming stops. Verify the recorded operation executes once. Browser and app have independent login sessions.

The app uses system WebView. Keep Android System WebView updated. Website releases appear on subsequent loads. Native shell changes require a new APK.
