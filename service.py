"""Service Freeze Screen (service Android de premier plan).

Ce script tourne dans un processus séparé, sans fenêtre : il porte les couches
de gel et les deux coins de déblocage. Il continue donc de fonctionner même
quand l'application (main.py) est fermée.

Tout se commande depuis la notification (icône dans la barre d'état) :
  - bouton « Geler »   : gèle l'écran ;
  - bouton « Quitter » : arrête Freeze Screen.
Le dégel se fait uniquement en maintenant en même temps les deux coins gris.
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
Intent = autoclass('android.content.Intent')
IntentFilter = autoclass('android.content.IntentFilter')
PendingIntent = autoclass('android.app.PendingIntent')
NotificationBuilder = autoclass('android.app.Notification$Builder')
NotificationChannel = autoclass('android.app.NotificationChannel')
RDrawable = autoclass('android.R$drawable')
GenericBroadcastReceiver = autoclass('org.kivy.android.GenericBroadcastReceiver')

MATCH_PARENT = -1
CORNER_SIZE = 250  # px, ~1.6 cm sur le Redmi
# Dégel automatique de sécurité après N secondes (0 = désactivé).
AUTO_UNFREEZE_SECONDS = 0

# Notification du service : même identifiant que celle de python-for-android
# (« Id:1 » dans le log), donc la nôtre la remplace au lieu de s'ajouter.
NOTIF_ID = 1
NOTIF_CHANNEL = 'freeze_screen'
FLAG_IMMUTABLE = 0x04000000
FLAG_ACTIVITY_NEW_TASK = 0x10000000
Uri = autoclass('android.net.Uri')
RECEIVER_NOT_EXPORTED = 4
IMPORTANCE_LOW = 2


def cs(text):
    """Chaîne Python -> java.lang.CharSequence (pyjnius ne le fait pas seul)."""
    return cast('java.lang.CharSequence', JString(text))


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
# Écouteur de toucher (à garder référencé côté Python !)
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


# ---------------------------------------------------------------------------
# Gestion des vues flottantes (gel + coins de déblocage)
# ---------------------------------------------------------------------------
class OverlayManager:
    """Gère les vues flottantes : couche de gel et coins de déblocage."""

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
        self.frozen = False
        self.pressed_tl = False
        self.pressed_br = False
        self._timer = None

    def has_permission(self):
        return Settings.canDrawOverlays(self.ctx)

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
        self.pressed_tl = False
        self.pressed_br = False
        self._add_overlay_views()
        _notify_state(True)
        if AUTO_UNFREEZE_SECONDS:
            self._timer = threading.Timer(AUTO_UNFREEZE_SECONDS, self.unfreeze)
            self._timer.daemon = True
            self._timer.start()

    # ---------- DEGEL (uniquement par les deux coins) ----------
    def unfreeze(self):
        print("[Freeze] unfreeze() appelé, frozen =", self.frozen)
        if not self.frozen:
            return
        self.frozen = False
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        self._remove_overlay_views()
        _notify_state(False)

    # ---------- Arrêt complet (bouton « Quitter » de la notification) ----------
    def shutdown(self):
        print("[Freeze] Arrêt demandé depuis la notification")
        self.frozen = False
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        self._remove_overlay_views()
        # exécuté après le retrait ci-dessus (même file d'attente)
        on_ui(lambda: PythonService.mService.stopSelf())

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
            _notify_state(False)

    @ui_thread
    def _remove_overlay_views(self):
        for v in (self.blocker, self.corner_tl, self.corner_br):
            try:
                if v is not None:
                    self.wm.removeView(v)
            except Exception as e:
                print(f"[Freeze] Erreur retrait vue : {e}")
        print("[Freeze] Dégel effectué")

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


# ---------------------------------------------------------------------------
# Notification avec boutons (geler / quitter)
# ---------------------------------------------------------------------------
class ActionCallback(PythonJavaClass):
    """Reçoit les appuis sur les boutons de la notification."""
    __javainterfaces__ = ['org/kivy/android/GenericBroadcastReceiverCallback']
    __javacontext__ = 'app'

    def __init__(self, handler):
        super().__init__()
        self.handler = handler

    @java_method('(Landroid/content/Context;Landroid/content/Intent;)V')
    def onReceive(self, context, intent):
        try:
            self.handler(str(intent.getAction()))
        except Exception as e:
            print(f"[Freeze] Erreur bouton notification : {e}")


class ActionNotifier:
    def __init__(self, mgr):
        self.mgr = mgr
        self.ctx = PythonService.mService
        self.pkg = str(self.ctx.getPackageName())
        self.nm = self.ctx.getSystemService(Context.NOTIFICATION_SERVICE)
        self.act_freeze = self.pkg + '.FREEZE'
        self.act_quit = self.pkg + '.QUIT'
        self.frozen = False

        # Écoute des deux actions (récepteur privé à l'appli : obligatoire
        # de préciser « non exporté » sur Android 14+)
        self.callback = ActionCallback(self.on_action)  # garder la référence
        self.receiver = GenericBroadcastReceiver(self.callback)
        flt = IntentFilter()
        for act in (self.act_freeze, self.act_quit):
            flt.addAction(act)
        if SDK_INT >= 33:
            self.ctx.registerReceiver(self.receiver, flt, RECEIVER_NOT_EXPORTED)
        else:
            self.ctx.registerReceiver(self.receiver, flt)

        if SDK_INT >= 26:
            channel = NotificationChannel(NOTIF_CHANNEL, cs('Freeze Screen'),
                                          IMPORTANCE_LOW)
            self.nm.createNotificationChannel(channel)

    def on_action(self, action):
        print("[Freeze] bouton notification :", action)
        if action == self.act_freeze:
            self.collapse_shade()
            self.mgr.freeze()
        elif action == self.act_quit:
            self.mgr.shutdown()

    def collapse_shade(self):
        """Replie le volet de notifications (nécessite la permission
        EXPAND_STATUS_BAR déclarée dans buildozer.spec)."""
        try:
            sb = self.ctx.getSystemService('statusbar')
            method = sb.getClass().getMethod('collapsePanels')
            try:
                method.invoke(sb)
            except Exception:
                method.invoke(sb, [])
            return
        except Exception as e:
            print(f"[Freeze] Repli du volet (statusbar) impossible : {e}")
        try:
            self.ctx.sendBroadcast(Intent('android.intent.action.CLOSE_SYSTEM_DIALOGS'))
        except Exception as e:
            print(f"[Freeze] Repli du volet (broadcast) impossible : {e}")

    def _pending(self, action, code):
        intent = Intent(action)
        intent.setPackage(self.pkg)
        return PendingIntent.getBroadcast(
            self.ctx, code, intent, PendingIntent.FLAG_UPDATE_CURRENT | FLAG_IMMUTABLE)

    def _pending_permission(self):
        """Ouvre directement l'écran Android « Afficher par-dessus les autres
        applis » de Freeze Screen (action de la notification)."""
        intent = Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                        Uri.parse("package:" + str(self.pkg)))
        intent.addFlags(FLAG_ACTIVITY_NEW_TASK)
        return PendingIntent.getActivity(
            self.ctx, 3, intent,
            PendingIntent.FLAG_UPDATE_CURRENT | FLAG_IMMUTABLE)

    def update(self, frozen=None):
        if frozen is not None:
            self.frozen = frozen
        try:
            if SDK_INT >= 26:
                b = NotificationBuilder(self.ctx, NOTIF_CHANNEL)
            else:
                b = NotificationBuilder(self.ctx)
            b.setSmallIcon(self.ctx.getApplicationInfo().icon)
            b.setContentTitle(cs('Freeze Screen'))
            has_perm = bool(Settings.canDrawOverlays(self.ctx))
            if self.frozen:
                text = 'Écran gelé : maintiens les deux coins pour dégeler'
            elif has_perm:
                text = 'Touche « pause » pour geler l\'écran'
            else:
                text = 'Permission manquante : touche l\'icône réglages'
            b.setContentText(cs(text))
            b.setOngoing(True)
            b.setShowWhen(False)
            # fond bleu glacé : le système en déduit des icônes claires,
            # au lieu de la teinte rosée imposée par défaut
            try:
                b.setColor(argb(0xFF1E88E5))
                b.setColorized(True)
            except Exception as e:
                print(f"[Freeze] Couleur de notification impossible : {e}")
            # trois icônes d'action : pause = geler, réglages = permission,
            # marche/arrêt = quitter
            b.addAction(RDrawable.ic_media_pause, cs('Geler'),
                        self._pending(self.act_freeze, 1))
            b.addAction(RDrawable.ic_menu_manage, cs('Permission'),
                        self._pending_permission())
            b.addAction(RDrawable.ic_lock_power_off, cs('Quitter'),
                        self._pending(self.act_quit, 2))
            try:
                # affichage compact avec les deux icônes, comme un lecteur
                style = autoclass('android.app.Notification$MediaStyle')()
                try:
                    # méthode à arguments variables (int...) : entiers séparés
                    style.setShowActionsInCompactView(0, 1, 2)
                except Exception:
                    from jnius import cast as _cast  # noqa: F401
                    IntArr = autoclass('java.lang.reflect.Array')
                    arr = IntArr.newInstance(autoclass('java.lang.Integer').TYPE, 3)
                    IntArr.setInt(arr, 0, 0)
                    IntArr.setInt(arr, 1, 1)
                    IntArr.setInt(arr, 2, 2)
                    style.setShowActionsInCompactView(arr)
                b.setStyle(style)
            except Exception as e:
                print(f"[Freeze] Style compact indisponible : {e}")
            self.nm.notify(NOTIF_ID, b.build())
        except Exception as e:
            print(f"[Freeze] Notification à boutons impossible : {e}")


_notifier = None


def _notify_state(frozen):
    if _notifier is not None:
        _notifier.update(frozen)


def main():
    global _handler, _notifier
    _handler = Handler(Looper.getMainLooper())
    mgr = OverlayManager()
    print("[Freeze] Service démarré")
    try:
        _notifier = ActionNotifier(mgr)
        _notifier.update(False)
        # python-for-android peut reposter sa notification simple juste après
        # le démarrage : on repasse par-dessus quelques secondes plus tard
        t = threading.Timer(3.0, lambda: _notifier.update())
        t.daemon = True
        t.start()
    except Exception as e:
        print(f"[Freeze] Boutons de notification indisponibles : {e}")
    if not mgr.has_permission():
        print("[Freeze] Permission d'affichage par-dessus les autres apps "
              "manquante : le gel ne pourra pas s'afficher")
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
