[app]
title = Freeze Screen
package.name = freezesscreen
package.domain = org.albrej
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ttf

version = 1.0

requirements = python3==3.12.10,kivy==2.3.0

orientation = portrait

fullscreen = 0

android.archs = arm64-v8a,armeabi-v7a

# Permissions : aucune permission Android spécifique nécessaire pour l'épinglage
android.permissions =

android.api = 34
android.minapi = 21
android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 1