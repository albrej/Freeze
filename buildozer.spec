[app]
title = Freeze Screen
package.name = freezesscreen
package.domain = org.albrej
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ttf

version = 1.0

requirements = python3,kivy==2.3.1,pyjnius

orientation = all

fullscreen = 0

android.permissions =

android.api = 34
android.minapi = 24
android.ndk = 25b
android.ndk_api = 24
android.archs = arm64-v8a,armeabi-v7a
android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 0