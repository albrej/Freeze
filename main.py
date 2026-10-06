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
        
        # Bouton recouvrant tout l'écran faisant office de bouclier anti-clic
        self.lock_btn = Button(
            text="🔒 Écran Gelé\nCliquez ici pour déverrouiller",
            font_size='22sp',
            halign='center',
            background_color=(0, 0, 0, 0.6),  # Fond sombre transparent
            color=(1, 1, 1, 1),
            size_hint=(1, 1),
            pos_hint={'x': 0, 'y': 0}
        )
        
        self.lock_btn.bind(on_press=self.unlock_screen)
        layout.add_widget(self.lock_btn)
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

    def unlock_screen(self, instance):
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
