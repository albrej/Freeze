[app]
title = Freeze Screen
package.name = freezesscreen
package.domain = org.albrej
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ttf
android.modules_blacklist = grp

version = 1.0

requirements = python3==3.11.8,hostpython3==3.11.8,kivy==2.3.1

orientation = portrait

fullscreen = 0

android.archs = arm64-v8a,armeabi-v7a

# Permissions : aucune permission Android spécifique nécessaire pour l'épinglage
android.permissions =

android.api = 34
android.minapi = 24
android.ndk = 25b
android.ndk_api = 24
android.archs = arm64-v8a


[buildozer]
log_level = 2
warn_on_root = 1