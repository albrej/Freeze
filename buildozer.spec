[app]
title = Freeze Screen
package.name = freezesscreen
package.domain = org.perso
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ttf,gpx,kml,kmz,xml

version = 0.2
requirements = python3==3.11.8,hostpython3==3.11.8,kivy==2.3.1,gpxpy,kivy_garden.mapview,piexif
# p4a.branch = v2024.01.21

android.permissions = READ_MEDIA_IMAGES,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,MANAGE_EXTERNAL_STORAGE,INTERNET,ACCESS_FINE_LOCATION,ACCESS_COARSE_LOCATION,ACCESS_BACKGROUND_LOCATION,CAMERA,POST_NOTIFICATIONS,FOREGROUND_SERVICE,FOREGROUND_SERVICE_LOCATION,SYSTEM_ALERT_WINDOW

android.manifest_intent_filters = intent_filters.xml

orientation = portrait
icon.filename = %(source.dir)s/Icone.png
fullscreen = 0

android.api = 34
android.minapi = 24
android.ndk = 25b
android.ndk_api = 24
# android.archs = arm64-v8a

android.archs = arm64-v8a,armeabi-v7a
android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 1