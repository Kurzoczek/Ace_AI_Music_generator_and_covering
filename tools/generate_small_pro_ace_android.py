# ACE-Step: generate_small_pro_ace_android.py - Android version (Termux, C++ engine acestep.cpp). Installation: bash install_android.sh
import sys
import os
from pathlib import Path
import subprocess

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ==============================================================================
# 0. AUTOMATIC DRIVE DETECTION (F: / H:) AND VENV AUTOLAUNCH
# ==============================================================================
# ==============================================================================
# LOCAL INSTALLER (standard library only): everything goes into the script directory, nothing on the system drive
#   python <script> --install           -> uv + Python 3.12 + venv + ACE-Step (PyTorch) + ACE-Step C++ (GGUF) + directories
#   python <script> --install-ace       -> only ACE-Step in PyTorch (Python 3.12, torch CPU, repository)
#   python <script> --install-cpp       -> only ACE-Step C++ (acestep.cpp: programs + GGUF models) - light, fast on CPU
#   python <script> --install-cpp-source -> acestep.cpp compiled from source (all cores, Vulkan)
#   Simplest: install.cmd (double-click) or python install.py - one installer for everything
#   python <script> --install-gpu=cuda  -> torch with NVIDIA (CUDA) support in both environments
#   python <script> --install-gpu=xpu   -> torch with Intel Arc / Core Ultra (XPU) support in both environments
# Variables: GENERATE_GGUF_QUANT=Q8_0|Q6_K|Q5_K_M|Q4_K_M (default Q8_0), GENERATE_CPP_CUDA=1 (also download the CUDA backend)
# ==============================================================================
_URL_GGUF = "https://huggingface.co/Serveurperso/ACE-Step-1.5-GGUF/resolve/main/"
_URL_CPP_WIN = "https://www.serveurperso.com/temp/acestep.cpp-win64/build/Release/"   # prebuilt programs from the acestep.cpp author
_CPP_WIN_FILES = ["ace-synth.exe", "ace-lm.exe", "ace-understand.exe", "ace-server.exe", "ggml.dll", "ggml-base.dll",
                  "ggml-cpu-x64.dll", "ggml-cpu-sse42.dll", "ggml-cpu-sandybridge.dll", "ggml-cpu-haswell.dll",
                  "ggml-cpu-skylakex.dll", "ggml-cpu-cannonlake.dll", "ggml-cpu-cascadelake.dll", "ggml-cpu-icelake.dll",
                  "ggml-cpu-alderlake.dll", "ggml-vulkan.dll"]
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


def _download_url(url, dest, description=""):
    """Download with resume (.part), real size and speed. Returns True when the file is ready."""
    import urllib.request
    dest = Path(dest)
    if dest.exists() and dest.stat().st_size > 0:
        print(f"[DOWNLOAD] {dest.name}: already present ({dest.stat().st_size / 2 ** 20:.1f} MB)")
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    for attempt in range(1, 6):
        start = tmp.stat().st_size if tmp.exists() else 0
        req_headers = {"User-Agent": "generate-installer"}
        if start:
            req_headers["Range"] = f"bytes={start}-"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=req_headers), timeout=60) as r:
                if start and getattr(r, "status", 200) != 206:
                    start = 0                                    # server does not support resume - start over
                together = int(r.headers.get("Content-Length") or 0) + start
                print(f"[DOWNLOAD] {description or dest.name}: {together / 2 ** 20:.1f} MB" + (f" (resuming from {start / 2 ** 20:.1f} MB)" if start else ""))
                t0, t_print, downloaded = time.time(), 0.0, start
                with open(tmp, "ab" if start else "wb") as f:
                    while True:
                        block = r.read(1 << 20)
                        if not block:
                            break
                        f.write(block)
                        downloaded += len(block)
                        if time.time() - t_print > 3:
                            t_print = time.time()
                            tempo = (downloaded - start) / max(1e-3, time.time() - t0) / 2 ** 20
                            print(f"   {downloaded / 2 ** 20:8.1f} / {together / 2 ** 20:.1f} MB  ({tempo:.1f} MB/s)", flush=True)
            if together and tmp.stat().st_size < together:
                raise IOError(f"incomplete file ({tmp.stat().st_size} of {together} B)")
            tmp.replace(dest)
            return True
        except Exception as e:
            print(f"[DOWNLOAD] {dest.name}: attempt {attempt}/5 failed ({type(e).__name__}: {e})")
            time.sleep(min(30, 5 * attempt))
    return False


def cpp_dir():
    return Path(os.environ.get("ACESTEP_CPP_DIR") or (Path(__file__).resolve().parent / "acestep_cpp"))


def program_cpp(item_name):
    """Path to ace-synth / ace-lm (prebuilt programs in bin/ or own build in src/build/)."""
    folder = cpp_dir()
    exe = item_name + (".exe" if os.name == "nt" else "")
    for p in (folder / "bin" / exe, folder / "src" / "build" / "Release" / exe, folder / "src" / "build" / exe):
        if p.exists():
            return p
    return None


def download_gguf_models(file_list):
    folder = cpp_dir() / "models"
    ok = True
    for file in [p for p in file_list if p]:
        ok = _download_url(_URL_GGUF + file, folder / file, file) and ok
    return ok


def _fix_threads(src):
    """acestep.cpp on CPU hard-codes half of the cores (hardware_concurrency() / 2) - we change it to all of them."""
    file = Path(src) / "src" / "backend.h"
    try:
        t = file.read_text(encoding="utf-8")
    except OSError:
        print(f"[CPP] Could not find {file} - thread count unchanged.")
        return False
    old = "std::thread::hardware_concurrency() / 2"
    if old in t:
        file.write_text(t.replace(old, "std::thread::hardware_concurrency()"), encoding="utf-8")
        print("[CPP] Patch: the C++ engine will compute on all cores (instead of half).")
        return True
    if "hardware_concurrency()" in t:
        print("[CPP] Thread count already set to all cores (patch applied earlier or changed by the author).")
        return True
    print("[CPP] The author changed the thread setup code - not applying the patch.")
    return False


def _vcvars64():
    """Path to vcvars64.bat from an installed Visual Studio / Build Tools (via vswhere) or None."""
    vswhere = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
    candidates = []
    if vswhere.exists():
        r = subprocess.run([str(vswhere), "-latest", "-products", "*", "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
                            "-property", "installationPath"], capture_output=True, text=True, errors="replace")
        candidates += [Path(l.strip()) for l in r.stdout.splitlines() if l.strip()]
    for base in (os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), os.environ.get("ProgramFiles", r"C:\Program Files")):
        for ver in ("18", "2022", "17"):
            for edition in ("BuildTools", "Community", "Professional", "Enterprise"):
                candidates.append(Path(base) / "Microsoft Visual Studio" / ver / edition)
    for k in candidates:
        bat = k / "VC" / "Auxiliary" / "Build" / "vcvars64.bat"
        if bat.exists():
            return bat
    return None


def _compile_cpp(root_note, dry, launch):
    """Compiles acestep.cpp from source (with the thread patch), output in acestep_cpp/bin. Returns True on success."""
    import json, shutil, time
    folder = cpp_dir()
    src, build = folder / "src", folder / "src" / "build"
    print("-" * 72)
    print(" COMPILING acestep.cpp from source (all CPU cores; Vulkan if the Vulkan SDK is present)")
    print("-" * 72)
    if not shutil.which("git"):
        print("[CPP] git is missing. Install it: winget install Git.Git  (or git-scm.com), then run the installer again.")
        return False
    vcvars = None
    if os.name == "nt":
        vcvars = _vcvars64()
        if vcvars is None:
            print("[CPP] No C++ compiler (Visual Studio Build Tools). Install it, e.g.:\n"
                  "   winget install Microsoft.VisualStudio.2022.BuildTools --override \"--passive --wait "
                  "--add Microsoft.VisualStudio.Workload.VCTools --includeRecommended\"\n"
                  "   (takes a few GB, mostly on drive C:), then run the installer again.")
            return False
        print(f"[CPP] Compiler: {vcvars}")
    elif not shutil.which("cmake"):
        print("[CPP] cmake is missing (e.g. apt install git cmake build-essential).")
        return False
    if not (src / "CMakeLists.txt").exists():
        if src.exists():
            shutil.rmtree(src, ignore_errors=True)
        launch(["git", "clone", "--recurse-submodules", "https://github.com/ServeurpersoCom/acestep.cpp.git", src])
    else:
        launch(["git", "-C", src, "checkout", "--", "src/backend.h"], critical=False)    # remove the old patch before updating
        launch(["git", "-C", src, "pull", "--rebase"], critical=False)
        launch(["git", "-C", src, "submodule", "update", "--init", "--recursive"], critical=False)
    if dry:
        return True
    _fix_threads(src)
    vulkan_sdk = os.environ.get("VULKAN_SDK")
    vulkan = bool(vulkan_sdk and Path(vulkan_sdk).exists()) if os.name == "nt" else bool(shutil.which("glslc"))
    print(f"[CPP] Vulkan (graphics card, including Intel UHD): {'YES' if vulkan else 'NO - Vulkan SDK missing (vulkan.lunarg.com), CPU-only build'}")
    shutil.rmtree(build, ignore_errors=True)
    options = f"-DGGML_VULKAN={'ON' if vulkan else 'OFF'}"
    threads = os.cpu_count() or 2
    if os.name == "nt":
        command = (f'call "{vcvars}" >nul && cmake -S "{src}" -B "{build}" -G "Ninja Multi-Config" {options} '
                     f'&& cmake --build "{build}" --config Release -j {threads}')
        print("$", command)
        rc = subprocess.run(command, shell=True).returncode
    else:
        rc = subprocess.run(["cmake", "-S", str(src), "-B", str(build), "-DGGML_BLAS=OFF", options, "-DCMAKE_BUILD_TYPE=Release"]).returncode
        if rc == 0:
            rc = subprocess.run(["cmake", "--build", str(build), "--config", "Release", "-j", str(threads)]).returncode
    exe = "ace-synth" + (".exe" if os.name == "nt" else "")
    finished = next((p for p in build.rglob(exe) if p.is_file()), None) if build.exists() else None
    if rc != 0 or finished is None:
        print(f"[CPP] Compilation failed (code {rc}). Details in the messages above.")
        return False
    # new programs go to bin/ (old ones - e.g. the author's prebuilt files - are moved to bin_old/)
    bin_ = folder / "bin"
    if bin_.exists() and any(bin_.iterdir()):
        old = folder / "bin_old"
        shutil.rmtree(old, ignore_errors=True)
        bin_.rename(old)
        print(f"[CPP] Previous programs moved to {old}")
    bin_.mkdir(parents=True, exist_ok=True)
    for f in finished.parent.iterdir():
        if f.is_file() and (f.suffix.lower() in (".exe", ".dll", ".so") or (os.name != "nt" and os.access(f, os.X_OK))):
            shutil.copy2(f, bin_ / f.name)
    (bin_ / "compiled.json").write_text(json.dumps({"threads": "all", "vulkan": vulkan, "data": time.strftime("%Y-%m-%d %H:%M")}),
                                            encoding="utf-8")
    print(f"[CPP] Compiled programs in {bin_}")
    return True


def _install_cpp(root_note, dry, launch):
    import platform
    folder = cpp_dir()
    (folder / "bin").mkdir(parents=True, exist_ok=True)
    (folder / "models").mkdir(parents=True, exist_ok=True)
    print("-" * 72)
    print(" ACE-Step C++ (acestep.cpp, MIT license) - GGUF models, works without PyTorch; CPU, Vulkan (incl. Intel UHD), CUDA")
    print("-" * 72)
    if program_cpp("ace-synth") is None:
        if os.name == "nt":
            file_list = list(_CPP_WIN_FILES)
            if os.environ.get("GENERATE_CPP_CUDA") == "1" or shutil.which("nvidia-smi"):
                file_list.append("ggml-cuda.dll")                   # 139 MB, only for NVIDIA cards
            print(f"[CPP] Downloading prebuilt programs from {_URL_CPP_WIN}")
            print("      (this is a temporary release by the project author - link given in his README; alternative: compile from source)")
            for file in file_list:
                if not dry and not _download_url(_URL_CPP_WIN + file, folder / "bin" / file, file):
                    if file.startswith(("ace-synth", "ace-lm", "ggml.dll", "ggml-base")):
                        raise SystemExit(f"[CPP] Could not download {file}. Try again later or compile from source (acestep.cpp README).")
        else:
            if not (shutil.which("git") and shutil.which("cmake")):
                raise SystemExit("[CPP] git and cmake are needed to compile acestep.cpp (e.g. apt install git cmake build-essential).")
            if not (folder / "src").exists():
                launch(["git", "clone", "--depth", "1", "--recurse-submodules", "--shallow-submodules",
                         "https://github.com/ServeurpersoCom/acestep.cpp.git", folder / "src"])
            _fix_threads(folder / "src")
            vulkan = "-DGGML_VULKAN=ON" if shutil.which("glslc") else "-DGGML_VULKAN=OFF"
            launch(["cmake", "-S", folder / "src", "-B", folder / "src" / "build", "-DGGML_BLAS=OFF", vulkan, "-DCMAKE_BUILD_TYPE=Release"])
            launch(["cmake", "--build", folder / "src" / "build", "--config", "Release", "-j", str(os.cpu_count() or 2),
                     "--target", "ace-synth", "ace-lm"])
    exe = program_cpp("ace-synth")
    if exe and not dry:
        r = subprocess.run([str(exe)], capture_output=True, text=True, errors="replace")
        if "Usage" in (r.stdout + r.stderr):
            print(f"[CPP] ace-synth works: {exe}")
        else:
            print(f"[CPP] WARNING: ace-synth did not start correctly (code {r.returncode}). On Windows you may be missing "
                  f"'Microsoft Visual C++ Redistributable' (x64) - install it from the Microsoft website.\n{(r.stderr or r.stdout)[-400:]}")
    quant = os.environ.get("GENERATE_GGUF_QUANT", "Q8_0")
    if quant not in _GGUF_QUANTS:
        quant = "Q8_0"
    file_list = ["vae-BF16.gguf", f"Qwen3-Embedding-0.6B-{'BF16' if quant == 'BF16' else 'Q8_0'}.gguf",
             gguf_dit_name("acestep-v15-turbo", quant), gguf_lm_name("0.6B", quant)]
    print(f"[CPP] GGUF models ({quant}): {', '.join(file_list)} -> {folder / 'models'}")
    if not dry and not download_gguf_models(file_list):
        raise SystemExit("[CPP] Not all models were downloaded - run the installation again (the download will resume).")
    print("[CPP] Done. Other models (SFT, Base, XL, other quantizations) will be downloaded by the script when you choose them.")


def _local_install(rng):
    import platform, zipfile, tarfile, urllib.request
    root_note = Path(__file__).resolve().parent
    dry = os.environ.get("GENERATE_DRY_RUN") == "1"
    win = os.name == "nt"
    d_tools, d_py, d_cache, d_tmp = root_note / "tools", root_note / "python_local", root_note / ".cache", root_note / ".tmp"
    d_main_venv, d_ace_venv, d_ace = root_note / "venv", root_note / "ace_venv", root_note / "ACE-Step-1.5"
    print("=" * 72)
    print(f" LOCAL INSTALLATION in: {root_note}")
    print(" Python, libraries, models and caches will go ONLY into this directory.")
    print("=" * 72)
    for d in (d_tools, d_py, d_cache / "pip", d_cache / "uv", d_cache / "huggingface", d_cache / "torch", d_tmp,
              root_note / "input", root_note / "output"):
        d.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "UV_PYTHON_INSTALL_DIR": str(d_py), "UV_CACHE_DIR": str(d_cache / "uv"),
           "UV_PYTHON_BIN_DIR": str(d_tools / "bin_py"), "UV_TOOL_DIR": str(d_tools / "uv_tools"), "UV_LINK_MODE": "copy",
           "PIP_CACHE_DIR": str(d_cache / "pip"), "HF_HOME": str(d_cache / "huggingface"), "TORCH_HOME": str(d_cache / "torch"),
           "UV_HTTP_TIMEOUT": os.environ.get("UV_HTTP_TIMEOUT", "900"), "UV_CONCURRENT_DOWNLOADS": os.environ.get("UV_CONCURRENT_DOWNLOADS", "8"),
           "XDG_CACHE_HOME": str(d_cache), "TEMP": str(d_tmp), "TMP": str(d_tmp), "TMPDIR": str(d_tmp), "PYTHONUTF8": "1"}

    def launch(cmd, critical=True):
        print("$", " ".join(str(c) for c in cmd))
        if dry:
            return 0
        rc = 1
        for attempt in range(1, 4):   # temporary network / disk problems: up to 3 attempts
            rc = subprocess.run([str(c) for c in cmd], env=env).returncode
            if rc == 0 or not critical:
                break
            if attempt < 3:
                print(f"[INSTALL] Attempt {attempt}/3 failed (code {rc}) - retrying in 10 s (downloaded parts are cached).")
                time.sleep(10)
        if rc != 0 and critical:
            raise SystemExit(f"[INSTALL] Step failed (code {rc}). Fix the problem and run the installation again - completed steps will be skipped.")
        return rc

    if rng == "only_cpp":
        _install_cpp(root_note, dry, launch)
        return

    # --- 1. uv (Python and package manager) in the tools directory ---
    uv_name = "uv.exe" if win else "uv"
    uv = next((p for p in d_tools.rglob(uv_name) if p.is_file()), None)
    if uv is None:
        arch = "aarch64" if platform.machine().lower() in ("arm64", "aarch64") else "x86_64"
        asset = f"uv-{arch}-pc-windows-msvc.zip" if win else f"uv-{arch}-unknown-linux-gnu.tar.gz"
        arch_p = d_tools / asset
        try:
            if not dry and not _download_url(f"https://github.com/astral-sh/uv/releases/latest/download/{asset}", arch_p, asset):
                raise IOError("download failed")
            if not dry:
                if asset.endswith(".zip"):
                    with zipfile.ZipFile(arch_p) as z:
                        z.extractall(d_tools / "uv")
                else:
                    with tarfile.open(arch_p) as t:
                        t.extractall(d_tools / "uv")
                arch_p.unlink()
        except Exception as e:
            print(f"[INSTALL] Downloading uv from GitHub failed ({type(e).__name__}: {e}) - trying pip --target.")
            launch([sys.executable, "-m", "pip", "install", "--target", d_tools / "uv_pip", "uv"])
        uv = next((p for p in d_tools.rglob(uv_name) if p.is_file()), None)
    if uv is None:
        if dry:
            uv = d_tools / "uv" / uv_name
        else:
            raise SystemExit("[INSTALL] uv not found after download.")
    print(f"[INSTALL] uv: {uv}")

    def py_from(venv):
        return venv / ("Scripts" if win else "bin") / ("python.exe" if win else "python")

    def make_venv(directory):
        if py_from(directory).exists():
            print(f"[INSTALL] {directory.name}: already exists - skipping creation.")
            return False
        launch([uv, "venv", "--seed", "--managed-python", "--python", "3.12", directory])
        return True

    if rng.startswith("gpu:"):
        variant_name = rng.split(":", 1)[1]
        indices = {"xpu": ["https://download.pytorch.org/whl/xpu"],
                   "cuda": [os.environ.get("GENERATE_CUDA_INDEX") or "https://download.pytorch.org/whl/cu130",
                            "https://download.pytorch.org/whl/cu128", "https://download.pytorch.org/whl/cu126"]}.get(variant_name)
        if not indices:
            raise SystemExit("[GPU] Use --install-gpu=cuda (NVIDIA) or --install-gpu=xpu (Intel Arc / Core Ultra).")
        print(f"[GPU] Installing torch with {variant_name.upper()} support. Note: Intel UHD (e.g. N100/N150) is NOT supported by XPU - "
              "for such a card use the C++ engine with Vulkan.")
        for venv in (d_ace_venv, d_main_venv):
            if not py_from(venv).exists():
                continue
            for idx in indices:
                if launch([uv, "pip", "install", "--python", py_from(venv), "--reinstall", "torch", "torchaudio", "--index-url", idx],
                           critical=False) == 0:
                    print(f"[GPU] {venv.name}: torch from {idx}")
                    break
            else:
                print(f"[GPU] {venv.name}: failed to install torch with {variant_name} support.")
        return

    cpu_idx = "https://download.pytorch.org/whl/cpu"
    # --- 2. main environment (analysis, Ollama, MIDI, Demucs...) ---
    if rng == "everything":
        if make_venv(d_main_venv):
            p = py_from(d_main_venv)
            launch([uv, "pip", "install", "--python", p, "torch", "torchaudio", "--index-url", cpu_idx])
            launch([uv, "pip", "install", "--python", p, "numpy==1.26.4", "soundfile", "av", "requests", "transformers"])
    # --- 3. ACE-Step environment (PyTorch) ---
    make_venv(d_ace_venv)
    pa = py_from(d_ace_venv)
    launch([uv, "pip", "install", "--python", pa, "torch", "torchaudio", "--index-url", cpu_idx])
    launch([uv, "pip", "install", "--python", pa, "hf_xet", "hf_transfer"], critical=False)   # fast model downloads
    if not (d_ace / "acestep").is_dir():
        if shutil.which("git") and launch(["git", "clone", "--depth", "1", "https://github.com/ace-step/ACE-Step-1.5", d_ace], critical=False) == 0:
            pass
        else:
            zip_p = root_note / "_ace_repo.zip"
            if not dry and not _download_url("https://github.com/ace-step/ACE-Step-1.5/archive/refs/heads/main.zip", zip_p, "ACE-Step-1.5.zip"):
                raise SystemExit("[INSTALL] Could not download the ACE-Step repository.")
            if not dry:
                tmp_r = root_note / "_ace_unpacked"
                with zipfile.ZipFile(zip_p) as z:
                    z.extractall(tmp_r)
                shutil.move(str(next(tmp_r.iterdir())), str(d_ace))
                shutil.rmtree(tmp_r, ignore_errors=True)
                zip_p.unlink()
    req = d_ace / "requirements.txt"
    if req.exists() or dry:
        skipped = ("torch", "torchaudio", "torchvision", "triton", "nvidia", "flash", "vllm", "bitsandbytes", "--", "#")
        if not dry:
            lines = [l for l in req.read_text(encoding="utf-8", errors="ignore").splitlines()
                     if l.strip() and not l.strip().lower().startswith(skipped)]
            (d_ace / "requirements_cpu.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        launch([uv, "pip", "install", "--python", pa, "-r", d_ace / "requirements_cpu.txt"])
    elif (d_ace / "pyproject.toml").exists():
        launch([uv, "pip", "install", "--python", pa, "-e", d_ace])
        print("[INSTALL] Note: requirements.txt missing - installed from pyproject.toml; if import errors appear, let me know.")
    # --- 4. ACE-Step C++ (GGUF) ---
    if rng == "everything":
        try:
            _install_cpp(root_note, dry, launch)
        except SystemExit as e:
            print(f"{e}\n[INSTALL] The C++ engine did not install - the scripts will use the PyTorch engine. You can retry: --install-cpp")
    print("=" * 72)
    print(" DONE. Layout (everything in the script directory):")
    if not py_from(d_main_venv).exists() and not dry:
        print(" NOTE: the main environment (venv) does not exist yet. Run install.cmd (double-click) or:  python install.py")
    for n, description in (("tools", "uv"), ("python_local", "Python 3.12 (downloaded locally)"), ("venv", "main environment"),
                    ("ace_venv", "ACE-Step environment (PyTorch)"), ("ACE-Step-1.5", "repository + PyTorch models (downloaded on the 1st generation)"),
                    ("acestep_cpp", "C++ engine: bin/ (programs) + models/ (GGUF)"),
                    (".cache", "pip/uv/HuggingFace/torch caches"), (".tmp", "temporary files"), ("input", "put your tracks here"), ("output", "results")):
        print(f"   {n:<16} {description}")
    print(" The Ollama model and any other ACE-Step models will be downloaded into this directory on first use (with their size shown).")
    print("=" * 72)


_INSTALL_FLAGS = [a for a in sys.argv[1:] if a.startswith("--install")]
if _INSTALL_FLAGS:
    print("[ANDROID] On Android installation is done via:  bash install_android.sh   (C++ engine: bash install_android.sh cpp)")
    sys.exit(1)
if _INSTALL_FLAGS:
    import shutil
    import time
    _f = _INSTALL_FLAGS[0]
    if _f == "--install-cpp-source":
        _compile_cpp(Path(__file__).resolve().parent, os.environ.get("GENERATE_DRY_RUN") == "1",
                      lambda cmd, critical=True: subprocess.run([str(c) for c in cmd]).returncode)
    elif _f.startswith("--install-gpu"):
        _local_install("gpu:" + (_f.split("=", 1)[1].strip().lower() if "=" in _f else ""))
    else:
        _local_install({"--install-ace": "only_ace", "--install-cpp": "only_cpp"}.get(_f, "everything"))
    sys.exit(0)

def detect_workspace():
    # Everything (input, results, venv, models, cache) lives in the script directory; GENERATE_WORKSPACE overrides it.
    forced = os.environ.get("GENERATE_WORKSPACE")
    return Path(forced) if forced else Path(__file__).resolve().parent

WORKSPACE_DIR = detect_workspace()
VENV_PYTHON = WORKSPACE_DIR / "venv" / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python")

# Caches and temporary files in the working directory (not on the system drive)
if os.environ.get("GENERATE_SYSTEM_CACHE") != "1":
    for _var, _rel in (("PIP_CACHE_DIR", ".cache/pip"), ("UV_CACHE_DIR", ".cache/uv"), ("TORCH_HOME", ".cache/torch"),
                      ("XDG_CACHE_HOME", ".cache"), ("TEMP", ".tmp"), ("TMP", ".tmp"), ("TMPDIR", ".tmp")):
        _dir = WORKSPACE_DIR / _rel
        try:
            _dir.mkdir(parents=True, exist_ok=True)
            os.environ[_var] = str(_dir)
        except Exception:
            pass

if (VENV_PYTHON.exists() and os.environ.get("GENERATE_VENV") != "1"
        and Path(sys.prefix).resolve() != (WORKSPACE_DIR / "venv").resolve()):
    print(f"[VENV] Detected a run outside the virtual environment.")
    print(f"[VENV] Automatic redirect to venv: {VENV_PYTHON}")
    try:
        result = subprocess.run([str(VENV_PYTHON), "-X", "utf8", "-u"] + sys.argv,
                                env={**os.environ, "GENERATE_VENV": "1"})
        sys.exit(result.returncode)
    except Exception as e:
        print(f"[VENV ERROR] Could not start venv: {e}")
        sys.exit(1)

if (not VENV_PYTHON.exists() and os.environ.get("GENERATE_VENV") != "1" and os.environ.get("GENERATE_NO_VENV") != "1"):
    print("[VENV] No local Python environment in the script directory (" + str(VENV_PYTHON) + ").")
    print("[VENV] I do not install anything into the system Python. Run the installer once:  bash install_android.sh")
    print("[VENV] (GENERATE_NO_VENV=1 skips this check and uses the current Python.)")
    sys.exit(1)

# ==============================================================================
# 1. DLL PROTECTION, FFMPEG PATH AND MAGICMOCK SHIELD (NO C++ COMPILATION)
# ==============================================================================
import gc
import time
import shutil
import struct
import traceback
import importlib.util
import importlib.machinery
from datetime import datetime
from unittest.mock import MagicMock
from concurrent.futures import ThreadPoolExecutor

system32_path = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32")
if hasattr(os, "add_dll_directory"):
    try:
        os.add_dll_directory(system32_path)
    except Exception:
        pass

local_ffmpeg = WORKSPACE_DIR / "ffmpeg" / "bin"
_localappdata = os.environ.get("LOCALAPPDATA")
ollama_win_path = Path(_localappdata) / "Programs" / "Ollama" if _localappdata else None
extra_paths = [system32_path]
if local_ffmpeg.exists():
    extra_paths.append(str(local_ffmpeg))
if ollama_win_path is not None and ollama_win_path.exists():
    extra_paths.append(str(ollama_win_path))
os.environ["PATH"] = os.pathsep.join(extra_paths + [os.environ.get("PATH", "")])

# Quick install of prebuilt binary wheels only, if any is missing
for mod_name, pip_name in [("numpy", "numpy==1.26.4"), ("soundfile", "soundfile"), ("av", "av"), ("requests", "requests"), ("torch", "torch"), ("transformers", "transformers")]:
    if importlib.util.find_spec(mod_name) is None:
        print(f"[INSTALLER] Installing prebuilt binary package: {pip_name}...")
        subprocess.run([sys.executable, "-m", "pip", "install", "--prefer-binary", "--no-compile", pip_name], check=False)

CACHE_DIR = Path(os.environ.get("GENERATE_CACHE") or (WORKSPACE_DIR / ".cache"))  # GENERATE_CACHE: e.g. a faster drive than a USB HDD
OLLAMA_DIR = WORKSPACE_DIR / ".ollama_models"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
OLLAMA_DIR.mkdir(parents=True, exist_ok=True)

os.environ["HF_HOME"] = str(CACHE_DIR)
os.environ["OLLAMA_MODELS"] = str(OLLAMA_DIR)

def create_valid_mock(name):
    mock_mod = MagicMock()
    mock_mod.__name__ = name
    mock_mod.__spec__ = importlib.machinery.ModuleSpec(name, loader=None)
    mock_mod.__path__ = []
    if name.startswith("scipy"):
        mock_mod.__version__ = "1.13.1"
    return mock_mod

def _module_available(item_name):
    # We check the FULL name (e.g. scipy.optimize) - a partially installed package has the main module but not the submodules
    try:
        return importlib.util.find_spec(item_name) is not None
    except (ImportError, ValueError, AttributeError):
        return False

def _missing_module(exc):
    # Searches the exception chain (transformers wraps errors) for the name of a missing module that may be mocked
    while exc is not None:
        item_name = getattr(exc, "name", None)
        if isinstance(exc, ModuleNotFoundError) and item_name and item_name.split(".")[0] in ("scipy", "numba", "soxr", "librosa"):
            return item_name
        exc = exc.__cause__ or exc.__context__
    return None

for mod in ["soxr", "scipy", "scipy.signal", "scipy.optimize", "scipy.integrate", "numba", "numba.core"]:
    if not _module_available(mod):
        sys.modules[mod] = create_valid_mock(mod)

import torch
try:
    import av
except ImportError:
    av = None    # Android/Termux: no PyAV - decoding via the ffmpeg program
import numpy as np
import soundfile as sf
import requests

# Patch torch.load to save RAM (mmap=True)
_orig_torch_load = torch.load
def _safe_mmap_load(*args, **kwargs):
    # WARNING: weights_only=False allows code execution from pickle - load only trusted models.
    kwargs.setdefault("weights_only", False)
    used_mmap = False
    if "map_location" not in kwargs and "mmap" not in kwargs:
        kwargs["mmap"] = True
        used_mmap = True
    try:
        return _orig_torch_load(*args, **kwargs)
    except Exception:
        if not used_mmap:
            raise
        kwargs.pop("mmap", None)  # older checkpoint format does not support mmap
        return _orig_torch_load(*args, **kwargs)
torch.load = _safe_mmap_load

# ==============================================================================
# 2. NATIVE CHROMAGRAM AND NOTE DETECTOR IN PYTORCH + MIDI WRITING (PURE PYTHON)
# ==============================================================================
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

def native_chromagram_pytorch(y, sr, n_fft=4096, hop_length=512, n_chroma=12, fmin=27.5, fmax=None):
    y_t = torch.from_numpy(y).float() if isinstance(y, np.ndarray) else y.float()
    if y_t.dim() == 1:
        y_t = y_t.unsqueeze(0)

    window = torch.hann_window(n_fft)
    stft = torch.stft(y_t, n_fft=n_fft, hop_length=hop_length, win_length=n_fft, window=window, center=True, return_complex=True)
    spec = stft.abs().pow(2).squeeze(0).numpy()

    freqs = np.linspace(0, sr / 2.0, n_fft // 2 + 1)
    chroma_fb = np.zeros((n_chroma, len(freqs)), dtype=np.float32)

    valid = (freqs > fmin) & (freqs <= (fmax if fmax else sr / 2.0))
    midi = np.zeros_like(freqs)
    midi[valid] = 69.0 + 12.0 * np.log2(freqs[valid] / 440.0)

    for i in range(len(freqs)):
        if valid[i]:
            c_bin = int(np.round(midi[i])) % n_chroma
            chroma_fb[c_bin, i] += 1.0

    col_norms = np.maximum(1.0, chroma_fb.sum(axis=1, keepdims=True))
    chroma_fb = chroma_fb / col_norms

    chroma = np.dot(chroma_fb, spec)
    max_vals = np.maximum(1e-6, np.max(chroma, axis=0, keepdims=True))
    return chroma / max_vals

def _stft_mag(y_np, n_fft, hop):
    y_t = torch.from_numpy(np.ascontiguousarray(y_np)).float()
    if y_t.dim() == 1:
        y_t = y_t.unsqueeze(0)
    window = torch.hann_window(n_fft)
    stft = torch.stft(y_t, n_fft=n_fft, hop_length=hop, win_length=n_fft, window=window, center=True, return_complex=True)
    return stft.abs().squeeze(0).numpy()

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

try:
    import librosa
except ImportError:
    mock_librosa = MagicMock()
    mock_librosa.__name__ = "librosa"
    mock_librosa.__spec__ = importlib.machinery.ModuleSpec("librosa", loader=None)
    mock_feature = MagicMock()
    mock_feature.chroma_stft = lambda y, sr, n_fft=4096, hop_length=512, n_chroma=12, **kwargs: native_chromagram_pytorch(y, sr, n_fft, hop_length, n_chroma)
    mock_librosa.feature = mock_feature
    sys.modules["librosa"] = mock_librosa
    sys.modules["librosa.feature"] = mock_feature

def _import_transformers():
    from transformers import (
        AutoProcessor,
        MusicgenForConditionalGeneration,
        LogitsProcessor,
        LogitsProcessorList
    )
    return dict(locals())

for _attempt in range(10):
    try:
        globals().update(_import_transformers())
        break
    except ModuleNotFoundError as _error:
        _missing = _missing_module(_error)
        if not _missing or _missing in sys.modules:
            raise
        print(f"[MOCK] Missing module '{_missing}' - substituting a stub and retrying the transformers import.")
        sys.modules[_missing] = create_valid_mock(_missing)

# ==============================================================================
# 3. HYBRID CONFIGURATION (CPU + INTEL GPU/XPU/DIRECTML) AND PARAMETERS
# ==============================================================================
# --- ACE-Step 1.5 instead of MusicGen: the model runs in a separate process with Python 3.12 (one-time installation: --install) ---
ACE_MODEL_DIT = "acestep-v15-turbo"          # acestep-v15-turbo (fast, 8 steps) | acestep-v15-sft (better quality, slower) | acestep-v15-base
MODEL_ID = ACE_MODEL_DIT
MODEL_LARGE = False                 # kept for compatibility with old code
ACE_STEPS = 8                       # turbo: 8; sft/base: 32-60 (each step takes longer on CPU)
ACE_GUIDANCE = None                   # None = model default
ACE_DIR = Path(os.environ.get("ACESTEP_DIR") or (WORKSPACE_DIR / "ACE-Step-1.5"))
ACE_VENV_DIR = Path(os.environ.get("ACESTEP_VENV") or (WORKSPACE_DIR / "ace_venv"))
ACE_PYTHON_ENV = os.environ.get("ACESTEP_PYTHON")   # or point to a Python 3.11/3.12 interpreter with ACE-Step manually
ACE_LOG_LEVEL = "detailed"         # "basic" (console only) | "detailed" (function calls, data, model layers) | "full" (EVERY line and variable change + model operations; very slow)
ACE_LOG_MAX_MB = 2048                # log size limit (MB); once exceeded, details are skipped
ACE_LOG_PROFILER_STEPS = 2            # full level: how many diffusion steps to record with the PyTorch profiler (each operation: name, shapes, time)
RESOURCE_PROFILE = "balanced"       # "economical" (1/2 of cores, low priority - the computer stays usable) | "balanced" | "maximum" (all cores, high priority)
ACE_ENGINE = "cpp"                    # "auto" (C++ when installed, otherwise PyTorch) | "cpp" (acestep.cpp, GGUF - light) | "pytorch"
ACE_DEVICE = "cpu"                # "cpu" | "gpu" | "cpu+gpu" (GPU + offloading to RAM). C++: GPU = Vulkan/CUDA, PyTorch: CUDA/XPU/MPS
ACE_GGUF_QUANT = "Q8_0"               # C++ engine: Q8_0 (most faithful) | Q6_K | Q5_K_M | Q4_K_M (least RAM) | BF16
ACE_CPP_LM = "0.6B"                   # C++ engine, text mode: language model that plans the structure ("" = none, "0.6B", "1.7B", "4B")
ACE_SWAP_FILE = None               # "own swap" for model weights (PyTorch engine, CPU computation): a directory or file on any
                                      # drive, including USB, e.g. r"H:\ace_swap" or r"H:\weights.bin". Weights stop loading pagefile.sys
                                      # and the commit limit - the system reads them back from this file. The file disappears by itself when done.
                                      # None = disabled
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
                                      # their sound goes to ACE-Step as reference audio (instead of a fragment of the input file)
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

# --- PRO VERSION: separation into instruments and neural classification ---
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

# --- results export: output/<SCRIPT_SUBDIR>/<session>/... ---
SCRIPT_SUBDIR = "small_pro_ace"
CHANNEL_FORMATS = ("mono", "stereo", "surround")  # versions of every audio file; surround = pseudo 5.1
WAV_SUBTYPE = "PCM_24"
EXPORT_NOTATION = True          # MusicXML + LilyPond + text
EXPORT_SAMPLES = True           # 1- and 2-bar loops and band stems
EXPORT_USED_SOUNDS = True # slices of the input file used for analysis / as melody

DEFAULT_USER_DESCRIPTION = "professional hardstyle and dark synth-goth, massive distorted reverse bass, soaring detuned supersaw"

def _xpu_available():
    try:
        return hasattr(torch, "xpu") and torch.xpu.is_available()
    except Exception:
        return False

def detect_hybrid_devices():
    """
    Configures simultaneous work of the CPU and the integrated Intel Graphics card (XPU or DirectML).
    While the GPU/XPU computes the main transformer, the CPU computes DSP/STFT/Ollama in the background and handles EnCodec.
    """
    if _xpu_available():
        gpu_name = torch.xpu.get_device_name(0) if hasattr(torch.xpu, "get_device_name") else "Intel Graphics XPU"
        return "xpu", "cpu", f"HYBRID ACTIVE: Intel GPU ({gpu_name}) [Transformer] + CPU [DSP/EnCodec/Ollama]"
    try:
        import torch_directml
        if torch_directml.is_available():
            dml_dev = torch_directml.device()
            return dml_dev, "cpu", f"HYBRID ACTIVE: Intel DirectML GPU ({torch_directml.device_name(0)}) + CPU [DSP/Ollama]"
    except Exception:
        pass
    if torch.cuda.is_available():
        return "cuda", "cpu", "HYBRID ACTIVE: GPU CUDA + CPU [DSP/Ollama]"
    return "cpu", "cpu", "CPU MODE (no supported GPU): CPU threads [Transformer] + 1 background thread [DSP/STFT/Ollama]"

MAIN_DEVICE, AUX_DEVICE, MODE_DESCRIPTION = detect_hybrid_devices()

def _ram_gb():
    # (total, free) RAM in GB or None when it cannot be determined
    try:
        import ctypes
        class _MemStatus(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
        ms = _MemStatus()
        ms.dwLength = ctypes.sizeof(_MemStatus)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms)):
            return None
        return ms.ullTotalPhys / 2 ** 30, ms.ullAvailPhys / 2 ** 30
    except Exception:
        return None

def choose_model_dtype():
    # GPU: fp16. CPU: fp32; with little RAM (<12 GB) and a large model (melody): bf16 (half the memory).
    # Override: environment variable GENERATE_DTYPE=fp32 or bf16.
    forced = os.environ.get("GENERATE_DTYPE", "").strip().lower()
    if forced in ("fp32", "float32"):
        return torch.float32
    if forced in ("bf16", "bfloat16"):
        return torch.bfloat16
    if str(MAIN_DEVICE) in ("cuda", "xpu"):
        return torch.float16
    ram = _ram_gb()
    if MODEL_LARGE and ram and ram[0] < 12:
        return torch.bfloat16
    return torch.float32

# We leave 1 physical thread for the asynchronous DSP/Ollama background pipeline
num_cores = os.cpu_count() or 4
transformer_threads = max(1, num_cores - 1) if str(MAIN_DEVICE) == "cpu" else max(1, num_cores // 2)
torch.set_num_threads(transformer_threads)

INPUT_DIR = WORKSPACE_DIR / "input"
OUTPUT_DIR = WORKSPACE_DIR / "output" / SCRIPT_SUBDIR
TEMP_DIR = OUTPUT_DIR / "_temp"
for d in [INPUT_DIR, OUTPUT_DIR, TEMP_DIR]:
    d.mkdir(parents=True, exist_ok=True)

ALL_AUDIO_FORMATS = {
    ".opus", ".mp3", ".wav", ".flac", ".ogg", ".m4a", ".wma", ".aac",
    ".aiff", ".aif", ".alac", ".ape", ".wv", ".mp2", ".webm", ".mp4"
}

def get_prompt_from_user():
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        return " ".join(sys.argv[1:]).strip()
    print("\n" + "=" * 72)
    print(f" 🎛️  GENERATE_SMALL_PRO_ACE.PY (ACE-Step turbo + DEMUCS + AST) | MODE: {MODE_DESCRIPTION}")
    print("=" * 72)
    print(f"Default guidelines: {DEFAULT_USER_DESCRIPTION}")
    try:
        entry = input("\nEnter your own prompt / description of changes (or press ENTER for the default):\n> ").strip()
    except EOFError:
        entry = ""
    return entry if entry else DEFAULT_USER_DESCRIPTION

def find_audio_files():
    found = []
    if INPUT_DIR.exists():
        for p in INPUT_DIR.rglob("*"):
            if p.is_file() and p.suffix.lower() in ALL_AUDIO_FORMATS and not p.name.startswith("_temp_"):
                found.append(p.resolve())
    if not found:
        for p in WORKSPACE_DIR.iterdir():
            if p.is_file() and p.suffix.lower() in ALL_AUDIO_FORMATS:
                found.append(p.resolve())
    found.sort()
    return found

class ProgressMonitor(LogitsProcessor):
    def __init__(self, total_tokens, segment_num, all_segments):
        self.step = 0
        self.total_tokens = total_tokens
        self.segment_num = segment_num
        self.all_segments = all_segments
        self.start_time = time.time()

    def __call__(self, input_ids, scores):
        self.step += 1
        elapsed = time.time() - self.start_time
        speed = self.step / elapsed if elapsed > 0 else 0
        eta_sec = (self.total_tokens - self.step) / speed if speed > 0 else 0
        sys.stdout.write(
            f"\r[Segment {self.segment_num}/{self.all_segments}] "
            f"Token: {self.step}/{self.total_tokens} | "
            f"Time: {elapsed:.1f}s | {speed:.2f} tok/s | ETA: {eta_sec/60:.1f} min   "
        )
        sys.stdout.flush()
        return scores

OLLAMA_URL = "http://localhost:11434"

def _ollama_options():
    # Short answer and small context; with 4 cores Ollama gets 1 thread so it does not starve the transformer
    options = {"num_ctx": 1024, "num_predict": 80}
    if (os.cpu_count() or 4) <= 4:
        options["num_thread"] = 1
    return options

def _ollama_state():
    """None = server not responding, False = model missing, True = ready."""
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        if r.status_code != 200:
            return None
        names = [m.get("name", "") for m in r.json().get("models", [])]
        return any(n == OLLAMA_MODEL or n.startswith(OLLAMA_MODEL + ":") for n in names)
    except Exception:
        return None

OLLAMA_LOCAL_DIR = Path(__file__).resolve().parent / "ollama"  # installation next to the script, not on the system drive

def _find_ollama():
    candidates = [OLLAMA_LOCAL_DIR / "ollama.exe", OLLAMA_LOCAL_DIR / "bin" / "ollama",
                 OLLAMA_LOCAL_DIR / "ollama"]
    fpath = shutil.which("ollama")
    if fpath:
        return fpath
    localappdata_dir = os.environ.get("LOCALAPPDATA")
    if localappdata_dir:
        candidates.append(Path(localappdata_dir) / "Programs" / "Ollama" / "ollama.exe")
    candidates += [Path("/usr/local/bin/ollama"), Path("/usr/bin/ollama"), Path("/opt/homebrew/bin/ollama"),
                  Path("/Applications/Ollama.app/Contents/Resources/ollama")]
    for k in candidates:
        if k.is_file():
            os.environ["PATH"] = os.pathsep.join([str(k.parent), os.environ.get("PATH", "")])
            return str(k)
    return None

def _download_file(url, dest):
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1024 * 1024):
                f.write(chunk)

def _stop_ollama_processes():
    """On Windows the installer starts Ollama by itself with the default models directory (system drive) - we stop it."""
    if os.name == "nt":
        for item_name in ("ollama app.exe", "ollama.exe"):
            subprocess.run(["taskkill", "/F", "/IM", item_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2)

def _install_ollama():
    """Installs Ollama IN A DIRECTORY NEXT TO THE SCRIPT (Windows: official installer with /DIR; Linux/macOS: archive from ollama.com)."""
    import tempfile, platform, tarfile
    if "ANDROID_ROOT" in os.environ:
        print("[OLLAMA] Android/Termux: installing the ollama package (pkg install ollama)...")
        subprocess.run(["pkg", "install", "-y", "ollama"])
        return bool(_find_ollama())
    dest = OLLAMA_LOCAL_DIR
    print(f"[OLLAMA] Ollama not found - installing it locally in: {dest}")
    try:
        dest.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(prefix="ollama_inst_"))
        if os.name == "nt":
            installer = tmp / "OllamaSetup.exe"
            print("[OLLAMA] Downloading the installer from ollama.com...")
            _download_file("https://ollama.com/download/OllamaSetup.exe", installer)
            print("[OLLAMA] Running the installer (silent mode)...")
            subprocess.run(f'"{installer}" /SILENT /NORESTART /CURRENTUSER /DIR="{dest}"', timeout=900)
            _stop_ollama_processes()
        else:
            arch = "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "amd64"
            system = "darwin" if sys.platform == "darwin" else "linux"
            if system == "darwin":
                variants = ["ollama-darwin.tgz"]
            else:
                variants = [f"ollama-linux-{arch}.tgz", f"ollama-linux-{arch}.tar.zst"]
            downloaded_bytes = None
            for item_name in variants:
                try:
                    print(f"[OLLAMA] Downloading {item_name}...")
                    _download_file(f"https://ollama.com/download/{item_name}", tmp / item_name)
                    downloaded_bytes = tmp / item_name
                    break
                except Exception as e:
                    print(f"[OLLAMA] {item_name}: {e}")
            if downloaded_bytes is None:
                if system == "darwin" and shutil.which("brew"):
                    print("[OLLAMA] Installing via Homebrew (outside the script directory)...")
                    subprocess.run(["brew", "install", "ollama"], timeout=900)
                else:
                    return False
            elif downloaded_bytes.suffix == ".tgz":
                with tarfile.open(downloaded_bytes) as t:
                    t.extractall(dest)
            else:
                subprocess.run(["tar", "--zstd", "-xf", str(downloaded_bytes), "-C", str(dest)], check=True)
            for file in (dest / "bin" / "ollama", dest / "ollama"):
                if file.exists():
                    file.chmod(0o755)
    except Exception as e:
        print(f"[OLLAMA] Installation failed ({e}). Install manually: https://ollama.com/download")
        return False
    if _find_ollama():
        print("[OLLAMA] Installation finished.")
        return True
    print("[OLLAMA] Could not install Ollama. Install manually: https://ollama.com/download")
    return False

def _download_ollama_model(ollama_bin):
    print(f"[OLLAMA] Downloading model '{OLLAMA_MODEL}' (one-time, approx. 2 GB)...")
    try:
        subprocess.run([ollama_bin, "pull", OLLAMA_MODEL], timeout=3600)
    except Exception as e:
        print(f"[OLLAMA] Model download failed ({e}).")
    return _ollama_state()

def prepare_ollama():
    if not USE_OLLAMA:
        return False
    state = _ollama_state()
    ollama_bin = _find_ollama()
    if state is None and not ollama_bin:
        if not AUTOINSTALL_OLLAMA or not _install_ollama():
            if not AUTOINSTALL_OLLAMA:
                print("[OLLAMA] Ollama not found - using default prompts.")
            return False
        ollama_bin = _find_ollama()
        state = _ollama_state()
    if state is None:
        subprocess.Popen(
            [ollama_bin, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
        )
        for _ in range(30):
            time.sleep(1)
            state = _ollama_state()
            if state is not None:
                break
    if state is None:
        print("[OLLAMA] Server not responding - using default prompts.")
        return False
    if not state:
        if AUTOINSTALL_OLLAMA and ollama_bin:
            state = _download_ollama_model(ollama_bin)
        if not state:
            print(f"[OLLAMA] Model '{OLLAMA_MODEL}' missing (download: ollama pull {OLLAMA_MODEL}) - using default prompts.")
            return False
    return True

def load_audio_via_av_or_ffmpeg(file_path, target_sr=32000):
    try:
        container = av.open(str(file_path))
        stream = container.streams.audio[0]
        resampler = av.audio.resampler.AudioResampler(format='flt', layout='mono', rate=target_sr)
        frames = []
        for frame in container.decode(stream):
            for rf in resampler.resample(frame):
                frames.append(rf.to_ndarray())
        try:
            for rf in resampler.resample(None):
                frames.append(rf.to_ndarray())
        except Exception:
            pass
        container.close()
        audio_np = np.concatenate(frames, axis=1).squeeze(0).astype(np.float32)
    except Exception:
        temp_wav = TEMP_DIR / f"_temp_decode_{os.getpid()}.wav"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(file_path), "-vn", "-acodec", "pcm_f32le", "-ar", str(target_sr), "-ac", "1", str(temp_wav)], check=True)
        audio_np, _ = sf.read(str(temp_wav), dtype='float32')
        if temp_wav.exists():
            temp_wav.unlink()

    peak = np.max(np.abs(audio_np))
    if peak > 1e-5:
        audio_np = (audio_np / peak) * 0.9
    return audio_np, target_sr

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

# ==============================================================================
# INPUT TRACK ANALYSIS: structure, chords, sound character, section plan
# (pure numpy; STFT computed in blocks, so RAM usage is small)
# ==============================================================================
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

# ---------------------------- chords ----------------------------
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

# ---------------------------- section plan ----------------------------
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

# ---------------------------- worker: notes + chords + prompt ----------------------------
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

# ==============================================================================
# PRO VERSION: separation into instruments (Demucs / HPSS as fallback), neural
# instrument classification (AST AudioSet), percussion and MIDI per stem
# ==============================================================================
import hashlib
import types as _types

# friendly, group  (AudioSet labels -> instrument)
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

# ---------------------------- tools ----------------------------
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

def _stub_module(item_name, **attrs):
    m = _types.ModuleType(item_name)
    m.__spec__ = importlib.machinery.ModuleSpec(item_name, loader=None)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[item_name] = m
    return m

def _ensure_demucs_stubs():
    """Demucs imports modules needed only for training (openunmix, dora, omegaconf) - when they are missing, we substitute stubs."""
    def missing_mod(item_name):
        try:
            importlib.import_module(item_name)
            return False
        except Exception:
            for k in [k for k in sys.modules if k == item_name or k.startswith(item_name + ".")]:
                sys.modules.pop(k, None)
            return True

    def _error(message="unavailable"):
        raise RuntimeError(message)

    if missing_mod("openunmix.filtering"):
        package = _stub_module("openunmix")
        package.__path__ = []
        package.filtering = _stub_module("openunmix.filtering", wiener=lambda *a, **k: _error("wiener niedostepny"))
    if missing_mod("dora.log"):
        package = _stub_module("dora")
        package.__path__ = []
        package.log = _stub_module("dora.log", fatal=_error, bold=lambda t: t)
    if missing_mod("omegaconf"):
        _stub_module("omegaconf", OmegaConf=type("OmegaConf", (), {}))

def _pip(*packages, no_deps=False):
    command = [sys.executable, "-m", "pip", "install", "--quiet"] + (["--no-deps"] if no_deps else []) + list(packages)
    try:
        return subprocess.run(command).returncode == 0
    except Exception as e:
        print(f"[DEMUCS] pip did not work ({e})")
        return False

def _import_demucs():
    _ensure_demucs_stubs()
    from demucs.pretrained import get_model
    from demucs.apply import apply_model
    return get_model, apply_model

def _load_demucs():
    try:
        return _import_demucs()
    except Exception as e:
        error = e
    if AUTOINSTALL_DEMUCS:
        print(f"[DEMUCS] Library unavailable ({type(error).__name__}: {error}) - installing (einops, julius, tqdm, pyyaml, demucs)...")
        _pip("einops", "julius", "tqdm", "pyyaml")
        _pip("demucs", no_deps=True)
        importlib.invalidate_caches()
        for k in [k for k in sys.modules if k == "demucs" or k.startswith("demucs.")]:
            sys.modules.pop(k, None)
        try:
            return _import_demucs()
        except Exception as e:
            error = e
    print(f"[DEMUCS] Could not load Demucs ({type(error).__name__}: {error}) - using the fallback separator (HPSS).")
    return None

# ---------------------------- separators ----------------------------
class _SeparatorDemucs:
    def __init__(self, get_model, apply_model):
        os.environ.setdefault("TORCH_HOME", str(WORKSPACE_DIR / "models" / "torch"))
        self._apply = apply_model
        print(f"[DEMUCS] Loading model '{MODEL_DEMUCS}' (on the first run the weights are downloaded, a few dozen MB)...")
        original = torch.load

        def _load(*a, **k):
            k.setdefault("weights_only", False)  # trusted Demucs weights contain Python classes
            return original(*a, **k)
        torch.load = _load
        try:
            self.model = get_model(MODEL_DEMUCS)
        finally:
            torch.load = original
        self.model.eval()
        self.names = list(self.model.sources)
        self.sr_model = int(self.model.samplerate)
        self.description = f"demucs:{MODEL_DEMUCS}"

    def separate(self, audio, sr):
        x = _resample_fft(audio, sr, self.sr_model)
        wav = torch.from_numpy(np.stack([x, x])).float()
        ref = wav.mean(0)
        avg, dev = ref.mean(), ref.std() + 1e-8
        wav = (wav - avg) / dev
        with torch.no_grad():
            output = self._apply(self.model, wav[None], shifts=SEPARATION_SHIFTS, split=True, overlap=0.25,
                                  progress=False, device=aux_device(), num_workers=0)[0]
        output = output * dev + avg
        return {n: _match_length(_resample_fft(output[i].mean(0).cpu().numpy(), self.sr_model, sr), len(audio))
                for i, n in enumerate(self.names)}

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

# ---------------------------- instrument classification ----------------------------
class _ASTClassifier:
    def __init__(self):
        from transformers import ASTFeatureExtractor, ASTForAudioClassification
        print(f"[CLASSIFIER] Loading the AST network '{CLASSIFIER_MODEL}' (on the first run the weights are downloaded)...")
        self.fe = ASTFeatureExtractor.from_pretrained(CLASSIFIER_MODEL)
        self.model = ASTForAudioClassification.from_pretrained(CLASSIFIER_MODEL).eval()
        self.indices = {int(i): AUDIOSET_INSTRUMENTS[l] for i, l in self.model.config.id2label.items() if l in AUDIOSET_INSTRUMENTS}
        if not self.indices:
            raise RuntimeError("the model does not contain AudioSet instrument labels")

    def classify(self, audio, sr, allowed_groups):
        fragment = _loudest_fragment(np.asarray(audio, dtype=np.float32), sr, 10.24)
        a16 = _resample_fft(fragment, sr, 16000)
        inp = self.fe(a16, sampling_rate=16000, return_tensors="pt")
        with torch.no_grad():
            p = torch.sigmoid(self.model(**inp).logits[0]).cpu().numpy()
        best_items = {}
        for i, (item_name, grp) in self.indices.items():
            if grp in allowed_groups and float(p[i]) > best_items.get(item_name, -1.0):
                best_items[item_name] = float(p[i])
        return sorted(best_items.items(), key=lambda x: -x[1])

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

# ---------------------------- percussion and MIDI ----------------------------
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

# ---------------------------- stems for plan windows ----------------------------
def _cache_path(file, start_s, len_s, separator_description):
    try:
        st = Path(file).stat()
        base = f"{Path(file).name}|{st.st_size}|{int(st.st_mtime)}"
    except Exception:
        base = str(file)
    h = hashlib.sha1(f"{base}|{start_s:.3f}|{len_s:.3f}|{separator_description}".encode("utf-8")).hexdigest()[:16]
    return WORKSPACE_DIR / "stem_cache" / f"{h}.npz"

def prepare_window_stems(file, audio, sr, plan, window_len_sec):
    """For each plan window: separates the audio into stems and classifies the instruments. Returns a list of dicts (or None on error)."""
    try:
        loaded = _load_demucs()
        separator = None
        if loaded is not None:
            try:
                separator = _SeparatorDemucs(*loaded)
            except Exception as e:
                print(f"[DEMUCS] Could not load the model ({type(e).__name__}: {e}) - using the fallback separator (HPSS).")
        if separator is None:
            separator = _SeparatorHPSS()
        classifier = None
        if NEURAL_CLASSIFIER:
            try:
                classifier = _ASTClassifier()
            except Exception as e:
                print(f"[CLASSIFIER] AST network unavailable ({type(e).__name__}: {e}) - using heuristics.")
        print(f"\n[STEMS] Separation ({separator.description}) {len(plan)} windows of {window_len_sec:.1f}s; stems: {', '.join(separator.names)}")
        n_window = int(window_len_sec * sr)
        results = []
        for i, p in enumerate(plan, 1):
            start = min(max(0.0, float(p["start_s"])), max(0.0, len(audio) / sr - window_len_sec))
            wnd = _match_length(audio[int(start * sr):int(start * sr) + n_window], n_window)
            fpath = _cache_path(file, start, window_len_sec, separator.description)
            stems, from_cache = None, False
            if STEM_CACHE and fpath.exists():
                try:
                    with np.load(fpath, allow_pickle=False) as z:
                        stems = {k: z[k] for k in z.files}
                    from_cache = True
                except Exception:
                    stems = None
            t0 = time.time()
            if stems is None:
                stems = separator.separate(wnd, sr)
                if STEM_CACHE:
                    try:
                        fpath.parent.mkdir(parents=True, exist_ok=True)
                        np.savez(fpath, **stems)
                    except Exception:
                        pass
            class_names = classify_stems(stems, sr, classifier)
            mel = {n: a for n, a in stems.items() if n in MELODIC_STEMS and class_names[n]["present"]}
            lead = max(mel, key=lambda n: _rms(mel[n])) if mel else None
            description = instruments_description(class_names)
            print(f"[STEMS] window {i}/{len(plan)} ({start:.1f}s){' [cache]' if from_cache else ''} {time.time() - t0:.0f}s: " +
                  " | ".join(f"{n}: {', '.join(k['instruments']) or '-'}" if k["present"] else f"{n}: (silence)" for n, k in class_names.items()))
            results.append({"stems": stems, "classes": class_names, "lead_stem": lead, "description": description, "start_s": round(start, 3),
                           "separator": separator.description})
        del separator, classifier
        gc.collect()
        return results
    except Exception as e:
        print(f"[STEMS] Separation skipped ({type(e).__name__}: {e}) - working on the full mix.")
        return None

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

# ==============================================================================
# EXPORT: directory structure, mono/stereo/surround versions, notation, samples
# ==============================================================================
import json
import re
from xml.sax.saxutils import escape as _xml_escape

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

# ---------- DSP tools (pure numpy - scipy may be a stub) ----------
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

# ---------- sample ----------
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

# ---------- notation: MusicXML, LilyPond, text ----------
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

# ==============================================================================
# MAIN COMPOSITION
# ==============================================================================
# ==============================================================================
# DETAILED LOGS: text file + JSONL, tracing of function calls and (level "full") every line of code
# ==============================================================================
import atexit
import linecache
import threading
import types

_LOG = {"txt": None, "jsonl": None, "t0": None, "bytes": 0, "limit_exceeded": False, "path": None,
        "stats": {}, "counter": {}, "active": False}
_LOG_LOCK = threading.Lock()
_LOG_MAX_CALLS_PER_FUNCTION = 40        # afterwards we only count (detailed level); full logs everything
_LOG_SKIPPED_FUNCTIONS = {"_write_log", "_shorten", "log_line", "_array_description", "_trace_global", "_trace_local", "_variable_label",
                         "_ram_gb", "_show", "_reader", "_wait", "_download_progress", "_dir_size", "<genexpr>",
                         "<listcomp>", "<dictcomp>", "<setcomp>", "<lambda>"}


def _array_description(x):
    """Short but complete description of an array: shape, dtype, min/max/mean/RMS/std (from a sample for large arrays)."""
    try:
        a = np.asarray(x)
        if a.size == 0:
            return f"ndarray{tuple(a.shape)} {a.dtype} (empty)"
        if a.dtype.kind in "fciu":
            p = a.reshape(-1)
            if p.size > 2_000_000:
                p = p[:: p.size // 1_000_000]
            if np.iscomplexobj(p):
                p = np.abs(p)
            p = p.astype(np.float64)
            return (f"ndarray{tuple(a.shape)} {a.dtype} min={np.nanmin(p):.6g} max={np.nanmax(p):.6g} "
                    f"mean={np.nanmean(p):.6g} rms={np.sqrt(np.nanmean(p * p)):.6g} std={np.nanstd(p):.6g}")
        return f"ndarray{tuple(a.shape)} {a.dtype}"
    except Exception as e:
        return f"ndarray(? {type(e).__name__})"


def _shorten(v, depth=0):
    """Readable description of any value (arrays reduced to statistics, long lists to their beginning)."""
    try:
        if isinstance(v, np.ndarray):
            return _array_description(v)
        if "torch" in type(v).__module__ and hasattr(v, "shape"):
            try:
                return "tensor " + _array_description(v.detach().float().cpu().numpy())
            except Exception:
                return f"tensor{tuple(v.shape)}"
        if isinstance(v, (int, float, bool, complex, type(None), np.generic)):
            return repr(v)
        if isinstance(v, str):
            return repr(v) if len(v) <= 300 else repr(v[:300]) + f"...(+{len(v) - 300} chars)"
        if isinstance(v, Path):
            return f"Path({str(v)!r})"
        if isinstance(v, (list, tuple, set)) and depth < 2:
            el = list(v)[:12]
            interior = ", ".join(_shorten(x, depth + 1) for x in el)
            rest = f", ...(+{len(v) - 12})" if len(v) > 12 else ""
            return f"{type(v).__name__}[{len(v)}]({interior}{rest})"
        if isinstance(v, dict) and depth < 2:
            el = list(v.items())[:15]
            interior = ", ".join(f"{k!r}: {_shorten(x, depth + 1)}" for k, x in el)
            rest = f", ...(+{len(v) - 15})" if len(v) > 15 else ""
            return "{" + interior + rest + "}"
        if isinstance(v, (types.FunctionType, types.MethodType, types.ModuleType, type)):
            return f"<{type(v).__name__} {getattr(v, '__name__', '?')}>"
        r = repr(v)
        return r if len(r) <= 200 else r[:200] + "..."
    except Exception as e:
        return f"<{type(v).__name__}: cannot be described ({type(e).__name__})>"


def _write_log(line, data=None):
    if _LOG["txt"] is None:
        return
    with _LOG_LOCK:
        if _LOG["limit_exceeded"]:
            return
        try:
            t = time.time() - _LOG["t0"]
            heading = f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]} +{t:9.3f}s] "
            txt = heading + line + "\n"
            _LOG["txt"].write(txt)
            _LOG["bytes"] += len(txt.encode("utf-8", "replace"))
            if data is not None and _LOG["jsonl"] is not None:
                j = json.dumps({"t": round(t, 4), "event": line[:120], **data}, ensure_ascii=False, default=_shorten)
                _LOG["jsonl"].write(j + "\n")
                _LOG["bytes"] += len(j) + 1
            if _LOG["bytes"] > ACE_LOG_MAX_MB * 2 ** 20:
                _LOG["limit_exceeded"] = True
                _LOG["txt"].write(f"\n[LOG] Reached the {ACE_LOG_MAX_MB} MB limit - skipping further details (increase ACE_LOG_MAX_MB).\n")
                sys.settrace(None)
                threading.settrace(None)
        except Exception:
            pass


def log_line(category, message, **data):
    """Log event: human-readable text + a JSONL record with all values."""
    if _LOG["txt"] is None:
        return
    details = "".join(f"\n      {k} = {_shorten(v)}" for k, v in data.items())
    _write_log(f"[{category}] {message}{details}", {"category": category, **{k: _shorten(v) for k, v in data.items()}})


_SIMPLE_TYPES = (bool, int, float, complex, type(None), np.generic, Path, datetime)


def _variable_label(v):
    """Cheap 'fingerprint' of a variable's value for detecting its changes in full mode (called on EVERY line of code).
    Never computes a full repr(): the repr of a list of thousands of arrays (e.g. frames of a decoded track) or of a large tensor
    on every line made loading a track take tens of minutes (time grew with the square of the file length)."""
    try:
        if isinstance(v, _SIMPLE_TYPES):
            return repr(v)
        if isinstance(v, str):
            return (len(v), v[:400])
        if isinstance(v, (list, tuple, dict, set, frozenset, bytes, bytearray)):
            return (type(v), id(v), len(v))
        if isinstance(v, np.ndarray) or ("torch" in type(v).__module__ and hasattr(v, "shape")):
            return (type(v), id(v), tuple(v.shape))
    except Exception:
        pass
    return (type(v), id(v))


def _trace_local(frame, event, arg):
    co = frame.f_code
    if event == "line" and ACE_LOG_LEVEL == "full":
        prev = _LOG["stats"].setdefault(("loc", id(frame)), {})
        changes = []
        for k, v in frame.f_locals.items():
            if k.startswith("__"):
                continue
            sig_label = _variable_label(v)
            if prev.get(k) != sig_label:
                prev[k] = sig_label
                changes.append(f"{k} = {_shorten(v)}")
        code = linecache.getline(co.co_filename, frame.f_lineno).strip()
        _write_log(f"      L{frame.f_lineno:<5} {code[:160]}" + ("".join(f"\n            → {z}" for z in changes) if changes else ""))
    elif event == "return":
        key_id = co.co_name
        t0 = _LOG["stats"].pop(("t", id(frame)), None)
        _LOG["stats"].pop(("loc", id(frame)), None)
        dt = time.perf_counter() - t0 if t0 else 0.0
        st = _LOG["counter"].setdefault(key_id, [0, 0.0])
        st[1] += dt
        if ACE_LOG_LEVEL == "full" or st[0] <= _LOG_MAX_CALLS_PER_FUNCTION:
            _write_log(f"  ← {key_id} returns {_shorten(arg)}  ({dt * 1000:.2f} ms)")
    elif event == "exception":
        _write_log(f"  ! {co.co_name} L{frame.f_lineno}: exception {arg[0].__name__}: {str(arg[1])[:300]}")
    return _trace_local


def _trace_global(frame, event, arg):
    if event != "call":
        return None
    co = frame.f_code
    ours = _LOG["files"].get(co.co_filename)
    if ours is None:      # comparison by real path (symlinks, letter case on Windows) - computed once per file
        ours = _LOG["files"][co.co_filename] = os.path.normcase(os.path.realpath(co.co_filename)) == _LOG["script_file"]
    if not ours or co.co_name in _LOG_SKIPPED_FUNCTIONS or _LOG["limit_exceeded"]:
        return None
    st = _LOG["counter"].setdefault(co.co_name, [0, 0.0])
    st[0] += 1
    _LOG["stats"][("t", id(frame))] = time.perf_counter()
    frame.f_trace_lines = ACE_LOG_LEVEL == "full"      # line events only in full mode (speed)
    if ACE_LOG_LEVEL == "full" or st[0] <= _LOG_MAX_CALLS_PER_FUNCTION:
        n_arg = co.co_argcount + co.co_kwonlyargcount
        arguments = ", ".join(f"{k}={_shorten(frame.f_locals.get(k))}" for k in co.co_varnames[:n_arg])
        _write_log(f"→ {co.co_name}({arguments})  [call #{st[0]}, line {frame.f_lineno}]")
        if st[0] == _LOG_MAX_CALLS_PER_FUNCTION and ACE_LOG_LEVEL != "full":
            _write_log(f"  (further calls of {co.co_name} are only counted - summary at the end of the log)")
    return _trace_local


def logs_start(directory):
    """Opens the log files and enables tracing according to ACE_LOG_LEVEL."""
    if ACE_LOG_LEVEL == "basic" or _LOG["txt"] is not None:
        return
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    marker = datetime.now().strftime("%Y%m%d_%H%M%S")
    _LOG["path"] = directory / f"log_{marker}.txt"
    _LOG["txt"] = open(_LOG["path"], "w", encoding="utf-8", buffering=1)
    _LOG["jsonl"] = open(directory / f"log_{marker}.jsonl", "w", encoding="utf-8", buffering=1)
    _LOG["t0"] = time.time()
    _LOG["script_file"] = os.path.normcase(os.path.realpath(__file__))
    _LOG["files"] = {}
    _LOG["active"] = True
    print(f"[LOG] Level '{ACE_LOG_LEVEL}', writing to: {_LOG['path']}  (+ .jsonl with data for analysis)")
    consts = {k: v for k, v in globals().items() if k.isupper() and not k.startswith("_")
             and isinstance(v, (int, float, str, bool, list, tuple, dict, type(None), Path))}
    log_line("START", f"Script {Path(__file__).name}, Python {sys.version.split()[0]}, numpy {np.__version__}, "
                   f"torch {getattr(torch, '__version__', '?')}, system {sys.platform}, cores {os.cpu_count()}",
          ram=_ram_gb(), argv=sys.argv, **{f"const_{k}": v for k, v in sorted(consts.items())})
    atexit.register(logs_end)
    if ACE_LOG_LEVEL in ("detailed", "full"):
        sys.settrace(_trace_global)
        threading.settrace(_trace_global)


def logs_end():
    if _LOG["txt"] is None:
        return
    sys.settrace(None)
    threading.settrace(None)
    _LOG["limit_exceeded"] = False
    ranking = sorted(_LOG["counter"].items(), key=lambda kv: -kv[1][1])
    _write_log("[SUMMARY] Script functions: number of calls and total time (longest first):" +
              "".join(f"\n      {n:<40} {c:>9}×  {t:10.3f} s" for n, (c, t) in ranking[:200]))
    _write_log(f"[END] Log size: {_LOG['bytes'] / 2 ** 20:.1f} MB")
    for k in ("txt", "jsonl"):
        try:
            _LOG[k].close()
        except Exception:
            pass
        _LOG[k] = None


# ==============================================================================
# SETTINGS FROM THE MENU (menu_ace_android.py): the JSON file named in the GENERATE_SETTINGS variable overrides the script constants
# ==============================================================================
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

def _load_settings_from_menu():
    fpath = os.environ.get("GENERATE_SETTINGS")
    if not fpath:
        return
    try:
        sett = json.loads(Path(fpath).read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[MENU] Could not load settings from {fpath}: {e}")
        return
    g = globals()
    changed = []
    for k, v in sett.items():
        if k in MENU_VARIABLES and k in g:
            if k == "CHANNEL_FORMATS":
                v = tuple(v)
            g[k] = v
            changed.append(f"{k}={v!r}")
    file_list = [Path(p) for p in (sett.get("_FILES") or []) if Path(p).is_file()]
    if file_list:
        g["find_audio_files"] = lambda: list(file_list)
        changed.append("files=" + ", ".join(p.name for p in file_list))
    g["MODEL_ID"] = g.get("ACE_MODEL_DIT", g.get("MODEL_ID"))
    g["ACE_SECTION_TIMEOUT_SEC"] = g["ACE_GENERATION_LIMIT_SEC"] + 1800
    g["_ACE_WHOLE"] = g["ACE_WHOLE_TRACK"] or g["ACE_MODE"] == "cover"
    if changed:
        print("[MENU] Settings from the menu: " + "; ".join(changed))

# ==============================================================================
# ACE-STEP ENGINE: separate process (Python 3.11/3.12) + job server via stdin/stdout
# ==============================================================================
import atexit
import threading
import queue

_ACE_WORKER_CODE = '# -*- coding: utf-8 -*-\n# ACE-Step worker process: started with a Python 3.11/3.12 interpreter that has ACE-Step installed.\n# Protocol: stdin = JSON lines with jobs; stdout = logs and lines "@@READY", "@@RESULT {json}", "@@ERROR text".\nimport sys, os, json, time, gc, inspect, shutil, threading\n\ncfg = json.load(open(sys.argv[1], encoding="utf-8"))\nos.environ["OMP_NUM_THREADS"] = str(cfg["threads"])\nos.environ["MKL_NUM_THREADS"] = str(cfg["threads"])\nos.environ["TOKENIZERS_PARALLELISM"] = "false"\nsys.path.insert(0, cfg["directory"])\nos.chdir(cfg["directory"])\nif os.name != "nt" and cfg.get("priority") == "low":\n    try:\n        os.nice(10)\n    except Exception:\n        pass\n\ndef emit(*a):\n    print(*a, flush=True)\n\nLOG_LEVEL = cfg.get("log_level", "basic")\n\n\ndef log(description, **data):\n    """Event for the log file in the main process (does not go to the console)."""\n    if LOG_LEVEL == "basic":\n        return\n    try:\n        emit("@@LOG " + json.dumps({"description": description, **data}, ensure_ascii=False, default=lambda o: repr(o)[:300]))\n    except Exception:\n        pass\n\n\ndef tensor_stats(t):\n    """Shape, dtype and statistics of a tensor (from a sample for large ones)."""\n    try:\n        x = t.detach()\n        if x.numel() == 0:\n            return {"shape": list(x.shape), "type": str(x.dtype).replace("torch.", "")}\n        y = x.reshape(-1)\n        if y.numel() > 1_000_000:\n            y = y[:: y.numel() // 1_000_000]\n        if y.is_complex():\n            y = y.abs()\n        y = y.float()\n        return {"shape": list(x.shape), "type": str(x.dtype).replace("torch.", ""), "min": round(float(y.min()), 6),\n                "max": round(float(y.max()), 6), "sr": round(float(y.mean()), 6),\n                "dev": round(float(y.std()), 6) if y.numel() > 1 else 0.0, "nan": int(torch.isnan(y).sum())}\n    except Exception as e:\n        return {"error": f"{type(e).__name__}: {str(e)[:80]}"}\n\n\ndef describe_value(v, lvl=0):\n    if hasattr(v, "detach") and hasattr(v, "shape"):\n        return tensor_stats(v)\n    if isinstance(v, (int, float, bool, type(None))):\n        return v\n    if isinstance(v, str):\n        return v[:200]\n    if isinstance(v, (list, tuple)) and lvl < 2:\n        return [describe_value(x, lvl + 1) for x in list(v)[:8]] + ([f"...(+{len(v) - 8})"] if len(v) > 8 else [])\n    if isinstance(v, dict) and lvl < 2:\n        return {str(k): describe_value(x, lvl + 1) for k, x in list(v.items())[:12]}\n    return type(v).__name__\n\n\ndef filter_kwargs(obj, kw):\n    try:\n        sig = inspect.signature(obj)\n        if any(p.kind == p.VAR_KEYWORD for p in sig.parameters.values()):\n            return dict(kw), []\n        ok = {k: v for k, v in kw.items() if k in sig.parameters}\n    except (TypeError, ValueError):\n        ok = dict(kw)\n    return ok, [k for k in kw if k not in ok]\n\ndef free_ram_mb():\n    try:\n        import ctypes\n        class MS(ctypes.Structure):\n            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),\n                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),\n                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),\n                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),\n                        ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]\n        ms = MS(); ms.dwLength = ctypes.sizeof(MS)\n        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms)):\n            return ms.ullAvailPhys // 2 ** 20\n    except Exception:\n        pass\n    try:\n        with open("/proc/meminfo") as f:\n            for l in f:\n                if l.startswith("MemAvailable:"):\n                    return int(l.split()[1]) // 1024\n    except Exception:\n        pass\n    return None\n\ndef watchdog():\n    last_warn = 0\n    while True:\n        time.sleep(2.0)\n        a = free_ram_mb()\n        if a is not None and a < cfg["ram_threshold_mb"] and time.time() - last_warn > 10:\n            last_warn = time.time()\n            gc.collect()\n            emit(f"[ACE] WARNING: only {a} MB of free RAM - the system may start swapping (close other programs).")\n\nthreading.Thread(target=watchdog, daemon=True).start()\n\nimport importlib.util\nif importlib.util.find_spec("hf_transfer") is not None:\n    os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "1")\n\ndef _download_report():\n    """Before downloading a model, reports the REAL size of the files that still need to be downloaded."""\n    try:\n        import huggingface_hub, fnmatch\n        orig = huggingface_hub.snapshot_download\n\n        def snap(repo_id, *a, **k):\n            try:\n                info = huggingface_hub.HfApi().repo_info(repo_id, repo_type=k.get("repo_type") or "model",\n                                                         revision=k.get("revision"), files_metadata=True)\n                allow, ign = k.get("allow_patterns"), k.get("ignore_patterns")\n                allow = [allow] if isinstance(allow, str) else allow\n                ign = [ign] if isinstance(ign, str) else ign\n                loc = k.get("local_dir")\n                total, n, whole_total = 0, 0, 0\n                for s in info.siblings:\n                    if allow and not any(fnmatch.fnmatch(s.rfilename, p) for p in allow):\n                        continue\n                    if ign and any(fnmatch.fnmatch(s.rfilename, p) for p in ign):\n                        continue\n                    whole_total += s.size or 0\n                    sc = os.path.join(str(loc), s.rfilename) if loc else None\n                    if sc and os.path.exists(sc) and os.path.getsize(sc) == (s.size or -1):\n                        continue\n                    total += s.size or 0\n                    n += 1\n                emit(f"[ACE] Downloading {repo_id}: {n} files to download, {total / 2**30:.2f} GB (whole repository in this scope: {whole_total / 2**30:.2f} GB).")\n            except Exception:\n                pass\n            return orig(repo_id, *a, **k)\n        huggingface_hub.snapshot_download = snap\n    except Exception:\n        pass\n\n_download_report()\n\ntry:\n    import torch\n    torch.set_num_threads(cfg["threads"])\n    from acestep.handler import AceStepHandler\n    from acestep.llm_inference import LLMHandler\n    from acestep.inference import GenerationParams, GenerationConfig, generate_music\nexcept Exception as e:\n    emit(f"@@ERROR import ACE-Step/torch: {type(e).__name__}: {e}")\n    sys.exit(2)\n\nif cfg.get("device") == "auto-gpu":\n    if torch.cuda.is_available():\n        cfg["device"] = "cuda"\n    elif hasattr(torch, "xpu") and torch.xpu.is_available():\n        cfg["device"] = "xpu"\n    elif getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():\n        cfg["device"] = "mps"\n    else:\n        cfg["device"] = "cpu"\n        emit("[ACE] GPU selected, but this PyTorch installation does not see any card (CUDA/XPU/MPS) - computing on the CPU. "\n             "NVIDIA card: --install-gpu=cuda; Intel Arc/Core Ultra: --install-gpu=xpu; Intel UHD: C++ engine (Vulkan).")\n    emit(f"[ACE] PyTorch device: {cfg[\'device\']}" + (" + offloading to RAM (CPU+GPU)" if cfg.get("offload") and cfg["device"] != "cpu" else ""))\nif cfg.get("bf16"):\n    # ACE-Step on CPU sets self.dtype = float32 (init_service_orchestrator). We replace this BEFORE loading the weights,\n    # so the model loads directly in bfloat16 (half the RAM), instead of converting it afterwards.\n    class _HandlerBf16(AceStepHandler):\n        @property\n        def dtype(self):\n            return self.__dict__.get("_dtype_forced", torch.bfloat16)\n\n        @dtype.setter\n        def dtype(self, value_):\n            self.__dict__["_dtype_forced"] = torch.bfloat16 if value_ == torch.float32 else value_\n    dit = _HandlerBf16()\nelse:\n    dit = AceStepHandler()\nllm = LLMHandler()\ninit_kw = {"project_root": cfg["directory"], "config_path": cfg["model"], "device": cfg["device"],\n           "offload_to_cpu": cfg["offload"], "offload_dit_to_cpu": cfg["offload"],\n           "quantization": cfg["quantization"], "compile_model": False, "use_flash_attention": False}\nkw, skipped_kw = filter_kwargs(dit.initialize_service, init_kw)\nif skipped_kw:\n    emit(f"[ACE] The handler does not support these parameters (skipped): {skipped_kw}")\nt0 = time.time()\ntry:\n    init_result = dit.initialize_service(**kw)\nexcept Exception as e:\n    emit(f"@@ERROR initialize_service: {type(e).__name__}: {e}")\n    sys.exit(3)\nif isinstance(init_result, tuple) and len(init_result) >= 2 and init_result[1] is False:\n    emit(f"@@ERROR initialize_service returned an error: {init_result[0]}")\n    sys.exit(3)\ndef committed_memory_mb():\n    """Committed memory of the whole system (Windows: \'Committed\' in Task Manager, Linux: Committed_AS)."""\n    try:\n        import ctypes\n        class MS(ctypes.Structure):\n            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),\n                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),\n                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),\n                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),\n                        ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]\n        ms = MS(); ms.dwLength = ctypes.sizeof(MS)\n        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms)):\n            return (ms.ullTotalPageFile - ms.ullAvailPageFile) // 2 ** 20, ms.ullTotalPageFile // 2 ** 20\n    except Exception:\n        pass\n    try:\n        d = {}\n        with open("/proc/meminfo") as f:\n            for l in f:\n                d[l.split(":")[0]] = int(l.split()[1]) // 1024\n        return d.get("Committed_AS"), d.get("CommitLimit")\n    except Exception:\n        return None, None\n\n\n# ------------------------------------------------------------------------------------------------\n# "Own swap": model weights in a file on a drive chosen by the user (memory-mapped file).\n# The system reads the needed weight fragments back from it and can drop them from RAM without writing to pagefile.sys;\n# the weights also stop counting towards the commit limit. Activations (computations) use regular memory.\n# ------------------------------------------------------------------------------------------------\nSWAP = {"mappings": [], "transfers": 0, "created": 0}\n_LIMIT_FAT = 4 * 2 ** 30 - 64 * 2 ** 20          # FAT32: a single file max 4 GB\n_PAGE = 4096\n\n\ndef _model_modules():\n    import torch.nn as nn\n    outcome, seen = [], set()\n    for holder in (dit, llm):\n        for m in list(vars(holder).values()):\n            if isinstance(m, nn.Module) and id(m) not in seen:\n                seen.add(id(m))\n                outcome.append(m)\n    return outcome\n\n\ndef _in_swap_file(address):\n    for mp in SWAP["mappings"]:\n        if mp["start"] <= address < mp["end"]:\n            return mp\n    return None\n\n\ndef _filesystem_type(directory):\n    """NTFS / exFAT / FAT32 ... (FAT32 will not accept a file larger than 4 GB)."""\n    try:\n        if os.name == "nt":\n            import ctypes\n            k32 = ctypes.WinDLL("kernel32", use_last_error=True)\n            volume = ctypes.create_unicode_buffer(300)\n            if not k32.GetVolumePathNameW(ctypes.c_wchar_p(directory), volume, 300):\n                return ""\n            fs = ctypes.create_unicode_buffer(300)\n            if k32.GetVolumeInformationW(ctypes.c_wchar_p(volume.value), None, 0, None, None, None, fs, 300):\n                return fs.value\n            return ""\n        best, type_ = "", ""\n        with open("/proc/mounts", encoding="utf-8", errors="replace") as f:\n            for line in f:\n                pt = line.split()\n                if len(pt) >= 3:\n                    mp = pt[1].replace("\\\\040", " ")\n                    if (directory == mp or directory.startswith(mp.rstrip("/") + "/")) and len(mp) >= len(best):\n                        best, type_ = mp, pt[2]\n        return type_\n    except Exception:\n        return ""\n\n\ndef _swap_path(fpath, num):\n    """A path without an extension or an existing directory = directory for the file; with an extension = exactly this file.\n    Subsequent files (FAT32 or a top-up) get _2, _3 ... before the extension."""\n    p = os.path.abspath(os.path.expanduser(str(fpath)))\n    if os.path.isdir(p) or p.endswith(("/", "\\\\")) or not os.path.splitext(p)[1]:\n        model = os.path.basename(str(cfg["model"]).rstrip("/\\\\")) or "model"\n        p = os.path.join(p, "ace_swap_" + model + ".bin")\n    if num > 0:\n        root_part, ext = os.path.splitext(p)\n        p = f"{root_part}_{num + 1}{ext}"\n    return p\n\n\ndef _open_mapped_file(p, size_val, delete_on_close):\n    """A memory-mapped file of the given size. delete_on_close=True: the file disappears by itself when the process ends -\n    also when it gets killed (Windows: \'delete on close\' flag, Linux: removing the entry right after mapping)."""\n    import numpy as np\n    if os.path.exists(p) and not os.path.basename(p).lower().startswith("ace_swap"):\n        raise RuntimeError(f"file {p} already exists and is not this script\'s swap file - I will not overwrite it "\n                           "(choose a directory or a new file name)")\n    oflags = os.O_RDWR | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0)\n    if delete_on_close and os.name == "nt":\n        oflags |= getattr(os, "O_TEMPORARY", 0)\n    fd = os.open(p, oflags, 0o600)\n    with os.fdopen(fd, "r+b", buffering=0) as f:\n        reserved = False\n        if hasattr(os, "posix_fallocate"):\n            try:\n                os.posix_fallocate(f.fileno(), 0, size_val)     # space allocated immediately - no \'holes\' and no SIGBUS when the disk is full\n                reserved = True\n            except OSError:\n                pass\n        if not reserved:\n            f.truncate(size_val)                                 # NTFS/exFAT allocate space immediately\n        mm = np.memmap(f, dtype=np.uint8, mode="r+", shape=(size_val,))\n    if delete_on_close and os.name != "nt":\n        try:\n            os.unlink(p)\n        except OSError:\n            pass\n    return mm\n\n\ndef move_weights_to_file(fpath, reason="start"):\n    """Moves all weights (parameters and buffers) of the models from RAM to the swap file(s). Returns the number of bytes moved."""\n    import torch.nn as nn\n    delete_on_close = not cfg.get("swap_file_keep")\n    groups, skipped_count = {}, 0      # id(tensor) -> [tensor, [(dict, name, is_parameter)]]; shared weights stay shared\n    for m in _model_modules():\n        for mod in m.modules():\n            for dct, is_param in ((mod._parameters, True), (mod._buffers, False)):\n                for tensor_name, t in list(dct.items()):\n                    if t is None or t.device.type != "cpu" or t.numel() == 0:\n                        continue\n                    if type(t) not in (torch.Tensor, nn.Parameter) or t.layout != torch.strided or t.is_quantized:\n                        skipped_count += 1      # e.g. quantized weights (torchao) - they stay in RAM\n                        continue\n                    if _in_swap_file(t.data_ptr()) is not None:\n                        continue\n                    groups.setdefault(id(t), [t, []])[1].append((dct, tensor_name, is_param))\n    if not groups:\n        if reason == "start":\n            emit("[ACE] Swap file: found no weights on the CPU to move - skipping.")\n        return 0\n    align = lambda n: (n + _PAGE - 1) // _PAGE * _PAGE\n    p0 = _swap_path(fpath, SWAP["created"])\n    directory = os.path.dirname(p0)\n    os.makedirs(directory, exist_ok=True)\n    fs = _filesystem_type(directory)\n    limit = _LIMIT_FAT if fs.upper() in ("FAT", "FAT12", "FAT16", "FAT32", "VFAT", "MSDOS") else None\n    parts, current, size_val = [], [], 0\n    for g in groups.values():\n        nb = align(g[0].numel() * g[0].element_size())\n        if limit and nb > limit:\n            skipped_count += 1\n            continue\n        if limit and size_val + nb > limit and current:\n            parts.append((current, size_val))\n            current, size_val = [], 0\n        current.append(g)\n        size_val += nb\n    if current:\n        parts.append((current, size_val))\n    together = sum(r for _, r in parts)\n    free_space = shutil.disk_usage(directory).free\n    if free_space < together + 256 * 2 ** 20:\n        emit(f"[ACE] Swap file: not enough space on {directory} ({free_space / 2**30:.1f} GB free, {together / 2**30:.1f} GB needed) "\n             "- the weights stay in regular memory.")\n        return 0\n    committed_before = committed_memory_mb()[0]\n    ram_before = free_ram_mb()\n    emit(f"[ACE] Swap file ({reason}): moving {together / 2**30:.2f} GB of weights ({len(groups)} tensors) to {p0}"\n         + (f" and the following ones (total {len(parts)} files - filesystem {fs} has a 4 GB per file limit)" if len(parts) > 1 else "")\n         + (f" [filesystem: {fs}]" if fs and len(parts) == 1 else "") + " ...")\n    t0 = time.time()\n    done_bytes, next_pct, since_flush = 0, 10, 0\n    for part_groups, part_size in parts:\n        p = _swap_path(fpath, SWAP["created"])     # always a new name (the old file may still be waiting to be deleted)\n        mm = _open_mapped_file(p, part_size, delete_on_close)\n        SWAP["created"] += 1\n        base = torch.from_numpy(mm)\n        beginning = base.data_ptr()\n        SWAP["mappings"].append({"mm": mm, "file": p, "start": beginning, "end": beginning + part_size,\n                                     "bytes": part_size, "deleted": delete_on_close})\n        shift = 0\n        for g in part_groups:\n            t, slots = g\n            nb = t.numel() * t.element_size()\n            tview = base[shift:shift + nb].view(t.dtype).view(t.shape)\n            with torch.no_grad():\n                tview.copy_(t.detach())\n            new_param = None\n            for dct, tensor_name, is_param in slots:\n                if is_param:\n                    if new_param is None:\n                        new_param = nn.Parameter(tview, requires_grad=t.requires_grad)\n                    dct[tensor_name] = new_param\n                else:\n                    dct[tensor_name] = tview\n            g[0] = g[1] = None      # the original in RAM loses its last reference and is freed immediately\n            del t, slots, tview, new_param\n            shift += align(nb)\n            done_bytes += align(nb)\n            since_flush += nb\n            if since_flush >= 512 * 2 ** 20:\n                mm.flush()          # write to disk -> \'clean\' pages: the system can free them without the pagefile and read them back later\n                since_flush = 0\n            proc = done_bytes * 100 // together\n            if proc >= next_pct:\n                emit(f"[ACE] Swap file: {proc}% ({done_bytes / 2**30:.2f}/{together / 2**30:.2f} GB, "\n                     f"{done_bytes / 2**20 / max(time.time() - t0, 1e-3):.0f} MB/s)")\n                next_pct = (proc // 10 + 1) * 10\n        mm.flush()\n        del base\n    groups.clear()\n    gc.collect()\n    if sys.platform.startswith("linux"):\n        try:\n            import ctypes\n            ctypes.CDLL("libc.so.6").malloc_trim(0)     # glibc: give the memory freed after the weights back to the system immediately\n        except Exception:\n            pass\n    SWAP["transfers"] += 1\n    committed_after = committed_memory_mb()[0]\n    ram_after = free_ram_mb()\n    emit(f"[ACE] Swap file ready in {time.time() - t0:.0f} s: {together / 2**30:.2f} GB of weights now live in the file"\n         + (f"; system committed memory: {committed_before} -> {committed_after} MB" if committed_before and committed_after else "")\n         + (f"; free RAM: {ram_before} -> {ram_after} MB" if ram_before and ram_after else "")\n         + (" (the file will disappear by itself when work is done)" if delete_on_close else " (the file will remain on disk)"))\n    if skipped_count:\n        emit(f"[ACE] Swap file: {skipped_count} tensors stay in regular memory (unusual format, e.g. quantization).")\n    log("Weights swap file", reason=reason, file_list=[m_["file"] for m_ in SWAP["mappings"]], gb=round(together / 2**30, 3),\n        time_sec=round(time.time() - t0, 1), filesystem=fs, committed_before_mb=committed_before, committed_after_mb=committed_after,\n        free_ram_before_mb=ram_before, free_ram_after_mb=ram_after, skipped_tensors=skipped_count)\n    PREFETCH.prepare()\n    return together\n\n\nclass _Prefetcher:\n    """Weight prefetching: while layer N is being computed, we bring layers N+1 and N+2 from the swap file in the background\n    with large reads (Windows: PrefetchVirtualMemory, Linux: madvise WILLNEED) instead of thousands of small reads\n    on missing pages. When everything fits in RAM, it costs practically nothing."""\n    LOOKAHEAD = 2\n\n    def __init__(self):\n        self.task_queue = None\n        self.hooks = []\n        self.disabled_reason = None\n        self.requests_n = self.error_list = self.raw_bytes = 0\n        self._win = None\n\n    def _start(self):\n        if self.task_queue is not None:\n            return\n        import queue\n        if os.name == "nt":\n            import ctypes\n            from ctypes import wintypes\n\n            class RANGE_T(ctypes.Structure):\n                _fields_ = [("VirtualAddress", ctypes.c_void_p), ("NumberOfBytes", ctypes.c_size_t)]\n            k32 = ctypes.WinDLL("kernel32", use_last_error=True)\n            fn = k32.PrefetchVirtualMemory          # Windows 8 and newer\n            fn.argtypes = [wintypes.HANDLE, ctypes.c_size_t, ctypes.POINTER(RANGE_T), wintypes.ULONG]\n            fn.restype = wintypes.BOOL\n            k32.GetCurrentProcess.restype = wintypes.HANDLE\n            self._win = (ctypes, RANGE_T, fn, k32.GetCurrentProcess())\n        self.task_queue = queue.Queue(maxsize=4)\n        threading.Thread(target=self._loop, daemon=True, name="weight_prefetch").start()\n\n    def submit(self, ranges):\n        if self.disabled_reason is None and ranges and self.task_queue is not None:\n            try:\n                self.task_queue.put_nowait(ranges)\n            except Exception:\n                pass                # queue full (slow disk) - we skip, so as not to prefetch layers that are no longer current\n        return None                 # a forward_pre hook must not return anything (otherwise it would replace the layer\'s input)\n\n    def _loop(self):\n        while True:\n            ranges = self.task_queue.get()\n            try:\n                if self._win:\n                    ctypes, RANGE_T, fn, proc = self._win\n                    tab = (RANGE_T * len(ranges))(*[RANGE_T(a, b - a) for a, b in ranges])\n                    ok = bool(fn(proc, len(ranges), tab, 0))\n                else:\n                    import mmap as _mmap\n                    ok = True\n                    for a, b in ranges:\n                        mp = _in_swap_file(a)\n                        if mp is None:\n                            continue\n                        st = (a - mp["start"]) // _mmap.PAGESIZE * _mmap.PAGESIZE\n                        mp["mm"]._mmap.madvise(_mmap.MADV_WILLNEED, st, min(b, mp["end"]) - mp["start"] - st)\n                self.requests_n += 1\n                if ok:\n                    self.raw_bytes += sum(b - a for a, b in ranges)\n                else:\n                    self.error_list += 1         # with very little free memory the system may refuse - it is only a hint\n            except Exception as e:\n                self.disabled_reason = f"{type(e).__name__}: {e}"\n                emit(f"[ACE] Weight prefetching disabled ({self.disabled_reason}) - weights will be read back the regular way.")\n                return\n\n    @staticmethod\n    def _ranges(mod):\n        rngs = []\n        for t in list(mod.parameters()) + list(mod.buffers()):\n            n = t.numel() * t.element_size()\n            if n and t.device.type == "cpu" and _in_swap_file(t.data_ptr()) is not None:\n                rngs.append([t.data_ptr(), t.data_ptr() + n])\n        rngs.sort()\n        merged = []\n        for a, b in rngs:\n            if merged and a <= merged[-1][1] + _PAGE:\n                merged[-1][1] = max(merged[-1][1], b)\n            else:\n                merged.append([a, b])\n        return [tuple(z) for z in merged]\n\n    def prepare(self):\n        """Hooks on consecutive model blocks (lists of at least 4 layers of >= 8 MB each in the swap file)."""\n        import torch.nn as nn\n        for h in self.hooks:\n            h.remove()\n        self.hooks = []\n        lists = []\n        for m in _model_modules():\n            for sub in m.modules():\n                if isinstance(sub, nn.ModuleList) and len(sub) >= 4:\n                    children = list(sub)\n                    ranges = [self._ranges(d) for d in children]\n                    size_val = sum(b - a for z in ranges for a, b in z)\n                    if size_val >= 8 * 2 ** 20 * len(children):\n                        lists.append((size_val, children, ranges))\n        if not lists:\n            log("Prefetching: no layer lists to handle")\n            return\n        try:\n            self._start()\n        except Exception as e:\n            self.disabled_reason = f"{type(e).__name__}: {e}"\n            emit(f"[ACE] Weight prefetching unavailable ({self.disabled_reason}).")\n            return\n        largest = max(r for r, _, _ in lists)\n        for size_val, children, ranges in lists:\n            n = len(children)\n            for i, d in enumerate(children):\n                next_layers = [i + k for k in range(1, self.LOOKAHEAD + 1)]\n                if size_val == largest:\n                    next_layers = [j % n for j in next_layers]      # main model: after the last layer we go back to the first one (next diffusion step)\n                z = [zz for j in next_layers if j < n for zz in ranges[j]]\n                if z:\n                    self.hooks.append(d.register_forward_pre_hook(lambda mod, inp_, z=z: PREFETCH.submit(z)))\n        emit(f"[ACE] Weight prefetching: {sum(len(d) for _, d, _ in lists)} layers in {len(lists)} model blocks.")\n        log("Prefetching", blocks=[{"layers": len(d), "gb": round(r / 2**30, 3)} for r, d, _ in lists],\n            lookahead_layers=self.LOOKAHEAD)\n\n\nPREFETCH = _Prefetcher()\n\n\ndef check_mapping():\n    """After each generation: how many weights still lie in the swap file. If ACE-Step copied or reloaded part of the model,\n    the new weights go to the next file, and files the model no longer uses are released."""\n    if not SWAP["mappings"]:\n        return\n    in_file = outside = 0\n    in_use = set()\n    for m in _model_modules():\n        for t in list(m.parameters()) + list(m.buffers()):\n            if t.device.type != "cpu":\n                continue\n            nb = t.numel() * t.element_size()\n            mp = _in_swap_file(t.data_ptr())\n            if mp is not None:\n                in_file += nb\n                in_use.add(id(mp))\n            else:\n                outside += nb\n    for mp in SWAP["mappings"]:\n        if id(mp) not in in_use:\n            emit(f"[ACE] Swap file {mp[\'file\']} is no longer used by the model - releasing it.")\n    # (comparison by identity - the dicts contain numpy arrays, which must not be compared with the == operator)\n    SWAP["mappings"] = [mp for mp in SWAP["mappings"] if id(mp) in in_use]\n    gc.collect()\n    log("Swap file check", in_file_gb=round(in_file / 2**30, 3), outside_file_gb=round(outside / 2**30, 3),\n        file_list=len(SWAP["mappings"]), prefetch_requests=PREFETCH.requests_n,\n        prefetch_gb=round(PREFETCH.raw_bytes / 2**30, 2), prefetch_refusals=PREFETCH.error_list)\n    if outside > 256 * 2 ** 20:\n        if SWAP["transfers"] < 4:\n            emit(f"[ACE] {outside / 2**30:.2f} GB of weights are outside the swap file (ACE-Step copied or reloaded part of the model) - moving them.")\n            try:\n                move_weights_to_file(cfg["swap_file"], "top-up")\n            except Exception as e:\n                emit(f"[ACE] Swap file: top-up failed ({type(e).__name__}: {e}).")\n        else:\n            emit(f"[ACE] Warning: {outside / 2**30:.2f} GB of weights are outside the swap file again - ACE-Step copies the model on every "\n                 "generation, so the swap file helps only partially.")\n\n\ndef _weights_memory_report():\n    try:\n        together = in_file = 0\n        descriptions = []\n        for attr_name, obj in list(vars(dit).items()) + [("lm_" + k, v) for k, v in vars(llm).items()]:\n            if isinstance(obj, torch.nn.Module):\n                tens = list(obj.parameters()) + list(obj.buffers())\n                b = sum(t.numel() * t.element_size() for t in tens)\n                wp = sum(t.numel() * t.element_size() for t in tens if t.device.type == "cpu" and _in_swap_file(t.data_ptr()))\n                dtypes = sorted({str(t.dtype).replace("torch.", "") for t in obj.parameters()})\n                together += b\n                in_file += wp\n                descriptions.append(f"{attr_name} {b / 2**30:.2f} GB ({\'/\'.join(dtypes) or \'-\'})")\n        emit(f"[ACE] Model weights: {together / 2**30:.2f} GB -> " + (", ".join(descriptions) or "no modules found")\n             + (f"; in the swap file: {in_file / 2**30:.2f} GB, in regular memory: {(together - in_file) / 2**30:.2f} GB" if SWAP["mappings"] else ""))\n        emit(f"[ACE] Handler precision: {getattr(dit, \'dtype\', \'?\')}")\n    except Exception as e:\n        emit(f"[ACE] Could not compute the weights\' memory ({type(e).__name__}: {e})")\n\n\ndef enable_swap_file():\n    if not cfg.get("swap_file"):\n        return\n    if str(cfg.get("device")) != "cpu":\n        emit("[ACE] The swap file works only when computing on the CPU - with a GPU the weights are in the card\'s memory anyway. Skipping.")\n        return\n    try:\n        move_weights_to_file(cfg["swap_file"])\n    except Exception as e:\n        emit(f"[ACE] Swap file: failed ({type(e).__name__}: {e}) - the weights stay in regular memory.")\n\n\ndef install_hooks():\n    """Hooks on the model layers: every layer call -> input, output (shape, min/max/mean), time."""\n    if LOG_LEVEL == "basic":\n        return\n    import torch.nn as nn\n    mods = [(n, m) for n, m in vars(dit).items() if isinstance(m, nn.Module)]\n    for item_name, mod in mods:\n        params = sum(p.numel() for p in mod.parameters())\n        children = [(n, type(c).__name__, sum(p.numel() for p in c.parameters())) for n, c in mod.named_children()]\n        log(f"Model structure: {item_name} ({type(mod).__name__})", params=params, dtypes=sorted({str(p.dtype) for p in mod.parameters()}),\n            target_device=sorted({str(p.device) for p in mod.parameters()}), submodules=len(list(mod.modules())), children=children)\n    to_hook = []\n    for item_name, mod in mods:\n        if LOG_LEVEL == "full":\n            to_hook += [(f"{item_name}.{n}" if n else item_name, m) for n, m in mod.named_modules()]\n        else:\n            to_hook += [(item_name, mod)] + [(f"{item_name}.{n}", c) for n, c in mod.named_children()]\n    counters, times = {}, {}\n    main_model = max(to_hook, key=lambda nm: sum(p.numel() for p in nm[1].parameters()) if nm[0].count(".") == 1 else -1)[0]\n\n    def pre(item_name):\n        def h(mod, args, kwargs):\n            times[item_name] = time.perf_counter()\n            if item_name == main_model:\n                log(f"=== DIFFUSION STEP #{counters.get(item_name, 0) + 1} (call of {item_name}) ===", input_kwargs=describe_value(kwargs),\n                    input_args=describe_value(list(args)), free_ram_mb=free_ram_mb())\n        return h\n\n    def post(item_name):\n        def h(mod, args, kwargs, out):\n            counters[item_name] = counters.get(item_name, 0) + 1\n            dt = (time.perf_counter() - times.pop(item_name, time.perf_counter())) * 1000\n            data = {"module": item_name, "class": type(mod).__name__, "invocation": counters[item_name], "ms": round(dt, 2),\n                    "output": describe_value(out)}\n            if LOG_LEVEL == "full" or item_name.count(".") <= 1:\n                data["input"] = describe_value(list(args))\n                if kwargs:\n                    data["input_kwargs"] = describe_value(kwargs)\n            log(f"layer {item_name} #{counters[item_name]}: {dt:.1f} ms", **data)\n            if item_name == main_model and PROFILER["prof"] is not None:\n                PROFILER["prof"].step()\n        return h\n\n    for item_name, m in to_hook:\n        try:\n            m.register_forward_pre_hook(pre(item_name), with_kwargs=True)\n            m.register_forward_hook(post(item_name), with_kwargs=True)\n        except Exception as e:\n            log(f"Could not attach to {item_name}: {e}")\n    log(f"Attached hooks to {len(to_hook)} layers; diffusion step counted on: {main_model}", layers=[n for n, _ in to_hook][:400])\n\n\nPROFILER = {"prof": None}\n\n\ndef start_profiler():\n    """Full mode: the PyTorch profiler records EVERY operation (matmul, softmax, conv...) with shapes and time for a few steps."""\n    if LOG_LEVEL != "full" or int(cfg.get("profiler_steps") or 0) <= 0:\n        return None\n    try:\n        from torch.profiler import profile, schedule, ProfilerActivity\n        directory = cfg.get("log_dir") or "."\n\n        def ready(p):\n            marker = time.strftime("%Y%m%d_%H%M%S")\n            trace_path = os.path.join(directory, f"profiler_{marker}.json")\n            table_path = os.path.join(directory, f"profiler_{marker}_operations.txt")\n            try:\n                p.export_chrome_trace(trace_path)\n            except Exception as e:\n                trace_path = f"(not saved: {e})"\n            with open(table_path, "w", encoding="utf-8") as f:\n                f.write(p.key_averages(group_by_input_shape=True).table(sort_by="cpu_time_total", row_limit=400))\n            log("Profiler: saved all operations from the recorded steps", stats_table=table_path, chrome_trace=trace_path,\n                how_to_open="open the .json trace in https://ui.perfetto.dev or chrome://tracing")\n            emit(f"[ACE] Operation profiler saved: {table_path}")\n\n        prof = profile(activities=[ProfilerActivity.CPU], record_shapes=True, profile_memory=True, with_stack=False,\n                       schedule=schedule(wait=0, warmup=0, active=int(cfg["profiler_steps"]), repeat=1), on_trace_ready=ready)\n        prof.__enter__()\n        PROFILER["prof"] = prof\n        log(f"Operation profiler enabled for {cfg[\'profiler_steps\']} diffusion steps")\n        return prof\n    except Exception as e:\n        log(f"Profiler unavailable: {e}")\n        return None\n\n\ninstall_hooks()\nif cfg["use_lm"]:\n    try:\n        lkw, _ = filter_kwargs(llm.initialize, {"checkpoint_dir": os.path.join(cfg["directory"], "checkpoints"),\n                                          "lm_model_path": cfg["lm_model"], "backend": "pt", "device": cfg["device"]})\n        llm.initialize(**lkw)\n    except Exception as e:\n        emit(f"[ACE] Language model unavailable ({type(e).__name__}: {e}) - working without it.")\nenable_swap_file()\n_weights_memory_report()\nemit(f"[ACE] Model {cfg[\'model\']} ready after {time.time() - t0:.0f}s.")\nemit("@@READY")\n\nfor line in sys.stdin:\n    line = line.strip()\n    if not line:\n        continue\n    if line == "@@END":\n        break\n    try:\n        z = json.loads(line)\n        pkw = {"caption": z["caption"][:500], "lyrics": z["lyrics"], "instrumental": z["instrumental"],\n               "duration": float(z["duration"]), "inference_steps": int(z["steps"]), "seed": int(z["seed"]),\n               "bpm": z.get("bpm"), "keyscale": z.get("keyscale") or "", "reference_audio": z.get("reference_audio"),\n               "guidance_scale": z.get("guidance"),\n               "thinking": False, "use_cot_caption": False, "use_cot_metas": False, "use_cot_language": False}\n        for k_ in ("task_type", "src_audio", "audio_cover_strength", "cover_noise_strength", "repainting_start", "repainting_end"):\n            if z.get(k_) is not None:\n                pkw[k_] = z[k_]\n        pkw = {k: v for k, v in pkw.items() if v is not None}\n        pkw, skipped_kw = filter_kwargs(GenerationParams, pkw)\n        if skipped_kw:\n            emit(f"[ACE] GenerationParams - skipped: {skipped_kw}")\n        ckw, _ = filter_kwargs(GenerationConfig, {"batch_size": 1, "audio_format": "wav", "use_random_seed": int(z["seed"]) < 0})\n        try:\n            import dataclasses\n            gp, gc_ = GenerationParams(**pkw), GenerationConfig(**ckw)\n            log("Full generation parameters (with ACE-Step default values)",\n                params=dataclasses.asdict(gp) if dataclasses.is_dataclass(gp) else vars(gp),\n                configuration=dataclasses.asdict(gc_) if dataclasses.is_dataclass(gc_) else vars(gc_), skipped_count=skipped_kw)\n        except Exception as e:\n            log(f"Could not describe the parameters: {e}")\n        start_profiler()\n        tmp_folder = z["out"] + "_tmp"\n        os.makedirs(tmp_folder, exist_ok=True)\n        t0 = time.time()\n        outcome = generate_music(dit, llm, GenerationParams(**pkw), GenerationConfig(**ckw), save_dir=tmp_folder)\n        if PROFILER["prof"] is not None:\n            try:\n                PROFILER["prof"].__exit__(None, None, None)\n            except Exception:\n                pass\n            PROFILER["prof"] = None\n        check_mapping()\n        log(f"generate_music result after {time.time() - t0:.1f} s",\n            **{k: describe_value(v) for k, v in (vars(outcome).items() if hasattr(outcome, "__dict__") else [])})\n        if not getattr(outcome, "success", False):\n            emit(f"@@ERROR generate_music: {getattr(outcome, \'error\', \'?\')}")\n            continue\n        fpath = outcome.audios[0]["path"]\n        if os.path.exists(z["out"]):\n            os.remove(z["out"])\n        shutil.move(fpath, z["out"])\n        shutil.rmtree(tmp_folder, ignore_errors=True)\n        gc.collect()\n        emit("@@RESULT " + json.dumps({"out": z["out"], "time": round(time.time() - t0, 1)}))\n    except Exception as e:\n        emit(f"@@ERROR {type(e).__name__}: {e}")\nemit("[ACE] Process work finished.")\n'
_load_settings_from_menu()

# ---------- resource profile: how many cores and what priority generation gets ----------
_ACE_PRIORITY = "normal"

def _set_process_priority(prio):
    try:
        if os.name == "nt":
            import ctypes
            klass = {"low": 0x00004000, "high": 0x00000080}.get(prio)   # BELOW_NORMAL / HIGH_PRIORITY_CLASS
            if klass:
                ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), klass)
        elif prio == "low":
            os.nice(10)
    except Exception:
        pass

def _apply_resource_profile():
    global _ACE_PRIORITY, ACE_THREADS, _ollama_options
    cores = os.cpu_count() or 4
    if RESOURCE_PROFILE == "economical":
        ACE_THREADS, main_threads, ollama_threads, _ACE_PRIORITY = max(1, cores // 2), max(1, cores // 2), 1, "low"
    elif RESOURCE_PROFILE == "maximum":
        ACE_THREADS, main_threads, ollama_threads, _ACE_PRIORITY = cores, cores, cores, "high"
    else:
        return
    try:
        torch.set_num_threads(main_threads)
    except Exception:
        pass
    _ollama_options = lambda: {"num_ctx": 1024, "num_predict": 80, "num_thread": ollama_threads}  # noqa: E731
    _set_process_priority(_ACE_PRIORITY)
    print(f"[RESOURCES] Profile '{RESOURCE_PROFILE}': ACE-Step {ACE_THREADS} threads, analysis {main_threads}, Ollama {ollama_threads}, priority {_ACE_PRIORITY}")

_apply_resource_profile()

def _ace_python_path():
    if ACE_PYTHON_ENV:
        return Path(ACE_PYTHON_ENV)
    for p in (ACE_VENV_DIR / "Scripts" / "python.exe", ACE_VENV_DIR / "bin" / "python"):
        if p.exists():
            return p
    return ACE_VENV_DIR / "Scripts" / "python.exe"

def _ace_free_ram_mb():
    r = _ram_gb()
    return int(r[1] * 1024) if r else None

def _resample_linear(x, sr_from, sr_to):
    if int(sr_from) == int(sr_to):
        return x
    n = int(round(len(x) * sr_to / sr_from))
    t_new = np.linspace(0, len(x) - 1, n)
    if x.ndim == 1:
        return np.interp(t_new, np.arange(len(x)), x).astype(np.float32)
    return np.stack([np.interp(t_new, np.arange(len(x)), x[:, c]) for c in range(x.shape[1])], axis=1).astype(np.float32)

def _priority_flags():
    if os.name == "nt":
        klass = {"low": 0x00004000, "high": 0x00000080}.get(_ACE_PRIORITY)
        return {"creationflags": klass} if klass else {}
    return {}

def pytorch_device():
    """cpu -> 'cpu'; gpu / cpu+gpu -> 'auto-gpu' (the model process picks cuda / xpu / mps itself, and if none - CPU).
    Old values 'cuda', 'xpu', 'mps' pass through unchanged."""
    u = str(ACE_DEVICE).lower()
    if u in ("gpu", "cpu+gpu"):
        return "auto-gpu"
    return u if u in ("cpu", "cuda", "xpu", "mps") else "cpu"


def aux_device():
    """Device for Demucs (PRO versions) in the main process: GPU only when GPU was chosen and torch can see it."""
    if str(ACE_DEVICE).lower() == "cpu":
        return "cpu"
    try:
        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch, "xpu") and torch.xpu.is_available():
            return "xpu"
    except Exception:
        pass
    return "cpu"


class AceStepEngine:
    """Keeps one worker process with the model loaded. A failed job = process restart and another attempt."""
    def __init__(self):
        self.proc = None
        self.task_queue = queue.Queue()
        self._last_print = 0.0
        self._t_progress = 0.0
        self._prev_size = None
        atexit.register(self.stop)

    @staticmethod
    def _dir_size(p):
        total = 0
        try:
            for corr, _, file_list in os.walk(str(p)):
                for f in file_list:
                    try:
                        total += os.path.getsize(os.path.join(corr, f))
                    except OSError:
                        pass
        except Exception:
            pass
        return total

    def _download_progress(self):
        """Every ~5 s: how much was actually downloaded to disk (checkpoints + HuggingFace cache) and at what speed."""
        t = time.time()
        if t - self._t_progress < 5.0:
            return
        sz = sum(self._dir_size(p) for p in (ACE_DIR / "checkpoints", Path(os.environ.get("HF_HOME", CACHE_DIR))))
        if self._prev_size is not None and self._t_progress:
            increment = sz - self._prev_size
            if increment > 1 << 20:
                tempo = increment / (t - self._t_progress) / 2 ** 20
                print(f"[ACE] On disk with models: {sz / 2 ** 30:.2f} GB (downloading ~{tempo:.1f} MB/s)")
        self._t_progress, self._prev_size = t, sz

    def _check_environment(self):
        py = _ace_python_path()
        if not py.exists() or not (ACE_DIR / "acestep").is_dir():
            print("\n" + "!" * 70)
            print(" ACE-Step environment missing (Python 3.12 + repository).")
            print(f"   interpreter: {py}  ({'present' if py.exists() else 'MISSING'})")
            print(f"   repository: {ACE_DIR}  ({'present' if (ACE_DIR / 'acestep').is_dir() else 'MISSING'})")
            print(f" Run once:  python {Path(__file__).name} --install")
            print("!" * 70)
            raise SystemExit(1)
        return py

    def _reader(self, proc):
        try:
            for line in proc.stdout:
                self.task_queue.put(line.rstrip("\r\n"))
        except Exception:
            pass
        self.task_queue.put(None)  # EOF

    def _show(self, line):
        # messages of our worker process ("[ACE] ...") always; logs of ACE-Step itself (progress bars) - at most one line per ~2 s
        if line.startswith("[ACE]"):
            print(f"   {line[:300]}")
            return
        if time.time() - self._last_print > 2.0 and line.strip():
            self._last_print = time.time()
            print(f"   {line[:160]}")

    def _wait(self, pfx, timeout):
        end = time.time() + timeout
        while True:
            if pfx == "@@READY":
                self._download_progress()
            try:
                line = self.task_queue.get(timeout=max(0.5, min(5.0, end - time.time())))
            except queue.Empty:
                if time.time() > end:
                    raise TimeoutError(f"time limit exceeded ({timeout:.0f}s)")
                if self.proc is not None and self.proc.poll() is not None:
                    raise RuntimeError(f"the ACE-Step process ended (code {self.proc.returncode})")
                continue
            if line is None:
                log_line("ACE", "The model process ended unexpectedly", code=self.proc.poll() if self.proc else None, ram=_ram_gb())
                raise RuntimeError("the ACE-Step process ended unexpectedly (possibly out of RAM)")
            if line.startswith("@@LOG "):
                try:
                    d = json.loads(line[6:])
                    _write_log("[MODEL] " + str(d.pop("description", "")) + "".join(f"\n      {k} = {v}" for k, v in d.items()), d)
                except Exception:
                    _write_log("[MODEL] " + line[6:])
                continue
            _write_log("[ACE] " + line)
            if line.startswith("@@ERROR"):
                raise RuntimeError(line[7:])
            if line.startswith(pfx):
                return line[len(pfx):].strip()
            self._show(line)

    def start(self):
        py = self._check_environment()
        TEMP_DIR.mkdir(parents=True, exist_ok=True)
        script = TEMP_DIR / "_ace_worker.py"
        script.write_text(_ACE_WORKER_CODE, encoding="utf-8")
        cfg = {"directory": str(ACE_DIR), "model": ACE_MODEL_DIT, "threads": ACE_THREADS, "device": pytorch_device(),
               "offload": ACE_DEVICE == "cpu+gpu" or (ACE_CPU_OFFLOAD and ACE_DEVICE not in ("cpu", "gpu")), "quantization": ACE_QUANTIZATION, "use_lm": ACE_USE_LM,
               "lm_model": ACE_MODEL_LM, "ram_threshold_mb": 700, "bf16": ACE_BF16, "priority": _ACE_PRIORITY,
               "swap_file": str(ACE_SWAP_FILE) if ACE_SWAP_FILE else None, "swap_file_keep": bool(ACE_SWAP_FILE_KEEP),
               "log_level": ACE_LOG_LEVEL if _LOG["txt"] is not None else "basic",
               "log_dir": str(Path(_LOG["path"]).parent) if _LOG["path"] else str(TEMP_DIR),
               "profiler_steps": ACE_LOG_PROFILER_STEPS}
        log_line("ACE", "Model process configuration", **cfg)
        cfg_p = TEMP_DIR / "_ace_cfg.json"
        cfg_p.write_text(json.dumps(cfg), encoding="utf-8")
        ram = _ram_gb()
        if ram:
            print(f"[ACE] RAM: {ram[0]:.1f} GB ({ram[1]:.1f} GB free). Model {ACE_MODEL_DIT} on CPU needs a lot of RAM - close other programs.")
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", "HF_XET_HIGH_PERFORMANCE": "1",
               "HF_HUB_DOWNLOAD_TIMEOUT": "120", "HF_HUB_ETAG_TIMEOUT": "60",
               "ACESTEP_GENERATION_TIMEOUT": str(int(ACE_GENERATION_LIMIT_SEC))}
        try:   # fast model downloads: without hf_xet HuggingFace falls back to slow HTTP mode
            if subprocess.run([str(py), "-c", "import hf_xet"], capture_output=True, env=env).returncode != 0:
                print("[ACE] Installing hf_xet and hf_transfer (much faster model downloads)...")
                subprocess.run([str(py), "-m", "pip", "install", "--no-input", "hf_xet", "hf_transfer"], env=env)
        except Exception:
            pass
        print(f"[ACE] Starting the ACE-Step process ({py}). If the models are not on disk, they will be downloaded (size shown below)...")
        self.task_queue = queue.Queue()
        self.proc = subprocess.Popen([str(py), "-X", "utf8", "-u", str(script), str(cfg_p)], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                     errors="replace", bufsize=1, env=env, **_priority_flags())
        threading.Thread(target=self._reader, args=(self.proc,), daemon=True).start()
        self._wait("@@READY", ACE_START_TIMEOUT_SEC)
        print("[ACE] Model ready.")

    def stop(self):
        p, self.proc = self.proc, None
        if p is None:
            return
        try:
            if p.poll() is None:
                try:
                    p.stdin.write("@@END\n"); p.stdin.flush()
                    p.wait(timeout=15)
                except Exception:
                    pass
            if p.poll() is None:
                p.kill()
        except Exception:
            pass

    def _submit_job(self, job):
        log_line("ACE", "Job for the model", ram=_ram_gb(), **job)
        self.proc.stdin.write(json.dumps(job, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()
        return json.loads(self._wait("@@RESULT", ACE_SECTION_TIMEOUT_SEC))

    def generate(self, job):
        last = None
        for attempt in range(1, ACE_MAX_RETRIES + 1):
            try:
                if self.proc is None or self.proc.poll() is not None:
                    self.start()
                return self._submit_job(job)
            except SystemExit:
                raise
            except Exception as e:
                last = e
                print(f"\n[ACE] Attempt {attempt}/{ACE_MAX_RETRIES} failed: {type(e).__name__}: {e}")
                self.stop()
                gc.collect()
                if attempt < ACE_MAX_RETRIES:
                    print("[ACE] Restarting the process after a 10 s pause...")
                    time.sleep(10)
        raise RuntimeError(f"ACE-Step did not generate the section despite {ACE_MAX_RETRIES} attempts: {last}")

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


# ==============================================================================
# COVER: track fragments and splitting into passes
# ==============================================================================
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

def _ffmpeg_stereo(file, sr_target):
    """Android/Termux (no PyAV): any format -> stereo float32 [samples, 2] via the ffmpeg program."""
    tmp = TEMP_DIR / f"_temp_stereo_{os.getpid()}.wav"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(file), "-vn", "-acodec", "pcm_f32le", "-ar", str(int(sr_target)),
                    "-ac", "2", str(tmp)], check=True)
    try:
        x, _ = sf.read(str(tmp), dtype="float32", always_2d=True)
    finally:
        tmp.unlink(missing_ok=True)
    if x.shape[1] == 1:
        x = np.repeat(x, 2, axis=1)
    return x[:, :2].astype(np.float32)


def load_original_stereo(file, sr_target, reserve_mono, sr_mono):
    """Original in 48 kHz stereo (a better source for the cover than the 32 kHz mono from analysis)."""
    try:
        import av
        frame_list = []
        with av.open(str(file)) as cont:
            res = av.AudioResampler(format="fltp", layout="stereo", rate=int(sr_target))
            for fr in cont.decode(audio=0):
                for r in res.resample(fr):
                    frame_list.append(r.to_ndarray())
            for r in res.resample(None):
                frame_list.append(r.to_ndarray())
        x = np.concatenate(frame_list, axis=1).T.astype(np.float32)
        if x.ndim == 2 and x.shape[1] == 2 and len(x) > sr_target:
            return x
    except Exception as e:
        try:
            return _ffmpeg_stereo(file, sr_target)
        except Exception as e2:
            print(f"[ACE] Stereo original unavailable ({type(e).__name__}: {e}; ffmpeg: {e2}) - using the mono version.")
    m = _resample_linear(np.asarray(reserve_mono, dtype=np.float32), sr_mono, sr_target)
    return np.stack([m, m], axis=1)

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

def segment_cover(engine, orig_st, sr, a_sec, b_sec, n_passes, common, description):
    """Cover of fragment [a, b] of the original in n passes (overlaps + crossfade). Returns stereo of length b-a."""
    L = b_sec - a_sec
    n = max(1, min(int(n_passes), int(L // 10) or 1))      # each pass at least ~10 s
    if n < int(n_passes):
        print(f"[ACE] {description}: {n_passes} passes is too many for {L:.1f}s - using {n} (min. approx. 10 s per pass).")
    ln = L / n
    m = min(ACE_MARGIN_SEC, ln / 2) if n > 1 else 0.0
    xf = min(1.0, m)
    outcome = None
    for k in range(n):
        pa, pb = max(0.0, k * ln - m), min(L, (k + 1) * ln + m)
        src = orig_st[int((a_sec + pa) * sr):int((a_sec + pb) * sr)]
        p_src, p_out = TEMP_DIR / f"_temp_ace_src_{k:03d}.wav", TEMP_DIR / f"_temp_ace_cov_{k:03d}.wav"
        sf.write(str(p_src), np.clip(src, -1.0, 1.0), int(sr))
        z = dict(common, duration=max(10.0, pb - pa), out=str(p_out), task_type="cover", src_audio=str(p_src),
                 audio_cover_strength=float(ACE_COVER_STRENGTH), cover_noise_strength=float(ACE_COVER_NOISE))
        print(f"[ACE] {description}: pass {k + 1}/{n} ({_t(a_sec + pa)} - {_t(a_sec + pb)}), original strength {ACE_COVER_STRENGTH}")
        t0 = time.time()
        engine.generate(z)
        print(f"\n[ACE] {description}: pass {k + 1}/{n} done in {(time.time() - t0) / 60:.1f} min.")
        pt = load_stereo_48k(p_out, sr)
        n_parts = int((pb - pa) * sr)
        pt = pt[:n_parts] if len(pt) >= n_parts else np.concatenate([pt, np.zeros((n_parts - len(pt), 2), dtype=np.float32)])
        left = (k * ln - pa - xf / 2) if k > 0 else 0.0
        right = ((k + 1) * ln + xf / 2 - pa) if k < n - 1 else (pb - pa)
        log_line("COVER", f"{description}: pass {k + 1}/{n} - model output", segment_s=(a_sec + pa, a_sec + pb), segment_len=L,
              transition_len=ln, tab_m=m, crossfade_xf=xf, trim_left_s=left, trim_right_s=right,
              source=src, model_output=pt, rms_source=_rms(src), rms_result=_rms(pt))
        pt = pt[int(left * sr):int(right * sr)]
        outcome = pt if outcome is None else join_stereo_with_crossfade(outcome, pt, sr, crossfade_time_sec=xf)
        for p in (p_src, p_out):
            try:
                p.unlink()
            except Exception:
                pass
    n_target = int(L * sr)
    return outcome[:n_target] if len(outcome) >= n_target else np.concatenate([outcome, np.zeros((n_target - len(outcome), 2), dtype=np.float32)])

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


# ==============================================================================
# STYLE TEMPLATES: example tracks whose sound (timbre, mix, playing style) the result should adopt.
# ACE-Step takes 30 s from the reference audio (10 s each from the beginning, middle and end of the file) and averages them over time -
# it acts globally on timbre and mix, not on melody or structure (in a cover those come from the input track).
# That is why we assemble a reference file of exactly 30 s from the strongest fragments of the templates: the PyTorch engine will take
# the same 3 segments of 10 s 1:1, and the C++ engine (acestep.cpp) encodes the whole reference file, so also these 30 s.
# ==============================================================================
TEMPLATES_DIR = WORKSPACE_DIR / "templates"
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


def _load_stereo(file, sr_target):
    """Any audio format -> stereo float32 [samples, 2] at sr_target (PyAV; ffmpeg in mono as fallback)."""
    try:
        frame_list = []
        with av.open(str(file)) as cont:
            res = av.AudioResampler(format="fltp", layout="stereo", rate=int(sr_target))
            for fr in cont.decode(audio=0):
                for r in res.resample(fr):
                    frame_list.append(r.to_ndarray())
            try:
                for r in res.resample(None):
                    frame_list.append(r.to_ndarray())
            except Exception:
                pass
        x = np.concatenate(frame_list, axis=1).T.astype(np.float32)
        if x.ndim == 2 and x.shape[1] == 2 and len(x):
            return x
    except Exception:
        pass
    try:
        return _ffmpeg_stereo(file, sr_target)
    except Exception:
        pass
    m, _ = load_audio_via_av_or_ffmpeg(file, target_sr=sr_target)
    return np.stack([m, m], axis=1).astype(np.float32)


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
# C++ ENGINE (acestep.cpp): GGUF models (Q8/Q6/Q5/Q4), no PyTorch; CPU, Vulkan (incl. Intel UHD), CUDA
# ==============================================================================
class AceCppEngine:
    """Same interface as AceStepEngine: generate(job) -> wav file in job['out']."""
    item_name = "C++ (acestep.cpp, GGUF)"

    def __init__(self):
        self.proc = None
        atexit.register(self.stop)

    @staticmethod
    def available():
        folder = cpp_dir() / "models"
        return program_cpp("ace-synth") is not None and folder.exists() and any(folder.glob("acestep-v15-*.gguf"))

    def _check_environment(self):
        if program_cpp("ace-synth") is None:
            print("\n" + "!" * 70)
            print(" C++ engine (acestep.cpp) missing. Install it once:")
            print("   bash install_android.sh cpp   (compiles acestep.cpp on the phone, 10-20 minutes)")
            print(f"   or: python {Path(__file__).name} --install-cpp")
            print("!" * 70)
            raise SystemExit(1)
        if ACE_SWAP_FILE:
            print("[ACE-C++] The own swap file (ACE_SWAP_FILE) applies only to the PyTorch engine - the C++ engine keeps "
                  "the quantized model in RAM (the 2B Q8_0 model is approx. 2.4 GB, so it fits). Ignoring the setting.")
        self._model_dit()      # downloads the selected model if missing

    def _model_dit(self):
        file = gguf_dit_name(ACE_MODEL_DIT, ACE_GGUF_QUANT)
        folder = cpp_dir() / "models"
        if not (folder / file).exists():
            print(f"[ACE-C++] Model {file} missing - downloading (size shown below)...")
            if not download_gguf_models([file, "vae-BF16.gguf", "Qwen3-Embedding-0.6B-Q8_0.gguf"]):
                raise RuntimeError(f"could not download {file} - check the model/quantization name at huggingface.co/Serveurperso/ACE-Step-1.5-GGUF")
        return file

    def _model_lm(self):
        file = gguf_lm_name(ACE_CPP_LM, ACE_GGUF_QUANT)
        if file and not (cpp_dir() / "models" / file).exists():
            if not download_gguf_models([file]):
                print(f"[ACE-C++] Could not download {file} - generating without the language model.")
                return None
        return file

    @staticmethod
    def _device_flags():
        u = str(ACE_DEVICE).lower()
        if u == "cpu":
            return ["--device", "CPU"]
        if u in ("cuda", "vulkan"):
            return ["--device", "CUDA0" if u == "cuda" else "Vulkan0"]
        return []          # gpu / cpu+gpu: best available (CUDA > Vulkan > CPU); operations without GPU support run on the CPU

    def stop(self):
        p, self.proc = self.proc, None
        if p is not None and p.poll() is None:
            try:
                p.kill()
            except Exception:
                pass

    def _run(self, argv, description):
        log_line("ACE-C++", f"Starting {description}", command=argv)
        print(f"[ACE-C++] {description}: {' '.join(str(a) for a in argv[1:])[:300]}")
        env = {**os.environ}
        t0, last = time.time(), 0.0
        self.proc = subprocess.Popen([str(a) for a in argv], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                     encoding="utf-8", errors="replace", bufsize=1, env=env, cwd=str(cpp_dir()),
                                     **_priority_flags())
        tail = []
        for line in self.proc.stdout:
            line = line.rstrip("\r\n")
            if not line.strip():
                continue
            _write_log("[ACE-C++] " + line)
            tail = (tail + [line])[-25:]
            if "[Load]" in line or "FATAL" in line or "ERROR" in line or time.time() - last > 2.0:
                last = time.time()
                print(f"   {line[:170]}")
            if time.time() - t0 > ACE_GENERATION_LIMIT_SEC:
                self.stop()
                raise TimeoutError(f"time limit exceeded ({ACE_GENERATION_LIMIT_SEC}s)")
        rc = self.proc.wait() if self.proc else -1
        self.proc = None
        if rc != 0:
            raise RuntimeError(f"{description} exited with code {rc}: " + " | ".join(tail[-4:]))
        return time.time() - t0

    def _single_job(self, z):
        tmp_dir = Path(z["out"] + "_cpp")
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
                        "cover_noise_strength": float(ACE_COVER_NOISE)})
        models_dir = cpp_dir() / "models"
        fpath = tmp_dir / "request.json"
        fpath.write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")
        log_line("ACE-C++", "Request for acestep.cpp", **task)
        time_s = 0.0
        lm = None if cover else self._model_lm()
        if lm:                                       # the language model plans the structure (audio codes) - text mode only
            task_lm = dict(task, lm_model=lm)
            fpath.write_text(json.dumps(task_lm, ensure_ascii=False, indent=2), encoding="utf-8")
            time_s += self._run([program_cpp("ace-lm"), "--models", models_dir, "--request", fpath] + self._device_flags(),
                                  f"ace-lm ({lm})")
            new_items = sorted(tmp_dir.glob("request[0-9]*.json"))
            if new_items:
                fpath = new_items[0]
        argv = [program_cpp("ace-synth"), "--models", models_dir, "--request", fpath] + self._device_flags()
        if z.get("src_audio"):
            argv += ["--src-audio", z["src_audio"]]
        if z.get("reference_audio"):
            argv += ["--ref-audio", z["reference_audio"]]
        if ACE_LOG_LEVEL == "full" and _LOG["path"]:
            snapshot = Path(_LOG["path"]).parent / f"tensors_{datetime.now().strftime('%H%M%S')}"
            argv += ["--dump", snapshot]
            log_line("ACE-C++", "Dump of the model's intermediate tensors", directory=snapshot)
        time_s += self._run(argv, f"ace-synth ({task['synth_model']}, {ACE_DEVICE})")
        results = sorted(tmp_dir.glob(fpath.stem + "*.wav"), key=lambda p: p.stat().st_mtime)
        if not results:
            raise RuntimeError(f"ace-synth did not write a wav file in {tmp_dir}")
        if os.path.exists(z["out"]):
            os.remove(z["out"])
        shutil.move(str(results[-1]), z["out"])
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return {"out": z["out"], "time": round(time_s, 1)}

    def generate(self, job):
        log_line("ACE-C++", "Job for the model", ram=_ram_gb(), **job)
        last = None
        for attempt in range(1, ACE_MAX_RETRIES + 1):
            try:
                return self._single_job(job)
            except SystemExit:
                raise
            except Exception as e:
                last = e
                print(f"\n[ACE-C++] Attempt {attempt}/{ACE_MAX_RETRIES} failed: {type(e).__name__}: {e}")
                log_line("ACE-C++", "Attempt failed", attempt=attempt, error=f"{type(e).__name__}: {e}")
                self.stop()
                if attempt < ACE_MAX_RETRIES:
                    time.sleep(5)
        raise RuntimeError(f"acestep.cpp did not generate audio despite {ACE_MAX_RETRIES} attempts: {last}")


def choose_engine():
    """ACE_ENGINE: 'cpp' | 'pytorch' | 'auto' (C++ when installed - lighter and faster on CPU, otherwise PyTorch)."""
    s = str(ACE_ENGINE).lower()
    if s == "cpp" or (s == "auto" and AceCppEngine.available()):
        engine = AceCppEngine()
    else:
        engine = AceStepEngine()
    print(f"[ACE] Engine: {getattr(engine, 'item_name', 'PyTorch (ACE-Step 1.5)')}, model {ACE_MODEL_DIT}"
          + (f" {ACE_GGUF_QUANT}" if isinstance(engine, AceCppEngine) else "") + f", device: {ACE_DEVICE}")
    log_line("ACE", "Selected engine", engine=type(engine).__name__, model=ACE_MODEL_DIT, quantization=ACE_GGUF_QUANT,
          target_device=ACE_DEVICE, installed_cpp=AceCppEngine.available())
    return engine

def generate_coherent_composition():
    global NUM_SEGMENTS
    logs_start(OUTPUT_DIR / "logs")
    user_guidelines = get_prompt_from_user()
    input_files = find_audio_files()
    if not input_files:
        raise FileNotFoundError(f"No music files in '{INPUT_DIR}' or in '{WORKSPACE_DIR}'.")

    print(f"\n[INFO] {MODE_DESCRIPTION}")
    print(f"[INFO] Files found to process: {len(input_files)}")
    ollama_active = prepare_ollama()

    ram = _ram_gb()
    if ram:
        print(f"[INFO] RAM: {ram[0]:.1f} GB (free: {ram[1]:.1f} GB). Engine: ACE-Step {ACE_MODEL_DIT}, steps {ACE_STEPS}, device {ACE_DEVICE}")
        if ram[0] < 12:
            print("[WARNING] The 2B DiT model on CPU with this little RAM is borderline; close other programs. ACE_LOW_RAM=True (default) keeps Ollama and ACE-Step apart.")
    weights_dtype = f"ACE-Step {ACE_MODEL_DIT} ({ACE_DEVICE})"
    sampling_rate = ACE_SR
    engine = choose_engine()
    engine._check_environment()   # quick check (the model loads lazily at the first section)
    templates = prepare_style_templates()   # template tracks -> sound reference (None = none)

    for file_idx, input_file in enumerate(input_files, 1):
        clean_name = input_file.stem
        short_name = _safe_name(clean_name)
        session_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        print("\n" + "#" * 70)
        print(f" 💿 FILE [{file_idx}/{len(input_files)}]: {input_file.name}")
        print("#" * 70)

        print(f"[LOADING] Decoding {input_file.name}...", flush=True)
        _t_load = time.time()
        full_base_audio, sr = load_audio_via_av_or_ffmpeg(input_file, target_sr=32000)
        print(f"[LOADING] Done: {len(full_base_audio) / sr:.1f} s of audio in {time.time() - _t_load:.1f} s.")
        detected_bpm, detected_key = analyze_base_audio(full_base_audio, sr, input_file.name)
        analysis = analyze_input(full_base_audio, sr, detected_bpm, detected_key, input_file.name)

        beat_sec = 60.0 / detected_bpm
        num_beats = 32  # 8 full bars; at a slow tempo we shorten them so as not to exceed ~30 s
        while num_beats > 8 and num_beats * beat_sec + CROSSFADE_SEC > MAX_SEGMENT_LEN_SEC:
            num_beats //= 2
        segment_length_sec = beat_sec * num_beats
        base_length_sec = len(full_base_audio) / sr
        if ACE_MODE == "cover":
            _fr = cover_fragments(base_length_sec)
            if _fr and ACE_COVER_FRAGMENTS_MODE == "separate":
                _cov_len = sum(b_ - a_ for a_, b_ in _fr)
            elif ACE_COVER_WHOLE_FILE or _fr:
                _cov_len = min(base_length_sec, ACE_COVER_MAX_SEC or base_length_sec)
            else:
                _cov_len = None
            if _cov_len:
                NUM_SEGMENTS = max(1, int(np.ceil(_cov_len / segment_length_sec - 0.05)))
                print(f"[ACE] Cover: {_cov_len:.1f}s -> {NUM_SEGMENTS} sections of {segment_length_sec:.1f}s (for saving parts, MIDI and notation)")
        elif not ACE_WHOLE_TRACK and ACE_NUM_PASSES:
            NUM_SEGMENTS = max(1, int(ACE_NUM_PASSES))
            print(f"[ACE] Text mode in {NUM_SEGMENTS} passes (1 pass = 1 section)")

        session_name = f"{short_name}_{int(detected_bpm)}bpm_{session_ts}"
        directories = prepare_session_dirs(session_name)
        directories["stems"] = directories["root"] / "stems"
        root = directories["root"]
        manifest = {"final": [], "parts": [], "midi": [], "notation": [], "samples": [], "used_sounds": [], "stems": []}
        sections_meta = []
        print(f"[INFO] Output directory: {root}")
        if templates and EXPORT_USED_SOUNDS:
            _p_ref = save_template_references(templates, directories["used"] / "style_reference_from_templates.wav")
            manifest["used_sounds"].append(str(_p_ref.relative_to(root)).replace("\\", "/"))

        plan = plan_segments(analysis, NUM_SEGMENTS, segment_length_sec, num_beats, detected_bpm, base_length_sec)
        for i, p_ in enumerate(plan):
            if analysis and p_.get("source") != "cyclic":
                p_["window"] = window_character(analysis, p_["start_s"], segment_length_sec)
        if analysis:
            print("[PLAN] Choosing input fragments for sections (energy matched to the section's role):")
            for i, p_ in enumerate(plan, 1):
                print(f"   section {i}: start {p_['start_s']:.1f}s ({p_['source']}, rel. energy {p_.get('rel_energy', '-')})")
        profile_tags = analysis["profile"]["tags"] if analysis else None
        if templates and templates["tags"]:
            profile_tags = templates["tags"]      # target sound = sound of the templates (structure and tempo come from the input track)

        def tags_for(idx):
            tags = list(profile_tags or [])
            tags += plan[idx].get("window", {}).get("tags", [])
            return tags or None

        window_stems = None
        if STEM_SEPARATION:
            window_stems = prepare_window_stems(input_file, full_base_audio, sr, plan, segment_length_sec + CROSSFADE_SEC)

        def stem_data(i):
            return window_stems[i] if window_stems and i < len(window_stems) else None

        stem_midi, stem_percussion = {}, {}

        finished_track = None
        finished_stereo = None
        whole_st = whole_mono = orig_st = total_len_samples = None
        grids_lead, grids_bass, grids_chords = [], [], []
        track_name = f"track_{SCRIPT_SUBDIR}_{session_name}"
        temp_path = directories["final"] / f"{track_name}_in_progress_mono.wav"

        def cut_base_segment(seg_idx, length_sec=None):
            length_sec = length_sec or segment_length_sec
            reserve = base_length_sec - length_sec
            if seg_idx < len(plan) and plan[seg_idx].get("source") != "cyclic":
                start_sec = min(max(0.0, plan[seg_idx]["start_s"]), max(0.0, reserve))
            else:
                start_sec = (seg_idx * segment_length_sec) % reserve if reserve > 1.0 else 0.0
            s_samp = int(start_sec * sr)
            return full_base_audio[s_samp:s_samp + int(length_sec * sr)]

        # Concurrent pipeline: the CPU analyzes notes and queries Ollama for segment N+1 while the main engine renders segment N
        with _background_executor() as cpu_worker:
            future_next = cpu_worker.submit(
                prepare_segment_data_stems,
                1, NUM_SEGMENTS, cut_base_segment(0), sr, detected_bpm, detected_key, user_guidelines, ollama_active, num_beats, tags_for(0), stem_data(0)
            )

            for idx in range(NUM_SEGMENTS):
                num = idx + 1
                label, prompt_text, notes_info = future_next.result()
                grids_lead.append(notes_info["lead_midi"])
                grids_bass.append(notes_info["bass_midi"])
                grids_chords.append(notes_info.get("chords_beat") or [""] * len(notes_info["bass_midi"]))
                for name_s, midi_s in (notes_info.get("stem_midi") or {}).items():
                    stem_midi.setdefault(name_s, {})[idx] = midi_s
                for note_s, hits_s in (notes_info.get("percussion") or {}).items():
                    stem_percussion.setdefault(note_s, {})[idx] = hits_s

                if num < NUM_SEGMENTS:
                    future_next = cpu_worker.submit(
                        prepare_segment_data_stems,
                        num + 1, NUM_SEGMENTS, cut_base_segment(idx + 1), sr, detected_bpm, detected_key, user_guidelines, ollama_active and not _ACE_WHOLE, num_beats, tags_for(idx + 1), stem_data(idx + 1)
                    )

                print("\n" + "=" * 70)
                print(f"[SECTION {num}/{NUM_SEGMENTS} - {label.upper()}] Rendering with model {SCRIPT_SUBDIR}...")
                print(f"[LEAD NOTES] {notes_info['lead_str']} | [BASS NOTES] {notes_info['bass_str']}")
                if notes_info.get("progression_str"):
                    print(f"[CHORDS] {notes_info['progression_str']}")
                print(f"[PROMPT] {prompt_text}")


                log_line("SECTION", f"Section {num}/{NUM_SEGMENTS}: {label}", prompt=prompt_text, notes=notes_info, section_length_s=segment_length_sec, beat_count=num_beats, bpm=detected_bpm, key_sig=detected_key, ram=_ram_gb())
                tokens_to_generate = None  # ACE-Step does not use MusicGen tokens
                target_time = segment_length_sec + CROSSFADE_SEC  # section + overlap for crossfade
                melody = None
                generation_time = 0.0
                if _ACE_WHOLE and whole_st is None:
                    # ---- one pass for the whole track: consistent sound, natural transitions, no fades between sections ----
                    total_sec = NUM_SEGMENTS * segment_length_sec + CROSSFADE_SEC
                    markers = {"intro": "[Intro]", "build_up": "[Build-Up]", "climax_drop": "[Drop]",
                                 "climax_variation": "[Drop 2]", "outro": "[Outro]"}
                    structure = "\n\n".join(markers.get(get_section_label_and_description(k + 1, NUM_SEGMENTS)[0], "[Verse]")
                                              for k in range(NUM_SEGMENTS))
                    intro_description = get_section_label_and_description(1, NUM_SEGMENTS)[1]
                    overall_description = "full track: atmospheric intro, build-up, main climax drop, variation and outro"
                    caption = prompt_text.replace(intro_description, overall_description) if intro_description in prompt_text else f"{prompt_text}, {overall_description}"
                    lyrics = structure if ACE_LYRICS.strip() == "[Instrumental]" else ACE_LYRICS
                    ref_path = None
                    if templates:
                        ref_path = save_template_references(templates, TEMP_DIR / "_temp_ace_ref_templates.wav")
                    elif ACE_USE_REFERENCE:
                        idx_ref = min(2, NUM_SEGMENTS - 1)          # the most energetic fragment of the plan (drop)
                        melody = cut_base_segment(idx_ref, length_sec=ACE_REFERENCE_LEN_SEC)
                        ref_path = TEMP_DIR / "_temp_ace_ref_whole.wav"
                        sf.write(str(ref_path), np.clip(np.asarray(melody, dtype=np.float32), -1.0, 1.0), int(sr))
                    out_path = TEMP_DIR / "_temp_ace_out_whole.wav"
                    job = {"caption": caption, "lyrics": lyrics, "instrumental": ACE_INSTRUMENTAL,
                                "duration": max(10.0, total_sec), "steps": ACE_STEPS, "guidance": ACE_GUIDANCE,
                                "seed": ACE_SEED if ACE_SEED >= 0 else -1,
                                "bpm": int(round(detected_bpm)), "keyscale": str(detected_key),
                                "reference_audio": str(ref_path) if ref_path else None, "out": str(out_path)}
                    src_path = None
                    t_start = time.time()
                    if ACE_MODE == "cover":
                        if orig_st is None:
                            orig_st = load_original_stereo(input_file, sampling_rate, full_base_audio, sr)
                        common = {k_: v_ for k_, v_ in job.items() if k_ not in ("duration", "out")}
                        common["lyrics"] = ACE_LYRICS                      # in a cover the structure comes from the original
                        if int(common["seed"]) < 0:
                            import random
                            common["seed"] = random.randint(0, 2 ** 31 - 1)       # the same seed in all passes
                        print(f"[ACE] Description: {caption}")
                        st = generate_cover(engine, input_file, orig_st, sampling_rate, base_length_sec, total_sec, NUM_SEGMENTS,
                                           common, directories["final"], track_name)
                        total_len_samples = len(st)
                    else:
                        print(f"[ACE] WHOLE TRACK MODE: generating {total_sec:.1f}s in one pass, steps {ACE_STEPS}, structure: {structure.replace(chr(10), ' ')}")
                        print(f"[ACE] Description: {caption}")
                        engine.generate(job)
                        st = load_stereo_48k(out_path, sampling_rate)
                    generation_time = time.time() - t_start
                    print(f"\n[ACE] Whole track done in {generation_time / 60:.1f} min.")
                    n_cal = int(total_sec * sampling_rate)
                    st = st[:n_cal] if len(st) >= n_cal else np.concatenate([st, np.zeros((n_cal - len(st), 2), dtype=np.float32)])
                    mono_cal = st.mean(axis=1).astype(np.float32)
                    log_line("WHOLE", "Whole-track result before normalization", stereo=st, mono=mono_cal, rms=_rms(mono_cal), len_s=len(st) / sampling_rate, generation_time_s=generation_time)
                    whole_st = match_rms_stereo(st, mono_cal)            # one normalization for the whole = even level across sections
                    whole_mono = match_rms(mono_cal, target_rms=0.18)
                    for _p in (out_path, ref_path, src_path):
                        try:
                            if _p is not None:
                                _p.unlink()
                        except Exception:
                            pass
                if _ACE_WHOLE:
                    a_ = int(idx * segment_length_sec * sampling_rate)
                    b_ = a_ + int(target_time * sampling_rate)
                    new_stereo = whole_st[a_:b_].copy()
                    new_part = whole_mono[a_:b_].copy()
                    if len(new_part) < b_ - a_:
                        missing_mod = b_ - a_ - len(new_part)
                        new_stereo = np.concatenate([new_stereo, np.zeros((missing_mod, 2), dtype=np.float32)])
                        new_part = np.concatenate([new_part, np.zeros(missing_mod, dtype=np.float32)])
                else:
                    ref_path = None
                    if templates:
                        ref_path = save_template_references(templates, TEMP_DIR / f"_temp_ace_ref_{num:03d}.wav")
                    elif ACE_USE_REFERENCE:
                        if ACE_REFERENCE_MODE == "previous" and finished_track is not None and len(finished_track) > 5 * sampling_rate:
                            ref_audio, ref_sr = finished_track[-int(ACE_REFERENCE_LEN_SEC * sampling_rate):], sampling_rate
                        else:
                            melody = cut_base_segment(idx, length_sec=min(ACE_REFERENCE_LEN_SEC, target_time))
                            ref_audio, ref_sr = melody, sr
                        ref_path = TEMP_DIR / f"_temp_ace_ref_{num:03d}.wav"
                        sf.write(str(ref_path), np.clip(np.asarray(ref_audio, dtype=np.float32), -1.0, 1.0), int(ref_sr))
                    out_path = TEMP_DIR / f"_temp_ace_out_{num:03d}.wav"
                    margin = max(0.0, ACE_MARGIN_SEC)
                    job = {"caption": prompt_text, "lyrics": ACE_LYRICS, "instrumental": ACE_INSTRUMENTAL,
                                "duration": max(10.0, target_time + 2 * margin), "steps": ACE_STEPS, "guidance": ACE_GUIDANCE,
                                "seed": (ACE_SEED + num) if ACE_SEED >= 0 else -1,
                                "bpm": int(round(detected_bpm)), "keyscale": str(detected_key),
                                "reference_audio": str(ref_path) if ref_path else None, "out": str(out_path)}
                    print(f"[ACE] Generating {job['duration']:.1f}s (taking the middle {target_time:.1f}s), steps {ACE_STEPS}, reference: {'yes' if ref_path else 'no'}...")
                    t_start = time.time()
                    engine.generate(job)
                    generation_time = time.time() - t_start
                    print()
                    new_stereo = load_stereo_48k(out_path, sampling_rate)
                    a_ = int(margin * sampling_rate)
                    n_needed = int(target_time * sampling_rate)
                    if len(new_stereo) < a_ + n_needed:          # the model returned less - take from the beginning
                        a_ = max(0, len(new_stereo) - n_needed)
                    new_stereo = new_stereo[a_:a_ + n_needed]
                    if len(new_stereo) < n_needed:
                        new_stereo = np.concatenate([new_stereo, np.zeros((n_needed - len(new_stereo), 2), dtype=np.float32)])
                    new_part = new_stereo.mean(axis=1).astype(np.float32)
                    new_stereo = match_rms_stereo(new_stereo, new_part)
                    new_part = match_rms(new_part, target_rms=0.18)
                    for _p in (out_path, ref_path):
                        try:
                            if _p is not None:
                                _p.unlink()
                        except Exception:
                            pass

                # --- section outputs: part, used sounds, samples ---
                part_name = f"{short_name}_part_{num:03d}_{label}"
                save_audio_versions_ace(directories["parts"], part_name, new_part, new_stereo, sampling_rate, manifest["parts"], root)
                if EXPORT_USED_SOUNDS:
                    save_audio_versions(directories["used"], f"analysis_slice_{num:03d}_{label}", cut_base_segment(idx), sr, manifest["used_sounds"], root)
                    if melody is not None:
                        save_audio_versions(directories["used"], f"input_melody_{num:03d}_{label}", melody, sr, manifest["used_sounds"], root)
                if EXPORT_SAMPLES:
                    export_loops(directories["samples"], f"sample_{num:03d}_{label}", new_part, sampling_rate, detected_bpm, num_beats, manifest["samples"], root)
                if EXPORT_STEMS and stem_data(idx) is not None:
                    save_section_stems(directories["stems"], num, label, stem_data(idx), sr, manifest["stems"], root)

                finished_track = join_bar_aligned_with_crossfade(finished_track, new_part, sampling_rate, crossfade_time_sec=CROSSFADE_SEC)
                finished_stereo = join_stereo_with_crossfade(finished_stereo, new_stereo, sampling_rate, crossfade_time_sec=CROSSFADE_SEC)
                if _ACE_WHOLE:   # one recording - no stitching, simply the next piece of the whole
                    _end = int(((idx + 1) * segment_length_sec + CROSSFADE_SEC) * sampling_rate)
                    finished_track = whole_mono[:_end].copy()
                    finished_stereo = whole_st[:_end].copy()
                sf.write(str(temp_path), np.clip(finished_track, -1.0, 1.0), sampling_rate, subtype=WAV_SUBTYPE)

                sections_meta.append({
                    "num": num, "label": label, "prompt": prompt_text,
                    "notes_lead": notes_info["lead_str"], "notes_bass": notes_info["bass_str"],
                    "chord_progression": notes_info.get("progression_str", ""),
                    "chords_per_beat": notes_info.get("chords_beat"),
                    "input_fragment_start_s": plan[idx]["start_s"] if idx < len(plan) else None,
                    "input_fragment": plan[idx].get("window") if idx < len(plan) else None,
                    "stems": stems_to_json(stem_data(idx)),
                    "tokens": tokens_to_generate, "generation_time_s": round(generation_time, 1),
                })
                print(f"[SAVED] section {num}/{NUM_SEGMENTS} (Total: {len(finished_track)/sampling_rate:.1f}s) -> {root}")

                del new_part, new_stereo, melody
                gc.collect()
                if str(MAIN_DEVICE) == "xpu":
                    torch.xpu.empty_cache()

        # The crossfade overlap remains at the end - we trim to full bars and do a short fade-out
        target_length = int(NUM_SEGMENTS * segment_length_sec * sampling_rate)
        if total_len_samples:
            target_length = min(target_length, int(total_len_samples))
        finished_track = finished_track[:target_length].copy()
        n_fade = min(len(finished_track), int(0.25 * sampling_rate))
        if n_fade > 0:
            finished_track[-n_fade:] *= np.linspace(1.0, 0.0, n_fade, dtype=np.float32)
        finished_stereo = finished_stereo[:target_length].copy()
        if n_fade > 0:
            finished_stereo[-n_fade:] *= np.linspace(1.0, 0.0, n_fade, dtype=np.float32)[:, None]

        # --- final: mono / stereo / surround ---
        save_audio_versions_ace(directories["final"], track_name, finished_track, finished_stereo, sampling_rate, manifest["final"], root)
        try:
            temp_path.unlink()
        except Exception:
            pass
        if EXPORT_SAMPLES:
            export_band_stems(directories["samples"], f"{track_name}", finished_track, sampling_rate, manifest["samples"], root)

        # --- MIDI and notation ---
        midi_path = directories["midi"] / f"notes_{SCRIPT_SUBDIR}_{session_name}.mid"
        save_native_midi(midi_path, grids_lead, grids_bass, detected_bpm)
        manifest["midi"].append(str(midi_path.relative_to(root)).replace("\\", "/"))
        if stem_midi or stem_percussion:
            try:
                mid_paths = [(n, MIDI_PROGRAMS.get(n, 81), [m.get(i, [0] * num_beats) for i in range(NUM_SEGMENTS)])
                               for n, m in stem_midi.items()]
                perc = {k: [m.get(i, [0] * (num_beats * 4)) for i in range(NUM_SEGMENTS)] for k, m in stem_percussion.items()}
                mid_st_path = directories["midi"] / f"stems_{SCRIPT_SUBDIR}_{session_name}.mid"
                save_multitrack_midi(mid_st_path, detected_bpm, mid_paths, perc)
                manifest["midi"].append(str(mid_st_path.relative_to(root)).replace("\\", "/"))
            except Exception as e:
                print(f"[MIDI] Could not save the multitrack MIDI ({type(e).__name__}: {e})")
        if EXPORT_NOTATION:
            save_notes(directories["notation"], f"notes_{SCRIPT_SUBDIR}_{session_name}", clean_name, detected_bpm, detected_key,
                        grids_lead, grids_bass, manifest["notation"], root, grids_chords)

        # --- metadata ---
        meta = {
            "script": SCRIPT_SUBDIR,
            "input_file": str(input_file),
            "model": MODEL_ID,
            "mode": MODE_DESCRIPTION,
            "weights_type": str(weights_dtype),
            "engine": "ACE-Step 1.5", "ace_model": ACE_MODEL_DIT, "ace_steps": ACE_STEPS, "ace_reference": bool(ACE_USE_REFERENCE), "ace_reference_mode": ACE_REFERENCE_MODE, "ace_mode": ACE_MODE, "ace_cover_strength": ACE_COVER_STRENGTH, "ace_fragments": ACE_COVER_FRAGMENTS, "ace_fragments_mode": ACE_COVER_FRAGMENTS_MODE, "ace_passes": ACE_NUM_PASSES, "ace_whole_track": bool(_ACE_WHOLE),
            "bpm": detected_bpm,
            "key": detected_key,
            "sample_rate": int(sampling_rate),
            "beats_per_section": num_beats,
            "num_sections": NUM_SEGMENTS,
            "ace_guidance": ACE_GUIDANCE,
            "crossfade_s": CROSSFADE_SEC,
            "user_guidelines": user_guidelines,
            "channel_formats": list(CHANNEL_FORMATS),
            "surround_layout": "5.1, WAV channel order: FL, FR, FC, LFE, SL, SR (pseudo-upmix from mono)",
            "input_analysis": analysis_to_json(analysis),
            "stem_separation": {"enabled": bool(STEM_SEPARATION), "done": window_stems is not None, "model_demucs": MODEL_DEMUCS, "classifier": CLASSIFIER_MODEL if NEURAL_CLASSIFIER else None},
            "fragments_plan": plan,
            "style_templates": templates_description_to_json(templates),
            "sections": sections_meta,
            "files": manifest,
        }
        with open(root / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2, default=str)

        print("\n" + "=" * 70)
        print(f"[SUCCESS] Done ({SCRIPT_SUBDIR}): {root}")
        for key_id in ("final", "parts", "midi", "notation", "samples", "used_sounds", "stems"):
            if manifest[key_id]:
                print(f"   • {key_id:<12}: {len(manifest[key_id])} files")
        print("=" * 70)


if __name__ == "__main__" and "--prepare-ollama" in sys.argv:      # calls install.py
    sys.exit(0 if prepare_ollama() else 1)
if __name__ == "__main__":
    try:
        generate_coherent_composition()
    except KeyboardInterrupt:
        print("\n[PRZERWANO]")
    except Exception:
        traceback.print_exc()