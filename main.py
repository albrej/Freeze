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
import kivy
from kivy.app import App
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.boxlayout import BoxLayout
from kivy.utils import platform

if platform == 'android':
    from jnius import autoclass, PythonJavaClass, java_method
    from android.runnable import run_on_ui_thread

    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    Settings = autoclass('android.provider.Settings')
    Context = autoclass('android.content.Context')
    WindowManagerLP = autoclass('android.view.WindowManager$LayoutParams')
    PixelFormat = autoclass('android.graphics.PixelFormat')
    View = autoclass('android.view.View')
    AButton = autoclass('android.widget.Button')
    ColorDrawable = autoclass('android.graphics.drawable.ColorDrawable')
    Gravity = autoclass('android.view.Gravity')
    MotionEvent = autoclass('android.view.MotionEvent')
    Uri = autoclass('android.net.Uri')
    Intent = autoclass('android.content.Intent')
    SDK_INT = autoclass('android.os.Build$VERSION').SDK_INT
else:
    PythonActivity = None

    # Factice sur PC : exécute directement la fonction (comportement identique)
    def run_on_ui_thread(func):
        return func

MAX_DELAY = 2.0
MATCH_PARENT = -1
CORNER_SIZE = 250  # px, ~1.6 cm sur le Redmi


def argb(value):
    """Convertit une couleur 0xAARRGGBB en entier signé 32 bits (int Java)."""
    return value - 0x100000000 if value > 0x7FFFFFFF else value


if platform == 'android':

    class SwallowListener(PythonJavaClass):
        """Avale tous les touchers (le gel lui-même)."""
        __javainterfaces__ = ['android/view/View$OnTouchListener']
        __javacontext__ = 'app'

        def __init__(self):
            super().__init__()

        @java_method('(Landroid/view/View;Landroid/view/MotionEvent;)Z')
        def onTouch(self, v, event):
            return True


    class CornerListener(PythonJavaClass):
        """Un coin de déblocage : prévient Python à l'appui."""
        __javainterfaces__ = ['android/view/View$OnTouchListener']
        __javacontext__ = 'app'

        def __init__(self, callback):
            super().__init__()
            self.cb = callback

        @java_method('(Landroid/view/View;Landroid/view/MotionEvent;)Z')
        def onTouch(self, v, event):
            if event.getAction() == MotionEvent.ACTION_DOWN:
                self.cb()
            return True


    class FreezeListener(PythonJavaClass):
        """Bouton flottant 'regeler'."""
        __javainterfaces__ = ['android/view/View$OnTouchListener']
        __javacontext__ = 'app'

        def __init__(self, callback):
            super().__init__()
            self.cb = callback

        @java_method('(Landroid/view/View;Landroid/view/MotionEvent;)Z')
        def onTouch(self, v, event):
            if event.getAction() == MotionEvent.ACTION_DOWN:
                self.cb()
            return True


class OverlayManager:
    """Gère les vues flottantes : gel, coins, bouton regeler."""

    def __init__(self):
        self.activity = PythonActivity.mActivity
        # Contexte de l'application : vit aussi longtemps que le processus,
        # contrairement à l'activité qui peut être détruite en arrière-plan.
        self.ctx = self.activity.getApplicationContext()
        self.wm = self.ctx.getSystemService(Context.WINDOW_SERVICE)
        self.overlay_type = (WindowManagerLP.TYPE_APPLICATION_OVERLAY
                              if SDK_INT >= 26 else WindowManagerLP.TYPE_PHONE)
        self.flags = (WindowManagerLP.FLAG_NOT_FOCUSABLE
                      | WindowManagerLP.FLAG_LAYOUT_NO_LIMITS)

        self.blocker = None      # couche qui gèle tout
        self.corner_tl = None    # coin haut-gauche
        self.corner_br = None    # coin bas-droit
        self.btn_relock = None   # petit bouton pour regeler
        self.frozen = False
        self.last_tl = 0
        self.last_br = 0

    def _make_lp(self, w, h, gravity):
        lp = WindowManagerLP(w, h, self.overlay_type, self.flags,
                             PixelFormat.TRANSLUCENT)
        lp.gravity = gravity
        return lp

    # ---------- GEL ----------
    def freeze(self):
        if self.frozen:
            return
        self.frozen = True
        self._add_overlay_views()

    # ---------- DEGEL ----------
    def unfreeze(self):
        if not self.frozen:
            return
        self.frozen = False
        self._remove_overlay_views()
        self._show_relock_button()

    # ---------- Vues (thread UI Android) ----------
    @run_on_ui_thread
    def _add_overlay_views(self):
        try:
            # 1. Couche invisible plein écran qui avale les touchers
            if self.blocker is None:
                self.blocker = View(self.ctx)
                self.blocker.setOnTouchListener(SwallowListener())
            lp = self._make_lp(MATCH_PARENT, MATCH_PARENT, Gravity.TOP)
            self.wm.addView(self.blocker, lp)

            # 2. Coin haut-gauche (visible, gris translucide)
            if self.corner_tl is None:
                self.corner_tl = AButton(self.ctx)
                self.corner_tl.setText("")
                self.corner_tl.setBackground(
                    ColorDrawable(argb(0x59505050)))  # gris, alpha 0x59
                self.corner_tl.setOnTouchListener(CornerListener(self._on_tl))
            lp = self._make_lp(CORNER_SIZE, CORNER_SIZE,
                               Gravity.TOP | Gravity.LEFT)
            self.wm.addView(self.corner_tl, lp)

            # 3. Coin bas-droit
            if self.corner_br is None:
                self.corner_br = AButton(self.ctx)
                self.corner_br.setText("")
                self.corner_br.setBackground(ColorDrawable(argb(0x59505050)))
                self.corner_br.setOnTouchListener(CornerListener(self._on_br))
            lp = self._make_lp(CORNER_SIZE, CORNER_SIZE,
                               Gravity.BOTTOM | Gravity.RIGHT)
            self.wm.addView(self.corner_br, lp)

            print("[Freeze] Gel actif")
        except Exception as e:
            print(f"[Freeze] Erreur gel : {e}")

    @run_on_ui_thread
    def _remove_overlay_views(self):
        try:
            for v in (self.blocker, self.corner_tl, self.corner_br):
                if v is not None:
                    self.wm.removeView(v)
            print("[Freeze] Dégel effectué")
        except Exception as e:
            print(f"[Freeze] Erreur dégel : {e}")

    @run_on_ui_thread
    def _show_relock_button(self):
        try:
            if self.btn_relock is None:
                self.btn_relock = AButton(self.ctx)
                self.btn_relock.setText("GELER")
                self.btn_relock.setBackground(ColorDrawable(argb(0xAA505050)))
                self.btn_relock.setOnTouchListener(
                    FreezeListener(self._on_relock))
            lp = self._make_lp(280, 130, Gravity.BOTTOM | Gravity.CENTER)
            self.wm.addView(self.btn_relock, lp)
        except Exception as e:
            print(f"[Freeze] Erreur bouton regeler : {e}")

    @run_on_ui_thread
    def _hide_relock_button(self):
        try:
            if self.btn_relock is not None:
                self.wm.removeView(self.btn_relock)
        except Exception:
            pass

    # ---------- Callbacks toucher ----------
    def _on_tl(self):
        from time import time
        self.last_tl = time()
        self._check_unlock()

    def _on_br(self):
        from time import time
        self.last_br = time()
        self._check_unlock()

    def _check_unlock(self):
        if self.last_tl and self.last_br:
            if abs(self.last_tl - self.last_br) <= MAX_DELAY:
                self.last_tl = 0
                self.last_br = 0
                self.unfreeze()
            else:
                # trop lent : on repart de zéro
                self.last_tl = 0
                self.last_br = 0

    def _on_relock(self):
        self._hide_relock_button()
        self.freeze()

    # ---------- Permission ----------
    def has_permission(self):
        return Settings.canDrawOverlays(self.activity)

    def ask_permission(self):
        intent = Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                        Uri.parse("package:" + self.activity.getPackageName()))
        self.activity.startActivity(intent)


class FreezeApp(App):
    def build(self):
        layout = BoxLayout(orientation='vertical', padding=30, spacing=20)

        self.status = Label(
            text="Freeze Screen\n\nÉcran de contrôle",
            font_size='22sp', halign='center')
        layout.add_widget(self.status)

        self.btn_perm = Button(
            text="1. Accorder la permission\n\"Afficher par-dessus les autres apps\"",
            background_normal='', background_down='',
            background_color=(0.2, 0.6, 1.0, 1), size_hint=(1, 0.3))
        self.btn_perm.bind(on_press=self.on_ask_permission)
        layout.add_widget(self.btn_perm)

        self.btn_freeze = Button(
            text="2. GELER l'écran et revenir à l'app précédente",
            background_normal='', background_down='',
            background_color=(0.1, 0.7, 0.3, 1), size_hint=(1, 0.3))
        self.btn_freeze.bind(on_press=self.on_freeze)
        layout.add_widget(self.btn_freeze)

        return layout

    def on_start(self):
        if platform != 'android':
            self.status.text = ("Version PC : la fonction gel\n"
                               "ne fonctionne que sur Android.")
            return
        self.overlay = OverlayManager()
        self.refresh_status()

    def on_pause(self):
        # Sans ça, Kivy arrête l'appli dès qu'elle passe en arrière-plan
        # et les couches de gel disparaissent avec elle.
        return True

    def on_resume(self):
        # appelé aussi au retour depuis les paramètres Android
        if platform == 'android':
            self.refresh_status()

    def refresh_status(self):
        if self.overlay.has_permission():
            self.status.text = ("Freeze Screen\n\n"
                                "✓ Permission accordée\n"
                                "Étape 2 : Geler l'écran")
            self.btn_perm.disabled = True
        else:
            self.status.text = ("Freeze Screen\n\n"
                               "✗ Permission manquante\n"
                               "Étape 1 obligatoire")
            self.btn_perm.disabled = False

    def on_ask_permission(self, *args):
        self.overlay.ask_permission()

    def on_freeze(self, *args):
        if platform != 'android':
            return
        if not self.overlay.has_permission():
            self.refresh_status()
            return
        self.overlay.freeze()
        # L'app passe à l'arrière-plan : l'app précédente revient au premier
        # plan, la couche de gel reste par-dessus.
        PythonActivity.mActivity.moveTaskToBack(True)


if __name__ == '__main__':
    FreezeApp().run()