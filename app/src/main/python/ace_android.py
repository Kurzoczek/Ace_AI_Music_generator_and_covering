# -*- coding: utf-8 -*-
"""Entry point of the Python part of the Android app (called from Kotlin through Chaquopy).

Kotlin (engine/PythonBridge.kt) calls  run(config_json, bridge)  inside the foreground service. The bridge is a Kotlin
object; Python calls these methods on it:
    onLog(line)                          - one line of log text for the screen
    onProgress(fraction, text)           - fraction 0..1 or -1 when unknown
    isCancelled() -> bool                - the user pressed Stop
    onNativeStart(pid, stage)            - a native acestep.cpp process started (the ResourceGovernor throttles it)
    onNativeEnd(pid, code, peakRssKb, stage, durationSec, threads)
    onLowMemory(stage, peakRssKb, attempt, threads) -> JSON {"threads": n, "lm_enabled": bool, "wait_sec": s}
    waitForMemory(neededMb, maxWaitSec) -> bool  - blocks until enough RAM is available (or the time is up)

Design rules for low memory (the user may declare less RAM than the model needs):
  * the run never gives up because of memory: a native process killed by the system (OOM) is restarted after the
    memory recovers, with fewer threads and without the language model, and long passes are split into shorter ones;
  * every finished pass / section is checkpointed on disk, so a restart (or a service timeout) continues where it stopped.
"""
import gc
import hashlib
import json
import os
import random
import signal
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

import numpy as np

import ace_core as C
import wavsf as sf

_BRIDGE = None
MIN_SHRINKABLE_SEC = 24.0       # passes shorter than this are not split any further (10 s + margins)


# ------------------------------------------------------------------ logging to the app screen
class _BridgeWriter:
    def __init__(self, bridge, original):
        self.bridge, self.original, self.buf = bridge, original, ""

    def write(self, s):
        self.buf += s
        while "\n" in self.buf or "\r" in self.buf:
            cut = min(i for i in (self.buf.find("\n"), self.buf.find("\r")) if i >= 0)
            line, self.buf = self.buf[:cut], self.buf[cut + 1:]
            if line.strip():
                C._write_log(line)
                try:
                    self.bridge.onLog(line)
                except Exception:
                    pass
        return len(s)

    def flush(self):
        pass


# ------------------------------------------------------------------ configuration
def configure(cfg):
    paths = cfg["paths"]
    C.WORKSPACE_DIR = Path(paths["workspace"])
    C.OUTPUT_DIR = Path(paths["output"])
    C.TEMP_DIR = Path(paths["temp"])
    C.TEMPLATES_DIR = Path(paths["templates"])
    C.CHECKPOINT_DIR = Path(paths["checkpoints"])
    C.INPUT_DIR = Path(paths.get("input", paths["temp"]))
    for d in (C.WORKSPACE_DIR, C.OUTPUT_DIR, C.TEMP_DIR, C.CHECKPOINT_DIR):
        d.mkdir(parents=True, exist_ok=True)
    C.LOG_FILE = str(Path(paths["logs"]) / f"log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
    Path(paths["logs"]).mkdir(parents=True, exist_ok=True)
    C._LOG["path"] = C.LOG_FILE

    settings = cfg.get("settings", {})
    for k, v in settings.items():
        if k in C.MENU_VARIABLES:
            setattr(C, k, tuple(v) if k == "CHANNEL_FORMATS" else v)
    # the app always uses the C++ engine on the CPU; Ollama, Demucs and AST are not available on the phone
    C.ACE_ENGINE, C.ACE_DEVICE, C.USE_OLLAMA, C.NEURAL_CLASSIFIER = "cpp", "cpu", False, False
    if not C.ACE_STEPS:
        C.ACE_STEPS = 8 if "turbo" in str(C.ACE_MODEL_DIT) else 32
    C.MODEL_ID = C.ACE_MODEL_DIT
    C._ACE_WHOLE = bool(C.ACE_WHOLE_TRACK) or C.ACE_MODE == "cover"
    C.SCRIPT_SUBDIR = cfg.get("subdir", "android")
    C.ACE_GENERATION_LIMIT_SEC = float(settings.get("ACE_GENERATION_LIMIT_SEC") or 72 * 3600)


# ------------------------------------------------------------------ native engine
def _read_status(pid):
    out = {}
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith(("VmRSS:", "VmHWM:")):
                    k, v = line.split(":", 1)
                    out[k] = int(v.split()[0])
    except Exception:
        pass
    return out


def _looks_like_oom(rc, tail):
    if rc in (-signal.SIGKILL, 137):
        return True
    text = " ".join(tail).lower()
    return any(s in text for s in ("bad_alloc", "out of memory", "failed to allocate", "cannot allocate", "oom"))


class AndroidCppEngine:
    """acestep.cpp executables packaged in the APK (nativeLibraryDir), run as separate processes.
    Separate processes keep the app alive when the system kills the model for memory, and let the app
    throttle the CPU usage (SIGSTOP / SIGCONT duty cycle, done by the Kotlin ResourceGovernor)."""
    item_name = "C++ (acestep.cpp, GGUF, Android)"

    def __init__(self, cfg, bridge):
        r = cfg["resources"]
        self.bridge = bridge
        self.native_dir = Path(cfg["paths"]["native"])
        self.models_dir = Path(cfg["paths"]["models"])
        self.threads = max(1, int(r.get("threads") or 1))
        self.nice = int(r.get("nice") or 0)
        self.cores = [int(c) for c in (r.get("cores") or [])]
        self.lm_enabled = bool(r.get("lm_enabled", True))
        self.max_pass_sec = float(r.get("max_pass_sec") or 0)
        self.vae_chunk = int(r.get("vae_chunk") or 0)        # 0 = engine default (1024 latent frames per tile)
        self.allow_shrink = True
        self.proc = None

    def _program(self, name):
        p = self.native_dir / {"ace-synth": "libacesynth.so", "ace-lm": "libacelm.so"}[name]
        if not p.exists():
            raise FileNotFoundError(f"native program missing: {p}")
        return p

    def _model_dit(self):
        file = C.gguf_dit_name(C.ACE_MODEL_DIT, C.ACE_GGUF_QUANT)
        if not (self.models_dir / file).exists():
            raise FileNotFoundError(f"model {file} is not downloaded")
        return file

    def _model_lm(self):
        if not self.lm_enabled or not C.ACE_CPP_LM:
            return None
        file = C.gguf_lm_name(C.ACE_CPP_LM, C.ACE_GGUF_QUANT)
        return file if file and (self.models_dir / file).exists() else None

    def _preexec(self):
        try:
            if self.nice:
                os.nice(self.nice)
        except Exception:
            pass
        try:
            if self.cores:
                os.sched_setaffinity(0, set(self.cores))
        except Exception:
            pass

    def _run(self, argv, description, stage, duration):
        print(f"[ACE-C++] {description} (threads: {self.threads})")
        C.log_line("ACE-C++", f"Starting {description}", command=[str(a) for a in argv])
        env = dict(os.environ)
        env.update({"ACE_THREADS": str(self.threads), "OMP_NUM_THREADS": str(self.threads),
                    "LD_LIBRARY_PATH": str(self.native_dir) + ":" + env.get("LD_LIBRARY_PATH", "")})
        t0 = time.time()
        self.proc = subprocess.Popen([str(a) for a in argv], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, encoding="utf-8", errors="replace", bufsize=1, env=env,
                                     cwd=str(self.models_dir), preexec_fn=self._preexec, start_new_session=True)
        pid = self.proc.pid
        self.bridge.onNativeStart(pid, stage)
        lines, tail, peak = [], [], 0
        lock = threading.Lock()

        def reader(stream):
            for line in stream:
                with lock:
                    lines.append(line.rstrip("\r\n"))

        th = threading.Thread(target=reader, args=(self.proc.stdout,), daemon=True)
        th.start()
        last_print = 0.0
        try:
            while True:
                rc = self.proc.poll()
                st = _read_status(pid)
                peak = max(peak, st.get("VmHWM", 0), st.get("VmRSS", 0))
                with lock:
                    new, lines[:] = list(lines), []
                for line in new:
                    if not line.strip():
                        continue
                    C._write_log("[ACE-C++] " + line)
                    tail = (tail + [line])[-25:]
                    if "[Load]" in line or "FATAL" in line or "ERROR" in line or time.time() - last_print > 2.0:
                        last_print = time.time()
                        print(f"   {line[:170]}")
                if rc is not None:
                    break
                if self.bridge.isCancelled():
                    self.stop()
                    raise C.Cancelled()
                if time.time() - t0 > C.ACE_GENERATION_LIMIT_SEC:
                    self.stop()
                    raise TimeoutError(f"time limit exceeded ({C.ACE_GENERATION_LIMIT_SEC:.0f}s)")
                time.sleep(0.25)
        finally:
            th.join(timeout=2.0)
            rc = self.proc.poll() if self.proc else -1
            self.bridge.onNativeEnd(pid, int(rc if rc is not None else -1), int(peak), stage, float(duration), self.threads)
            self.proc = None
        return rc, tail, peak, time.time() - t0

    def stop(self):
        p, self.proc = self.proc, None
        if p is not None and p.poll() is None:
            try:
                os.kill(p.pid, signal.SIGCONT)      # a paused (throttled) process must run to be able to die cleanly
            except Exception:
                pass
            try:
                p.kill()
                p.wait(timeout=10)
            except Exception:
                pass

    def _single_job(self, z):
        tmp_dir = Path(z["out"] + "_cpp")
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)
        tmp_dir.mkdir(parents=True, exist_ok=True)
        cover = z.get("task_type") == "cover"
        task = {"caption": z["caption"][:500], "lyrics": z.get("lyrics") or "[Instrumental]", "duration": float(z["duration"]),
                "bpm": int(z.get("bpm") or 0), "keyscale": z.get("keyscale") or "", "timesignature": "4",
                "seed": int(z.get("seed", -1)), "inference_steps": int(z.get("steps") or 0),
                "guidance_scale": float(z.get("guidance") or 0.0), "synth_model": self._model_dit(),
                "output_format": "wav24", "synth_batch_size": 1, "lm_batch_size": 1, "use_cot_caption": False}
        if cover:
            task.update({"task_type": "cover", "audio_cover_strength": float(z.get("audio_cover_strength", 1.0)),
                         "cover_noise_strength": float(C.ACE_COVER_NOISE)})
        fpath = tmp_dir / "request.json"
        fpath.write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")
        lm = None if cover else self._model_lm()
        if lm:
            fpath.write_text(json.dumps(dict(task, lm_model=lm), ensure_ascii=False, indent=2), encoding="utf-8")
            rc, tail, peak, _ = self._run([self._program("ace-lm"), "--models", self.models_dir, "--request", fpath,
                                           "--device", "CPU"], f"ace-lm ({lm})", "lm", task["duration"])
            if rc != 0:
                return rc, tail, peak, "lm"
            produced = sorted(tmp_dir.glob("request[0-9]*.json"))
            if produced:
                fpath = produced[0]
        argv = [self._program("ace-synth"), "--models", self.models_dir, "--request", fpath, "--device", "CPU"]
        if z.get("src_audio"):
            argv += ["--src-audio", z["src_audio"]]
        if z.get("reference_audio"):
            argv += ["--ref-audio", z["reference_audio"]]
        if self.vae_chunk:
            argv += ["--vae-chunk", str(self.vae_chunk), "--vae-overlap", str(min(64, self.vae_chunk // 4))]
        rc, tail, peak, _ = self._run(argv, f"ace-synth ({task['synth_model']}, {task['duration']:.0f} s)", "synth", task["duration"])
        if rc != 0:
            return rc, tail, peak, "synth"
        results = sorted(tmp_dir.glob(fpath.stem + "*.wav"), key=lambda p: p.stat().st_mtime)
        if not results:
            return 1, tail + [f"ace-synth did not write a wav file in {tmp_dir}"], peak, "synth"
        if os.path.exists(z["out"]):
            os.remove(z["out"])
        shutil.move(str(results[-1]), z["out"])
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return 0, tail, peak, "synth"

    def generate(self, job):
        """Never gives up because of memory: waits for free RAM, lowers threads, drops the LM, asks for shorter passes."""
        other_failures, oom_in_row, attempt = 0, 0, 0
        while True:
            C.check_cancel()
            attempt += 1
            rc, tail, peak, stage = self._single_job(job)
            if rc == 0:
                return {"out": job["out"]}
            if _looks_like_oom(rc, tail):
                oom_in_row += 1
                print(f"[MEMORY] The model process ran out of memory ({stage}, peak {peak / 1024:.0f} MB, attempt {attempt}).")
                try:
                    plan = json.loads(str(self.bridge.onLowMemory(stage, int(peak), attempt, self.threads)))
                except Exception:
                    plan = {"threads": max(1, self.threads // 2), "lm_enabled": False, "wait_sec": 30}
                self.threads = max(1, int(plan.get("threads", self.threads)))
                if stage == "synth":                       # smaller VAE tiles = less memory for decoding the audio
                    self.vae_chunk = max(64, (self.vae_chunk or 1024) // 2)
                if stage == "lm" or not plan.get("lm_enabled", True):
                    if self.lm_enabled and C.ACE_CPP_LM and C.ACE_MODE != "cover":
                        print("[MEMORY] Continuing without the language model (it needs extra RAM).")
                    self.lm_enabled = False
                if stage == "synth" and oom_in_row >= 2 and self.allow_shrink and float(job.get("duration", 0)) > MIN_SHRINKABLE_SEC:
                    raise C.NeedSmallerPass()
                need_mb = max(256, int(peak / 1024 * 1.1))
                wait = int(plan.get("wait_sec", 30))
                print(f"[MEMORY] Waiting up to {wait} s for ~{need_mb} MB of free RAM, then retrying with {self.threads} thread(s)...")
                C.report_progress(None, "Waiting for free memory")
                self.bridge.waitForMemory(need_mb, wait)
                continue
            oom_in_row = 0
            other_failures += 1
            msg = " | ".join(tail[-4:])
            print(f"[ACE-C++] Attempt {attempt} failed (code {rc}): {msg}")
            if other_failures >= C.ACE_MAX_RETRIES:
                raise RuntimeError(f"acestep.cpp failed {other_failures} times (code {rc}): {msg}")
            time.sleep(5)


# ------------------------------------------------------------------ resumable state
def _state_for(input_wav, cfg):
    key = json.dumps({"in": str(input_wav), "size": Path(input_wav).stat().st_size, "settings": cfg.get("settings"),
                      "prompt": cfg.get("prompt")}, sort_keys=True, default=str)
    h = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
    path = C.CHECKPOINT_DIR / f"state_{h}.json"
    if path.exists():
        try:
            return path, json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    state = {"session_ts": datetime.now().strftime("%Y%m%d_%H%M%S"), "seed": random.randint(0, 2 ** 31 - 1)}
    path.write_text(json.dumps(state), encoding="utf-8")
    return path, state


def _clear_checkpoints(state_path):
    for p in C.CHECKPOINT_DIR.glob("*.npy"):
        try:
            p.unlink()
        except Exception:
            pass
    try:
        state_path.unlink()
    except Exception:
        pass


# ------------------------------------------------------------------ one input file
def process_file(engine, cfg, input_item, templates, file_idx, n_files):
    input_file = Path(input_item["wav"])
    clean_name = Path(input_item.get("name") or input_file.stem).stem
    short_name = C._safe_name(clean_name)
    state_path, state = _state_for(input_file, cfg)
    session_ts = state["session_ts"]
    user_guidelines = cfg.get("prompt") or C.DEFAULT_USER_DESCRIPTION
    print("\n" + "#" * 50)
    print(f" FILE [{file_idx}/{n_files}]: {clean_name}")
    print("#" * 50)

    C.report_progress(0.0, f"Analyzing {clean_name}")
    full_base_audio, sr = C.load_audio_via_av_or_ffmpeg(input_file, target_sr=32000)
    print(f"[LOADING] {len(full_base_audio) / sr:.1f} s of audio.")
    C.check_cancel()
    detected_bpm, detected_key = C.analyze_base_audio(full_base_audio, sr, clean_name)
    C.check_cancel()
    analysis = C.analyze_input(full_base_audio, sr, detected_bpm, detected_key, clean_name)
    C.check_cancel()

    beat_sec = 60.0 / detected_bpm
    num_beats = 32
    while num_beats > 8 and num_beats * beat_sec + C.CROSSFADE_SEC > C.MAX_SEGMENT_LEN_SEC:
        num_beats //= 2
    segment_length_sec = beat_sec * num_beats
    base_length_sec = len(full_base_audio) / sr
    if C.ACE_MODE == "cover":
        fr = C.cover_fragments(base_length_sec)
        if fr and C.ACE_COVER_FRAGMENTS_MODE == "separate":
            cov_len = sum(b - a for a, b in fr)
        elif C.ACE_COVER_WHOLE_FILE or fr:
            cov_len = min(base_length_sec, C.ACE_COVER_MAX_SEC or base_length_sec)
        else:
            cov_len = None
        if cov_len:
            C.NUM_SEGMENTS = max(1, int(np.ceil(cov_len / segment_length_sec - 0.05)))
            print(f"[ACE] Cover: {cov_len:.1f}s -> {C.NUM_SEGMENTS} sections of {segment_length_sec:.1f}s")
    elif not C._ACE_WHOLE and C.ACE_NUM_PASSES:
        C.NUM_SEGMENTS = max(1, int(C.ACE_NUM_PASSES))
    n_seg = C.NUM_SEGMENTS
    total_sec = n_seg * segment_length_sec + C.CROSSFADE_SEC

    # text mode, whole track: if the declared RAM is too small for the whole track, go section by section from the start
    if C.ACE_MODE != "cover" and C._ACE_WHOLE and engine.max_pass_sec and total_sec > engine.max_pass_sec:
        print(f"[MEMORY] The whole track ({total_sec:.0f} s) does not fit in the RAM limit - generating section by section.")
        C._ACE_WHOLE = False

    session_name = f"{short_name}_{int(detected_bpm)}bpm_{session_ts}"
    directories = C.prepare_session_dirs(session_name)
    directories["stems"] = directories["root"] / "stems"
    root = directories["root"]
    manifest = {"final": [], "parts": [], "midi": [], "notation": [], "samples": [], "used_sounds": [], "stems": []}
    sections_meta = []
    if templates and C.EXPORT_USED_SOUNDS:
        p_ref = C.save_template_references(templates, directories["used"] / "style_reference_from_templates.wav")
        manifest["used_sounds"].append(str(p_ref.relative_to(root)).replace("\\", "/"))

    plan = C.plan_segments(analysis, n_seg, segment_length_sec, num_beats, detected_bpm, base_length_sec)
    for p_ in plan:
        if analysis and p_.get("source") != "cyclic":
            p_["window"] = C.window_character(analysis, p_["start_s"], segment_length_sec)
    profile_tags = analysis["profile"]["tags"] if analysis else None
    if templates and templates["tags"]:
        profile_tags = templates["tags"]

    def tags_for(i):
        tags = list(profile_tags or []) + plan[i].get("window", {}).get("tags", []) if i < len(plan) else list(profile_tags or [])
        return tags or None

    window_stems = None
    if C.STEM_SEPARATION:
        C.report_progress(None, "Separating stems")
        window_stems = C.prepare_window_stems(input_file, full_base_audio, sr, plan, segment_length_sec + C.CROSSFADE_SEC)

    def stem_data(i):
        return window_stems[i] if window_stems and i < len(window_stems) else None

    def cut_base_segment(seg_idx, length_sec=None):
        length_sec = length_sec or segment_length_sec
        reserve = base_length_sec - length_sec
        if seg_idx < len(plan) and plan[seg_idx].get("source") != "cyclic":
            start_sec = min(max(0.0, plan[seg_idx]["start_s"]), max(0.0, reserve))
        else:
            start_sec = (seg_idx * segment_length_sec) % reserve if reserve > 1.0 else 0.0
        s = int(start_sec * sr)
        return full_base_audio[s:s + int(length_sec * sr)]

    sampling_rate = C.ACE_SR
    seed = int(C.ACE_SEED) if int(C.ACE_SEED) >= 0 else int(state["seed"])
    stem_midi, stem_percussion = {}, {}
    finished_track = finished_stereo = whole_st = whole_mono = orig_st = total_len_samples = None
    grids_lead, grids_bass, grids_chords = [], [], []
    track_name = f"track_{C.SCRIPT_SUBDIR}_{session_name}"

    infos = []
    for idx in range(n_seg):           # analysis of all sections first (cheap, no model in memory at the same time)
        C.check_cancel()
        C.report_progress(0.05 * idx / n_seg, f"Analyzing section {idx + 1}/{n_seg}")
        infos.append(C.prepare_segment_data_stems(idx + 1, n_seg, cut_base_segment(idx), sr, detected_bpm, detected_key,
                                                  user_guidelines, False, num_beats, tags_for(idx), stem_data(idx)))
    gc.collect()

    for idx in range(n_seg):
        C.check_cancel()
        num = idx + 1
        label, prompt_text, notes_info = infos[idx]
        grids_lead.append(notes_info["lead_midi"])
        grids_bass.append(notes_info["bass_midi"])
        grids_chords.append(notes_info.get("chords_beat") or [""] * len(notes_info["bass_midi"]))
        for name_s, midi_s in (notes_info.get("stem_midi") or {}).items():
            stem_midi.setdefault(name_s, {})[idx] = midi_s
        for note_s, hits_s in (notes_info.get("percussion") or {}).items():
            stem_percussion.setdefault(note_s, {})[idx] = hits_s
        print(f"\n[SECTION {num}/{n_seg} - {label.upper()}]")
        print(f"[PROMPT] {prompt_text}")
        target_time = segment_length_sec + C.CROSSFADE_SEC
        melody = None
        generation_time = 0.0
        frac0 = 0.05 + 0.85 * idx / n_seg
        C.report_progress(frac0, f"Generating section {num}/{n_seg}")
        if C._ACE_WHOLE and whole_st is None:
            markers = {"intro": "[Intro]", "build_up": "[Build-Up]", "climax_drop": "[Drop]",
                       "climax_variation": "[Drop 2]", "outro": "[Outro]"}
            structure = "\n\n".join(markers.get(C.get_section_label_and_description(k + 1, n_seg)[0], "[Verse]") for k in range(n_seg))
            intro_description = C.get_section_label_and_description(1, n_seg)[1]
            overall_description = "full track: atmospheric intro, build-up, main climax drop, variation and outro"
            caption = prompt_text.replace(intro_description, overall_description) if intro_description in prompt_text \
                else f"{prompt_text}, {overall_description}"
            lyrics = structure if C.ACE_LYRICS.strip() == "[Instrumental]" else C.ACE_LYRICS
            ref_path = None
            if templates:
                ref_path = C.save_template_references(templates, C.TEMP_DIR / "_temp_ace_ref_templates.wav")
            elif C.ACE_USE_REFERENCE:
                melody = cut_base_segment(min(2, n_seg - 1), length_sec=C.ACE_REFERENCE_LEN_SEC)
                ref_path = C.TEMP_DIR / "_temp_ace_ref_whole.wav"
                sf.write(str(ref_path), np.clip(np.asarray(melody, dtype=np.float32), -1.0, 1.0), int(sr))
            out_path = C.TEMP_DIR / "_temp_ace_out_whole.wav"
            job = {"caption": caption, "lyrics": lyrics, "duration": max(10.0, total_sec), "steps": C.ACE_STEPS,
                   "guidance": C.ACE_GUIDANCE, "seed": seed, "bpm": int(round(detected_bpm)), "keyscale": str(detected_key),
                   "reference_audio": str(ref_path) if ref_path else None, "out": str(out_path)}
            t_start = time.time()
            if C.ACE_MODE == "cover":
                if orig_st is None:
                    orig_st = C.load_original_stereo(input_file, sampling_rate, full_base_audio, sr)
                common = {k_: v_ for k_, v_ in job.items() if k_ not in ("duration", "out")}
                common["lyrics"] = C.ACE_LYRICS
                print(f"[ACE] Description: {caption}")
                st = C.generate_cover(engine, input_file, orig_st, sampling_rate, base_length_sec, total_sec, n_seg,
                                      common, directories["final"], track_name)
                total_len_samples = len(st)
            else:
                ck = C._ckpt_path("whole", input_file, caption, seed, total_sec, C.ACE_MODEL_DIT, C.ACE_GGUF_QUANT, C.ACE_STEPS)
                if ck.exists():
                    st = np.load(ck)
                    print("[ACE] Whole track restored from the checkpoint.")
                else:
                    print(f"[ACE] WHOLE TRACK MODE: {total_sec:.1f}s in one pass, steps {C.ACE_STEPS}")
                    try:
                        engine.generate(job)
                    except C.NeedSmallerPass:
                        print("[MEMORY] Not enough memory for the whole track at once - switching to section by section.")
                        C._ACE_WHOLE = False
                        return process_file(engine, cfg, input_item, templates, file_idx, n_files)
                    st = C.load_stereo_48k(out_path, sampling_rate)
                    np.save(ck, st)
            generation_time = time.time() - t_start
            n_cal = int(total_sec * sampling_rate)
            st = st[:n_cal] if len(st) >= n_cal else np.concatenate([st, np.zeros((n_cal - len(st), 2), dtype=np.float32)])
            mono_cal = st.mean(axis=1).astype(np.float32)
            whole_st = C.match_rms_stereo(st, mono_cal)
            whole_mono = C.match_rms(mono_cal, target_rms=0.18)
            for _p in (out_path, ref_path):
                try:
                    if _p is not None:
                        Path(_p).unlink()
                except Exception:
                    pass
        if C._ACE_WHOLE:
            a_ = int(idx * segment_length_sec * sampling_rate)
            b_ = a_ + int(target_time * sampling_rate)
            new_stereo = whole_st[a_:b_].copy()
            new_part = whole_mono[a_:b_].copy()
            if len(new_part) < b_ - a_:
                miss = b_ - a_ - len(new_part)
                new_stereo = np.concatenate([new_stereo, np.zeros((miss, 2), dtype=np.float32)])
                new_part = np.concatenate([new_part, np.zeros(miss, dtype=np.float32)])
        else:
            ck = C._ckpt_path("section", input_file, idx, prompt_text, seed, target_time, C.ACE_MODEL_DIT, C.ACE_GGUF_QUANT, C.ACE_STEPS)
            if ck.exists():
                new_stereo = np.load(ck)
                print(f"[ACE] Section {num} restored from the checkpoint.")
            else:
                ref_path = None
                if templates:
                    ref_path = C.save_template_references(templates, C.TEMP_DIR / f"_temp_ace_ref_{num:03d}.wav")
                elif C.ACE_USE_REFERENCE:
                    if C.ACE_REFERENCE_MODE == "previous" and finished_track is not None and len(finished_track) > 5 * sampling_rate:
                        ref_audio, ref_sr = finished_track[-int(C.ACE_REFERENCE_LEN_SEC * sampling_rate):], sampling_rate
                    else:
                        melody = cut_base_segment(idx, length_sec=min(C.ACE_REFERENCE_LEN_SEC, target_time))
                        ref_audio, ref_sr = melody, sr
                    ref_path = C.TEMP_DIR / f"_temp_ace_ref_{num:03d}.wav"
                    sf.write(str(ref_path), np.clip(np.asarray(ref_audio, dtype=np.float32), -1.0, 1.0), int(ref_sr))
                out_path = C.TEMP_DIR / f"_temp_ace_out_{num:03d}.wav"
                margin = max(0.0, C.ACE_MARGIN_SEC)
                job = {"caption": prompt_text, "lyrics": C.ACE_LYRICS, "duration": max(10.0, target_time + 2 * margin),
                       "steps": C.ACE_STEPS, "guidance": C.ACE_GUIDANCE, "seed": seed + num,
                       "bpm": int(round(detected_bpm)), "keyscale": str(detected_key),
                       "reference_audio": str(ref_path) if ref_path else None, "out": str(out_path)}
                t_start = time.time()
                engine.allow_shrink = False   # sections are already the shortest unit - only waiting/threads adapt here
                try:
                    engine.generate(job)
                finally:
                    engine.allow_shrink = True
                generation_time = time.time() - t_start
                new_stereo = C.load_stereo_48k(out_path, sampling_rate)
                a_ = int(margin * sampling_rate)
                n_needed = int(target_time * sampling_rate)
                if len(new_stereo) < a_ + n_needed:
                    a_ = max(0, len(new_stereo) - n_needed)
                new_stereo = new_stereo[a_:a_ + n_needed]
                if len(new_stereo) < n_needed:
                    new_stereo = np.concatenate([new_stereo, np.zeros((n_needed - len(new_stereo), 2), dtype=np.float32)])
                np.save(ck, new_stereo)
                for _p in (out_path, ref_path):
                    try:
                        if _p is not None:
                            Path(_p).unlink()
                    except Exception:
                        pass
            new_part = new_stereo.mean(axis=1).astype(np.float32)
            new_stereo = C.match_rms_stereo(new_stereo, new_part)
            new_part = C.match_rms(new_part, target_rms=0.18)

        part_name = f"{short_name}_part_{num:03d}_{label}"
        C.save_audio_versions_ace(directories["parts"], part_name, new_part, new_stereo, sampling_rate, manifest["parts"], root)
        if C.EXPORT_USED_SOUNDS:
            C.save_audio_versions(directories["used"], f"analysis_slice_{num:03d}_{label}", cut_base_segment(idx), sr, manifest["used_sounds"], root)
            if melody is not None:
                C.save_audio_versions(directories["used"], f"input_melody_{num:03d}_{label}", melody, sr, manifest["used_sounds"], root)
        if C.EXPORT_SAMPLES:
            C.export_loops(directories["samples"], f"sample_{num:03d}_{label}", new_part, sampling_rate, detected_bpm, num_beats, manifest["samples"], root)
        if C.EXPORT_STEMS and stem_data(idx) is not None:
            C.save_section_stems(directories["stems"], num, label, stem_data(idx), sr, manifest["stems"], root)
        if C._ACE_WHOLE:
            _end = int(((idx + 1) * segment_length_sec + C.CROSSFADE_SEC) * sampling_rate)
            finished_track, finished_stereo = whole_mono[:_end].copy(), whole_st[:_end].copy()
        else:
            finished_track = C.join_bar_aligned_with_crossfade(finished_track, new_part, sampling_rate, crossfade_time_sec=C.CROSSFADE_SEC)
            finished_stereo = C.join_stereo_with_crossfade(finished_stereo, new_stereo, sampling_rate, crossfade_time_sec=C.CROSSFADE_SEC)
        sections_meta.append({"num": num, "label": label, "prompt": prompt_text, "notes_lead": notes_info["lead_str"],
                              "notes_bass": notes_info["bass_str"], "chord_progression": notes_info.get("progression_str", ""),
                              "chords_per_beat": notes_info.get("chords_beat"),
                              "input_fragment_start_s": plan[idx]["start_s"] if idx < len(plan) else None,
                              "stems": C.stems_to_json(stem_data(idx)), "generation_time_s": round(generation_time, 1)})
        print(f"[SAVED] section {num}/{n_seg} ({len(finished_track) / sampling_rate:.1f}s)")
        del new_part, new_stereo, melody
        gc.collect()

    C.report_progress(0.92, "Saving results")
    target_length = int(n_seg * segment_length_sec * sampling_rate)
    if total_len_samples:
        target_length = min(target_length, int(total_len_samples))
    finished_track = finished_track[:target_length].copy()
    finished_stereo = finished_stereo[:target_length].copy()
    n_fade = min(len(finished_track), int(0.25 * sampling_rate))
    if n_fade > 0:
        ramp = np.linspace(1.0, 0.0, n_fade, dtype=np.float32)
        finished_track[-n_fade:] *= ramp
        finished_stereo[-n_fade:] *= ramp[:, None]
    C.save_audio_versions_ace(directories["final"], track_name, finished_track, finished_stereo, sampling_rate, manifest["final"], root)
    if C.EXPORT_SAMPLES:
        C.export_band_stems(directories["samples"], track_name, finished_track, sampling_rate, manifest["samples"], root)
    midi_path = directories["midi"] / f"notes_{C.SCRIPT_SUBDIR}_{session_name}.mid"
    C.save_native_midi(midi_path, grids_lead, grids_bass, detected_bpm)
    manifest["midi"].append(str(midi_path.relative_to(root)).replace("\\", "/"))
    if stem_midi or stem_percussion:
        try:
            mid_paths = [(n, C.MIDI_PROGRAMS.get(n, 81), [m.get(i, [0] * num_beats) for i in range(n_seg)]) for n, m in stem_midi.items()]
            perc = {k: [m.get(i, [0] * (num_beats * 4)) for i in range(n_seg)] for k, m in stem_percussion.items()}
            p = directories["midi"] / f"stems_{C.SCRIPT_SUBDIR}_{session_name}.mid"
            C.save_multitrack_midi(p, detected_bpm, mid_paths, perc)
            manifest["midi"].append(str(p.relative_to(root)).replace("\\", "/"))
        except Exception as e:
            print(f"[MIDI] Could not save the multitrack MIDI ({type(e).__name__}: {e})")
    if C.EXPORT_NOTATION:
        C.save_notes(directories["notation"], f"notes_{C.SCRIPT_SUBDIR}_{session_name}", clean_name, detected_bpm, detected_key,
                     grids_lead, grids_bass, manifest["notation"], root, grids_chords)
    meta = {"app": "AI Music Generator and Cover Maker (Android)", "input_file": clean_name, "engine": engine.item_name,
            "ace_model": C.ACE_MODEL_DIT, "quantization": C.ACE_GGUF_QUANT, "ace_steps": C.ACE_STEPS, "ace_mode": C.ACE_MODE,
            "ace_cover_strength": C.ACE_COVER_STRENGTH, "ace_whole_track": bool(C._ACE_WHOLE), "seed": seed,
            "bpm": detected_bpm, "key": detected_key, "sample_rate": int(sampling_rate), "beats_per_section": num_beats,
            "num_sections": n_seg, "user_guidelines": user_guidelines, "channel_formats": list(C.CHANNEL_FORMATS),
            "input_analysis": C.analysis_to_json(analysis), "fragments_plan": plan,
            "style_templates": C.templates_description_to_json(templates), "sections": sections_meta, "files": manifest,
            "resources": {"threads": engine.threads, "lm_enabled": engine.lm_enabled, "max_pass_sec": engine.max_pass_sec}}
    with open(root / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, default=str)
    _clear_checkpoints(state_path)
    print(f"[SUCCESS] Done: {root}")
    return {"root": str(root), "session": session_name, "files": manifest}


# ------------------------------------------------------------------ entry point
def run(config_json, bridge):
    global _BRIDGE
    _BRIDGE = bridge
    cfg = json.loads(str(config_json))
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout = sys.stderr = _BridgeWriter(bridge, old_out)
    C._HOOKS["cancel"] = lambda: bool(bridge.isCancelled())
    C._HOOKS["progress"] = lambda frac, text: bridge.onProgress(float(-1 if frac is None else frac), str(text))
    results = []
    try:
        configure(cfg)
        engine = AndroidCppEngine(cfg, bridge)
        print(f"[ACE] Engine: {engine.item_name}, model {C.ACE_MODEL_DIT} {C.ACE_GGUF_QUANT}, steps {C.ACE_STEPS}, "
              f"threads {engine.threads}, max pass {engine.max_pass_sec or 'unlimited'} s")
        engine._model_dit()
        templates = C.prepare_style_templates() if C.ACE_STYLE_TEMPLATES else None
        inputs = cfg["inputs"]
        for i, item in enumerate(inputs, 1):
            whole_setting = bool(C.ACE_WHOLE_TRACK) or C.ACE_MODE == "cover"
            C._ACE_WHOLE = whole_setting
            results.append(process_file(engine, cfg, item, templates, i, len(inputs)))
        C.report_progress(1.0, "Done")
        return json.dumps({"ok": True, "results": results})
    except C.Cancelled:
        print("[ACE] Stopped by the user. Finished passes are kept - starting again continues from them.")
        return json.dumps({"ok": False, "cancelled": True, "results": results})
    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {e}")
        C._write_log(traceback.format_exc())
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}", "results": results})
    finally:
        sys.stdout, sys.stderr = old_out, old_err
