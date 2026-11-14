"""Builds app/src/main/python/ace_core.py from the desktop/Termux script generate_small_pro_ace_android.py.

The Android app reuses the music analysis, notation, MIDI, export and cover logic of the script unchanged.
Everything that cannot run inside an Android app is left out:
  * installers, venv switching, pip, Windows/Termux helpers,
  * PyTorch (the analysis STFT is replaced with numpy - see tools/ace_core_android.py, appended at the end),
  * Ollama (prompts are built from the analysis), Demucs and the AST network (HPSS + heuristics are used),
  * the line tracer / heavy logger, the PyTorch engine and its worker process,
  * the original main function (replaced by ace_android.run).

Usage (from the repository root):
    python tools/build_ace_core.py tools/generate_small_pro_ace_android.py app/src/main/python/ace_core.py
"""
import ast
import sys

SKIP_FUNCTIONS = {
    # installation / environment
    "_download_url", "cpp_dir", "program_cpp", "download_gguf_models", "_fix_threads", "_vcvars64", "_compile_cpp",
    "_install_cpp", "_local_install", "detect_workspace", "create_valid_mock", "_module_available", "_missing_module",
    "_safe_mmap_load", "_import_transformers", "_xpu_available", "detect_hybrid_devices", "choose_model_dtype",
    "get_prompt_from_user", "find_audio_files", "ProgressMonitor",
    # torch-based helpers (numpy replacements are appended from tools/ace_core_android.py)
    "native_chromagram_pytorch", "_stft_mag", "_ram_gb",
    # Ollama
    "_ollama_options", "_ollama_state", "_find_ollama", "_download_file", "_stop_ollama_processes", "_install_ollama",
    "_download_ollama_model", "prepare_ollama",
    # decoding via PyAV / ffmpeg (the app decodes with MediaCodec to WAV)
    "load_audio_via_av_or_ffmpeg", "_ffmpeg_stereo", "load_original_stereo", "_load_stereo",
    # Demucs / AST (not available on Android)
    "_stub_module", "_ensure_demucs_stubs", "_pip", "_import_demucs", "_load_demucs", "_SeparatorDemucs", "_ASTClassifier",
    "prepare_window_stems",
    # heavy logger / tracer
    "_array_description", "_shorten", "_write_log", "log_line", "_variable_label", "_trace_local", "_trace_global",
    "logs_start", "logs_end",
    # desktop menu / process control / PyTorch engine
    "_load_settings_from_menu", "_set_process_priority", "_apply_resource_profile", "_ace_python_path",
    "_ace_free_ram_mb", "_priority_flags", "pytorch_device", "aux_device", "AceStepEngine",
    # replaced by the Android engine and orchestration
    "segment_cover", "AceCppEngine", "choose_engine", "generate_coherent_composition",
}
SKIP_ASSIGNMENTS = {
    "_URL_CPP_WIN", "_CPP_WIN_FILES", "_INSTALL_FLAGS", "WORKSPACE_DIR", "VENV_PYTHON", "system32_path", "local_ffmpeg",
    "_localappdata", "ollama_win_path", "extra_paths", "CACHE_DIR", "OLLAMA_DIR", "_orig_torch_load", "ACE_DIR",
    "ACE_VENV_DIR", "ACE_PYTHON_ENV", "MAIN_DEVICE", "num_cores", "transformer_threads", "INPUT_DIR", "OUTPUT_DIR",
    "TEMP_DIR", "OLLAMA_URL", "OLLAMA_LOCAL_DIR", "_LOG", "_LOG_LOCK", "_LOG_MAX_CALLS_PER_FUNCTION",
    "_LOG_SKIPPED_FUNCTIONS", "_SIMPLE_TYPES", "_ACE_WORKER_CODE", "TEMPLATES_DIR",
}
SKIP_IMPORTS = {"torch", "soundfile", "requests", "unittest.mock", "traceback", "linecache", "importlib.machinery"}

HEADER = '''# -*- coding: utf-8 -*-
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
'''


def main(src_path, dst_path):
    src = open(src_path, encoding="utf-8").read()
    tree = ast.parse(src)
    out = [HEADER]
    kept_f, kept_a = [], []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            if node.name in SKIP_FUNCTIONS:
                continue
            kept_f.append(node.name)
        elif isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if not names or any(n in SKIP_ASSIGNMENTS for n in names):
                continue
            if isinstance(node.targets[0], ast.Tuple):
                continue
            kept_a.extend(names)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            continue        # the header provides all imports
        else:
            continue        # top-level statements (installers, venv switch, torch setup...) are not executed in the app
        start = node.lineno
        if getattr(node, "decorator_list", None):
            start = min(d.lineno for d in node.decorator_list)
        lines = src.splitlines()[start - 1:node.end_lineno]
        out.append("\n".join(lines) + "\n")
    import os
    overrides = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ace_core_android.py")
    out.append(open(overrides, encoding="utf-8").read())
    open(dst_path, "w", encoding="utf-8").write("\n\n".join(out))
    print(f"ace_core.py: {len(kept_f)} functions/classes, {len(kept_a)} constants")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
