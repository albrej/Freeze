[app]
title = Freeze Screen
package.name = freezescreen
package.domain = org.perso
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ttf

version = 0.3
requirements = python3==3.11.8,hostpython3==3.11.8,kivy==2.3.1,pyjnius,android

# SYSTEM_ALERT_WINDOW : bouton GELER et gel par-dessus les autres applis
# FOREGROUND_SERVICE(+_SPECIAL_USE) : service de premier plan (Android 14+)
# POST_NOTIFICATIONS : notification du service = icône dans la barre d'état
android.permissions = SYSTEM_ALERT_WINDOW,FOREGROUND_SERVICE,FOREGROUND_SERVICE_SPECIAL_USE,POST_NOTIFICATIONS

# Service qui porte le bouton GELER, le gel et les coins de déblocage.
# Nom "freeze" -> classe Java org.perso.freezescreen.ServiceFreeze
# (doit correspondre à SERVICE_NAME dans main.py)
services = freeze:service.py:foreground:foregroundServiceType=specialUse

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
