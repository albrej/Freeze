"""Service Freeze Screen (service Android de premier plan).

Ce script tourne dans un processus séparé, sans fenêtre : il porte le bouton
flottant « GELER », les couches de gel et les deux coins de déblocage. Il
continue donc de fonctionner même quand l'application (main.py) est fermée.
"""
import threading
import time
from functools import wraps

from jnius import autoclass, cast, PythonJavaClass, java_method

PythonService = autoclass('org.kivy.android.PythonService')
Settings = autoclass('android.provider.Settings')
Context = autoclass('android.content.Context')
WindowManagerLP = autoclass('android.view.WindowManager$LayoutParams')
PixelFormat = autoclass('android.graphics.PixelFormat')
View = autoclass('android.view.View')
AButton = autoclass('android.widget.Button')
ColorDrawable = autoclass('android.graphics.drawable.ColorDrawable')
Gravity = autoclass('android.view.Gravity')
MotionEvent = autoclass('android.view.MotionEvent')
Handler = autoclass('android.os.Handler')
Looper = autoclass('android.os.Looper')
SDK_INT = autoclass('android.os.Build$VERSION').SDK_INT
JString = autoclass('java.lang.String')

MATCH_PARENT = -1
CORNER_SIZE = 250  # px, ~1.6 cm sur le Redmi
# Dégel automatique de sécurité après N secondes (0 = désactivé).
AUTO_UNFREEZE_SECONDS = 0
# Durée d'appui (en secondes) sur le bouton GELER pour déclencher le gel.
LONG_PRESS_SECONDS = 0.8


def argb(value):
    """Convertit une couleur 0xAARRGGBB en entier signé 32 bits (int Java)."""
    return value - 0x100000000 if value > 0x7FFFFFFF else value


# ---------------------------------------------------------------------------
# Exécution sur le thread principal Android (pas d'Activity dans un service,
# donc on passe par un Handler lié au Looper principal)
# ---------------------------------------------------------------------------
_handler = None
_pending = []  # références gardées jusqu'à l'exécution (anti ramasse-miettes)


class UiRunnable(PythonJavaClass):
    __javainterfaces__ = ['java/lang/Runnable']
    __javacontext__ = 'app'

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    @java_method('()V')
    def run(self):
        try:
            self.fn()
        except Exception as e:
            print(f"[Freeze] Erreur thread UI : {e}")
        finally:
            try:
                _pending.remove(self)
            except ValueError:
                pass


def on_ui(fn):
    runnable = UiRunnable(fn)
    _pending.append(runnable)
    _handler.post(runnable)


def ui_thread(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        on_ui(lambda: f(*args, **kwargs))
    return wrapper


# ---------------------------------------------------------------------------
# Écouteurs de toucher (à garder référencés côté Python !)
# ---------------------------------------------------------------------------
class CornerListener(PythonJavaClass):
    """Un coin de déblocage : prévient Python à l'appui et au relâchement."""
    __javainterfaces__ = ['android/view/View$OnTouchListener']
    __javacontext__ = 'app'

    def __init__(self, callback):
        super().__init__()
        self.cb = callback

    @java_method('(Landroid/view/View;Landroid/view/MotionEvent;)Z')
    def onTouch(self, v, event):
        action = event.getActionMasked()
        if action == MotionEvent.ACTION_DOWN:
            self.cb(True)
        elif action in (MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL):
            self.cb(False)
        return True


class FreezeListener(PythonJavaClass):
    """Bouton flottant 'GELER' : se déclenche sur un appui long."""
    __javainterfaces__ = ['android/view/View$OnTouchListener']
    __javacontext__ = 'app'

    def __init__(self, callback, delay=LONG_PRESS_SECONDS):
        super().__init__()
        self.cb = callback
        self.delay = delay
        self._timer = None

    def _cancel(self):
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    @java_method('(Landroid/view/View;Landroid/view/MotionEvent;)Z')
    def onTouch(self, v, event):
        action = event.getActionMasked()
        if action == MotionEvent.ACTION_DOWN:
            self._cancel()
            self._timer = threading.Timer(self.delay, self.cb)
            self._timer.daemon = True
            self._timer.start()
        elif action in (MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL):
            self._cancel()
        return True


# ---------------------------------------------------------------------------
# Gestion des vues flottantes
# ---------------------------------------------------------------------------
class OverlayManager:
    """Gère les vues flottantes : gel, coins, bouton GELER."""

    def __init__(self):
        self.ctx = PythonService.mService
        self.wm = self.ctx.getSystemService(Context.WINDOW_SERVICE)
        self.overlay_type = (WindowManagerLP.TYPE_APPLICATION_OVERLAY
                             if SDK_INT >= 26 else WindowManagerLP.TYPE_PHONE)
        self.flags = (WindowManagerLP.FLAG_NOT_FOCUSABLE
                      | WindowManagerLP.FLAG_LAYOUT_NO_LIMITS
                      | WindowManagerLP.FLAG_SPLIT_TOUCH)

        self.blocker = None      # couche qui gèle tout
        self.corner_tl = None    # coin haut-gauche
        self.corner_br = None    # coin bas-droit
        self.btn_relock = None   # bouton GELER
        self.frozen = False
        self.pressed_tl = False
        self.pressed_br = False
        self.relock_shown = False
        self._timer = None

    def has_permission(self):
        return Settings.canDrawOverlays(self.ctx)

    def _make_lp(self, w, h, gravity):
        lp = WindowManagerLP(w, h, self.overlay_type, self.flags,
                             PixelFormat.TRANSLUCENT)
        lp.gravity = gravity
        return lp

    # ---------- ARMEMENT (bouton GELER seul, écran non gelé) ----------
    def arm(self):
        if self.frozen:
            return
        self._show_relock_button()

    # ---------- GEL ----------
    def freeze(self):
        if self.frozen:
            return
        self.frozen = True
        self.pressed_tl = False
        self.pressed_br = False
        self._add_overlay_views()
        if AUTO_UNFREEZE_SECONDS:
            self._timer = threading.Timer(AUTO_UNFREEZE_SECONDS, self.unfreeze)
            self._timer.daemon = True
            self._timer.start()

    # ---------- DEGEL ----------
    def unfreeze(self):
        print("[Freeze] unfreeze() appelé, frozen =", self.frozen)
        if not self.frozen:
            return
        self.frozen = False
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        self._remove_overlay_views()
        self._show_relock_button()

    # ---------- Vues (thread principal Android) ----------
    @ui_thread
    def _add_overlay_views(self):
        try:
            # 1. Couche invisible plein écran : la fenêtre absorbe les touchers
            if self.blocker is None:
                self.blocker = View(self.ctx)
            lp = self._make_lp(MATCH_PARENT, MATCH_PARENT, Gravity.TOP)
            self.wm.addView(self.blocker, lp)

            # 2. Coin haut-gauche (visible, gris translucide)
            if self.corner_tl is None:
                self.corner_tl = AButton(self.ctx)
                self.corner_tl.setBackground(ColorDrawable(argb(0x59505050)))
                # IMPORTANT : garder une référence Python vers l'écouteur
                self._ls_tl = CornerListener(self._on_tl)
                self.corner_tl.setOnTouchListener(self._ls_tl)
            lp = self._make_lp(CORNER_SIZE, CORNER_SIZE,
                               Gravity.TOP | Gravity.LEFT)
            self.wm.addView(self.corner_tl, lp)

            # 3. Coin bas-droit
            if self.corner_br is None:
                self.corner_br = AButton(self.ctx)
                self.corner_br.setBackground(ColorDrawable(argb(0x59505050)))
                self._ls_br = CornerListener(self._on_br)
                self.corner_br.setOnTouchListener(self._ls_br)
            lp = self._make_lp(CORNER_SIZE, CORNER_SIZE,
                               Gravity.BOTTOM | Gravity.RIGHT)
            self.wm.addView(self.corner_br, lp)

            print("[Freeze] Gel actif")
        except Exception as e:
            print(f"[Freeze] Erreur gel : {e}")
            # Ne jamais laisser l'écran bloqué sans coins de déblocage
            for v in (self.blocker, self.corner_tl, self.corner_br):
                try:
                    if v is not None:
                        self.wm.removeView(v)
                except Exception:
                    pass
            self.frozen = False

    @ui_thread
    def _remove_overlay_views(self):
        for v in (self.blocker, self.corner_tl, self.corner_br):
            try:
                if v is not None:
                    self.wm.removeView(v)
            except Exception as e:
                print(f"[Freeze] Erreur retrait vue : {e}")
        print("[Freeze] Dégel effectué")

    @ui_thread
    def _show_relock_button(self):
        try:
            if self.relock_shown:
                return
            if self.btn_relock is None:
                self.btn_relock = AButton(self.ctx)
                self.btn_relock.setText(
                    cast('java.lang.CharSequence', JString("GELER")))
                self.btn_relock.setBackground(ColorDrawable(argb(0xAA505050)))
                self._ls_relock = FreezeListener(self._on_relock)
                self.btn_relock.setOnTouchListener(self._ls_relock)
            lp = self._make_lp(280, 130, Gravity.BOTTOM | Gravity.CENTER)
            self.wm.addView(self.btn_relock, lp)
            self.relock_shown = True
        except Exception as e:
            print(f"[Freeze] Erreur bouton GELER : {e}")

    @ui_thread
    def _hide_relock_button(self):
        try:
            if self.btn_relock is not None and self.relock_shown:
                self.wm.removeView(self.btn_relock)
                self.relock_shown = False
        except Exception:
            pass

    # ---------- Callbacks toucher ----------
    def _on_tl(self, pressed):
        self.pressed_tl = pressed
        print("[Freeze] coin haut-gauche", "appuyé" if pressed else "relâché")
        self._check_unlock()

    def _on_br(self, pressed):
        self.pressed_br = pressed
        print("[Freeze] coin bas-droit", "appuyé" if pressed else "relâché")
        self._check_unlock()

    def _check_unlock(self):
        # Dégel seulement si les DEUX coins sont maintenus en même temps
        if self.pressed_tl and self.pressed_br:
            self.pressed_tl = False
            self.pressed_br = False
            self.unfreeze()

    def _on_relock(self):
        self._hide_relock_button()
        self.freeze()


def main():
    global _handler
    _handler = Handler(Looper.getMainLooper())
    mgr = OverlayManager()
    print("[Freeze] Service démarré")
    if mgr.has_permission():
        mgr.arm()
    else:
        print("[Freeze] Permission d'affichage par-dessus les autres apps "
              "manquante : bouton GELER non affiché")
    while True:
        time.sleep(1)


try:
    main()
except Exception:
    # Sans ça, une erreur ferait disparaître le service sans laisser de trace
    import traceback
    print("[Freeze] Erreur fatale dans le service :")
    traceback.print_exc()
    raise
