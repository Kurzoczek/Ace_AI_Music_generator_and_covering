# -*- coding: utf-8 -*-
# GENERATED FILE - do not edit by hand. Source: generate_small_pro_ace_android.py, builder: tools/build_ace_core.py
# Music analysis, notation, MIDI, export and cover helpers shared with the desktop/Termux scripts.
import os
import sys
import gc
import time
import json
import re
import struct
import shutil
import hashlib
import threading
import subprocess
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from xml.sax.saxutils import escape as _xml_escape

import numpy as np

import wavsf as sf

requests = None          # Ollama is not used in the app
torch = None             # PyTorch is not used in the app

# Paths - set by ace_android.configure() before anything runs
WORKSPACE_DIR = Path(".")
INPUT_DIR = Path(".")
OUTPUT_DIR = Path(".")
TEMP_DIR = Path(".")
TEMPLATES_DIR = Path(".")
MODE_DESCRIPTION = "Android: acestep.cpp (CPU)"


_URL_GGUF = "https://huggingface.co/Serveurperso/ACE-Step-1.5-GGUF/resolve/main/"


_GGUF_QUANTS = ("Q8_0", "Q6_K", "Q5_K_M", "Q4_K_M", "BF16")


def gguf_dit_name(model, quant):
    """acestep-v15-turbo + Q8_0 -> acestep-v15-turbo-Q8_0.gguf (this is how the Serveurperso/ACE-Step-1.5-GGUF repository names its files)."""
    return f"{model}-{quant}.gguf"


def gguf_lm_name(size_val, quant="Q8_0"):
    if not size_val:
        return None
    if size_val == "4B":
        return f"acestep-5Hz-lm-4B-{quant if quant in ('Q8_0', 'Q6_K', 'Q5_K_M', 'BF16') else 'Q5_K_M'}.gguf"
    return f"acestep-5Hz-lm-{size_val}-{'BF16' if quant == 'BF16' else 'Q8_0'}.gguf"


NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def _note_name(midi_no):
    return f"{NOTE_NAMES[midi_no % 12]}{(midi_no // 12) - 1}"


def _detect_lines(mag, freqs, f_min, f_max, rel_threshold, num_steps):
    mask = (freqs >= f_min) & (freqs <= f_max)
    f_band, m_band = freqs[mask], mag[mask, :]
    if m_band.size == 0:
        return [0] * num_steps, []
    threshold = np.max(m_band) * rel_threshold
    midi, names = [], []
    for idx in range(num_steps):
        if idx < m_band.shape[1] and np.max(m_band[:, idx]) > threshold:
            f = f_band[np.argmax(m_band[:, idx])]
            n = int(round(69.0 + 12.0 * np.log2(f / 440.0)))
            midi.append(n)
            item_name = _note_name(n)
            if not names or names[-1] != item_name:
                names.append(item_name)
        else:
            midi.append(0)
    return midi, names


def recognize_notes_bg_cpu(y_np, sr, num_steps=32):
    """Runs on CPU cores in parallel while the GPU/XPU is working.
    One step = one beat. Bass computed on a long FFT window (accuracy in low bands)."""
    min_len = 2 * 16384
    if len(y_np) < min_len:
        y_np = np.pad(y_np, (0, min_len - len(y_np)))
    hop = max(256, len(y_np) // max(1, num_steps))

    mag_lead = _stft_mag(y_np, 4096, hop)
    freqs_lead = np.linspace(0, sr / 2.0, 4096 // 2 + 1)
    mag_bass = _stft_mag(y_np, 16384, hop)
    freqs_bass = np.linspace(0, sr / 2.0, 16384 // 2 + 1)

    midi_bass, names_bass = _detect_lines(mag_bass, freqs_bass, 35.0, 180.0, 0.15, num_steps)
    midi_lead, names_lead = _detect_lines(mag_lead, freqs_lead, 200.0, 3200.0, 0.12, num_steps)

    return {
        "bass_str": " -> ".join(names_bass[:8]) if names_bass else "sub-bass pulse",
        "lead_str": " -> ".join(names_lead[:10]) if names_lead else "dark synth pad",
        "bass_midi": midi_bass,
        "lead_midi": midi_lead,
    }


def save_native_midi(midi_path, grid_lead, grid_bass, bpm):
    """Writes a standard SMF Format 1 (.mid) file directly in binary, without external libraries."""
    def varlen(val):
        buf = [val & 0x7F]
        val >>= 7
        while val > 0:
            buf.insert(0, (val & 0x7F) | 0x80)
            val >>= 7
        return bytes(buf)

    def build_track(note_list, channel=0, velocity=100, add_tempo=False):
        events = bytearray()
        if add_tempo:
            mpqn = int(60000000 / max(1.0, float(bpm)))
            events += b'\x00\xFF\x51\x03' + mpqn.to_bytes(3, 'big')
        curr = 0
        dt = 0
        step_ticks = 480  # 1 step = 1 beat (resolution 480 ticks per quarter note)
        for n in [x for seg in note_list for x in seg]:
            if n != curr:
                if curr > 0:
                    events += varlen(dt) + bytes([0x80 | channel, curr & 0x7F, 0])
                    dt = 0
                if n > 0:
                    events += varlen(dt) + bytes([0x90 | channel, n & 0x7F, velocity])
                    dt = 0
                curr = n
            dt += step_ticks
        if curr > 0:
            events += varlen(dt) + bytes([0x80 | channel, curr & 0x7F, 0])
        events += b'\x00\xFF\x2F\x00'
        return b'MTrk' + struct.pack('>I', len(events)) + bytes(events)

    header = b'MThd' + struct.pack('>IHHH', 6, 1, 2, 480)
    t1 = build_track(grid_lead, channel=0, velocity=105, add_tempo=True)
    t2 = build_track(grid_bass, channel=1, velocity=115, add_tempo=False)
    with open(midi_path, 'wb') as f:
        f.write(header + t1 + t2)


ACE_MODEL_DIT = "acestep-v15-turbo"          # acestep-v15-turbo (fast, 8 steps) | acestep-v15-sft (better quality, slower) | acestep-v15-base


MODEL_ID = ACE_MODEL_DIT


MODEL_LARGE = False                 # kept for compatibility with old code


ACE_STEPS = 8                       # turbo: 8; sft/base: 32-60 (each step takes longer on CPU)


ACE_GUIDANCE = None                   # None = model default


ACE_LOG_LEVEL = "detailed"         # "basic" (console only) | "detailed" (function calls, data, model layers) | "full" (EVERY line and variable change + model operations; very slow)


ACE_LOG_MAX_MB = 2048                # log size limit (MB); once exceeded, details are skipped


ACE_LOG_PROFILER_STEPS = 2            # full level: how many diffusion steps to record with the PyTorch profiler (each operation: name, shapes, time)


RESOURCE_PROFILE = "balanced"       # "economical" (1/2 of cores, low priority - the computer stays usable) | "balanced" | "maximum" (all cores, high priority)


ACE_ENGINE = "cpp"                    # "auto" (C++ when installed, otherwise PyTorch) | "cpp" (acestep.cpp, GGUF - light) | "pytorch"


ACE_DEVICE = "cpu"                # "cpu" | "gpu" | "cpu+gpu" (GPU + offloading to RAM). C++: GPU = Vulkan/CUDA, PyTorch: CUDA/XPU/MPS


ACE_GGUF_QUANT = "Q8_0"               # C++ engine: Q8_0 (most faithful) | Q6_K | Q5_K_M | Q4_K_M (least RAM) | BF16


ACE_CPP_LM = "0.6B"                   # C++ engine, text mode: language model that plans the structure ("" = none, "0.6B", "1.7B", "4B")


ACE_SWAP_FILE = None               # "own swap" for model weights (PyTorch engine, CPU computation): a directory or file on any


ACE_SWAP_FILE_KEEP = False       # True = do not delete the swap file when done (diagnostics only)


ACE_COVER_NOISE = 0.0                  # cover: how much noise to mix into the original at the start (0 = clean original; C++ and newer ACE-Step)


ACE_THREADS = max(1, os.cpu_count() or 4)


ACE_QUANTIZATION = None                # "int8_weight_only" | "fp8_weight_only" | "w8a8_dynamic" (handled by the ACE-Step handler; requires torchao, can be slow on CPU)


ACE_BF16 = True                       # PyTorch engine: weights in bfloat16 from loading (about half the RAM; on CPUs without native bf16 computation may be slower)


ACE_GENERATION_LIMIT_SEC = 72 * 3600 # time limit for one generation in ACE-Step (default was 600 s); 72 h


ACE_CPU_OFFLOAD = True             # keep unused modules outside the active computation (less RAM)


ACE_USE_LM = False                   # 5Hz language model - a lot of RAM, disabled on 8 GB


ACE_MODEL_LM = "acestep-5Hz-lm-0.6B"


ACE_LOW_RAM = True              # True: Ollama and ACE-Step do NOT work simultaneously (required with 8 GB RAM)


ACE_MODE = "cover"                    # "cover" = remake of YOUR track (keeps structure, tempo, melody); "text" = new track from the description


ACE_COVER_STRENGTH = 0.5                 # 0.0-1.0: how much of the original remains (1.0 = very close; approx. 0.2 = style only, per the ACE-Step docs)


ACE_COVER_WHOLE_FILE = True            # cover: number of sections chosen to cover the whole input file


ACE_COVER_MAX_SEC = None             # cover: length limit in seconds (None = whole track)


ACE_COVER_FRAGMENTS = []              # cover when ACE_COVER_WHOLE_FILE=False: list of [start, end] in seconds, e.g. [[30, 75], [120, 165]]


ACE_COVER_FRAGMENTS_MODE = "insert"    # "insert" = remade fragments, rest of the track original | "separate" = only the remade fragments, one after another


ACE_NUM_PASSES = 0                # when ACE_WHOLE_TRACK=False: how many passes to split generation into (0 = as many as sections); less RAM per pass


ACE_WHOLE_TRACK = True                 # True = WHOLE track in one pass (coherent, no gaps); False = section by section


ACE_MARGIN_SEC = 6.0                # section mode: generate with a margin and take the middle (ACE-Step fades the start/end of short fragments)


ACE_USE_REFERENCE = True            # fragment of the input file as reference audio (style/timbre)


ACE_REFERENCE_MODE = "input"       # "input" = window from the input file | "previous" = end of the previous section (consistent sound)


ACE_REFERENCE_LEN_SEC = 30.0


ACE_STYLE_TEMPLATES = []                 # template tracks (target style): file names from the templates/ directory or full paths;


ACE_LYRICS = "[Instrumental]"


ACE_INSTRUMENTAL = True


ACE_SEED = -1                         # -1 = random; otherwise seed + section number


ACE_MAX_RETRIES = 3


ACE_START_TIMEOUT_SEC = 7200          # start (on the first run includes downloading the models)


ACE_SECTION_TIMEOUT_SEC = ACE_GENERATION_LIMIT_SEC + 1800


ACE_SR = 48000


_ACE_WHOLE = ACE_WHOLE_TRACK or ACE_MODE == "cover"   # cover always computes the whole track at once


OLLAMA_MODEL = "llama3.2"


NUM_SEGMENTS = 6


TEMPERATURE = 0.85


GUIDANCE_SCALE = 4.5


USE_OLLAMA = True


AUTOINSTALL_OLLAMA = True  # when Ollama (or the model) is missing - install/download automatically


STEM_SEPARATION = True                      # False = behaves like the regular version (full mix)


MODEL_DEMUCS = "htdemucs_6s"                 # 6 stems: drums, bass, other, vocals, guitar, piano ("htdemucs" = 4 stems, "htdemucs_ft" = more accurate, 4x slower)


SEPARATION_SHIFTS = 0                   # shifts in Demucs: 0 = fastest (CPU), 1-2 = slightly better quality, slower


AUTOINSTALL_DEMUCS = True                # when the demucs library is missing - install it; if that fails - fallback separator (HPSS)


NEURAL_CLASSIFIER = True                # the AST network (AudioSet) recognizes the instrument in each stem


CLASSIFIER_MODEL = "MIT/ast-finetuned-audioset-10-10-0.4593"


STEM_PRESENCE_THRESHOLD_DB = -32.0              # a stem quieter than the mix by more than this many dB is considered absent


EXPORT_STEMS = True                        # save the stems of each section to the stems/ directory


STEMS_ALL_FORMATS = True               # True = mono+stereo+surround, False = mono only (faster on a slow drive)


STEM_CACHE = True                          # caches Demucs results in workspace/stem_cache (subsequent runs are fast)


CROSSFADE_SEC = 0.4


MAX_SEGMENT_LEN_SEC = 60.0  # ACE-Step copes with longer fragments (min. 10 s)


SCRIPT_SUBDIR = "small_pro_ace"


CHANNEL_FORMATS = ("mono", "stereo", "surround")  # versions of every audio file; surround = pseudo 5.1


WAV_SUBTYPE = "PCM_24"


EXPORT_NOTATION = True          # MusicXML + LilyPond + text


EXPORT_SAMPLES = True           # 1- and 2-bar loops and band stems


EXPORT_USED_SOUNDS = True # slices of the input file used for analysis / as melody


DEFAULT_USER_DESCRIPTION = "professional hardstyle and dark synth-goth, massive distorted reverse bass, soaring detuned supersaw"


ALL_AUDIO_FORMATS = {
    ".opus", ".mp3", ".wav", ".flac", ".ogg", ".m4a", ".wma", ".aac",
    ".aiff", ".aif", ".alac", ".ape", ".wv", ".mp2", ".webm", ".mp4"
}


MAJOR_PROFILE = np.array([1.0, 0.1, 0.7, 0.1, 0.7, 0.7, 0.1, 0.8, 0.1, 0.7, 0.1, 0.7])


MINOR_PROFILE = np.array([1.0, 0.1, 0.7, 0.7, 0.1, 0.7, 0.1, 0.8, 0.7, 0.1, 0.7, 0.1])


def _norm_vector(v):
    v = np.asarray(v, dtype=np.float64)
    v = v - v.mean()
    return v / max(1e-9, np.linalg.norm(v))


def detect_tempo(audio_np, sr, defaults=150.0):
    """Tempo from the autocorrelation of onset strength (spectral flux, 200 frames/s), parabolic interpolation.
    Analyzes up to 120 s from the middle of the recording. Result folded into the 90-180 BPM range."""
    env_sr = 200
    max_samples = int(120 * sr)
    if len(audio_np) > max_samples:
        start = (len(audio_np) - max_samples) // 2
        audio_np = audio_np[start:start + max_samples]
    if len(audio_np) < sr * 4:
        return defaults
    mag = _stft_mag(audio_np, 1024, max(1, sr // env_sr))
    lm = np.log1p(1000.0 * mag)
    onset = np.maximum(0.0, np.diff(lm, axis=1, prepend=lm[:, :1])).sum(axis=0)
    onset = onset - onset.mean()
    nfft = 1 << int(np.ceil(np.log2(2 * len(onset))))
    spectrum = np.fft.rfft(onset, nfft)
    ac = np.fft.irfft(spectrum * np.conj(spectrum), nfft)[: len(onset)]
    ac = ac / np.arange(len(onset), 0, -1)  # compensation for the decreasing overlap
    ac = ac / max(1e-12, ac[0])
    min_lag = int(env_sr * 60 / 180)
    max_lag = min(int(env_sr * 60 / 60), len(ac) - 2)
    if max_lag <= min_lag:
        return defaults
    best = int(np.argmax(ac[min_lag:max_lag + 1])) + min_lag
    lag = float(best)
    a, b, c = ac[best - 1], ac[best], ac[best + 1]
    denominator = a - 2.0 * b + c
    if abs(denominator) > 1e-12:
        lag += 0.5 * (a - c) / denominator
    bpm = 60.0 * env_sr / lag
    while bpm < 90:
        bpm *= 2
    while bpm >= 180:
        bpm /= 2
    return round(float(bpm), 1)


def detect_key(chroma):
    avg_val = _norm_vector(np.mean(chroma, axis=1))
    best, key_id = -2.0, "F minor"
    for i in range(12):
        for res_profile, run_mode in ((MAJOR_PROFILE, "major"), (MINOR_PROFILE, "minor")):
            outcome = float(np.dot(avg_val, _norm_vector(np.roll(res_profile, i))))
            if outcome > best:
                best = outcome
                key_id = f"{NOTE_NAMES[i]} {run_mode}"
    return key_id


def analyze_base_audio(audio_np, sr, file_name):
    print(f"\n[ANALYSIS] Analyzing file '{file_name}' to determine tempo and key...")
    max_samples = int(120 * sr)  # the key is constant, so a fragment from the middle is enough (saves RAM)
    fragment = audio_np
    if len(fragment) > max_samples:
        start = (len(fragment) - max_samples) // 2
        fragment = fragment[start:start + max_samples]
    # long FFT window and a 130 Hz lower bound - in the low band semitones smeared into neighboring notes
    chroma = native_chromagram_pytorch(fragment, sr, n_fft=8192, hop_length=512, fmin=130.0, fmax=5000.0)
    detected_bpm = detect_tempo(audio_np, sr)
    detected_key = detect_key(chroma)

    print("=" * 60)
    print(f" 🎵 ANALYSIS REPORT: {file_name}")
    print("=" * 60)
    print(f" • Detected tempo (BPM): {detected_bpm}")
    print(f" • Detected key        : {detected_key}")
    print("=" * 60)

    return detected_bpm, detected_key


def get_section_label_and_description(segment_num, all_segments):
    if segment_num == 1:
        return "intro", "atmospheric dark synth-goth intro, hypnotic dark arpeggio, deep sub-bass pulse"
    elif segment_num == 2:
        return "build_up", "mid-intro build-up, driving hardstyle kick drum entering, dark gothic synth lead melody"
    elif segment_num in (3, 4):
        return "climax_drop", "main climax euphoric dark hardstyle drop, massive distorted kick bass, soaring dark supersaw synth melody"
    elif segment_num == all_segments - 1:
        return "climax_variation", "second climax variation, industrial synth-goth counter-melody, heavy reverse bass groove"
    else:
        return "outro", "structured outro, steady hardstyle kick drum, dark atmospheric gothic synth pads, clean decay"


ANALYSIS_MAX_SEC = 600          # we analyze at most this many seconds from the beginning of the file


ANALYSIS_FFT = 2048


ANALYSIS_HOP = 512


_CHORD_MATRIX = None


def _stft_blocks(audio_np, sr, n_fft=ANALYSIS_FFT, hop=ANALYSIS_HOP, block_sec=30.0):
    """Generator returning (magnitudes [bins x frames]) of consecutive blocks; continuous frames, no gaps."""
    block_len = int(block_sec * sr) // hop * hop
    for start in range(0, len(audio_np), block_len):
        fragment = audio_np[start:start + block_len]
        if len(fragment) < hop * 4:
            break
        mag = _stft_mag(fragment, n_fft, hop)
        yield mag[:, :max(1, len(fragment) // hop)]


def _chroma_map(sr, n_fft, fmin=130.0, fmax=4000.0):
    f = np.arange(n_fft // 2 + 1) * sr / n_fft
    mapping = np.zeros((len(f), 12), dtype=np.float32)
    for k, fk in enumerate(f):
        if fmin <= fk <= fmax:
            mapping[k, (int(round(12 * np.log2(fk / 440.0))) + 9) % 12] = 1.0
    return mapping


def frame_features(audio_np, sr):
    """Per-frame features (hop 512): RMS energy, centroid (Hz), bass share (<250 Hz), spectral flatness, flux, chroma."""
    n_fft, hop = ANALYSIS_FFT, ANALYSIS_HOP
    f = np.arange(n_fft // 2 + 1) * sr / n_fft
    mask_bass = (f < 250.0).astype(np.float32)
    mask_flat = ((f >= 500.0) & (f <= 8000.0))
    mapping = _chroma_map(sr, n_fft)
    outcome = {k: [] for k in ("rms", "centroid", "bass", "flat", "flux", "chroma")}
    previous = None
    for mag in _stft_blocks(audio_np, sr):
        mag = mag.astype(np.float32)
        power = mag ** 2
        total = power.sum(axis=0) + 1e-12
        outcome["rms"].append(np.sqrt(total) / np.sqrt(n_fft))
        outcome["centroid"].append((mag * f[:, None]).sum(axis=0) / (mag.sum(axis=0) + 1e-12))
        outcome["bass"].append((power * mask_bass[:, None]).sum(axis=0) / total)
        band = mag[mask_flat] + 1e-9
        outcome["flat"].append(np.exp(np.mean(np.log(band), axis=0)) / np.mean(band, axis=0))
        logm = np.log1p(10.0 * mag)
        prev = logm[:, :1] if previous is None else previous
        shift = np.concatenate([prev, logm[:, :-1]], axis=1)
        outcome["flux"].append(np.maximum(0.0, logm - shift).sum(axis=0))
        previous = logm[:, -1:]
        outcome["chroma"].append((np.sqrt(mag).T @ mapping))
    return {k: np.concatenate(v, axis=0 if k == "chroma" else 0).astype(np.float32) for k, v in outcome.items()}


def _features_to_bars(features, fps, bpm, beats_per_bar=4):
    frames_per_bar = fps * 60.0 / bpm * beats_per_bar
    n_bars = int(len(features["rms"]) // frames_per_bar)
    rows, bounds = [], []
    for i in range(n_bars):
        a, b = int(round(i * frames_per_bar)), int(round((i + 1) * frames_per_bar))
        ch = features["chroma"][a:b].mean(axis=0)
        ch = ch / (np.linalg.norm(ch) + 1e-9)
        rows.append(np.concatenate([
            [np.log(features["rms"][a:b].mean() + 1e-6), features["centroid"][a:b].mean() / 1000.0,
             features["bass"][a:b].mean(), features["flat"][a:b].mean(), features["flux"][a:b].mean()], ch]))
        bounds.append((a, b))
    return np.array(rows, dtype=np.float64), bounds, frames_per_bar


def detect_sections(features, fps, bpm, min_bars=4, max_sections=10):
    """Section boundaries from the bar self-similarity matrix (checkerboard kernel), labels A/B/C... by similarity."""
    X, bounds, frames_per_bar = _features_to_bars(features, fps, bpm)
    n = len(X)
    if n < 2 * min_bars:
        return [], X, frames_per_bar
    Z = (X - X.mean(axis=0)) / (X.std(axis=0) + 1e-9)
    Z[:, 5:] *= 0.5
    N = Z / (np.linalg.norm(Z, axis=1, keepdims=True) + 1e-9)
    S = N @ N.T
    w = max(2, min(8, n // 6))
    novelty = np.zeros(n)
    for i in range(w, n - w + 1):
        a, b = S[i - w:i, i - w:i], S[i:i + w, i:i + w]
        c = S[i - w:i, i:i + w]
        novelty[i] = a.mean() + b.mean() - 2.0 * c.mean()
    threshold = novelty.mean() + 0.5 * novelty.std()
    candidates = [i for i in range(1, n) if novelty[i] > threshold and novelty[i] >= novelty[max(0, i - 1)] and novelty[i] >= novelty[min(n - 1, i + 1)]]
    candidates.sort(key=lambda i: -novelty[i])
    chosen = []
    for i in candidates:
        if len(chosen) >= max_sections - 1:
            break
        if i >= min_bars and n - i >= min_bars and all(abs(i - j) >= min_bars for j in chosen):
            chosen.append(i)
    edges = [0] + sorted(chosen) + [n]
    energies = np.array([X[a:b, 0].mean() for a, b in zip(edges[:-1], edges[1:])])
    centers, letters, sections = [], [], []
    for (a, b), e in zip(zip(edges[:-1], edges[1:]), energies):
        v = Z[a:b].mean(axis=0)
        v = v / (np.linalg.norm(v) + 1e-9)
        num = None
        for k, c in enumerate(centers):
            if float(v @ c) > 0.85:
                num = k
                break
        if num is None:
            centers.append(v)
            num = len(centers) - 1
        trend = 0.0
        if b - a >= 4:
            trend = float(X[b - 2:b, 0].mean() - X[a:a + 2, 0].mean())
        sections.append({"start_bar": a, "end_bar": b, "letter": chr(ord("A") + min(num, 25)),
                       "start_s": round(a * frames_per_bar / fps, 2), "end_s": round(b * frames_per_bar / fps, 2),
                       "_energy": float(e), "_trend": trend})
    rng = max(1e-9, energies.max() - energies.min())
    for sk in sections:
        r = (sk["_energy"] - energies.min()) / rng if len(sections) > 1 else 0.5
        sk["rel_energy"] = round(float(r), 2)
        sk["level"] = "low" if r < 0.33 else ("medium" if r < 0.66 else "high")
        sk["contour"] = "rising" if sk["_trend"] > 0.35 else ("falling" if sk["_trend"] < -0.35 else "steady")
        del sk["_energy"], sk["_trend"]
    return sections, X, frames_per_bar


def sound_character(features, fps, bpm):
    rms = features["rms"]
    active = rms > (0.1 * np.percentile(rms, 95) + 1e-9)
    if not active.any():
        active = np.ones_like(rms, dtype=bool)
    centroid = float(np.average(features["centroid"][active], weights=rms[active]))
    bass = float(np.average(features["bass"][active], weights=rms[active]))
    flat = float(np.mean(features["flat"][active]))
    db = 20 * np.log10(rms[active] + 1e-9)
    dynamics = float(np.percentile(db, 95) - np.percentile(db, 50))
    flux = features["flux"]
    peaks = int(np.sum((flux[1:-1] > flux[:-2]) & (flux[1:-1] >= flux[2:]) & (flux[1:-1] > flux.mean() + flux.std())))
    density = peaks / max(1e-6, (len(flux) / fps) * bpm / 60.0)
    tags = []
    brightness = "dark" if centroid < 1200 else ("balanced" if centroid < 2800 else "bright")
    tags.append({"dark": "dark warm timbre", "balanced": "balanced timbre", "bright": "bright sharp timbre"}[brightness])
    bass_desc = "heavy" if bass > 0.55 else ("solid" if bass > 0.30 else "light")
    tags.append({"heavy": "heavy sub-bass", "solid": "solid bass", "light": "light bass"}[bass_desc])
    noise = "noisy" if flat > 0.35 else ("clean" if flat < 0.15 else "mixed")
    if noise == "noisy":
        tags.append("gritty distorted texture")
    elif noise == "clean":
        tags.append("clean tonal texture")
    dyn_desc = "compressed" if dynamics < 6 else ("high" if dynamics > 12 else "moderate")
    if dyn_desc == "compressed":
        tags.append("loud compressed mix")
    elif dyn_desc == "high":
        tags.append("dynamic mix")
    density_desc = "dense" if density > 1.5 else ("sparse" if density < 0.6 else "moderate")
    if density_desc == "dense":
        tags.append("busy rhythmic")
    elif density_desc == "sparse":
        tags.append("sparse rhythm")
    return {"centroid_hz": round(centroid), "bass_share": round(bass, 2), "spectral_flatness": round(flat, 2),
            "dynamics_db": round(dynamics, 1), "beat_density": round(density, 2),
            "brightness": brightness, "bass": bass_desc, "texture": noise, "dynamics": dyn_desc, "rhythm": density_desc, "tags": tags}


def _chord_templates():
    global _CHORD_MATRIX
    if _CHORD_MATRIX is None:
        patterns = (("", (0, 4, 7)), ("m", (0, 3, 7)), ("dim", (0, 3, 6)))
        labels, vectors = [], []
        for root in range(12):
            for sfx, intervals in patterns:
                v = np.zeros(12)
                for i, iv in enumerate(intervals):
                    v[(root + iv) % 12] = (1.0, 0.8, 0.9)[i]
                labels.append((root, sfx))
                vectors.append(v / np.linalg.norm(v))
        _CHORD_MATRIX = (labels, np.array(vectors))
    return _CHORD_MATRIX


def _decompose_chord(label):
    if not label:
        return None
    ln = 2 if len(label) > 1 and label[1] == "#" else 1
    return NOTE_NAMES.index(label[:ln]), label[ln:]


def _scale_tones(key_id):
    try:
        item_name, run_mode = str(key_id).split()
        tonic = NOTE_NAMES.index(item_name)
        intervals = (0, 2, 3, 5, 7, 8, 10) if run_mode.lower().startswith("min") else (0, 2, 4, 5, 7, 9, 11)
        return {(tonic + i) % 12 for i in intervals}
    except Exception:
        return set(range(12))


def recognize_chords(audio_np, sr, bpm, num_steps, key_id=None):
    """Chord on every beat (list of length num_steps, '' = none). Resolution: half a bar (2 beats)."""
    labels, tmpls = _chord_templates()
    scale = _scale_tones(key_id)
    beat = sr * 60.0 / bpm
    n_fft = 8192
    wnd = np.hanning(n_fft).astype(np.float32)
    f = np.arange(n_fft // 2 + 1) * sr / n_fft
    pc = np.full(len(f), -1)
    use = (f >= 60) & (f <= 4200)
    pc[use] = (np.round(12 * np.log2(f[use] / 440.0)).astype(int) + 9) % 12
    use_bass = (f >= 40) & (f <= 250)
    pc_bas = np.full(len(f), -1)
    pc_bas[use_bass] = (np.round(12 * np.log2(np.maximum(f[use_bass], 1.0) / 440.0)).astype(int) + 9) % 12

    def range_chroma(a, b):
        seg = audio_np[int(a):int(b)]
        if len(seg) < 512:
            return None, None, 0.0
        if len(seg) > n_fft:  # several windows along the range, averaged
            starts = np.linspace(0, len(seg) - n_fft, max(1, int(len(seg) // (n_fft // 2)) - 1)).astype(int)
        else:
            starts = [0]
        ch, bs = np.zeros(12), np.zeros(12)
        for st in starts:
            frm = np.zeros(n_fft, dtype=np.float32)
            part = seg[st:st + n_fft]
            frm[:len(part)] = part
            mag = np.sqrt(np.abs(np.fft.rfft(frm * wnd)))
            for p in range(12):
                ch[p] += mag[pc == p].sum()
                bs[p] += mag[pc_bas == p].sum()
        energy = float(np.sqrt(np.mean(seg.astype(np.float64) ** 2)))
        return ch, bs, energy

    outcome = [""] * num_steps
    for k in range(0, num_steps, 2):
        ch, bs, energy = range_chroma(k * beat, min(num_steps, k + 2) * beat)
        if ch is None or energy < 1e-3 or ch.sum() <= 0:
            continue
        ch = ch / (np.linalg.norm(ch) + 1e-9)
        bs = bs / (bs.sum() + 1e-9)
        results = []
        for (root, sfx), tmpl in zip(labels, tmpls):
            pcs = {i for i in range(12) if tmpl[i] > 0}
            results.append(float(ch @ tmpl) + 0.35 * bs[root] + (0.04 if pcs <= scale else 0.0))
        root, sfx = labels[int(np.argmax(results))]
        for j in range(k, min(num_steps, k + 2)):
            outcome[j] = NOTE_NAMES[root] + sfx
    return outcome


def bar_progression(chords_beat, beats_per_bar=4, max_val=4):
    """Consecutive distinct chords (no immediate repeats), e.g. ['Am','F','C','G']; independent of the position of the bar's first beat."""
    outcome = []
    for a in chords_beat:
        if a and (not outcome or outcome[-1] != a):
            outcome.append(a)
    return outcome[:max_val]


ENERGY_TARGETS = {"intro": 0.15, "build_up": 0.5, "climax_drop": 0.92, "climax_variation": 0.8, "outro": 0.1}


def _window_mean(arr, fps, start_s, len_s):
    a = max(0, int(start_s * fps))
    b = min(len(arr), max(a + 1, int((start_s + len_s) * fps)))
    return float(np.mean(arr[a:b])) if b > a else 0.0


def align_start_to_beat(start_s, flux, fps, bpm, num_beats, reserve_s):
    """Shifts the window start (by at most half a beat) so the beat grid hits the strongest onsets."""
    beat = 60.0 / bpm
    best, best_result = start_s, -1.0
    for shift_amount in np.linspace(-0.5 * beat, 0.5 * beat, 21):
        s0 = start_s + shift_amount
        if s0 < 0 or s0 > reserve_s:
            continue
        idx = [int(round((s0 + k * beat) * fps)) for k in range(num_beats)]
        outcome = 0.0
        for i in idx:
            if 1 <= i < len(flux) - 1:
                outcome += float(flux[i - 1:i + 2].max())
        if outcome > best_result:
            best_result, best = outcome, s0
    return max(0.0, best)


def window_character(analysis, start_s, len_s):
    c, fps, prof = analysis["features"], analysis["fps"], analysis["profile"]
    cent = _window_mean(c["centroid"], fps, start_s, len_s)
    bass = _window_mean(c["bass"], fps, start_s, len_s)
    tags = []
    if cent > 1.3 * prof["centroid_hz"]:
        tags.append("brighter open sound")
    elif cent < 0.75 * prof["centroid_hz"]:
        tags.append("darker muted sound")
    if bass > prof["bass_share"] + 0.15:
        tags.append("bass-forward")
    return {"centroid_hz": round(cent), "bass_share": round(bass, 2), "tags": tags}


def plan_segments(analysis, num_segments, segment_len_s, num_beats, bpm, base_len_s):
    """For each section of the generated track, picks a window from the input whose energy matches its role."""
    reserve = base_len_s - segment_len_s
    labels = [get_section_label_and_description(num, num_segments)[0] for num in range(1, num_segments + 1)]
    if analysis is None or reserve <= 1.0:
        return [{"start_s": 0.0 if reserve <= 1.0 else float((i * segment_len_s) % reserve), "source": "cyclic"} for i in range(num_segments)]
    fps, c = analysis["fps"], analysis["features"]
    limit = min(reserve, analysis["length_s"] - segment_len_s)
    step_no = 4 * 60.0 / bpm
    candidates = np.arange(0.0, max(limit, 0.0) + 1e-6, step_no)
    if len(candidates) < 2:
        return [{"start_s": 0.0, "source": "cyclic"} for _ in range(num_segments)]
    energies = np.array([_window_mean(c["rms"], fps, s, segment_len_s) for s in candidates])
    ranks = energies.argsort().argsort() / max(1, len(energies) - 1)
    slope = np.array([_window_mean(c["rms"], fps, s + segment_len_s / 2, segment_len_s / 2) - _window_mean(c["rms"], fps, s, segment_len_s / 2) for s in candidates])
    edges = [sk["start_s"] for sk in analysis["sections"]]
    used, plan = [], []
    for num, et in enumerate(labels):
        dest = ENERGY_TARGETS.get(et, 0.5)
        cost = np.abs(ranks - dest)
        if et == "build_up":
            cost = cost - 0.1 * (slope > 0)
        for j, s in enumerate(candidates):
            overlapping = sum(max(0.0, 1.0 - abs(s - u) / segment_len_s) for u in used)
            cost[j] += 0.6 * overlapping
            if edges and min(abs(s - k) for k in edges) < 0.5 * step_no:
                cost[j] -= 0.05
        j = int(np.argmin(cost))
        start = align_start_to_beat(float(candidates[j]), c["flux"], fps, bpm, num_beats, reserve)
        used.append(start)
        plan.append({"start_s": round(float(start), 3), "rel_energy": round(float(ranks[j]), 2), "source": "matched to role"})
    return plan


def analyze_input(audio_np, sr, bpm, key_id, file_name):
    """Full analysis: sections, sound character, most common chords. Returns a dict or None on error."""
    try:
        print(f"\n[ANALYSIS+] Structure, chords and sound of file '{file_name}'...")
        fragment = audio_np[:int(ANALYSIS_MAX_SEC * sr)]
        features = frame_features(fragment, sr)
        fps = sr / ANALYSIS_HOP
        sections, _, _ = detect_sections(features, fps, bpm)
        res_profile = sound_character(features, fps, bpm)
        len_chords = min(len(audio_np), int(120 * sr))
        start_a = (len(audio_np) - len_chords) // 2
        num_beats = int(len_chords / sr * bpm / 60.0)
        start_a = int(align_start_to_beat(start_a / sr, features["flux"], fps, bpm, 16, max(0.0, (len(fragment) - len_chords) / sr)) * sr) if len(fragment) > len_chords else start_a
        chords = recognize_chords(audio_np[start_a:start_a + len_chords], sr, bpm, num_beats, key_id)
        counter = {}
        for a in chords:
            if a:
                counter[a] = counter.get(a, 0) + 1
        top = sorted(counter.items(), key=lambda x: -x[1])[:6]
        total = max(1, sum(counter.values()))
        most_common = [(a, round(100.0 * n / total)) for a, n in top]
        progression = bar_progression(chords[:64], max_val=8)
        analysis = {"features": features, "fps": fps, "length_s": len(fragment) / sr, "sections": sections, "profile": res_profile,
                   "most_common_chords": most_common, "example_progression": progression}
        print("=" * 60)
        print(f" 🔍 STRUCTURE / CHORDS / SOUND: {file_name}")
        print("=" * 60)
        if sections:
            print(" • Detected sections (bar = 4 beats):")
            for sk in sections:
                print(f"     [{sk['letter']}] {sk['start_s']:7.1f}s - {sk['end_s']:7.1f}s  bars {sk['start_bar']+1}-{sk['end_bar']}  "
                      f"energy: {sk['level']} ({sk['contour']})")
        else:
            print(" • Structure: track too short for a reliable split into sections")
        print(f" • Most common chords  : {', '.join(f'{a} ({p}%)' for a, p in most_common) or 'missing'}")
        print(f" • Example progression : {' - '.join(progression) or 'missing'}")
        print(f" • Sound               : brightness {res_profile['brightness']} (centroid {res_profile['centroid_hz']} Hz), bass {res_profile['bass']} "
              f"({int(res_profile['bass_share']*100)}% of energy <250 Hz), texture {res_profile['texture']}, "
              f"dynamics {res_profile['dynamics']} ({res_profile['dynamics_db']} dB), rhythm {res_profile['rhythm']}")
        print(f" • Prompt tags         : {', '.join(res_profile['tags'])}")
        print("=" * 60)
        return analysis
    except Exception as e:
        print(f"[ANALYSIS+] Extended analysis skipped ({type(e).__name__}: {e}) - working as before.")
        return None


def analysis_to_json(analysis):
    if not analysis:
        return None
    return {"input_sections": analysis["sections"], "timbre": {k: v for k, v in analysis["profile"].items()},
            "most_common_chords": analysis["most_common_chords"], "example_progression": analysis["example_progression"]}


def prepare_segment_data_bg_cpu(segment_num, all_segments, base_slice, sr, detected_bpm, detected_key,
                                      user_guidelines, ollama_active, num_steps=32, sound_tags=None,
                                      notes_ready=None, instruments_description=None):
    """
    Runs on the CPU in the background while the main engine renders the current segment: notes, chords, prompt (optionally refined by Ollama).
    """
    if notes_ready is not None:
        notes_info = notes_ready
        chords = notes_info.get("chords_beat") or [""] * num_steps
    else:
        notes_info = recognize_notes_bg_cpu(base_slice, sr, num_steps=num_steps)
        try:
            chords = recognize_chords(base_slice, sr, detected_bpm, num_steps, detected_key)
        except Exception as e:
            print(f"\n[CHORDS] Recognition error ({e}) - section {segment_num} without chords.")
            chords = [""] * num_steps
        notes_info["chords_beat"] = chords
    progression = bar_progression(chords)
    notes_info["progression_str"] = " - ".join(progression)
    label, section = get_section_label_and_description(segment_num, all_segments)
    parts = [f"{detected_bpm} BPM", str(detected_key), str(user_guidelines)]
    if progression:
        parts.append(f"chord progression {' '.join(progression)}")
    if instruments_description:
        parts.append(f"instruments: {instruments_description}")
    if sound_tags:
        parts.append(", ".join(sound_tags))
    parts.append(f"lead motif ({notes_info['lead_str']}), bass ({notes_info['bass_str']}), tight quantization")
    default_value = ", ".join(parts) + f", {section}"
    if not ollama_active:
        return label, default_value, notes_info

    url = "http://localhost:11434/api/generate"
    system_prompt = (
        f"You are a precision electronic music producer. Refine the description into a single 30-word English prompt "
        f"for ACE-Step (a text-to-music model that takes a style caption). You MUST keep '{detected_bpm} BPM, {detected_key}' at the very beginning, keep the chord progression, "
        f"instruments and timbre words if given, and incorporate user goals: '{user_guidelines}'. "
        "Output ONLY the prompt text, no quotes."
    )
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": f"Refine this section keeping exact tempo, key and chords: {default_value}",
        "system": system_prompt,
        "stream": False,
        "keep_alive": 0,
        "options": _ollama_options()
    }
    try:
        resp = requests.post(url, json=payload, timeout=300)
        if resp.status_code == 200:
            txt = resp.json().get("response", "").strip().replace('"', '').replace('\n', ' ')
            if len(txt) > 15:
                pfx = f"{detected_bpm} BPM, {detected_key}, "
                final_p = txt if str(detected_bpm) in txt else pfx + txt
                if progression and not any(a in final_p for a in progression):
                    final_p += f", chord progression {' '.join(progression)}"
                return label, final_p, notes_info
    except Exception as e:
        print(f"\n[OLLAMA] Request error ({e}) - using the default prompt for section {segment_num}.")
    return label, default_value, notes_info


AUDIOSET_INSTRUMENTS = {
    "Drum kit": ("drum kit", "perc"), "Drum machine": ("drum machine", "perc"), "Bass drum": ("kick drum", "perc"),
    "Snare drum": ("snare drum", "perc"), "Hi-hat": ("hi-hats", "perc"), "Cymbal": ("cymbals", "perc"),
    "Drum": ("drums", "perc"), "Percussion": ("percussion", "perc"), "Tom-tom": ("toms", "perc"),
    "Bass guitar": ("bass guitar", "bass"), "Double bass": ("double bass", "bass"),
    "Synthesizer": ("synthesizer", "synth"), "Sampler": ("sampler", "synth"),
    "Sine wave": ("sine tone", "synth"), "Theremin": ("theremin", "synth"),
    "Electric guitar": ("electric guitar", "guitar"), "Guitar": ("guitar", "guitar"),
    "Acoustic guitar": ("acoustic guitar", "guitar"), "Steel guitar, slide guitar": ("slide guitar", "guitar"),
    "Piano": ("piano", "keys"), "Electric piano": ("electric piano", "keys"),
    "Keyboard (musical)": ("keyboard", "keys"), "Organ": ("organ", "keys"),
    "Electronic organ": ("electronic organ", "keys"), "Hammond organ": ("hammond organ", "keys"),
    "Harpsichord": ("harpsichord", "keys"),
    "Singing": ("vocals", "vocal"), "Male singing": ("male vocals", "vocal"), "Female singing": ("female vocals", "vocal"),
    "Choir": ("choir", "vocal"), "Vocal music": ("vocals", "vocal"), "Humming": ("humming", "vocal"),
    "Violin, fiddle": ("violin", "strings"), "Cello": ("cello", "strings"), "String section": ("strings", "strings"),
    "Bowed string instrument": ("strings", "strings"), "Harp": ("harp", "strings"),
    "Brass instrument": ("brass", "winds"), "Trumpet": ("trumpet", "winds"), "Saxophone": ("saxophone", "winds"),
    "Flute": ("flute", "winds"), "Trombone": ("trombone", "winds"), "Wind instrument, woodwind instrument": ("woodwinds", "winds"),
    "Bell": ("bells", "other_instr"), "Mallet percussion": ("mallets", "other_instr"), "Marimba, xylophone": ("marimba", "other_instr"),
}


GROUPS_FOR_STEM = {
    "drums": {"perc"}, "bass": {"bass", "synth", "guitar"}, "vocals": {"vocal"},
    "guitar": {"guitar", "synth"}, "piano": {"keys"},
    "other": {"synth", "keys", "guitar", "strings", "winds", "other_instr"},
}


MELODIC_STEMS = ("other", "guitar", "piano", "vocals")


MIDI_PROGRAMS = {"bass": 38, "other": 81, "guitar": 29, "piano": 0, "vocals": 54}


def _resample_fft(x, sr_in, sr_out):
    x = np.asarray(x, dtype=np.float64)
    if int(sr_in) == int(sr_out) or len(x) == 0:
        return x.astype(np.float32)
    n_out = int(round(len(x) * sr_out / sr_in))
    X = np.fft.rfft(x)
    Y = np.zeros(n_out // 2 + 1, dtype=np.complex128)
    m = min(len(X), len(Y))
    Y[:m] = X[:m]
    return (np.fft.irfft(Y, n_out) * (n_out / len(x))).astype(np.float32)


def _match_length(x, n):
    x = np.asarray(x, dtype=np.float32)
    return x[:n] if len(x) >= n else np.pad(x, (0, n - len(x)))


def _rms(x):
    x = np.asarray(x, dtype=np.float64)
    return float(np.sqrt(np.mean(x ** 2))) if len(x) else 0.0


def _loudest_fragment(audio, sr, len_s):
    n = int(len_s * sr)
    if len(audio) <= n:
        return audio
    block = int(sr)
    rms_blocks = np.array([_rms(audio[i:i + block]) for i in range(0, len(audio) - block + 1, block)])
    k = max(1, int(len_s))
    if len(rms_blocks) <= k:
        return audio[:n]
    sums = np.convolve(rms_blocks, np.ones(k), mode="valid")
    start = int(np.argmax(sums)) * block
    return audio[start:start + n]


def _stft_c(x, n_fft=2048, hop=512):
    x = np.pad(np.asarray(x, dtype=np.float32), (n_fft // 2, n_fft // 2), mode="reflect")
    wnd = np.hanning(n_fft + 1)[:-1].astype(np.float32)
    n = 1 + (len(x) - n_fft) // hop
    idx = np.arange(n_fft)[None, :] + hop * np.arange(n)[:, None]
    return np.fft.rfft(x[idx] * wnd, axis=1)


def _istft_c(S, length, n_fft=2048, hop=512):
    wnd = np.hanning(n_fft + 1)[:-1].astype(np.float32)
    frame_list = np.fft.irfft(S, n_fft, axis=1).astype(np.float32) * wnd
    n = len(frame_list)
    y = np.zeros(hop * (n - 1) + n_fft, dtype=np.float32)
    norm_val = np.zeros_like(y)
    for i in range(n):
        y[i * hop:i * hop + n_fft] += frame_list[i]
        norm_val[i * hop:i * hop + n_fft] += wnd ** 2
    y = y / np.maximum(norm_val, 1e-6)
    return _match_length(y[n_fft // 2:], length)


def _windowed_median(A, k, os_):
    from numpy.lib.stride_tricks import sliding_window_view
    pad = [(0, 0), (0, 0)]
    pad[os_] = (k // 2, k // 2)
    Ap = np.pad(A, pad, mode="reflect")
    return np.median(sliding_window_view(Ap, k, axis=os_), axis=-1)


class _SeparatorHPSS:
    """Fallback separation without a neural network: drums (percussive component), bass (<200 Hz), rest (harmonic)."""
    names = ["drums", "bass", "other"]
    description = "hpss-numpy"

    def separate(self, audio, sr):
        n_fft, hop = 2048, 512
        S = _stft_c(audio, n_fft, hop)
        M = np.abs(S)
        H = _windowed_median(M, 17, 0)   # median over time -> tonal components
        P = _windowed_median(M, 17, 1)   # median over frequency -> percussive components
        mh = H ** 2 / (H ** 2 + P ** 2 + 1e-10)
        harm, perc = S * mh, S * (1.0 - mh)
        f = np.arange(n_fft // 2 + 1) * sr / n_fft
        low = (f < 200.0)[None, :]
        n = len(audio)
        return {"drums": _istft_c(perc, n, n_fft, hop),
                "bass": _istft_c(harm * low, n, n_fft, hop),
                "other": _istft_c(harm * (~low), n, n_fft, hop)}


def _instrument_heuristic(stem_name, audio, sr):
    a = np.asarray(audio, dtype=np.float32)[:int(30 * sr)]
    if len(a) < 1024:
        return [stem_name]
    spectrum = np.abs(np.fft.rfft(a * np.hanning(len(a)))) ** 2
    f = np.fft.rfftfreq(len(a), 1.0 / sr)
    total = spectrum.sum() + 1e-12
    centroid = float((spectrum * f).sum() / total)
    if stem_name == "drums":
        outcome = ["drums"]
        if spectrum[f < 130].sum() / total > 0.5:
            outcome.append("kick drum")
        if spectrum[f > 6000].sum() / total > 0.1:
            outcome.append("hi-hats")
        return outcome
    if stem_name == "bass":
        return ["sub bass" if centroid < 150 else "synth bass or bass guitar"]
    if stem_name == "vocals":
        return ["vocals"]
    if stem_name == "guitar":
        return ["guitar"]
    if stem_name == "piano":
        return ["piano or keys"]
    return ["bright lead synth" if centroid > 3000 else ("synth lead" if centroid > 1200 else "pad or synth")]


def classify_stems(stems, sr, classifier):
    mix = np.sum([np.asarray(a, dtype=np.float32) for a in stems.values()], axis=0)
    rms_mix = _rms(mix) + 1e-9
    outcome = {}
    for item_name, a in stems.items():
        db = 20 * np.log10(_rms(a) / rms_mix + 1e-9)
        present = bool(db > STEM_PRESENCE_THRESHOLD_DB)
        labels, method = [], "missing"
        if present:
            if classifier is not None:
                try:
                    labels = [(n, p) for n, p in classifier.classify(a, sr, GROUPS_FOR_STEM.get(item_name, {"synth", "keys", "guitar"})) if p >= 0.10][:3]
                    method = "AST"
                except Exception as e:
                    print(f"\n[CLASSIFIER] Network error ({type(e).__name__}: {e}) - heuristic for stem '{item_name}'.")
            if not labels:
                labels = [(n, 0.0) for n in _instrument_heuristic(item_name, a, sr)]
                method = "heuristic"
        outcome[item_name] = {"present": present, "level_db": round(float(db), 1),
                        "instruments": [n for n, _ in labels], "confidence": [round(float(p), 2) for _, p in labels], "method": method}
    return outcome


def instruments_description(class_names, max_val=5):
    names = []
    for item_name, info in class_names.items():
        if info["present"] and info["instruments"] and info["instruments"][0] not in names:
            names.append(info["instruments"][0])
    return ", ".join(names[:max_val])


def recognize_percussion(audio, sr, bpm, num_steps, division=4):
    """Kick(36)/snare(38)/hi-hat(42) hits on a sixteenth-note grid. Returns {GM_note: [0/1 ...]} of length num_steps*division."""
    slot = sr * 60.0 / bpm / division
    n_slots = int(num_steps * division)
    bands = {36: (30.0, 130.0), 38: (150.0, 500.0), 42: (5000.0, 14000.0)}
    n_fft = 2048
    wnd = np.hanning(n_fft).astype(np.float32)
    f = np.fft.rfftfreq(n_fft, 1.0 / sr)
    masks = {n: (f >= a) & (f <= b) for n, (a, b) in bands.items()}
    energies = {n: np.zeros(n_slots) for n in bands}
    for k in range(n_slots):
        a0 = int(k * slot)
        seg = np.asarray(audio[a0:a0 + min(int(slot), n_fft)], dtype=np.float32)
        if len(seg) < 64:
            continue
        frm = np.zeros(n_fft, dtype=np.float32)
        frm[:len(seg)] = seg
        power = np.abs(np.fft.rfft(frm * wnd)) ** 2
        for n, m in masks.items():
            energies[n][k] = power[m].sum()
    raw_snare_energies = energies[38].copy()
    outcome = {}
    # kick leakage into the snare band: we estimate the typical energy ratio and subtract it
    kick = energies[36]
    kick_on = kick > 0.25 * np.percentile(kick, 95) if kick.max() > 0 else np.zeros(n_slots, dtype=bool)
    if kick_on.any():
        leakage = float(np.median(energies[38][kick_on] / (kick[kick_on] + 1e-12)))
        energies[38] = np.maximum(0.0, energies[38] - 1.5 * leakage * kick)
    for n, e in energies.items():
        threshold = 0.25 * np.percentile(e, 95) if e.max() > 0 else 1.0
        if n == 38:
            threshold = max(threshold, 0.2 * float(np.percentile(raw_snare_energies, 95)))
        hits = [0] * n_slots
        for k in range(n_slots):
            prev = e[k - 1] if k > 0 else 0.0
            if e[k] > threshold and e[k] > 1.5 * prev:
                hits[k] = 1
        outcome[n] = hits
    return outcome


def save_multitrack_midi(midi_path, bpm, paths, percussion, division=4):
    """SMF format 1: tempo track + melodic tracks (one note per beat, 480 ticks) + percussion (channel 10, sixteenths).
    paths: list of (name, GM_program, [list of notes per segment]); percussion: {GM_note: [list of 0/1 per segment]}."""
    def varlen(v):
        buffer = [v & 0x7F]
        v >>= 7
        while v:
            buffer.insert(0, (v & 0x7F) | 0x80)
            v >>= 7
        return bytes(buffer)

    def track_from_events(event_list):
        event_list = sorted(event_list, key=lambda z: (z[0], z[1]))
        data, prev = bytearray(), 0
        for tick, _prio, raw_bytes in event_list:
            data += varlen(tick - prev) + raw_bytes
            prev = tick
        data += b"\x00\xFF\x2F\x00"
        return b"MTrk" + struct.pack(">I", len(data)) + bytes(data)

    def meta_name(item_name):
        b = item_name.encode("ascii", "replace")[:60]
        return b"\xFF\x03" + bytes([len(b)]) + b

    tempo = [(0, 0, meta_name("tempo")),
             (0, 0, b"\xFF\x51\x03" + int(60000000 / max(1.0, float(bpm))).to_bytes(3, "big")),
             (0, 0, b"\xFF\x58\x04\x04\x02\x18\x08")]
    paths_bytes = [track_from_events(tempo)]
    channels = [c for c in range(16) if c != 9]
    for num, (item_name, program, lists) in enumerate(paths):
        chan = channels[num % len(channels)]
        ev = [(0, 0, meta_name(item_name)), (0, 1, bytes([0xC0 | chan, program & 0x7F]))]
        tick, current, beginning = 0, 0, 0
        for n in [x for seg in lists for x in seg]:
            if n != current:
                if current > 0:
                    ev.append((tick, 2, bytes([0x80 | chan, current & 0x7F, 0])))
                if n > 0:
                    ev.append((tick, 3, bytes([0x90 | chan, n & 0x7F, 100])))
                current = n
            tick += 480
        if current > 0:
            ev.append((tick, 2, bytes([0x80 | chan, current & 0x7F, 0])))
        paths_bytes.append(track_from_events(ev))
    if percussion:
        ev = [(0, 0, meta_name("drums"))]
        step_no = 480 // division
        for note, lists in percussion.items():
            for k, t in enumerate([x for seg in lists for x in seg]):
                if t:
                    ev.append((k * step_no, 3, bytes([0x99, note & 0x7F, 100])))
                    ev.append((k * step_no + step_no // 2, 2, bytes([0x89, note & 0x7F, 0])))
        paths_bytes.append(track_from_events(ev))
    heading = b"MThd" + struct.pack(">IHHH", 6, 1, len(paths_bytes), 480)
    with open(midi_path, "wb") as f:
        f.write(heading + b"".join(paths_bytes))


def _cache_path(file, start_s, len_s, separator_description):
    try:
        st = Path(file).stat()
        base = f"{Path(file).name}|{st.st_size}|{int(st.st_mtime)}"
    except Exception:
        base = str(file)
    h = hashlib.sha1(f"{base}|{start_s:.3f}|{len_s:.3f}|{separator_description}".encode("utf-8")).hexdigest()[:16]
    return WORKSPACE_DIR / "stem_cache" / f"{h}.npz"


def melody_from_stems(data, n=None):
    """Mix without drums and bass (as in audiocraft for melody conditioning)."""
    components = [a for item_name, a in data["stems"].items() if item_name not in ("drums", "bass")]
    if not components:
        return None
    m = np.sum(components, axis=0).astype(np.float32)
    top_peak = float(np.max(np.abs(m))) if len(m) else 0.0
    if top_peak > 1e-6:
        m = m / top_peak * 0.9
    return m if n is None else _match_length(m, n)


def save_section_stems(directory, num, label, data, sr, registry, root):
    directory.mkdir(parents=True, exist_ok=True)
    for item_name, audio in data["stems"].items():
        if not data["classes"][item_name]["present"]:
            continue
        base = f"stem_{num:03d}_{label}_{item_name}"
        if STEMS_ALL_FORMATS:
            save_audio_versions(directory, base, audio, sr, registry, root)
        else:
            fpath = directory / f"{base}_mono.wav"
            sf.write(str(fpath), np.clip(audio, -1.0, 1.0), int(sr), subtype=WAV_SUBTYPE)
            registry.append(str(fpath.relative_to(root)).replace("\\", "/"))


def stems_to_json(data):
    if not data:
        return None
    return {"separator": data["separator"], "start_s": data["start_s"], "leading_stem": data["lead_stem"],
            "instruments_in_prompt": data["description"], "stems": data["classes"]}


def prepare_segment_data_stems(segment_num, all_segments, base_slice, sr, detected_bpm, detected_key,
                                  user_guidelines, ollama_active, num_steps=32, sound_tags=None, stem_data=None):
    """CPU worker of the PRO version: notes / chords / percussion from separate stems, then a common prompt (Ollama)."""
    if not stem_data:
        return prepare_segment_data_bg_cpu(segment_num, all_segments, base_slice, sr, detected_bpm, detected_key,
                                                 user_guidelines, ollama_active, num_steps, sound_tags)
    try:
        n = len(base_slice)
        stems = {k: _match_length(v, n) for k, v in stem_data["stems"].items()}
        class_names = stem_data["classes"]
        lead_name = stem_data["lead_stem"]
        source_lead = stems[lead_name] if lead_name else base_slice
        source_bass = stems["bass"] if "bass" in stems and class_names["bass"]["present"] else base_slice
        info_lead = recognize_notes_bg_cpu(source_lead, sr, num_steps=num_steps)
        info_bass = info_lead if source_bass is source_lead else recognize_notes_bg_cpu(source_bass, sr, num_steps=num_steps)
        notes_info = {"lead_midi": info_lead["lead_midi"], "lead_str": info_lead["lead_str"],
                     "bass_midi": info_bass["bass_midi"], "bass_str": info_bass["bass_str"], "stem_midi": {}, "percussion": None}
        if source_bass is not base_slice:
            notes_info["stem_midi"]["bass"] = info_bass["bass_midi"]
        for item_name in MELODIC_STEMS:
            if item_name in stems and class_names[item_name]["present"]:
                notes_info["stem_midi"][item_name] = info_lead["lead_midi"] if item_name == lead_name else \
                    recognize_notes_bg_cpu(stems[item_name], sr, num_steps=num_steps)["lead_midi"]
        if "drums" in stems and class_names["drums"]["present"]:
            notes_info["percussion"] = recognize_percussion(stems["drums"], sr, detected_bpm, num_steps)
        harmonic = np.sum([a for k, a in stems.items() if k != "drums"], axis=0) if len(stems) > 1 else base_slice
        notes_info["chords_beat"] = recognize_chords(harmonic, sr, detected_bpm, num_steps, detected_key)
    except Exception as e:
        print(f"\n[STEMS] Stem analysis error in section {segment_num} ({type(e).__name__}: {e}) - analyzing the full mix.")
        return prepare_segment_data_bg_cpu(segment_num, all_segments, base_slice, sr, detected_bpm, detected_key,
                                                 user_guidelines, ollama_active, num_steps, sound_tags)
    return prepare_segment_data_bg_cpu(segment_num, all_segments, base_slice, sr, detected_bpm, detected_key,
                                             user_guidelines, ollama_active, num_steps, sound_tags,
                                             notes_ready=notes_info, instruments_description=stem_data.get("description"))


def match_rms(audio_np, target_rms=0.18):
    rms = np.sqrt(np.mean(audio_np ** 2))
    if rms > 1e-5:
        audio_np = audio_np * (target_rms / rms)
    return np.tanh(audio_np) * 0.95


def join_bar_aligned_with_crossfade(track_so_far, new_segment, sr, crossfade_time_sec=0.4):
    if track_so_far is None or len(track_so_far) == 0:
        return new_segment
    fade_samples = int(crossfade_time_sec * sr)
    if len(track_so_far) < fade_samples or len(new_segment) < fade_samples:
        return np.concatenate([track_so_far, new_segment])
    t = np.linspace(0.0, np.pi / 2.0, fade_samples, dtype=np.float32)
    fade_out = np.cos(t)
    fade_in = np.sin(t)
    junction = track_so_far[-fade_samples:] * fade_out + new_segment[:fade_samples] * fade_in
    return np.concatenate([track_so_far[:-fade_samples], junction, new_segment[fade_samples:]])


def _safe_name(txt):
    item_name = re.sub(r"[^\w\-]+", "_", str(txt), flags=re.UNICODE).strip("_")
    return item_name[:50] or "track"


def prepare_session_dirs(session_name):
    """output/<small|large>/<session>/{final,parts,midi,notation,samples,used_sounds}"""
    root = OUTPUT_DIR / session_name
    directories = {
        "root": root,
        "final": root / "final",
        "parts": root / "parts",
        "midi": root / "midi",
        "notation": root / "notation",
        "samples": root / "samples",
        "used": root / "used_sounds",
    }
    for key_id, fpath in directories.items():
        if key_id == "notation" and not EXPORT_NOTATION:
            continue
        if key_id == "samples" and not EXPORT_SAMPLES:
            continue
        if key_id == "used" and not EXPORT_USED_SOUNDS:
            continue
        fpath.mkdir(parents=True, exist_ok=True)
    return directories


def _normalize_peak(a, limit=0.97):
    top_peak = float(np.max(np.abs(a))) if a.size else 0.0
    if top_peak > limit:
        a = a * (limit / top_peak)
    return a.astype(np.float32)


def _delay(x, samples):
    if samples <= 0:
        return x.copy()
    if len(x) <= samples:
        return np.zeros_like(x)
    return np.concatenate([np.zeros(samples, dtype=x.dtype), x[:-samples]])


def _fft_filter(x, sr, f_low=None, f_high=None):
    """Low-/high-/band-pass filter in the FFT domain with gentle slopes."""
    n = len(x)
    if n == 0:
        return x.astype(np.float32)
    spectrum = np.fft.rfft(x.astype(np.float64))
    f = np.fft.rfftfreq(n, 1.0 / sr)
    mask = np.ones_like(f)
    if f_low is not None and f_low > 0:
        width = max(10.0, 0.25 * f_low)
        mask *= np.clip((f - (f_low - width)) / (2.0 * width), 0.0, 1.0)
    if f_high is not None:
        width = max(10.0, 0.25 * f_high)
        mask *= np.clip(((f_high + width) - f) / (2.0 * width), 0.0, 1.0)
    return np.fft.irfft(spectrum * mask, n).astype(np.float32)


def mono_to_stereo(x, sr):
    """Mono-compatible pseudo-stereo: L+R = 2*x (the difference component cancels out when summed)."""
    x = np.asarray(x, dtype=np.float32)
    side_col = _delay(_fft_filter(x, sr, f_low=200.0), int(0.021 * sr)) * 0.45  # bass stays in the center
    return _normalize_peak(np.stack([x + side_col, x - side_col], axis=1))


def mono_to_surround51(x, sr):
    """Pseudo-surround 5.1, WAV channel order: FL, FR, FC, LFE, SL, SR."""
    x = np.asarray(x, dtype=np.float32)
    st = mono_to_stereo(x, sr)
    fl, fr = st[:, 0] * 0.8, st[:, 1] * 0.8
    fc = _fft_filter(x, sr, f_low=120.0) * 0.7
    lfe = _fft_filter(x, sr, f_high=120.0)
    high = _fft_filter(x, sr, f_low=250.0)
    sl = _delay(high, int(0.034 * sr)) * 0.5
    sp = -_delay(high, int(0.047 * sr)) * 0.5  # inverted polarity + a different delay = no correlation with SL
    return _normalize_peak(np.stack([fl, fr, fc, lfe, sl, sp], axis=1))


def save_audio_versions(directory, base_name, audio_mono, sr, registry=None, root=None):
    """Saves audio as mono / stereo / surround 5.1 (per CHANNEL_FORMATS). Returns a list of paths."""
    directory.mkdir(parents=True, exist_ok=True)
    audio_mono = np.asarray(audio_mono, dtype=np.float32)
    saved = []
    for fmt in CHANNEL_FORMATS:
        if fmt == "mono":
            data, sfx = audio_mono, "mono"
        elif fmt == "stereo":
            data, sfx = mono_to_stereo(audio_mono, sr), "stereo"
        elif fmt == "surround":
            data, sfx = mono_to_surround51(audio_mono, sr), "surround51"
        else:
            continue
        fpath = directory / f"{base_name}_{sfx}.wav"
        sf.write(str(fpath), np.clip(data, -1.0, 1.0), int(sr), subtype=WAV_SUBTYPE)
        saved.append(fpath)
        if registry is not None and root is not None:
            registry.append(str(fpath.relative_to(root)).replace("\\", "/"))
    return saved


def cut_loop(audio, sr, bpm, beat_start, num_beats, fade_ms=8.0):
    beat = 60.0 / float(bpm)
    s0 = int(round(beat_start * beat * sr))
    s1 = s0 + int(round(num_beats * beat * sr))
    if s1 > len(audio) or s0 < 0:
        return None
    loop = audio[s0:s1].astype(np.float32).copy()
    n = min(int(fade_ms / 1000.0 * sr), len(loop) // 2)
    if n > 0:
        loop[:n] *= np.linspace(0.0, 1.0, n, dtype=np.float32)
        loop[-n:] *= np.linspace(1.0, 0.0, n, dtype=np.float32)
    return loop


def export_loops(directory, item_name, audio, sr, bpm, num_beats, registry, root):
    """One- and two-bar loops cut from the beat grid of the generated section (approximate: depends on how well the model keeps tempo)."""
    start = 4 if num_beats >= 12 else 0
    loop = cut_loop(audio, sr, bpm, start, 4)
    if loop is not None:
        save_audio_versions(directory, f"{item_name}_loop_1bar", loop, sr, registry, root)
    if num_beats >= 16:
        loop2 = cut_loop(audio, sr, bpm, 8, 8)
        if loop2 is not None:
            save_audio_versions(directory, f"{item_name}_loop_2bars", loop2, sr, registry, root)


STEM_BANDS = (("bass", None, 180.0), ("mid", 180.0, 3200.0), ("top", 3200.0, None))


def export_band_stems(directory, item_name, audio, sr, registry, root):
    for label, f_low, f_high in STEM_BANDS:
        band = _fft_filter(audio, sr, f_low=f_low, f_high=f_high)
        save_audio_versions(directory, f"{item_name}_stem_{label}", band, sr, registry, root)


_FIFTHS_MAJOR = {0: 0, 7: 1, 2: 2, 9: 3, 4: 4, 11: 5, 6: 6, 1: -5, 8: -4, 3: -3, 10: -2, 5: -1}


_STEP_SHARP = [("C", 0), ("C", 1), ("D", 0), ("D", 1), ("E", 0), ("F", 0), ("F", 1), ("G", 0), ("G", 1), ("A", 0), ("A", 1), ("B", 0)]


_LY_NAMES = ["c", "cis", "d", "dis", "e", "f", "fis", "g", "gis", "a", "ais", "b"]


_NOTE_TYPES = {1: ("quarter", False), 2: ("half", False), 3: ("half", True), 4: ("whole", False)}


_LY_DURATIONS = {1: "4", 2: "2", 3: "2.", 4: "1"}


def _key_params(key_id):
    try:
        item_name, run_mode = str(key_id).split()
        tonic = NOTE_NAMES.index(item_name)
        run_mode = "minor" if run_mode.lower().startswith("min") else "major"
    except Exception:
        tonic, run_mode = 5, "minor"
    major_pc = (tonic + 3) % 12 if run_mode == "minor" else tonic
    return _FIFTHS_MAJOR[major_pc], tonic, run_mode


def _split_notes(grid, beats_per_bar=4):
    """1 list element = 1 beat (0 = rest). Returns bars: list of [midi, length, tie_from_previous, tie_to_next]."""
    grid = [int(n) for n in grid]
    bars = []
    for start in range(0, len(grid), beats_per_bar):
        fragment = grid[start:start + beats_per_bar]
        fragment += [0] * (beats_per_bar - len(fragment))
        bar, i = [], 0
        while i < len(fragment):
            j = i
            while j < len(fragment) and fragment[j] == fragment[i]:
                j += 1
            bar.append([fragment[i], j - i, False, False])
            i = j
        bars.append(bar)
    for k in range(len(bars) - 1):
        a, b = bars[k][-1], bars[k + 1][0]
        if a[0] > 0 and a[0] == b[0]:
            a[3] = True
            b[2] = True
    return bars


_KIND_XML = {"": ("major", ""), "m": ("minor", "m"), "dim": ("diminished", "dim")}


def _harmony_xml(label, offset):
    root, sfx = _decompose_chord(label)
    step_no, alter = _STEP_SHARP[root]
    kind, txt = _KIND_XML.get(sfx, ("major", ""))
    w = ["      <harmony>", "        <root>", f"          <root-step>{step_no}</root-step>"]
    if alter:
        w.append(f"          <root-alter>{alter}</root-alter>")
    w += ["        </root>", f'        <kind text="{txt}">{kind}</kind>']
    if offset:
        w.append(f"        <offset>{offset}</offset>")
    w.append("      </harmony>")
    return "\n".join(w)


def _bar_harmonies(chords, bar_num):
    """Chord markers for a bar (0-based): a new chord where it changes, offset = beat number within the bar."""
    outcome, prev = [], None
    if bar_num > 0 and bar_num * 4 - 1 < len(chords):
        prev = chords[bar_num * 4 - 1]
    for i in range(4):
        idx = bar_num * 4 + i
        if idx >= len(chords):
            break
        a = chords[idx]
        if a and a != prev:
            outcome.append(_harmony_xml(a, i))
        if a:
            prev = a
    return outcome


def _note_xml(midi, ln, tie_p, tie_n):
    type_, dotted = _NOTE_TYPES[ln]
    w = ["      <note>"]
    if midi > 0:
        step_no, alter = _STEP_SHARP[midi % 12]
        w.append("        <pitch>")
        w.append(f"          <step>{step_no}</step>")
        if alter:
            w.append(f"          <alter>{alter}</alter>")
        w.append(f"          <octave>{midi // 12 - 1}</octave>")
        w.append("        </pitch>")
    else:
        w.append("        <rest/>")
    w.append(f"        <duration>{ln}</duration>")
    if tie_p:
        w.append('        <tie type="stop"/>')
    if tie_n:
        w.append('        <tie type="start"/>')
    w.append(f"        <type>{type_}</type>")
    if dotted:
        w.append("        <dot/>")
    if tie_p or tie_n:
        w.append("        <notations>")
        if tie_p:
            w.append('          <tied type="stop"/>')
        if tie_n:
            w.append('          <tied type="start"/>')
        w.append("        </notations>")
    w.append("      </note>")
    return "\n".join(w)


def build_musicxml(song_title, bpm, key_id, grid_lead, grid_bass, chords=None):
    fifths, _, run_mode = _key_params(key_id)
    voices = [("P1", "Lead", "G", 2, grid_lead), ("P2", "Bass", "F", 4, grid_bass)]
    x = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.1 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">',
        '<score-partwise version="3.1">',
        f"  <work><work-title>{_xml_escape(str(song_title))}</work-title></work>",
        "  <part-list>",
    ]
    for pid, item_name, _, _, _ in voices:
        x.append(f'    <score-part id="{pid}"><part-name>{item_name}</part-name></score-part>')
    x.append("  </part-list>")
    for pid, _, clef_sign, line, grid in voices:
        x.append(f'  <part id="{pid}">')
        for num, bar in enumerate(_split_notes(grid), 1):
            x.append(f'    <measure number="{num}">')
            if num == 1:
                x += [
                    "      <attributes>",
                    "        <divisions>1</divisions>",
                    f"        <key><fifths>{fifths}</fifths><mode>{run_mode}</mode></key>",
                    "        <time><beats>4</beats><beat-type>4</beat-type></time>",
                    f"        <clef><sign>{clef_sign}</sign><line>{line}</line></clef>",
                    "      </attributes>",
                    f'      <direction placement="above"><direction-type><metronome><beat-unit>quarter</beat-unit><per-minute>{bpm}</per-minute></metronome></direction-type><sound tempo="{bpm}"/></direction>',
                ]
            if pid == "P1" and chords:
                x += _bar_harmonies(chords, num - 1)
            for midi, ln, tie_p, tie_n in bar:
                x.append(_note_xml(midi, ln, tie_p, tie_n))
            x.append("    </measure>")
        x.append("  </part>")
    x.append("</score-partwise>")
    return "\n".join(x) + "\n"


def _ly_note(midi, ln, tie_n):
    length = _LY_DURATIONS[ln]
    if midi <= 0:
        return f"r{length}"
    octave = midi // 12 - 1
    markers = "'" * (octave - 3) if octave >= 3 else "," * (3 - octave)
    return f"{_LY_NAMES[midi % 12]}{markers}{length}" + ("~" if tie_n else "")


def _ly_chord(label, ln):
    if not label:
        return f"r{_LY_DURATIONS[ln]}"
    root, sfx = _decompose_chord(label)
    return f"{_LY_NAMES[root]}{_LY_DURATIONS[ln]}" + {"": "", "m": ":m", "dim": ":dim"}.get(sfx, "")


def _chord_voice_ly(chords):
    unique = {a: i + 1 for i, a in enumerate(sorted({a for a in chords if a}))}
    bars = _split_notes([unique.get(a, 0) for a in chords])
    inv = {v: k for k, v in unique.items()}
    return "\n      ".join(" ".join(_ly_chord(inv.get(m, ""), d) for m, d, _tp, _tn in bar) + " |" for bar in bars)


def build_lilypond(song_title, bpm, key_id, grid_lead, grid_bass, chords=None):
    _, tonic, run_mode = _key_params(key_id)
    key_name = _LY_NAMES[tonic]

    def voice(grid):
        return "\n      ".join(
            " ".join(_ly_note(m, d, tn) for m, d, _tp, tn in bar) + " |"
            for bar in _split_notes(grid)
        )

    title_ly = str(song_title).replace('"', "'")
    lines = [
        '\\version "2.24.0"',
        f'\\header {{ title = "{title_ly}" }}',
        "\\score {",
        "  <<",
    ]
    if chords and any(chords):
        lines += ["    \\new ChordNames \\chordmode {", "      " + _chord_voice_ly(chords), "    }"]
    lines += [
        '    \\new Staff \\with { instrumentName = "Lead" } {',
        f"      \\clef treble \\time 4/4 \\key {key_name} \\{run_mode} \\tempo 4 = {int(round(float(bpm)))}",
        "      " + voice(grid_lead),
        "    }",
        '    \\new Staff \\with { instrumentName = "Bass" } {',
        f"      \\clef bass \\time 4/4 \\key {key_name} \\{run_mode}",
        "      " + voice(grid_bass),
        "    }",
        "  >>",
        "  \\layout { }",
        "  \\midi { }",
        "}",
    ]
    return "\n".join(lines) + "\n"


def build_notes_text(song_title, bpm, key_id, grid_lead, grid_bass, chords=None):
    def item_name(m):
        return "-" if m <= 0 else f"{NOTE_NAMES[m % 12]}{m // 12 - 1}"

    lines = [
        f"# {song_title}",
        f"# Tempo: {bpm} BPM | Key: {key_id} | Meter: 4/4 | 1 position = 1 beat, '-' = rest",
        "",
    ]
    count = max(len(grid_lead), len(grid_bass))
    for start in range(0, count, 4):
        lead = " ".join(f"{item_name(m):<4}" for m in grid_lead[start:start + 4])
        bass = " ".join(f"{item_name(m):<4}" for m in grid_bass[start:start + 4])
        row = f"Bar {start // 4 + 1:03d} | LEAD: {lead} | BASS: {bass}"
        if chords:
            row += " | CHORDS: " + " ".join(f"{(a or '-'):<4}" for a in chords[start:start + 4])
        lines.append(row)
    return "\n".join(lines) + "\n"


def save_notes(directory, base_name, song_title, bpm, key_id, grids_lead, grids_bass, registry, root, grids_chords=None):
    directory.mkdir(parents=True, exist_ok=True)
    lead = [int(n) for seg in grids_lead for n in seg]
    bass = [int(n) for seg in grids_bass for n in seg]
    chords = [a for seg in (grids_chords or []) for a in seg] or None
    bodies = {
        ".musicxml": build_musicxml(song_title, bpm, key_id, lead, bass, chords),
        ".ly": build_lilypond(song_title, bpm, key_id, lead, bass, chords),
        ".txt": build_notes_text(song_title, bpm, key_id, lead, bass, chords),
    }
    for extension, body in bodies.items():
        fpath = directory / f"{base_name}{extension}"
        fpath.write_text(body, encoding="utf-8")
        registry.append(str(fpath.relative_to(root)).replace("\\", "/"))


MENU_VARIABLES = {
    "ACE_MODEL_DIT", "ACE_STEPS", "ACE_GUIDANCE", "ACE_DEVICE", "ACE_ENGINE", "ACE_GGUF_QUANT", "ACE_CPP_LM", "ACE_COVER_NOISE", "ACE_SWAP_FILE", "ACE_SWAP_FILE_KEEP", "ACE_THREADS", "ACE_QUANTIZATION", "ACE_BF16",
    "ACE_GENERATION_LIMIT_SEC", "ACE_USE_LM", "ACE_LOW_RAM", "ACE_MODE", "ACE_COVER_STRENGTH",
    "ACE_COVER_WHOLE_FILE", "ACE_COVER_MAX_SEC", "ACE_COVER_FRAGMENTS", "ACE_COVER_FRAGMENTS_MODE", "ACE_NUM_PASSES", "ACE_WHOLE_TRACK", "ACE_MARGIN_SEC", "ACE_USE_REFERENCE",
    "ACE_REFERENCE_MODE", "ACE_REFERENCE_LEN_SEC", "ACE_STYLE_TEMPLATES", "ACE_LYRICS", "ACE_INSTRUMENTAL", "ACE_SEED",
    "NUM_SEGMENTS", "USE_OLLAMA", "OLLAMA_MODEL", "CHANNEL_FORMATS", "WAV_SUBTYPE", "EXPORT_NOTATION",
    "EXPORT_SAMPLES", "EXPORT_USED_SOUNDS", "CROSSFADE_SEC", "RESOURCE_PROFILE", "ACE_LOG_LEVEL", "ACE_LOG_MAX_MB", "ACE_LOG_PROFILER_STEPS",
    "STEM_SEPARATION", "MODEL_DEMUCS", "SEPARATION_SHIFTS", "NEURAL_CLASSIFIER", "EXPORT_STEMS",
    "STEMS_ALL_FORMATS", "STEM_CACHE",
}


_ACE_PRIORITY = "normal"


def _resample_linear(x, sr_from, sr_to):
    if int(sr_from) == int(sr_to):
        return x
    n = int(round(len(x) * sr_to / sr_from))
    t_new = np.linspace(0, len(x) - 1, n)
    if x.ndim == 1:
        return np.interp(t_new, np.arange(len(x)), x).astype(np.float32)
    return np.stack([np.interp(t_new, np.arange(len(x)), x[:, c]) for c in range(x.shape[1])], axis=1).astype(np.float32)


def load_stereo_48k(fpath, sr_dest):
    x, sr_x = sf.read(str(fpath), dtype="float32", always_2d=True)
    if x.shape[1] == 1:
        x = np.repeat(x, 2, axis=1)
    elif x.shape[1] > 2:
        x = x[:, :2]
    return _resample_linear(x, sr_x, sr_dest)


def match_rms_stereo(st, mono, target_rms=0.18):
    rms = float(np.sqrt(np.mean(mono ** 2)))
    g = (target_rms / rms) if rms > 1e-5 else 1.0
    return (np.tanh(st * g) * 0.95).astype(np.float32)


def join_stereo_with_crossfade(so_far, new_one, sr, crossfade_time_sec=0.4):
    if so_far is None or len(so_far) == 0:
        return new_one
    return np.stack([join_bar_aligned_with_crossfade(so_far[:, c], new_one[:, c], sr, crossfade_time_sec) for c in range(2)], axis=1)


def save_audio_versions_ace(directory, base_name, mono, stereo, sr, registry=None, root=None):
    """Like save_audio_versions, but the 'stereo' version is REAL stereo from ACE-Step (not pseudo-stereo from mono)."""
    paths = save_audio_versions(directory, base_name, mono, sr, registry, root)
    if "stereo" in CHANNEL_FORMATS and stereo is not None:
        for p in paths:
            if p.name.endswith("_stereo.wav"):
                sf.write(str(p), np.clip(stereo, -1.0, 1.0), int(sr), subtype=WAV_SUBTYPE)
    return paths


class _SequentialExecutor:
    """ThreadPoolExecutor replacement: the task is computed immediately (no parallelism with ACE-Step - saves RAM)."""
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False
    def submit(self, fn, *args, **kwargs):
        from concurrent.futures import Future
        f = Future()
        try:
            f.set_result(fn(*args, **kwargs))
        except BaseException as e:
            f.set_exception(e)
        return f


def _background_executor():
    return _SequentialExecutor() if ACE_LOW_RAM else ThreadPoolExecutor(max_workers=1)


def _t(sec):
    sec = max(0.0, float(sec))
    return f"{int(sec // 60)}:{sec % 60:04.1f}"


def cover_fragments(input_len):
    """List of (start, end) in seconds - sorted, clipped to the file length, overlapping ones merged."""
    if ACE_COVER_WHOLE_FILE or not ACE_COVER_FRAGMENTS:
        return []
    fr = []
    for f in ACE_COVER_FRAGMENTS:
        try:
            a, b = max(0.0, float(f[0])), min(float(input_len), float(f[1]))
        except Exception:
            continue
        if b - a >= 1.0:
            fr.append([a, b])
    fr.sort()
    merged = []
    for a, b in fr:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return [tuple(x) for x in merged]


def num_passes(n_sections):
    if ACE_WHOLE_TRACK:
        return 1
    return max(1, int(ACE_NUM_PASSES or n_sections))


def _rms(x):
    return float(np.sqrt(np.mean(np.square(x)))) if len(x) else 0.0


def insert_with_crossfade(base, chunk, start, sr, xf_sec=0.5):
    """Pastes a piece in place of the original from sample start, with a smooth transition at both edges."""
    out = base.copy()
    end = min(len(out), start + len(chunk))
    chunk = chunk[:end - start]
    n = min(int(xf_sec * sr), len(chunk) // 2)
    out[start:end] = chunk
    if n > 0:
        t = np.linspace(0.0, np.pi / 2, n, dtype=np.float32)[:, None]
        out[start:start + n] = base[start:start + n] * np.cos(t) + chunk[:n] * np.sin(t)
        out[end - n:end] = chunk[-n:] * np.cos(t) + base[end - n:end] * np.sin(t)
    return out


def generate_cover(engine, file, orig_st, sr, base_len, total_sec, n_sections, common, final_dir, track_name):
    """The whole cover according to the settings: whole file / fragments inserted into the original / fragments separately."""
    P = num_passes(n_sections)
    fr = cover_fragments(base_len)
    if not fr:
        len_c = min(total_sec, len(orig_st) / sr)
        print(f"[ACE] COVER MODE: {len_c:.1f}s of the track, passes: {P}")
        return segment_cover(engine, orig_st, sr, 0.0, len_c, P, common, "Cover")
    print(f"[ACE] FRAGMENT COVER MODE ({'inserted into the original' if ACE_COVER_FRAGMENTS_MODE == 'insert' else 'assembled separately'}): "
          + ", ".join(f"{_t(a)}-{_t(b)}" for a, b in fr) + f"; passes per fragment: {P}")
    if ACE_COVER_FRAGMENTS_MODE == "insert":
        st = orig_st[:int(min(total_sec, base_len) * sr)].copy()
        for i, (a, b) in enumerate(fr, 1):
            if a * sr >= len(st):
                continue
            pt = segment_cover(engine, orig_st, sr, a, b, P, common, f"Fragment {i}/{len(fr)}")
            orig = st[int(a * sr):int(a * sr) + len(pt)]
            if _rms(pt) > 1e-5:
                gain = min(4.0, _rms(orig) / _rms(pt))
                log_line("COVER", f"Fragment {i}: matching loudness to the original", rms_original=_rms(orig), rms_cover=_rms(pt),
                      gain_val=gain, gain_dB=20 * np.log10(max(gain, 1e-9)), start_sample=int(a * sr), num_samples=len(pt))
                pt = pt * gain                                          # loudness as in the original at this spot
            st = insert_with_crossfade(st, pt, int(a * sr), sr)
            sf.write(str(final_dir / f"{track_name}_fragment_{i:02d}_{_t(a).replace(':', 'm')}.wav"), np.clip(pt, -1, 1), int(sr), subtype=WAV_SUBTYPE)
        return st
    st = None
    for i, (a, b) in enumerate(fr, 1):
        pt = segment_cover(engine, orig_st, sr, a, b, P, common, f"Fragment {i}/{len(fr)}")
        sf.write(str(final_dir / f"{track_name}_fragment_{i:02d}_{_t(a).replace(':', 'm')}.wav"), np.clip(pt, -1, 1), int(sr), subtype=WAV_SUBTYPE)
        st = pt if st is None else join_stereo_with_crossfade(st, pt, sr, crossfade_time_sec=0.5)
    return st


_TEMPLATE_SR = 48000


_TEMPLATE_LEN_SEC = 30.0


_TEMPLATES_MAX = 10                     # more templates = fragments shorter than 3 s, which add little


def _template_paths():
    outcome = []
    for p in ACE_STYLE_TEMPLATES or []:
        p = Path(p)
        if not p.is_absolute():
            p = TEMPLATES_DIR / p
        if p.is_file():
            outcome.append(p)
        else:
            print(f"[TEMPLATES] File {p} does not exist - skipping.")
    return outcome


def _strongest_windows(mono, sr, len_sec, how_many):
    """Starts (in samples) of 'count' non-overlapping windows of len_sec with the highest energy (usually drop / chorus)."""
    n = int(len_sec * sr)
    block = max(1, sr // 2)
    nb = len(mono) // block
    k = max(1, int(round(len_sec * sr / block)))
    if len(mono) <= n or nb <= k:
        return [0] * how_many
    energy = np.square(mono[:nb * block].astype(np.float64)).reshape(nb, block).mean(axis=1)
    sums = np.convolve(energy, np.ones(k), mode="valid")       # energy of the window starting in the given block
    chosen = []
    for j in np.argsort(-sums):
        j = int(j)
        if all(abs(j - w) >= k for w in chosen):
            chosen.append(j)
            if len(chosen) == how_many:
                break
    while len(chosen) < how_many:                                    # short track: we repeat the best window
        chosen.append(chosen[0] if chosen else 0)
    return sorted(w * block for w in chosen)


def prepare_style_templates():
    """Loads the template tracks (ACE_STYLE_TEMPLATES), assembles a 30-second sound reference from them and describes that sound
    with prompt tags. Returns a dict or None when there are no templates (then the regular reference from the input file is used)."""
    file_list = _template_paths()
    if not file_list:
        return None
    if len(file_list) > _TEMPLATES_MAX:
        print(f"[TEMPLATES] {len(file_list)} templates selected - using the first {_TEMPLATES_MAX}.")
        file_list = file_list[:_TEMPLATES_MAX]
    n = len(file_list)
    slots = 3 if n <= 3 else n                    # 1-3 templates: 3 fragments of 10 s alternately; more: one from each
    sr = _TEMPLATE_SR
    slot_len = _TEMPLATE_LEN_SEC / slots
    n_slot = int(round(slot_len * sr))
    print(f"\n[TEMPLATES] Style based on template tracks ({n}): {', '.join(p.name for p in file_list)}")
    chunks, fragments, tag_counter, tempos = [None] * slots, [], {}, {}
    for i, file in enumerate(file_list):
        mine = [s for s in range(slots) if s % n == i]
        try:
            x = _load_stereo(file, sr)
        except Exception as e:
            print(f"[TEMPLATES] {file.name}: could not be loaded ({type(e).__name__}: {e}) - skipping.")
            continue
        if len(x) < sr:
            print(f"[TEMPLATES] {file.name}: shorter than 1 s - skipping.")
            continue
        mono = x.mean(axis=1)
        for s, st in zip(mine, _strongest_windows(mono, sr, slot_len, len(mine))):
            k = x[st:st + n_slot]
            if len(k) < n_slot:                                   # short track: we loop it
                k = np.tile(x, (int(np.ceil(n_slot / len(x))) + 1, 1))[st:st + n_slot]
            chunks[s] = k
            fragments.append({"file": file.name, "start_s": round(st / sr, 1), "len_s": round(n_slot / sr, 1),
                              "position_in_reference_s": round(s * n_slot / sr, 1)})
            print(f"   • {file.name}: fragment {int(st / sr) // 60}:{int(st / sr) % 60:02d} - "
                  f"{int((st + n_slot) / sr) // 60}:{int((st + n_slot) / sr) % 60:02d}")
        try:                                                       # sound of the template - the same measures as for the input track
            analysis_m = mono[:int(ANALYSIS_MAX_SEC * sr)]
            bpm_w = detect_tempo(analysis_m, sr)
            res_profile = sound_character(frame_features(analysis_m, sr), sr / ANALYSIS_HOP, bpm_w)
            tempos[file.name] = bpm_w
            for t in res_profile["tags"]:
                tag_counter[t] = tag_counter.get(t, 0) + 1
        except Exception as e:
            print(f"[TEMPLATES] {file.name}: sound analysis skipped ({type(e).__name__}: {e})")
        del x, mono
    ready = [k for k in chunks if k is not None]
    if not ready:
        print("[TEMPLATES] None of the templates could be loaded - using the regular reference.")
        return None
    parts = []
    nf = int(0.01 * sr)                                            # 10 ms fades at fragment edges (no clicks)
    for s in range(slots):
        k = np.array(chunks[s] if chunks[s] is not None else ready[s % len(ready)], dtype=np.float32)
        rms = float(np.sqrt(np.mean(np.square(k)))) if len(k) else 0.0
        if rms > 1e-5:
            k *= 0.2 / rms                                         # equalized loudness - no template dominates
        top_peak = float(np.max(np.abs(k))) if len(k) else 0.0
        if top_peak > 0.98:
            k *= 0.98 / top_peak
        if len(k) > 2 * nf:
            k[:nf] *= np.linspace(0.0, 1.0, nf, dtype=np.float32)[:, None]
            k[-nf:] *= np.linspace(1.0, 0.0, nf, dtype=np.float32)[:, None]
        parts.append(k)
    ref = np.concatenate(parts, axis=0)
    n_target = int(_TEMPLATE_LEN_SEC * sr)
    ref = ref[:n_target] if len(ref) >= n_target else np.concatenate([ref, np.zeros((n_target - len(ref), 2), dtype=np.float32)])
    threshold = max(1, (n + 1) // 2)                                    # tags common to at least half of the templates
    tags = [t for t, c in sorted(tag_counter.items(), key=lambda tc: -tc[1]) if c >= threshold]
    if tags:
        print(f"[TEMPLATES] Sound of the templates (goes into the description instead of the input track's sound): {', '.join(tags)}")
    print(f"[TEMPLATES] Style reference: {len(parts)} fragment(s) of {slot_len:.1f} s, total {_TEMPLATE_LEN_SEC:.0f} s "
          "(replaces the input file fragment as reference audio)")
    outcome = {"audio": ref, "sr": sr, "files": [str(p) for p in file_list], "fragments": fragments, "tags": tags, "tempo_bpm": tempos}
    log_line("TEMPLATES", "Style reference from template tracks", file_list=outcome["files"], fragments=fragments, tags=tags,
          tempo_bpm=tempos, reference=ref)
    return outcome


def save_template_references(templates, fpath):
    fpath = Path(fpath)
    fpath.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(fpath), np.clip(templates["audio"], -1.0, 1.0), int(templates["sr"]))
    return fpath


def templates_description_to_json(templates):
    if not templates:
        return None
    return {k: templates[k] for k in ("files", "fragments", "tags", "tempo_bpm")}


# ==============================================================================
# ANDROID REPLACEMENTS (appended to ace_core.py by tools/build_ace_core.py)
# ==============================================================================
# numpy instead of torch, WAV files decoded by the app instead of PyAV/ffmpeg, HPSS instead of Demucs,
# a small log instead of the line tracer, and a checkpointing cover that survives restarts and low memory.

LOG_FILE = None                 # set by ace_android.configure()
CHECKPOINT_DIR = Path(".")      # set by ace_android.configure()
_LOG = {"path": None}
_LOG_LOCK = threading.Lock()


class NeedSmallerPass(Exception):
    """Raised by the engine when the native process keeps running out of memory at the current pass length."""


class Cancelled(Exception):
    """Raised when the user stopped the job."""


def _write_log(text):
    if not LOG_FILE:
        return
    try:
        with _LOG_LOCK, open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {text}\n")
    except Exception:
        pass


def _short(v):
    if isinstance(v, np.ndarray):
        return f"ndarray{tuple(v.shape)}"
    s = repr(v)
    return s if len(s) <= 200 else s[:200] + "..."


def log_line(category, message, **details):
    _write_log(f"[{category}] {message}" + "".join(f" | {k}={_short(v)}" for k, v in details.items()))


def _ram_gb():
    """(total, available) RAM in GB from /proc/meminfo, or None."""
    try:
        d = {}
        with open("/proc/meminfo") as f:
            for line in f:
                k, v = line.split(":", 1)
                d[k] = int(v.split()[0]) / 2 ** 20
        return d["MemTotal"], d.get("MemAvailable", d.get("MemFree", 0.0))
    except Exception:
        return None


def _frames(y, n_fft, hop):
    y = np.pad(np.asarray(y, dtype=np.float32), (n_fft // 2, n_fft // 2), mode="reflect")
    n = 1 + max(0, (len(y) - n_fft) // hop)
    return y, n


def _stft_power_or_mag(y, n_fft, hop, power):
    """|STFT| (or |STFT|^2) as [bins, frames], computed in chunks so long windows do not need much RAM."""
    y, n = _frames(y, n_fft, hop)
    wnd = np.hanning(n_fft + 1)[:-1].astype(np.float32)
    out = np.empty((n_fft // 2 + 1, n), dtype=np.float32)
    chunk = max(1, int(2 ** 24 // n_fft))          # ~64 MB of float32 frames per chunk
    base = np.arange(n_fft)[None, :]
    for a in range(0, n, chunk):
        b = min(n, a + chunk)
        idx = base + hop * np.arange(a, b)[:, None]
        S = np.abs(np.fft.rfft(y[idx] * wnd, axis=1)).astype(np.float32)
        out[:, a:b] = (S * S if power else S).T
    return out


def _stft_mag(y_np, n_fft, hop):
    return _stft_power_or_mag(y_np, n_fft, hop, power=False)


def native_chromagram_pytorch(y, sr, n_fft=4096, hop_length=512, n_chroma=12, fmin=27.5, fmax=None):
    """Same chromagram as the desktop version, computed with numpy (the name is kept for compatibility)."""
    spec = _stft_power_or_mag(y, n_fft, hop_length, power=True)
    freqs = np.linspace(0, sr / 2.0, n_fft // 2 + 1)
    valid = (freqs > fmin) & (freqs <= (fmax if fmax else sr / 2.0))
    chroma_fb = np.zeros((n_chroma, len(freqs)), dtype=np.float32)
    midi = np.zeros_like(freqs)
    midi[valid] = 69.0 + 12.0 * np.log2(freqs[valid] / 440.0)
    bins = (np.round(midi[valid]).astype(int) % n_chroma)
    np.add.at(chroma_fb, (bins, np.nonzero(valid)[0]), 1.0)
    chroma_fb = chroma_fb / np.maximum(1.0, chroma_fb.sum(axis=1, keepdims=True))
    chroma = chroma_fb @ spec
    return chroma / np.maximum(1e-6, np.max(chroma, axis=0, keepdims=True))


def _read_stereo(file, sr_target):
    x, sr_x = sf.read(str(file), dtype="float32", always_2d=True)
    if x.shape[1] == 1:
        x = np.repeat(x, 2, axis=1)
    x = x[:, :2]
    return _resample_linear(x, sr_x, sr_target).astype(np.float32)


def load_audio_via_av_or_ffmpeg(file_path, target_sr=32000):
    """The app has already decoded the track to WAV (MediaCodec) - here: mono, resampled, peak normalized."""
    x, sr_x = sf.read(str(file_path), dtype="float32", always_2d=True)
    audio_np = x.mean(axis=1).astype(np.float32)
    del x
    audio_np = _resample_linear(audio_np, sr_x, target_sr)
    peak = float(np.max(np.abs(audio_np))) if len(audio_np) else 0.0
    if peak > 1e-5:
        audio_np = (audio_np / peak) * 0.9
    return audio_np.astype(np.float32), target_sr


def load_original_stereo(file, sr_target, reserve_mono, sr_mono):
    try:
        x = _read_stereo(file, sr_target)
        if len(x) > sr_target:
            return x
    except Exception as e:
        print(f"[ACE] Stereo original unavailable ({type(e).__name__}: {e}) - using the mono version.")
    m = _resample_linear(np.asarray(reserve_mono, dtype=np.float32), sr_mono, sr_target)
    return np.stack([m, m], axis=1)


def _load_stereo(file, sr_target):
    return _read_stereo(file, sr_target)


def prepare_window_stems(file, audio, sr, plan, window_len_sec):
    """PRO analysis on the phone: HPSS separation (numpy) + heuristic instrument recognition for each plan window."""
    try:
        separator = _SeparatorHPSS()
        print(f"\n[STEMS] Separation ({separator.description}) {len(plan)} windows of {window_len_sec:.1f}s; "
              f"stems: {', '.join(separator.names)}")
        n_window = int(window_len_sec * sr)
        results = []
        for i, p in enumerate(plan, 1):
            check_cancel()
            start = min(max(0.0, float(p["start_s"])), max(0.0, len(audio) / sr - window_len_sec))
            wnd = _match_length(audio[int(start * sr):int(start * sr) + n_window], n_window)
            fpath = _cache_path(file, start, window_len_sec, separator.description)
            stems = None
            if STEM_CACHE and fpath.exists():
                try:
                    with np.load(fpath, allow_pickle=False) as z:
                        stems = {k: z[k] for k in z.files}
                except Exception:
                    stems = None
            if stems is None:
                stems = separator.separate(wnd, sr)
                if STEM_CACHE:
                    try:
                        fpath.parent.mkdir(parents=True, exist_ok=True)
                        np.savez(fpath, **stems)
                    except Exception:
                        pass
            class_names = classify_stems(stems, sr, None)
            mel = {n: a for n, a in stems.items() if n in MELODIC_STEMS and class_names[n]["present"]}
            lead = max(mel, key=lambda n: _rms(mel[n])) if mel else None
            results.append({"stems": stems, "classes": class_names, "lead_stem": lead,
                            "description": instruments_description(class_names), "start_s": round(start, 3),
                            "separator": separator.description})
            report_progress(None, f"Stems {i}/{len(plan)}")
        return results
    except Cancelled:
        raise
    except Exception as e:
        print(f"[STEMS] Separation skipped ({type(e).__name__}: {e}) - working on the full mix.")
        return None


# ---------- hooks set by ace_android (cancel / progress) ----------
_HOOKS = {"cancel": lambda: False, "progress": lambda frac, text: None}


def check_cancel():
    if _HOOKS["cancel"]():
        raise Cancelled()


def report_progress(frac, text):
    try:
        _HOOKS["progress"](frac, text)
    except Exception:
        pass


def _ckpt_path(*key):
    h = hashlib.sha1("|".join(str(k) for k in key).encode("utf-8")).hexdigest()[:20]
    return CHECKPOINT_DIR / f"{h}.npy"


def segment_cover(engine, orig_st, sr, a_sec, b_sec, n_passes, common, description):
    """Cover of fragment [a, b] in n passes (overlaps + crossfade). Every finished pass is kept on disk, so an interrupted
    or memory-limited run continues where it stopped. The pass count grows automatically when memory is too small."""
    L = b_sec - a_sec
    max_pass = float(getattr(engine, "max_pass_sec", 0) or 0)
    want = int(n_passes)
    if max_pass > 0:
        want = max(want, int(np.ceil(L / max_pass)))
    while True:
        n = max(1, min(want, int(L // 10) or 1))      # each pass at least ~10 s
        try:
            return _segment_cover_passes(engine, orig_st, sr, a_sec, b_sec, n, common, description)
        except NeedSmallerPass:
            if n >= max(1, int(L // 10)):
                raise
            want = n * 2
            print(f"[ACE] {description}: not enough memory for passes of {L / n:.0f} s - continuing with {want} shorter passes.")


def _segment_cover_passes(engine, orig_st, sr, a_sec, b_sec, n, common, description):
    L = b_sec - a_sec
    ln = L / n
    m = min(ACE_MARGIN_SEC, ln / 2) if n > 1 else 0.0
    xf = min(1.0, m)
    outcome = None
    for k in range(n):
        check_cancel()
        pa, pb = max(0.0, k * ln - m), min(L, (k + 1) * ln + m)
        ck = _ckpt_path("cover", description, round(a_sec, 3), round(b_sec, 3), n, k, common.get("seed"),
                        common.get("caption"), ACE_COVER_STRENGTH, ACE_COVER_NOISE, ACE_MODEL_DIT, ACE_GGUF_QUANT, ACE_STEPS)
        report_progress(None, f"{description}: pass {k + 1}/{n}")
        if ck.exists():
            pt = np.load(ck)
            print(f"[ACE] {description}: pass {k + 1}/{n} restored from the checkpoint.")
        else:
            src = orig_st[int((a_sec + pa) * sr):int((a_sec + pb) * sr)]
            p_src, p_out = TEMP_DIR / f"_temp_ace_src_{k:03d}.wav", TEMP_DIR / f"_temp_ace_cov_{k:03d}.wav"
            sf.write(str(p_src), np.clip(src, -1.0, 1.0), int(sr))
            z = dict(common, duration=max(10.0, pb - pa), out=str(p_out), task_type="cover", src_audio=str(p_src),
                     audio_cover_strength=float(ACE_COVER_STRENGTH), cover_noise_strength=float(ACE_COVER_NOISE))
            print(f"[ACE] {description}: pass {k + 1}/{n} ({_t(a_sec + pa)} - {_t(a_sec + pb)}), original strength {ACE_COVER_STRENGTH}")
            t0 = time.time()
            engine.generate(z)
            print(f"[ACE] {description}: pass {k + 1}/{n} done in {(time.time() - t0) / 60:.1f} min.")
            pt = load_stereo_48k(p_out, sr)
            n_parts = int((pb - pa) * sr)
            pt = pt[:n_parts] if len(pt) >= n_parts else np.concatenate([pt, np.zeros((n_parts - len(pt), 2), dtype=np.float32)])
            np.save(ck, pt)
            for p in (p_src, p_out):
                try:
                    p.unlink()
                except Exception:
                    pass
        left = (k * ln - pa - xf / 2) if k > 0 else 0.0
        right = ((k + 1) * ln + xf / 2 - pa) if k < n - 1 else (pb - pa)
        pt = pt[int(left * sr):int(right * sr)]
        outcome = pt if outcome is None else join_stereo_with_crossfade(outcome, pt, sr, crossfade_time_sec=xf)
    n_target = int(L * sr)
    return outcome[:n_target] if len(outcome) >= n_target else np.concatenate([outcome, np.zeros((n_target - len(outcome), 2), dtype=np.float32)])


def _ollama_options():
    return {}
