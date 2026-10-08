[app]
title = Freeze Screen
package.name = freezescreen
package.domain = org.perso
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ttf

version = 0.2
requirements = python3==3.11.8,hostpython3==3.11.8,kivy==2.3.1,pyjnius,android

android.permissions = SYSTEM_ALERT_WINDOW

orientation = portrait
fullscreen = 0
icon.filename = %(source.dir)s/Icone.png

android.api = 34
android.minapi = 24
android.ndk = 25b
android.ndk_api = 24
android.archs = arm64-v8a
android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 1