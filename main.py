import kivy
from kivy.app import App
from kivy.uix.button import Button
from kivy.uix.floatlayout import FloatLayout
from kivy.utils import platform

# On charge les outils Android UNIQUEMENT si le script tourne sur Android
if platform == 'android':
    from jnius import autoclass
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
else:
    PythonActivity = None

class LockScreenApp(App):
    def build(self):
        layout = FloatLayout()
        
        # États pour suivre si chaque bouton est pressé
        self.top_left_pressed = False
        self.bottom_right_pressed = False

        # Bouton 1 : Haut à gauche (totalement invisible/incolore)
        self.btn_top_left = Button(
            text="",
            background_color=(0, 0, 0, 0),  # Fond totalement transparent
            size_hint=(None, None),
            size=(150, 150),
            pos_hint={'x': 0, 'top': 1}
        )
        self.btn_top_left.bind(on_press=self.on_top_left_press)

        # Bouton 2 : Bas à droite (totalement invisible/incolore)
        self.btn_bottom_right = Button(
            text="",
            background_color=(0, 0, 0, 0),  # Fond totalement transparent
            size_hint=(None, None),
            size=(150, 150),
            pos_hint={'right': 1, 'y': 0}
        )
        self.btn_bottom_right.bind(on_press=self.on_bottom_right_press)
        
        layout.add_widget(self.btn_top_left)
        layout.add_widget(self.btn_bottom_right)
        return layout

    def on_start(self):
        # Active l'épinglage d'écran système uniquement sur Android
        if platform == 'android' and PythonActivity:
            try:
                activity = PythonActivity.mActivity
                activity.startLockTask()
                print("[Android] Mode épinglage activé")
            except Exception as e:
                print(f"[Android] Erreur d'activation : {e}")
        else:
            print("[Windows/PC] Simulation : Mode épinglage ignoré sur ordinateur")

    def on_top_left_press(self, instance):
        self.top_left_pressed = True
        self.check_unlock()

    def on_bottom_right_press(self, instance):
        self.bottom_right_pressed = True
        self.check_unlock()

    def check_unlock(self):
        # Vérifie si les deux boutons ont été activés
        if self.top_left_pressed and self.bottom_right_pressed:
            self.unlock_screen()

    def unlock_screen(self):
        # Quitte le mode d'épinglage uniquement sur Android et ferme l'application
        if platform == 'android' and PythonActivity:
            try:
                activity = PythonActivity.mActivity
                activity.stopLockTask()
                print("[Android] Mode épinglage désactivé")
            except Exception as e:
                print(f"[Android] Erreur de désactivation : {e}")
        
        print("Fermeture de l'application.")
        self.stop()

if __name__ == '__main__':
    LockScreenApp().run()