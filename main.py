import os
import sys
import time

# --- Contournement du crash hwuiTask/mutex sur Android 14/15 ---
# Doit être exécuté AVANT tout import Kivy.
IS_ANDROID = hasattr(sys, "getandroidapiversion") or sys.platform == "android"

if IS_ANDROID:
    os.environ["KIVY_GL_BACKEND"] = "gles2"
    os.environ["KIVY_METRICS_DENSITY"] = "2"

from kivy.config import Config
if IS_ANDROID:
    Config.set("graphics", "multisamples", "0")

# --- Imports Kivy ---
from kivy.app import App
from kivy.clock import Clock, mainthread
from kivy.uix.widget import Widget
from kivy.utils import platform

if platform == 'android':
    from jnius import autoclass
    from android.permissions import request_permissions, check_permission

    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    Settings = autoclass('android.provider.Settings')
    Context = autoclass('android.content.Context')
    Uri = autoclass('android.net.Uri')
    Intent = autoclass('android.content.Intent')
    SDK_INT = autoclass('android.os.Build$VERSION').SDK_INT
else:
    PythonActivity = None
    SDK_INT = 0

# Nom du service déclaré dans buildozer.spec (services = freeze:service.py:...).
SERVICE_NAME = 'Freeze'

# True : la fenêtre disparaît aussi de la liste des applis récentes.
HIDE_FROM_RECENTS = True

NOTIF_PERMISSION = 'android.permission.POST_NOTIFICATIONS'
START_DEBOUNCE = 5.0  # secondes minimum entre deux démarrages du service


class ServiceController:
    """Pilote le service Android (démarrage, état), la permission et la fenêtre."""

    def __init__(self):
        self.activity = PythonActivity.mActivity
        self.package = str(self.activity.getPackageName())
        self.service_class_name = f"{self.package}.Service{SERVICE_NAME}"

    # ---------- Permission ----------
    def has_permission(self):
        return Settings.canDrawOverlays(self.activity)

    def ask_permission(self):
        intent = Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                        Uri.parse("package:" + self.package))
        self.activity.startActivity(intent)

    def notifications_ok(self):
        if SDK_INT < 33:
            return True
        try:
            return bool(check_permission(NOTIF_PERMISSION))
        except Exception as e:
            print(f"[Freeze] Etat des notifications illisible : {e}")
            return True

    # ---------- Service ----------
    def is_running(self):
        try:
            am = self.activity.getSystemService(Context.ACTIVITY_SERVICE)
            for info in am.getRunningServices(100):
                if str(info.service.getClassName()) == self.service_class_name:
                    return True
        except Exception as e:
            print(f"[Freeze] Etat du service illisible : {e}")
        return False

    def start(self):
        try:
            autoclass(self.service_class_name).start(self.activity, '')
            return True
        except Exception as e:
            print(f"[Freeze] Démarrage du service impossible : {e}")
            return False

    # ---------- Fenêtre ----------
    def exclude_from_recents(self, excluded):
        try:
            am = self.activity.getSystemService(Context.ACTIVITY_SERVICE)
            tasks = am.getAppTasks()
            for i in range(tasks.size()):
                tasks.get(i).setExcludeFromRecents(excluded)
        except Exception as e:
            print(f"[Freeze] Liste des récents inchangée : {e}")

    def hide_window(self):
        if HIDE_FROM_RECENTS:
            self.exclude_from_recents(True)
        self.activity.moveTaskToBack(True)


class FreezeApp(App):
    """Aucune fenêtre : l'appli démarre le service puis se masque aussitôt.
    La permission d'affichage se donne via l'icône « Permission » de la
    notification."""

    def build(self):
        self.ctrl = None
        self.last_start = 0.0
        self.asked_notifications = False
        return Widget()

    def on_start(self):
        if platform != 'android':
            return
        self.ctrl = ServiceController()
        Clock.schedule_once(self.auto_start, 0.1)

    def on_pause(self):
        return True

    def on_resume(self):
        if self.ctrl is not None:
            self.ctrl.exclude_from_recents(False)
            Clock.schedule_once(self.auto_start, 0.1)

    @mainthread
    def _after_notif_request(self, *args):
        self.auto_start()

    def auto_start(self, *args):
        if self.ctrl is None:
            return
        # Android 13+ : sans cette autorisation, pas d'icône dans la barre
        if not self.ctrl.notifications_ok() and not self.asked_notifications:
            self.asked_notifications = True
            try:
                request_permissions([NOTIF_PERMISSION],
                                    lambda *a: self._after_notif_request())
                return
            except Exception as e:
                print(f"[Freeze] Demande de notifications impossible : {e}")

        if not self.ctrl.is_running():
            now = time.time()
            if now - self.last_start > START_DEBOUNCE:
                self.last_start = now
                if not self.ctrl.start():
                    return
        Clock.schedule_once(lambda dt: self.ctrl.hide_window(), 0.3)


if __name__ == '__main__':
    FreezeApp().run()
