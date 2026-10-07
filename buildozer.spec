[app]
title = Freeze Screen
package.name = freezesscreen
package.domain = org.albrej
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ttf

version = 1.0

requirements = python3==3.11.8,hostpython3==3.11.8,kivy==2.3.1,pyjnius
p4a.branch = v2024.01.21

orientation = portrait
icon.filename = %(source.dir)s/Icone.png
fullscreen = 0

android.permissions = SYSTEM_ALERT_WINDOW

android.api = 34
android.minapi = 24
android.ndk = 25b
android.ndk_api = 24
android.archs = arm64-v8a,armeabi-v7a
android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 0