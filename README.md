# Exam Proctoring System

This project is a **real-time exam proctoring system** using audio and face verification. It allows recording voices and verifying faces during exams to prevent cheating.

---

## 🖥️ Prerequisites

* Python 3.11
* Git
* [ffmpeg](https://www.gyan.dev/ffmpeg/builds/) install (ffmpeg-git-essentials.7z) and add to PATH 

---

## ⚡ Installation

1. **Clone the repository**

```bash
git clone https://github.com/<your-username>/exam-proctoring-system.git
cd exam-proctoring-system
```

2. **Create a virtual environment**

```bash
# Windows
py -3.11 -m venv .venv311

# Activate the environment
# PowerShell
.venv311\Scripts\Activate.ps1
# or CMD
.venv311\Scripts\activate.bat
```

3. **Install dependencies**

```bash
pip install --upgrade pip
pip install -r requirements.txt --use-deprecated=legacy-resolver
```

> ⚠️ Make sure you have the correct version of Python (3.11) to avoid dependency conflicts.

---

## 🧰 Running the Project

1. **Start the Flask server**

```bash
python app.py
```

2. **Open your browser** at:

```
http://127.0.0.1:5000
```

3. **Test the functionality**


---

## 📝 Notes

* **Database**: The project uses `database.db` (SQLite). If you want to reset, delete the file and rerun the app.
* **Uploads**: `static/faces/` and `static/voices/` are ignored in Git.

---

## 💡 Tips

* Always activate the virtual environment before running any Python scripts.
* If you encounter errors related to **NumPy or TensorFlow**, ensure your virtual environment has Python 3.11 and `numpy<2`.

---

