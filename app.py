import streamlit as st
import numpy as np
import tempfile
import subprocess
from scipy.io import wavfile
import matplotlib.pyplot as plt
import os

st.set_page_config(page_title="Video Watermarking", layout="centered")

# DSSS PARAMETERS
BIT_SAMPLES = 22050
GAIN = 150.0
ID_BITS = 16


def get_pn_sequence(n, seed=42):
    np.random.seed(seed)
    return np.random.choice([-1,1], size=n).astype(np.float32)


def embed_watermark(samples, user_id):

    samples = samples.astype(np.float32)

    bits = np.array(list(np.binary_repr(user_id, width=ID_BITS)), dtype=int)
    bits = bits*2 - 1

    pn = get_pn_sequence(BIT_SAMPLES)

    frame_size = ID_BITS * BIT_SAMPLES
    num_frames = len(samples)//frame_size

    for f in range(num_frames):

        for i,b in enumerate(bits):

            start = (f*frame_size)+(i*BIT_SAMPLES)
            end = start + BIT_SAMPLES

            if end <= len(samples):
                samples[start:end] += (b*pn*GAIN)

    return np.clip(samples,-32768,32767).astype(np.int16)


def extract_audio(video,wav):

    subprocess.run([
        "ffmpeg","-y",
        "-i",video,
        "-vn","-ac","1","-ar","44100",
        "-acodec","pcm_s16le",
        wav
    ])


def merge_audio(video,wav,out):

    subprocess.run([
        "ffmpeg","-y",
        "-i",video,
        "-i",wav,
        "-c:v","copy",
        "-map","0:v:0",
        "-map","1:a:0",
        out
    ])


# -------- GRAPH FUNCTIONS --------

def plot_original(samples):

    fig,ax = plt.subplots(figsize=(8,3))

    ax.plot(samples[:5000])
    ax.set_title("Original Extracted Audio Signal")
    ax.set_xlabel("Sample Index")
    ax.set_ylabel("Amplitude")

    plt.savefig("original_audio.png", dpi=300)

    st.pyplot(fig)


def plot_watermarked(samples):

    fig,ax = plt.subplots(figsize=(8,3))

    ax.plot(samples[:5000])
    ax.set_title("DSSS Watermarked Audio Signal")
    ax.set_xlabel("Sample Index")
    ax.set_ylabel("Amplitude")

    plt.savefig("watermarked_audio.png", dpi=300)

    st.pyplot(fig)


def plot_waveform(original,watermarked):

    fig,ax = plt.subplots(figsize=(8,3))

    ax.plot(original[:5000],label="Original")
    ax.plot(watermarked[:5000],label="Watermarked",alpha=0.7)

    ax.legend()
    ax.set_title("Waveform Comparison")
    ax.set_xlabel("Sample Index")
    ax.set_ylabel("Amplitude")

    plt.savefig("waveform_comparison.png", dpi=300)

    st.pyplot(fig)


# -------- STREAMLIT UI --------

st.title("🎬 DSSS Video Watermarking")

user_id = st.number_input("Enter User ID", min_value=1)

video = st.file_uploader("Upload Video", type=["mp4","mkv"])

if video and st.button("Embed Watermark"):

    with tempfile.TemporaryDirectory() as tmp:

        input_video = os.path.join(tmp,video.name)
        open(input_video,"wb").write(video.read())

        audio = os.path.join(tmp,"audio.wav")
        wm_audio = os.path.join(tmp,"wm.wav")

        output_video = os.path.join(tmp,"watermarked.mp4")

        extract_audio(input_video,audio)

        sr,samples = wavfile.read(audio)

        # Graph 1: Original audio
        plot_original(samples)

        wm_samples = embed_watermark(samples,user_id)

        # Graph 2: Watermarked audio
        plot_watermarked(wm_samples)

        # Graph 3: Comparison
        plot_waveform(samples,wm_samples)

        wavfile.write(wm_audio,sr,wm_samples)

        merge_audio(input_video,wm_audio,output_video)

        st.success("Watermark Embedded Successfully")

        st.video(output_video)

        with open(output_video,"rb") as f:

            st.download_button(
                "Download Watermarked Video",
                f,
                file_name="watermarked_video.mp4"
            )
