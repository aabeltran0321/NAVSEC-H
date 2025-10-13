"""
Tkinter Face Recognition Access Control (Kiosk Layout)
------------------------------------------------------
- Maximized window (retains title bar)
- Larger fonts, centered layouts for touchscreen kiosk feel
- Uses OpenCV for face detection/recognition, TTS and speech recognition
"""

import os
import cv2
import numpy as np
import threading
import socket
import time
import csv
from pathlib import Path
from PIL import Image, ImageTk
import tkinter as tk
from tkinter import ttk, messagebox
import speech_recognition as sr
import pyttsx3

# ------------------------- Configuration -------------------------
DATA_DIR = Path("dataset")
TRAINER_FILE = Path("trainer.yml")
LABELS_FILE = Path("labels.csv")
CASCADE_PATH = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
ESP32_IP = "192.168.4.1"
ESP32_PORT = 4210
UNLOCK_MESSAGE = b"UNLOCK"
LOCKED_MESSAGE = b"LOCK"

IMG_WIDTH = 200
IMG_HEIGHT = 200
NUM_SAMPLES = 20
CONFIDENCE_THRESHOLD = 60

VALID_USERNAME = "admin"
VALID_PASSWORD = "admin"

HOSPITAL_MAP = {
    'radiology': 'Go straight and take the first left. Radiology is on your right.',
    'pharmacy': 'The pharmacy is on the ground floor near the main entrance.',
    'emergency': 'Proceed to the emergency wing, down the corridor and past reception.',
    'lab': 'The laboratory is on the second floor. Take the stairs or elevator to Level 2.'
}

# ------------------------- Utilities -------------------------
engine = pyttsx3.init()
engine.setProperty('rate', 170)

voices = engine.getProperty('voices')
engine.setProperty('voice', voices[1].id)

udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
labels = {}
names_to_id = {}
face_recognizer = None

def ensure_dirs():
    DATA_DIR.mkdir(exist_ok=True)
    if not LABELS_FILE.exists():
        with open(LABELS_FILE, 'w', newline='', encoding='utf-8') as f:
            csv.writer(f).writerow(['id', 'name'])

def load_labels():
    global labels, names_to_id
    labels.clear()
    names_to_id.clear()
    if LABELS_FILE.exists():
        with open(LABELS_FILE, newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                try:
                    i = int(row['id'])
                    n = row['name']
                    labels[i] = n
                    names_to_id[n.lower()] = i
                except Exception:
                    continue

def add_label(name):
    load_labels()
    if name.lower() in names_to_id:
        return names_to_id[name.lower()]
    next_id = max(labels.keys(), default=0) + 1
    with open(LABELS_FILE, 'a', newline='', encoding='utf-8') as f:
        csv.writer(f).writerow([next_id, name])
    labels[next_id] = name
    names_to_id[name.lower()] = next_id
    return next_id

def train_recognizer():
    global face_recognizer
    recognizer = cv2.face.LBPHFaceRecognizer_create()
    faces, ids = [], []
    for id_dir in DATA_DIR.iterdir():
        if not id_dir.is_dir():
            continue
        try:
            id_int = int(id_dir.name)
        except ValueError:
            continue
        for img_path in id_dir.glob("*.jpg"):
            img = cv2.imread(str(img_path), cv2.IMREAD_GRAYSCALE)
            if img is None:
                continue
            img = cv2.resize(img, (IMG_WIDTH, IMG_HEIGHT))
            faces.append(img)
            ids.append(id_int)
    if not faces:
        print("No faces found for training.")
        face_recognizer = None
        return False
    recognizer.train(faces, np.array(ids))
    recognizer.write(str(TRAINER_FILE))
    face_recognizer = recognizer
    return True

def load_trainer():
    global face_recognizer
    if not TRAINER_FILE.exists():
        face_recognizer = None
        return False
    recognizer = cv2.face.LBPHFaceRecognizer_create()
    recognizer.read(str(TRAINER_FILE))
    face_recognizer = recognizer
    return True

def send_unlock():
    try:
        udp_sock.sendto(UNLOCK_MESSAGE, (ESP32_IP, ESP32_PORT))
    except Exception as e:
        print("UDP send error:", e)

def send_lock():
    try:
        udp_sock.sendto(LOCKED_MESSAGE, (ESP32_IP, ESP32_PORT))
    except Exception as e:
        print("UDP send error:", e)

def speak(text):
    engine.say(text)
    engine.runAndWait()

def listen_and_extract(timeout=5, phrase_time_limit=6):
    r = sr.Recognizer()
    with sr.Microphone() as mic:
        r.adjust_for_ambient_noise(mic, duration=0.5)
        try:
            audio = r.listen(mic, timeout=timeout, phrase_time_limit=phrase_time_limit)
            text = r.recognize_google(audio)
            return text.lower()
        except Exception:
            return ""

def analyze_keywords(text):
    for kw in HOSPITAL_MAP:
        if kw in text:
            return HOSPITAL_MAP[kw]
    return None

# ------------------------- GUI -------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Face Recognition Access Control")
        self.state("zoomed")  # Maximized window
        self.configure(bg="#f0f4f8")

        self.container = ttk.Frame(self)
        self.container.pack(fill='both', expand=True)

        style = ttk.Style()
        style.configure("TButton", font=("Arial", 18), padding=10)
        style.configure("TLabel", background="#f0f4f8", font=("Arial", 18))
        style.configure("Header.TLabel", font=("Arial", 28, "bold"), background="#f0f4f8")

        self.frames = {}
        for F in (LoginPage, SelectionPage, EnrollPage, RecognizePage):
            frame = F(parent=self.container, controller=self)
            self.frames[F.__name__] = frame
            frame.grid(row=0, column=0, sticky='nsew')
        self.show_frame("LoginPage")

    def show_frame(self, page):
        frame = self.frames[page]
        frame.tkraise()

    def on_close(self):
        try:
            self.frames['RecognizePage'].stop_camera()
        except Exception:
            pass
        self.destroy()

import tkinter as tk
from tkinter import ttk, messagebox

VALID_USERNAME = "admin"
VALID_PASSWORD = "admin"

class LoginPage(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.focus_entry = None
        self.uppercase = False  # Track keyboard mode

        # Center frame for login UI
        container = ttk.Frame(self)
        container.pack(expand=True, anchor='center', padx=200, pady=50)

        ttk.Label(container, text='Login', font=('Arial', 32, 'bold')).pack(pady=20)

        frm = ttk.Frame(container)
        frm.pack(pady=10)

        # Username
        ttk.Label(frm, text='Username:', font=('Arial', 16)).grid(row=0, column=0, sticky='e', padx=10, pady=5)
        self.user_entry = ttk.Entry(frm, font=('Arial', 16), width=25)
        self.user_entry.grid(row=0, column=1, pady=5)
        self.user_entry.bind("<FocusIn>", lambda e: self.set_focus(self.user_entry))

        # Password
        ttk.Label(frm, text='Password:', font=('Arial', 16)).grid(row=1, column=0, sticky='e', padx=10, pady=5)
        self.pass_entry = ttk.Entry(frm, show='*', font=('Arial', 16), width=25)
        self.pass_entry.grid(row=1, column=1, pady=5)
        self.pass_entry.bind("<FocusIn>", lambda e: self.set_focus(self.pass_entry))

        # Login button
        ttk.Button(container, text='Login', command=self.do_login, width=15).pack(pady=15)

        # On-screen keyboard
        self.create_keyboard(container)

    def set_focus(self, entry):
        self.focus_entry = entry

    def insert_text(self, char):
        if self.focus_entry:
            self.focus_entry.insert(tk.END, char)

    def backspace(self):
        if self.focus_entry:
            current = self.focus_entry.get()
            self.focus_entry.delete(0, tk.END)
            self.focus_entry.insert(0, current[:-1])

    def clear_entry(self):
        if self.focus_entry:
            self.focus_entry.delete(0, tk.END)

    def toggle_case(self):
        self.uppercase = not self.uppercase
        self.update_keyboard()

    def create_keyboard(self, parent):
        self.keyboard_frame = ttk.Frame(parent)
        self.keyboard_frame.pack(pady=20)
        self.build_keys()

    def update_keyboard(self):
        for widget in self.keyboard_frame.winfo_children():
            widget.destroy()
        self.build_keys()

    def build_keys(self):
        keys = [
            ['1','2','3','4','5','6','7','8','9','0','Back'],
            ['q','w','e','r','t','y','u','i','o','p'],
            ['a','s','d','f','g','h','j','k','l'],
            ['Shift','z','x','c','v','b','n','m','Clear'],
            ['Space']
        ]

        for row in keys:
            row_frame = ttk.Frame(self.keyboard_frame)
            row_frame.pack(pady=3)
            for key in row:
                if key == 'Back':
                    ttk.Button(row_frame, text='⌫ Back', width=8, command=self.backspace).pack(side='left', padx=4)
                elif key == 'Space':
                    ttk.Button(row_frame, text='␣ Space', width=30, command=lambda k=' ': self.insert_text(k)).pack(side='left', padx=4)
                elif key == 'Shift':
                    text = '⇧ Shift ↑' if not self.uppercase else '⇩ Shift ↓'
                    ttk.Button(row_frame, text=text, width=10, command=self.toggle_case).pack(side='left', padx=4)
                elif key == 'Clear':
                    ttk.Button(row_frame, text='🧹 Clear', width=8, command=self.clear_entry).pack(side='left', padx=4)
                else:
                    char = key.upper() if self.uppercase else key.lower()
                    ttk.Button(row_frame, text=char, width=5, command=lambda k=char: self.insert_text(k)).pack(side='left', padx=4)

    def do_login(self):
        u = self.user_entry.get()
        p = self.pass_entry.get()
        if u == VALID_USERNAME and p == VALID_PASSWORD:
            self.controller.show_frame('SelectionPage')
        else:
            messagebox.showerror('Login failed', 'Invalid username / password')

class SelectionPage(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        ttk.Label(self, text="Select Mode", style="Header.TLabel").pack(pady=40)
        ttk.Button(self, text="Face Recognition", command=lambda: controller.show_frame("RecognizePage")).pack(pady=15)
        ttk.Button(self, text="Enrollment", command=lambda: controller.show_frame("EnrollPage")).pack(pady=15)
        ttk.Button(self, text="Reload / Train Recognizer", command=self.reload_train).pack(pady=15)

    def reload_train(self):
        ensure_dirs()
        load_labels()
        if train_recognizer():
            messagebox.showinfo("Training", "Trainer updated successfully")
        else:
            messagebox.showwarning("Training", "No data to train. Enroll users first.")

class EnrollPage(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        ttk.Label(self, text="Face Enrollment", style="Header.TLabel").pack(pady=40)
        frm = ttk.Frame(self)
        frm.pack(pady=20)
        ttk.Label(frm, text="Full Name:").grid(row=0, column=0, padx=10, pady=10)
        self.name_entry = ttk.Entry(frm, font=("Arial", 18))
        self.name_entry.grid(row=0, column=1, padx=10, pady=10)
        ttk.Button(self, text="Start Capture", command=self.start_capture).pack(pady=15)
        ttk.Button(self, text="Back", command=lambda: controller.show_frame("SelectionPage")).pack(pady=10)

    def start_capture(self):
        name = self.name_entry.get().strip()
        if not name:
            messagebox.showwarning("Input", "Please enter a name")
            return
        label_id = add_label(name)
        user_dir = DATA_DIR / str(label_id)
        user_dir.mkdir(parents=True, exist_ok=True)
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            messagebox.showerror("Camera", "Cannot open camera")
            return
        face_cascade = cv2.CascadeClassifier(CASCADE_PATH)
        messagebox.showinfo("Instructions", f"Look at the camera. {NUM_SAMPLES} samples will be captured.")
        count = 0
        while count < NUM_SAMPLES:
            ret, frame = cap.read()
            if not ret: break
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.1, 5)
            for (x, y, w, h) in faces:
                face = cv2.resize(gray[y:y+h, x:x+w], (IMG_WIDTH, IMG_HEIGHT))
                cv2.imwrite(str(user_dir / f"{count}.jpg"), face)
                count += 1
                cv2.rectangle(frame, (x,y), (x+w,y+h), (0,255,0), 2)
                cv2.putText(frame, f"{count}/{NUM_SAMPLES}", (10,40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,0), 2)
            cv2.imshow("Enrolling - press q to abort", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'): break
        cap.release()
        cv2.destroyAllWindows()
        if train_recognizer():
            messagebox.showinfo("Enroll", f"Enrollment complete for {name}")
        else:
            messagebox.showwarning("Enroll", "Enrollment saved but training failed")

class RecognizePage(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        ttk.Label(self, text="Face Recognition", style="Header.TLabel").pack(pady=20)
        btnfrm = ttk.Frame(self)
        btnfrm.pack(pady=10)
        ttk.Button(btnfrm, text="Back", command=self.back).grid(row=0, column=0, padx=8)
        ttk.Button(btnfrm, text="Send LOCK", command=send_lock).grid(row=0, column=1, padx=8)
        ttk.Button(btnfrm, text="Send UNLOCK (Test)", command=send_unlock).grid(row=0, column=2, padx=8)

        self.video_panel = ttk.Label(self)
        self.video_panel.pack(pady=20)

        self.cap = None
        self.stop_event = threading.Event()
        self.face_cascade = cv2.CascadeClassifier(CASCADE_PATH)
        load_labels(); load_trainer()

        ttk.Button(self, text="Start Camera", command=self.start_camera).pack(pady=10)
        ttk.Button(self, text="Stop Camera", command=self.stop_camera).pack(pady=10)

    def back(self):
        self.stop_camera()
        self.controller.show_frame("SelectionPage")

    def start_camera(self):
        if self.cap and self.cap.isOpened():
            messagebox.showinfo("Camera", "Camera already running")
            return
        self.stop_event.clear()
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            messagebox.showerror("Camera", "Cannot open camera")
            return
        threading.Thread(target=self.video_loop, daemon=True).start()

    def stop_camera(self):
        if self.cap:
            self.stop_event.set()
            time.sleep(0.2)
            self.cap.release()
            self.cap = None
            self.video_panel.config(image="")

    def video_loop(self):
        global face_recognizer
        recognized_recently = False
        recognized_name = None
        while not self.stop_event.is_set():
            ret, frame = self.cap.read()
            if not ret: continue
            display = frame.copy()
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self.face_cascade.detectMultiScale(gray, 1.1, 5)
            for (x, y, w, h) in faces:
                face_resized = cv2.resize(gray[y:y+h, x:x+w], (IMG_WIDTH, IMG_HEIGHT))
                name, conf = "Unknown", 100
                if face_recognizer:
                    try:
                        id_pred, conf = face_recognizer.predict(face_resized)
                        if conf < CONFIDENCE_THRESHOLD:
                            name = labels.get(id_pred, "Unknown")
                    except Exception:
                        pass
                color = (0,255,0) if name != "Unknown" else (0,0,255)
                cv2.rectangle(display, (x,y), (x+w,y+h), color, 2)
                cv2.putText(display, f"{name} ({conf:.1f})", (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
                if name != "Unknown" and (not recognized_recently or recognized_name != name):
                    send_unlock()
                    recognized_recently, recognized_name = True, name
                    threading.Thread(target=speak, args=(f"Welcome {name}, door is open.",), daemon=True).start()
                elif name == "Unknown" and not recognized_recently:
                    recognized_recently = True
                    threading.Thread(target=self.handle_unknown).start()
            if len(faces) == 0:
                recognized_recently = False
            img = Image.fromarray(cv2.cvtColor(display, cv2.COLOR_BGR2RGB))
            imgtk = ImageTk.PhotoImage(img.resize((1000, 600)))
            self.video_panel.imgtk = imgtk
            self.video_panel.config(image=imgtk)
            time.sleep(0.001)

    def handle_unknown(self):
        speak("I did not recognize you. Which part of the hospital are you looking for?")
        text = listen_and_extract()
        reply = analyze_keywords(text)
        if reply:
            speak(reply)
        else:
            speak("Sorry, I could not find that area. Please ask staff for assistance.")
        send_lock()

# ------------------------- Main -------------------------
def main():
    ensure_dirs()
    load_labels()
    load_trainer()
    app = App()
    app.mainloop()

if __name__ == "__main__":
    main()
