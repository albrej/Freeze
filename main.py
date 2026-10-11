import os
import sys

# --- Contournement du crash hwuiTask/mutex sur Android 14/15 ---
# Doit être exécuté AVANT tout import Kivy.
# sys.getandroidapiversion() n'existe que dans le Python embarqué par p4a.
IS_ANDROID = hasattr(sys, "getandroidapiversion") or sys.platform == "android"

if IS_ANDROID:
    os.environ["KIVY_GL_BACKEND"] = "gles2"
    os.environ["KIVY_METRICS_DENSITY"] = "2"

from kivy.config import Config
if IS_ANDROID:
    Config.set("graphics", "multisamples", "0")

# --- Imports Kivy ---
from kivy.app import App
from kivy.clock import Clock
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.boxlayout import BoxLayout
from kivy.utils import platform
from kivy.metrics import dp

if platform == 'android':
    from jnius import autoclass
    from android.permissions import request_permissions

    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    Settings = autoclass('android.provider.Settings')
    Context = autoclass('android.content.Context')
    Uri = autoclass('android.net.Uri')
    Intent = autoclass('android.content.Intent')
else:
    PythonActivity = None

# Nom du service déclaré dans buildozer.spec (services = freeze:service.py:...).
# La classe Java générée s'appelle <package>.Service<Nom avec majuscule>.
SERVICE_NAME = 'Freeze'


class ServiceController:
    """Pilote le service Android (démarrage, arrêt, état) et la permission.

    Les couches de gel et le bouton GELER vivent dans service.py, pas ici :
    cette fenêtre peut donc être fermée sans rien perdre.
    """

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

    def ask_notifications(self):
        # Android 13+ : sans cette autorisation, l'icône du service
        # n'apparaît pas dans la barre d'état.
        try:
            request_permissions(['android.permission.POST_NOTIFICATIONS'])
        except Exception as e:
            print(f"[Freeze] Demande de notifications impossible : {e}")

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

    def stop(self):
        try:
            autoclass(self.service_class_name).stop(self.activity)
        except Exception as e:
            print(f"[Freeze] Arrêt du service impossible : {e}")


class FreezeApp(App):
    def build(self):
        self.ctrl = None
        layout = BoxLayout(orientation='vertical', padding=30, spacing=20)

        self.status = Label(
            text="Freeze Screen\n\nÉcran de contrôle",
            font_size='22sp', halign='center')
        layout.add_widget(self.status)

        self.btn_perm = Button(
            text="1. Accorder la permission\nà l'appli \"Freeze Screen\"",
            halign='center', valign='middle',
            background_normal='', background_down='',
            background_color=(0.2, 0.6, 1.0, 1), size_hint=(1, 0.25))
        # Largeur de texte = largeur du bouton (moins une marge), pour que
        # les deux lignes restent centrées et dans le bouton
        self.btn_perm.bind(
            size=lambda b, sz: setattr(b, 'text_size', (sz[0] - dp(20), None)))
        self.btn_perm.bind(on_press=self.on_ask_permission)
        layout.add_widget(self.btn_perm)

        self.btn_freeze = Button(
            text="2. Afficher le bouton GELER",
            background_normal='', background_down='',
            background_color=(0.1, 0.7, 0.3, 1), size_hint=(1, 0.25))
        self.btn_freeze.bind(on_press=self.on_freeze)
        layout.add_widget(self.btn_freeze)

        self.btn_stop = Button(
            text="3. Arrêter Freeze Screen",
            background_normal='', background_down='',
            background_color=(0.8, 0.25, 0.25, 1), size_hint=(1, 0.25))
        self.btn_stop.bind(on_press=self.on_stop_service)
        layout.add_widget(self.btn_stop)

        return layout

    def on_start(self):
        if platform != 'android':
            self.status.text = ("Version PC : la fonction gel\n"
                               "ne fonctionne que sur Android.")
            self.btn_freeze.disabled = True
            self.btn_stop.disabled = True
            return
        self.ctrl = ServiceController()
        self.ctrl.ask_notifications()
        self.refresh_status()

    def on_pause(self):
        # Sans ça, Kivy arrête l'appli dès qu'elle passe en arrière-plan.
        return True

    def on_resume(self):
        # appelé aussi au retour depuis les paramètres Android
        if self.ctrl is not None:
            self.refresh_status()

    def refresh_status(self, *args):
        if self.ctrl is None:
            return
        running = self.ctrl.is_running()
        if self.ctrl.has_permission():
            if running:
                detail = "Service actif :\nle bouton GELER est affiché"
            else:
                detail = "Étape 2 : Afficher le bouton GELER"
            self.status.text = "Freeze Screen\n\nPermission accordée\n" + detail
            self.btn_perm.disabled = True
        else:
            self.status.text = ("Freeze Screen\n\n"
                               "Permission manquante\n"
                               "Étape 1 obligatoire")
            self.btn_perm.disabled = False
        self.btn_stop.disabled = not running

    def on_ask_permission(self, *args):
        self.ctrl.ask_permission()

    def on_freeze(self, *args):
        if self.ctrl is None:
            return
        if not self.ctrl.has_permission():
            self.refresh_status()
            return
        if not self.ctrl.is_running():
            if not self.ctrl.start():
                self.status.text = ("Freeze Screen\n\n"
                                    "Le service n'a pas pu démarrer\n"
                                    "(voir adb logcat -s python)")
                return
        # La fenêtre disparaît ; le service continue (icône dans la barre
        # d'état + bouton GELER flottant). Pour l'arrêter : bouton 3.
        PythonActivity.mActivity.moveTaskToBack(True)

    def on_stop_service(self, *args):
        if self.ctrl is None:
            return
        self.ctrl.stop()
        # l'état du service met un instant à changer
        Clock.schedule_once(self.refresh_status, 1.0)


if __name__ == '__main__':
    FreezeApp().run()