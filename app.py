import os
import sqlite3
import streamlit as st
import tempfile
import subprocess
import numpy as np
from scipy.io import wavfile
import pandas as pd
import matplotlib.pyplot as plt

# ---------------- CONFIG ----------------
st.set_page_config("Guardian OTT: DSSS Anti-Piracy", layout="wide")
DB = "users.db"
VIDEO_DIR = "storage/videos"
os.makedirs(VIDEO_DIR, exist_ok=True)

# ---------------- DSSS CONSTANTS ----------------
BIT_SAMPLES = 22050
GAIN = 150.0
ID_BITS = 16

def get_pn_sequence(n, seed=42):
    np.random.seed(seed)
    return np.random.choice([-1, 1], size=n).astype(np.float32)

# ---------------- VISUALIZATION FUNCTIONS ----------------

def plot_original_audio(samples):

    fig, ax = plt.subplots(figsize=(10,4))

    ax.plot(samples[:5000])
    ax.set_title("Original Extracted Audio Signal")
    ax.set_xlabel("Sample Index")
    ax.set_ylabel("Amplitude")

    plt.savefig("original_audio_signal.png", dpi=300)

    st.pyplot(fig)


def plot_watermarked_audio(samples):

    fig, ax = plt.subplots(figsize=(10,4))

    ax.plot(samples[:5000])
    ax.set_title("DSSS Watermarked Audio Signal")
    ax.set_xlabel("Sample Index")
    ax.set_ylabel("Amplitude")

    plt.savefig("watermarked_audio_signal.png", dpi=300)

    st.pyplot(fig)


def plot_waveform_comparison(original, watermarked):

    fig, ax = plt.subplots(figsize=(10,4))

    ax.plot(original[:5000], label="Original Audio")
    ax.plot(watermarked[:5000], label="Watermarked Audio", alpha=0.7)

    ax.set_title("Waveform Comparison (Original vs Watermarked)")
    ax.set_xlabel("Sample Index")
    ax.set_ylabel("Amplitude")
    ax.legend()

    plt.savefig("waveform_comparison.png", dpi=300)

    st.pyplot(fig)


def plot_correlation_detection(samples):

    pn = get_pn_sequence(BIT_SAMPLES)

    segment = samples[:BIT_SAMPLES]
    correlation = np.sum(segment * pn)

    fig, ax = plt.subplots(figsize=(6,3))

    ax.bar(["Correlation Value"], [correlation])

    ax.set_title("Watermark Correlation Detection")
    ax.set_ylabel("Correlation Strength")

    plt.savefig("correlation_detection.png", dpi=300)

    st.pyplot(fig)

# ---------------- DATABASE ----------------
conn = sqlite3.connect(DB, check_same_thread=False)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS users(
id INTEGER PRIMARY KEY AUTOINCREMENT,
username TEXT UNIQUE,
password TEXT,
phone TEXT)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS videos(
id INTEGER PRIMARY KEY AUTOINCREMENT,
filename TEXT,
path TEXT,
uploaded_by INTEGER)
""")

conn.commit()

# ---------------- WATERMARK CORE ----------------

def embed_watermark(samples, user_id):

    samples = samples.astype(np.float32)

    bits = np.array(list(np.binary_repr(user_id, width=ID_BITS)), dtype=int)
    bits = bits * 2 - 1

    pn = get_pn_sequence(BIT_SAMPLES)

    frame_size = ID_BITS * BIT_SAMPLES
    num_frames = len(samples) // frame_size

    for f in range(num_frames):

        for i, b in enumerate(bits):

            start = (f * frame_size) + (i * BIT_SAMPLES)
            end = start + BIT_SAMPLES

            if end <= len(samples):
                samples[start:end] += (b * pn * GAIN)

    return np.clip(samples, -32768, 32767).astype(np.int16)


def extract_watermark(samples):

    samples = samples.astype(np.float32)

    pn = get_pn_sequence(BIT_SAMPLES)

    frame_size = ID_BITS * BIT_SAMPLES
    num_frames = len(samples) // frame_size

    all_recovered_ids = []

    for f in range(num_frames):

        bits = ""

        for i in range(ID_BITS):

            start = (f * frame_size) + (i * BIT_SAMPLES)
            end = start + BIT_SAMPLES

            seg = samples[start:end]

            correlation = np.sum(seg * pn)

            bits += "1" if correlation > 0 else "0"

        try:

            recovered_id = int(bits, 2)

            if recovered_id > 0:
                all_recovered_ids.append(recovered_id)

        except:
            continue

    if not all_recovered_ids:
        return 0

    return max(set(all_recovered_ids), key=all_recovered_ids.count)

# ---------------- FFMPEG ----------------

def extract_audio(video, wav):

    subprocess.run([
        "ffmpeg","-y","-i",video,
        "-vn","-ac","1","-ar","44100",
        "-acodec","pcm_s16le",wav
    ], check=True, capture_output=True)


def merge_audio(video, wav, out):

    subprocess.run([
        "ffmpeg","-y",
        "-i",video,
        "-i",wav,
        "-c:v","copy",
        "-map","0:v:0",
        "-map","1:a:0",
        "-b:a","192k",
        out
    ], check=True, capture_output=True)

# ---------------- SESSION ----------------

if "user" not in st.session_state:
    st.session_state.user = None

# ---------------- LOGIN ----------------

if not st.session_state.user:

    st.title("🛡️ Guardian OTT Login")

    t1, t2 = st.tabs(["Login","Register"])

    with t1:

        u = st.text_input("Username")
        p = st.text_input("Password", type="password")

        if st.button("Login"):

            c.execute("SELECT id FROM users WHERE username=? AND password=?", (u,p))
            row = c.fetchone()

            if row:

                st.session_state.user = row[0]
                st.rerun()

            else:

                st.error("Invalid Login")

    with t2:

        ru = st.text_input("New Username")
        rp = st.text_input("New Password", type="password")
        rph = st.text_input("Phone")

        if st.button("Register"):

            try:

                c.execute(
                    "INSERT INTO users(username,password,phone) VALUES (?,?,?)",
                    (ru,rp,rph)
                )

                conn.commit()

                st.success("Registration Successful!")

            except:

                st.error("User already exists")

    st.stop()

# ---------------- MAIN APP ----------------

uid = st.session_state.user

tabs = st.tabs(["🎧 Watermark","🔍 Detect","📂 Library","👥 Users","🚪 Logout"])

# ---------------- WATERMARK TAB ----------------

with tabs[0]:

    st.header("Apply DSSS Watermark")

    vid = st.file_uploader("Upload Master Video", type=["mp4","mkv"])

    if vid and st.button("Protect Video"):

        with tempfile.TemporaryDirectory() as tmp:

            in_vid = os.path.join(tmp, vid.name)
            wav = os.path.join(tmp, "a.wav")
            wm_wav = os.path.join(tmp, "wm.wav")

            secure_filename = f"secured_u{uid}_{vid.name}"
            out_vid_path = os.path.join(VIDEO_DIR, secure_filename)

            open(in_vid,"wb").write(vid.read())

            extract_audio(in_vid, wav)

            sr, samples = wavfile.read(wav)

            wm_samples = embed_watermark(samples, uid)

            st.subheader("Audio Visualization")

            plot_original_audio(samples)

            plot_watermarked_audio(wm_samples)

            plot_waveform_comparison(samples, wm_samples)

            wavfile.write(wm_wav, sr, wm_samples)

            merge_audio(in_vid, wm_wav, out_vid_path)

            c.execute(
                "INSERT INTO videos(filename,path,uploaded_by) VALUES(?,?,?)",
                (vid.name,out_vid_path,uid)
            )

            conn.commit()

            st.success("Security Layer Applied!")

            st.video(out_vid_path)

# ---------------- DETECTION TAB ----------------

with tabs[1]:

    st.header("Identify Leak")

    leak_vid = st.file_uploader("Upload Pirated Clip", type=["mp4","mkv"], key="d")

    if leak_vid and st.button("Run Deep Scan"):

        with tempfile.TemporaryDirectory() as tmp:

            v = os.path.join(tmp, leak_vid.name)
            wav = os.path.join(tmp, "d.wav")

            open(v,"wb").write(leak_vid.read())

            extract_audio(v, wav)

            sr, samples = wavfile.read(wav)

            st.subheader("Detection Visualization")

            plot_correlation_detection(samples)

            wid = extract_watermark(samples)

            c.execute("SELECT username, phone FROM users WHERE id=?", (wid,))
            user = c.fetchone()

            if user:

                st.error(f"🚨 PIRACY DETECTED: User {user[0]} (ID: {wid})")
                st.warning(f"Contact Info: {user[1]}")

            else:

                st.success("No piracy signature detected.")

# ---------------- LIBRARY ----------------

with tabs[2]:

    st.header("Storage Vault")

    c.execute("""
        SELECT videos.id, videos.filename, videos.path, users.username
        FROM videos
        JOIN users ON users.id = videos.uploaded_by
    """)

    rows = c.fetchall()

    if rows:

        for vid_id, fname, fpath, uname in rows:

            st.subheader(f"Video: {fname}")
            st.write(f"🔐 Secured for User: {uname}")

            if os.path.exists(fpath):

                st.video(fpath)

            st.divider()

# ---------------- USERS ----------------

with tabs[3]:

    st.header("User Directory")

    users = pd.read_sql_query(
        "SELECT id, username, phone FROM users",
        conn
    )

    st.dataframe(users, use_container_width=True)

# ---------------- LOGOUT ----------------

with tabs[4]:

    if st.button("Logout Session"):

        st.session_state.user = None
        st.rerun()


