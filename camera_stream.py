import cv2  # OpenCV: Zugriff auf Kamera, Bildverarbeitung (Lesen, Konvertieren, Resizing)
from aiortc import VideoStreamTrack  # aiortc-Basisklasse für einen WebRTC-Videostream
from av import VideoFrame  # PyAV: Kapselt ein einzelnes Video-Frame für aiortc
import numpy as np  # NumPy: Matrizen-/Array-Operationen, hier für Bilder
import threading  # Threads: Hintergrundausführung für kontinuierliches Kameralesen


class MotionCameraStream(VideoStreamTrack):
    """🎥 Kamera-Stream mit Bild-Resize und Bewegungserkennung."""  # Klassenbeschreibung/Docstring

    def __init__(self, camera_index=0, target_size=(1280, 720), sensitivity=40):
        super().__init__()  # Basisklassen-Konstruktor aufrufen (wichtig für aiortc-internen Status)

        # Öffnet Kamera (z. B. USB-Kamera, CSI-Kamera oder Webcam)
        self.cap = cv2.VideoCapture(camera_index)  # Kamera-Handle erstellen; liefert später Frames

        # Lock für Thread-Synchronisation (wichtig für gleichzeitigen Zugriff)
        self.lock = threading.Lock()  # Mutex für sicheren Zugriff auf gemeinsame Variablen (z. B. self.frame)
        self.prev_gray = None  # vorheriges Bild (für Bewegungserkennung) – wird beim ersten Frame gesetzt
        self.motion_detected = False  # Statusflag: Ist Bewegung detektiert worden?
        self.sensitivity = sensitivity  # Empfindlichkeit der Bewegungserkennung (höher = empfindlicher)
        self.running = True  # Kontrollflag für den Kamerathread; beendet die Leseschleife, wenn False

        # Wenn Kamera nicht geöffnet werden kann → schwarzes Dummy-Bild
        if not self.cap.isOpened():  # Prüfen, ob der Kamera-Treiber/Stream erfolgreich geöffnet wurde
            print(f"❌ Kamera mit Index {camera_index} konnte nicht geöffnet werden!")  # Fehlermeldung ausgeben
            self.frame = np.zeros((target_size[1], target_size[0], 3), dtype=np.uint8)  # Fallback: schwarzes Frame
        else:
            # Kamera-Parameter setzen
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, target_size[0])  # Zielbreite setzen (sofern vom Treiber unterstützt)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, target_size[1])  # Zielhöhe setzen
            self.cap.set(cv2.CAP_PROP_FPS, 30)  # Wunsch-Framerate (30 fps) anfragen
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Nur 1 Frame puffern → geringere Latenz

        # Aktuelles Frame zwischenspeichern
        self.frame = np.zeros((target_size[1], target_size[0], 3), dtype=np.uint8)  # Initialer Framepuffer (schwarz)
        self._target_w, self._target_h = target_size  # Zielgröße für dynamisches Resizing merken

        # Startet eigenen Thread für kontinuierliches Lesen der Kamera
        self.thread = threading.Thread(target=self._reader, daemon=True)  # Hintergrundthread definieren (Daemon)
        self.thread.start()  # Thread starten → ab jetzt werden fortlaufend Frames gelesen

    # ==============================================
    # 📏 Auflösung dynamisch ändern
    # ==============================================
    def set_target_size(self, width: int, height: int):
        with self.lock:  # Sperre setzen: Threadsicheres Schreiben der Zielgröße
            self._target_w, self._target_h = width, height  # Neue Zielbreite/-höhe übernehmen

    def get_target_size(self):
        with self.lock:  # Sperre setzen: Threadsicheres Lesen der Zielgröße
            return self._target_w, self._target_h  # Aktuelle Zielgröße zurückgeben

    # ==============================================
    # 🧠 Bewegungserkennung
    # ==============================================
    def _detect_motion(self, frame):
        """Vergleicht aktuelle Frames, um Bewegung zu erkennen."""  # Kurzbeschreibung der Methode
        gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)  # Farbbild (RGB) in Graustufen umwandeln
        gray = cv2.GaussianBlur(gray, (21, 21), 0)  # Gauß-Blur: Rauschen glätten, kleine Flackerer unterdrücken

        # Erstes Bild als Referenz
        if self.prev_gray is None:  # Wenn noch kein Referenzbild vorhanden ist (erster Durchlauf)
            self.prev_gray = gray  # Referenz setzen
            return False  # Noch keine Bewegungsauswertung möglich → False zurückgeben

        # Differenz zum vorherigen Bild
        diff = cv2.absdiff(self.prev_gray, gray)  # Absoluten Unterschied der Graubilder berechnen (Bewegungs-Indikator)

        # Schwellwert: große Änderungen = Bewegung
        thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)[1]  # Binarisieren: Änderungen > 25 werden weiß (255)
        motion_level = np.sum(thresh) / 255  # Anzahl „weißer“ Pixel (geänderte Pixel) bestimmen

        # Referenzbild aktualisieren
        self.prev_gray = gray  # Aktuelles Bild als neue Referenz für den nächsten Vergleich speichern

        # Bewegung als erkannt markieren, wenn Schwelle überschritten
        self.motion_detected = motion_level > self.sensitivity * 1000  # Einfacher Schwellwert-Vergleich

    # ==============================================
    # 🔄 Kamerathread – liest Frames permanent
    # ==============================================
    def _reader(self):
        """Wird in eigenem Thread ausgeführt und hält das neueste Kamerabild aktuell."""  # Beschreibung des Threads
        while self.running and self.cap.isOpened():  # Solange Stop nicht angefordert und Kamera offen ist
            ret, frame = self.cap.read()  # Nächstes Frame aus der Kamera lesen (ret=True, wenn erfolgreich)
            if ret:  # Nur weiterarbeiten, wenn ein gültiges Bild vorliegt
                # OpenCV liefert BGR, für Browser/WebRTC brauchen wir RGB
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)  # Farbkanäle von BGR nach RGB konvertieren

                # Bild ggf. auf Zielgröße skalieren
                tw, th = self.get_target_size()  # Aktuelle Zielbreite/-höhe threadsicher holen
                if (frame.shape[1], frame.shape[0]) != (tw, th):  # Prüfen, ob die Größe bereits passt
                    frame = cv2.resize(frame, (tw, th), interpolation=cv2.INTER_AREA)  # Auf Zielgröße skalieren

                # Frame speichern (letztes gültiges Bild)
                self.frame = frame  # Neues Frame als „aktuelles“ Frame ablegen (wird später gesendet)

                # Bewegung prüfen
                self._detect_motion(frame)  # Bewegungserkennung auf dem aktuellen Frame ausführen

    # ==============================================
    # 📡 WebRTC Stream – sendet Frames an Browser
    # ==============================================
    async def recv(self):
        """Wird von WebRTC aufgerufen, um das nächste Videoframe zu liefern."""  # aiortc-Hook für Frame-Abruf
        pts, time_base = await self.next_timestamp()  # Zeitstempel und Zeitbasis für das nächste Frame berechnen
        frm = VideoFrame.from_ndarray(self.frame, format="rgb24")  # NumPy-Array → PyAV-VideoFrame (24-bit RGB)
        frm.pts = pts  # Präsentationszeitstempel setzen (Synchronisation)
        frm.time_base = time_base  # Zeitbasis setzen (Einheit/Skalierung des PTS)
        return frm  # Frame an die WebRTC-Pipeline zurückgeben

    # ==============================================
    # 🧹 Kamera sauber beenden
    # ==============================================
    def stop(self):
        """Stoppt den Kamera-Thread und gibt Ressourcen frei."""  # Öffentliche Methode zum Herunterfahren
        self.running = False  # Signal an den Lesethread: Schleife beenden
        if self.cap and self.cap.isOpened():  # Sicherstellen, dass ein Kamera-Handle existiert und offen ist
            self.cap.release()  # Kamera freigeben (sonst bleibt das Device blockiert)
            print("📷 Kamera gestoppt")  # Bestätigung in der Konsole ausgeben