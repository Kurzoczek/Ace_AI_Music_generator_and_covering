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
