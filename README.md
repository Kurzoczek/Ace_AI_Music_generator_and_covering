<div align="center">

# 🎵 AI Music Generator and Cover Maker 🎸

**A whole AI music studio in your pocket. No cloud, no subscription, no Termux black magic.** 🪄

[![Android build](https://github.com/Kurzoczek/Ace_AI_Music_generator_and_covering/actions/workflows/android.yml/badge.svg)](https://github.com/Kurzoczek/Ace_AI_Music_generator_and_covering/actions/workflows/android.yml)
![Android 10+](https://img.shields.io/badge/Android-10%2B-3DDC84?logo=android&logoColor=white)
![arm64](https://img.shields.io/badge/CPU-arm64%20ARMv8.2-blue)
![Offline](https://img.shields.io/badge/runs-100%25%20on%20your%20phone-purple)

🇬🇧 English · [🇵🇱 Polski](README.pl.md)

</div>

---

## 📦 Downloads

| What | Where | For whom |
|---|---|---|
| 📱 **APK (install on your phone)** | [**Releases → latest**](https://github.com/Kurzoczek/Ace_AI_Music_generator_and_covering/releases/latest) → `AceMusicGen-vX.Y.Z.apk` | normal humans 🙂 |
| 🧪 **Fresh test build** | [Actions](https://github.com/Kurzoczek/Ace_AI_Music_generator_and_covering/actions) → newest green run → *Artifacts* → `AceMusicGen-debug` | the impatient ones ⚡ |
| 🧑‍💻 **Source code** | `git clone --recurse-submodules https://github.com/Kurzoczek/Ace_AI_Music_generator_and_covering.git` | builders and tinkerers 🔧 |
| 🗜️ **Source as ZIP** | [main.zip](https://github.com/Kurzoczek/Ace_AI_Music_generator_and_covering/archive/refs/heads/main.zip) ⚠️ *without the engine submodule - see [Build](#-building-it-yourself)* | read-only browsing 👀 |

> 🔒 The repository is private for now, so these links work only for people who have access to it.
> 🏷️ No release yet? Somebody has to press **Actions → Release → Run workflow** first (see [Releases](#-making-a-release)).

---

## 🤔 What is this thing?

You give it a song 🎶 - it gives you **a new version of it**. Or you give it a sentence like *"sad accordion polka
about Monday mornings"* - and it composes **a brand-new track** 🪗😭.

Under the hood runs **[ACE-Step 1.5](https://huggingface.co/ACE-Step/Ace-Step1.5)**, a serious music-generating AI, through the
lightning-fast C++ engine **[acestep.cpp](https://github.com/ServeurpersoCom/acestep.cpp)** 🏎️. Everything happens
**on your phone**: your music never leaves the device. The only thing that ever travels over the internet is the AI
model itself, downloaded once (and only after you say "yes, I know it's big") 📥.

It is the grown-up version of the old Termux scripts (`generate_*_ace_android.py`, `menu_ace_android.py`,
`install_android.sh`): no Termux, no proot, no copy-pasting commands at 2 a.m. 🌙

---

## ✨ Features

### 🎤 Two creative modes

| Mode | What it does | Fun fact |
|---|---|---|
| 🔁 **Cover** | Takes your track and remakes it in a new style, keeping its soul (tempo, key, structure) | Your shower recording can finally become a symphony 🚿➡️🎻 |
| ✍️ **Text** | Writes a completely new track from a description (and optional lyrics) | Describe it, get it. Like ordering pizza, but it's music 🍕 |

* 🎛️ **Cover strength** - from "barely touched" to "who even is this?"
* ✂️ **Fragments** - remake only `0:30-1:15; 2:00-2:45` and insert them back, or export them separately.
* 🎨 **Style templates** (optional) - give it a few tracks as "make it sound like this" references.
* 🎙️ **Instrumental or with lyrics** - your choice, your poetry.
* 🎲 **Seed** - same seed = same result, so you can reproduce that one lucky take 🍀.

### 🧠 Musical brain (analysis and export)

* 🥁 Detects **tempo, key, chords and song structure** (intro, verse, chorus... the usual suspects).
* 🎼 Exports **MIDI** and **notation** (MusicXML, LilyPond, plain text) - for when you want to pretend you wrote it 😎
* 🧩 Saves **sections, loops/samples, stems** and the **slices of your input** that were used.
* 🔊 Output in **mono, stereo and even surround** - for your 5.1 kitchen speaker setup.
* 🔬 **PRO analysis** - separates harmonic and percussive parts right on the phone (slower, but smarter).

### 🤖 Models to pick from

* 🏃 **turbo** (fast, 8 steps), 🎯 **sft** and 🧱 **base** (32 steps, more careful) - each in a normal and an **XL** size.
* 🗜️ Quantization **Q4_K_M** (default, smallest RAM appetite) up to **BF16** (for phones with more RAM than sense).
* 💬 Optional **language model** (0.6B / 1.7B / 4B) that helps text mode understand what you meant.
* 📏 Exact sizes and SHA-256 checksums are read from the server - no "approximately 2-ish GB" guessing.

### 🛡️ Safety first: the "are you sure?" dialog

Before anything heavy starts, the app tells you honestly:

* 📥 **how much it will download and from where** (Hugging Face, HTTPS, exact size),
* 💾 **how much storage** the model will take and how much you have left,
* 🧮 **how much RAM** the chosen model needs,
* 🔥 that your phone **may get warm** - it is composing a symphony after all, not checking the weather.

### 🧮 Memory: smart even when there isn't much of it

* 🎚️ **RAM limit**: automatic, or any value you like - **no artificial 10 GB cap**.
* 🧩 Set it lower than the model needs? The app **does not give up** 💪: shorter passes, fewer threads, no language
  model, smaller decoding chunks... and if Android kills the engine anyway, it **waits for free memory and continues
  from the last checkpoint**. Stubborn like a cat at 5 a.m. 🐈

### 🔥 Processor and heat under control

* 🧵 **Threads** - automatic or manual.
* 🏋️ **Cores** - all, only the efficient ones 🐢, or only the fast ones 🐇.
* ⏱️ **Max CPU usage in %** - the engine works in short bursts with breaks, like a reasonable employee.
* 🌡️ **Overheating protection** - pauses when the phone gets hot and resumes after it cools down. No toasted pockets 🍞
* 🚦 **Process priority, Windows-style:**

| Level | Linux nice | In plain words |
|---|---|---|
| 🐢 Low | 19 | works only when the phone is bored |
| 🚶 Below normal *(default)* | 10 | other apps go first, phone stays smooth |
| 🚗 Normal | 0 | fair play |
| 🏎️ Above normal | -5 | music first, Instagram later |
| 🚀 High | -10 | the phone may get a bit sluggish |
| ☄️ Realtime | -20 | the highest level Android allows an app. True SCHED_FIFO is reserved for the system, and honestly, that's for the best 😅 |

> If the phone refuses a raised priority, the engine just runs at Normal and the **Log** says so:
> `[PRIORITY] nice requested -10, active 0`.

### 📁 You decide where things go

* 🗂️ **8 kinds of output** (final track, sections, samples, stems, used slices, MIDI, notation, metadata) - each can
  go to its own folder. Or press **"One folder for everything"** if you like order 🧹.
* 🧭 Defaults are always shown, so nothing gets lost in the depths of the file system.
* 🆘 Folder disappeared (SD card pulled out)? Files go to the default location instead - **no result is ever lost**.

### 🗄️ Where the models live

* 📍 Internal app storage 🔐, phone storage app folder *(default)* or the app folder on an **SD card** 💳.
* 🚚 **Move models** between them with a progress bar, cancel button and free-space check. An interrupted move never loses a file.
* 📥 **Import .gguf files** you already have (e.g. downloaded on a computer) - verified against the official size and checksum.

> 🤓 *Why not any folder?* The C++ engine reads models directly as files, and without the "access all files"
> permission (which Google Play almost never grants) Android allows that only in the app's own folders.

### 🩺 Diagnostics (for when something goes wrong)

* 📝 **Log files** (Settings → Diagnostics): everything from the Log tab with exact times, plus start/end and duration
  of every task and file, errors, system events (screen, charger, battery saver, doze, overheating, memory warnings,
  the app being ended), engine processes with their exit reason, and **every 10 minutes** temperatures, CPU speeds,
  memory and power state. Saved to `Download/ACE_music_gen/app logs` or a folder you pick.
* 🧯 **State dumps, Windows-style**: (none) / small / extended (≈ kernel dump) / complete (with Java heap `.hprof`) /
  automatic - written on crashes, unexpected ends, errors or pauses, plus a **Dump now** button. One ZIP per dump,
  in `Download/ACE_music_gen/state dumps` or your folder; keep 1 (overwrite) to 20.
* 🔁 **Nothing is lost when Android kills the app**: picked tracks are remembered, and an interrupted job shows a
  **Resume** card (with the reason Android gave) that continues from the last finished pass.

### 🌍 And the cherries on top 🍒

* 🇬🇧🇵🇱 **English and Polish UI**, switchable in Settings → Language (on Android 13+ also in the phone's app settings).
* 🚩 **Report content** button on every result - required by Google Play for AI generators, and just decent.
* 🔔 Progress notification, 📶 "Wi-Fi only" downloads, ⏯️ resumable downloads after a lost connection.
* 📜 **Log** tab for the curious and for bug reports.

---

## 📲 Installation

1. 📥 Download the newest **`AceMusicGen-vX.Y.Z.apk`** from [Releases](https://github.com/Kurzoczek/Ace_AI_Music_generator_and_covering/releases/latest).
2. 📂 Open it. Android will ask whether your browser / file manager may install apps - say **Allow** (just for this source).
3. ✅ **Install**, open, allow notifications (optional, but you'll want to know when your hit is ready 🔔).

**Requirements:** Android 10+ 🤖, a 64-bit ARM phone from roughly 2018-2019 or newer (ARMv8.2 with dot-product), a few
GB of free storage for the model 💾. How much RAM the chosen model needs is shown in the warning dialog before anything starts.

### 🔄 Updating

Just install the new APK over the old one - settings and downloaded models stay ✨.

> 😬 *"App not installed as package conflicts with an existing package"?* That version was signed with a different
> key (older test builds were signed with a random key). Uninstall once and install again. Want to keep the models
> (a few GB)? With `adb` on a computer:
>
> ```powershell
> ./adb pull /sdcard/Android/data/com.acemusicgen/files/models .     # 💾 models to the PC
> ./adb uninstall com.acemusicgen
> ./adb install AceMusicGen-vX.Y.Z.apk                                # then open the app once
> ./adb push models /sdcard/Android/data/com.acemusicgen/files/       # 🔙 models back, no new download
> ```
>
> Or use **Models → Import .gguf files** after reinstalling.

---

## 🎬 How to use it (in 60 seconds)

1. 🎵 **Generate** tab → **Add tracks** (any audio Android can play: mp3, opus, flac, wav, m4a...).
2. 🎨 *(optional)* **Add templates** - tracks whose style you like.
3. 🔁 Pick **Cover** or ✍️ **Text**, write a short description in English (e.g. *"anime-like opening, energetic"*).
4. ▶️ **Start** → read the warning dialog (yes, really 😉) → confirm.
5. ☕ Make a coffee. The first run downloads the model; the next ones go straight to generating.
6. 🎉 Results land in `Music/ACE_music_gen/` and `Download/ACE_music_gen/` (or wherever you told them to).

### 📂 Where the results go

Every track gets its own folder `<track>_<BPM>bpm_<date>_<time>`:

| Files | Default location |
|---|---|
| 🏆 final track | `Music/ACE_music_gen/<track>/final/` |
| 🧩 sections, 🔁 samples, 🎚️ stems, ✂️ used slices | `Music/ACE_music_gen/<track>/parts/`, `samples/`, `stems/`, `used_sounds/` |
| 🎹 MIDI | `Download/ACE_music_gen/<track>/midi/` |
| 🎼 notation (MusicXML, LilyPond, text) | `Download/ACE_music_gen/<track>/notation/` |
| 🗒️ metadata.json | `Download/ACE_music_gen/<track>/` |

---

## 🔨 Building it yourself

### 🧑‍💻 On a computer

You need: **JDK 17** ☕ (Java 8 will greet you with *"This build uses a Java 8 JVM"* 🙅), Android SDK **36**,
NDK **27.2.12479018**, CMake **3.22.1**. Android Studio installs the missing pieces itself.

```bash
git clone --recurse-submodules https://github.com/Kurzoczek/Ace_AI_Music_generator_and_covering.git
cd Ace_AI_Music_generator_and_covering
./gradlew assembleDebug        # 🎁 app/build/outputs/apk/debug/app-debug.apk
```

Already cloned without submodules? `git submodule update --init --recursive` 🩹

**Windows without Android Studio** (PowerShell):

```powershell
$env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"
$env:Path = "$env:JAVA_HOME\bin;$env:Path"
java -version                  # must say 17 or newer
.\gradlew.bat assembleDebug
```

The SDK location goes into `local.properties` (`sdk.dir=...`) or the `ANDROID_HOME` variable.

🧰 **Tuning knobs** in `gradle.properties`:

* `aceArmArch=armv8.2-a+dotprod+fp16` - fast engine for modern phones. Got a fossil 🦕 with only Cortex-A53/A73? Use `armv8-a`.
* `aceReportEmail=` - where "Report content" sends reports. Empty = a new GitHub issue in this repository.
* No `numpy` wheel for Python 3.12 in Chaquopy? Set `version = "3.11"` in the `chaquopy` block of `app/build.gradle.kts`.

### ☁️ In the cloud: GitHub Actions (no computer needed!)

| Workflow | When | What you get |
|---|---|---|
| 🧪 `android.yml` | every push to `main`, every pull request | debug APK in *Artifacts* + a check that the Python core matches the desktop script |
| 📦 `import-zip.yml` | you upload a project ZIP | unpacks, commits, deletes the ZIP and builds the APK - all in one run |
| 🏷️ `release.yml` | **Run workflow** with a version, or a `v*` tag | signed APK published as a GitHub Release |

### 📱 Updating the repository from a phone (ZIP import)

Coding on the bus? We've got you 🚌:

1. In the repository: **Add file → Upload files** → drop the project ZIP (main folder or `incoming/`) → **Commit changes**.
2. ☕ The **Import project ZIP** run unpacks it, commits, removes the ZIP and builds the APK (job *build*).
3. 📥 The APK is in that run's *Artifacts*.

Skipped on purpose: `.git`, signing keys (`*.p12`, `*.jks`, `*.keystore` - they belong in Secrets 🔐), the engine
submodule, build folders, and `.github/workflows/` (GitHub doesn't let a workflow edit workflows, so those are listed as
a warning to upload by hand). Files deleted from the project are not deleted from the repository by an import.

### 🚀 Making a release

**Actions → Release → Run workflow** → type a version, e.g. `1.1.1` → **Run workflow** → 🍿. You get a GitHub Release
`v1.1.1` with the APK.

📝 The release description is taken from [CHANGELOG.md](CHANGELOG.md): the section of that version, or **Unreleased**
when there is none yet (it then becomes the notes of whatever version you release). Every update ZIP comes with its
changes already written there.

### 🔐 Signing keys (repository Secrets)

*Settings → Secrets and variables → Actions*:

| Secret | What for |
|---|---|
| `ACE_DEBUG_KEYSTORE_BASE64`, `ACE_DEBUG_KEYSTORE_PASSWORD` | 🧪 fixed key for test builds and releases installed from GitHub, so updates keep your data (PKCS12, alias `acedebug`) |
| `ACE_KEYSTORE_BASE64`, `ACE_KEYSTORE_PASSWORD`, `ACE_KEY_ALIAS`, `ACE_KEY_PASSWORD` | 🏪 release key for Google Play (when present, releases use it instead of the debug key) |

Create a key: `keytool -genkeypair -keystore ace-debug.p12 -storetype PKCS12 -alias acedebug -keyalg RSA -keysize 2048 -validity 10950`,
then `base64 -w0 ace-debug.p12` → paste as the secret. 🗝️ **Keep a copy of the key file** - lose it and the next build
can't update the installed app. No key is ever stored in the repository.

`versionCode` in CI = minutes since 2026-01-01, so every build is "newer" than the previous one ⏫.

---

## 🔒 Privacy and security

* 🙈 **No account, no ads, no analytics, no own server.** Details: [PRIVACY.md](PRIVACY.md) (EN + PL).
* 📂 **Files**: opened only through the system picker, no storage permission at all. Results via MediaStore or folders you picked.
* 🌐 **Network**: HTTPS only, system certificates only, SHA-256 check of every model, optional "Wi-Fi only".
  No executable code is ever downloaded - the engine is inside the APK.
* 🔔 **Notifications**: asked at runtime on Android 13+, optional.
* ⚙️ **Background work**: foreground service (`dataSync` for downloads, `mediaProcessing` for generation on Android 15+),
  wake lock only while generating, the Android 15 time limit handled with checkpoints.
* 🧱 **Native code**: run only from `nativeLibraryDir` (W^X compliant), 16 KB page aligned.
* 💾 **Backup**: only settings - no multi-GB models in your Google Drive 😅.

## 🏪 Google Play readiness

* 🎯 `targetSdk` / `compileSdk` **36** (Android 16), as Google Play requires.
* 🚩 **Report content** button (AI-Generated Content policy).
* 📜 [PRIVACY.md](PRIVACY.md) - fill in the name and contact e-mail and publish it at a **public** URL.
* 📝 Play Console: declare foreground services `dataSync` and `mediaProcessing` (with a short screen recording each),
  Data safety: nothing collected or shared. New personal accounts also need a closed test (12 testers, 14 days) 🧑‍🤝‍🧑.

---

## 🏗️ Architecture (for the curious 🔍)

| Part | Where | What it does |
|---|---|---|
| 🖼️ UI | `ui/` (Jetpack Compose) | tracks/templates, mode and prompt, settings, models, log, report dialog; EN + PL |
| ⚠️ Warning dialog | `ui/PreflightDialog.kt`, `data/Preflight.kt` | download size and source, storage, RAM, heat - before anything starts |
| 🤖 Models | `data/ModelCatalog.kt`, `ModelDownloader.kt`, `ModelStorage.kt`, `ModelFiles.kt` | exact sizes + SHA-256, resumable HTTPS download, storage locations, move and import |
| 🧮 Memory | `data/MemoryPlanner.kt` | RAM estimate per model, calibrated from measured peaks; low-memory plan |
| ⚙️ Service | `engine/GenerationService.kt` | foreground service: decode → download → generate → save |
| 🌡️ CPU/heat | `engine/ResourceGovernor.kt` | threads, cores, priority, CPU % duty cycle (SIGSTOP/SIGCONT), thermal pause |
| 🐍 Analysis | `app/src/main/python/` (Chaquopy) | tempo/key/chords/structure, notation, MIDI, cover logic |
| 🏎️ Engine | `app/src/main/cpp/` | acestep.cpp `ace-synth` / `ace-lm` built with the NDK, run as separate processes |

`ace_core.py` is generated from the desktop script (the CI checks they stay in sync):

```bash
python tools/build_ace_core.py tools/generate_small_pro_ace_android.py app/src/main/python/ace_core.py
```

It keeps the analysis/export code and drops what can't run in an app (installers, PyTorch, Ollama, Demucs, AST);
Android replacements live in `tools/ace_core_android.py`.

### 📥 What gets downloaded

Only GGUF model files, only after you confirm, only from
[`huggingface.co/Serveurperso/ACE-Step-1.5-GGUF`](https://huggingface.co/Serveurperso/ACE-Step-1.5-GGUF).
Typical sizes: music model 1.45 GB (Q4_K_M) - 9.3 GB (XL BF16), text encoder 0.78 GB, VAE 0.34 GB, optional
language model 0.7 - 4.2 GB. The dialog shows the exact numbers before downloading.

---

## 🆘 Troubleshooting

| Symptom | Cure |
|---|---|
| 😵 *"This build uses a Java 8 JVM"* | set `JAVA_HOME` to JDK 17 (see [Build](#-building-it-yourself)) |
| 🚫 *"package conflicts with an existing package"* | different signing key - uninstall once (see [Updating](#-updating)) |
| 🔥 phone hot as a pancake pan | lower *Max CPU usage*, choose efficiency cores, keep overheating protection on |
| 🐌 very slow | turbo model, Q4_K_M, priority Normal or higher, performance cores |
| 💥 engine killed for lack of memory | nothing to do - the app waits and resumes from the checkpoint. Or pick a smaller model 😉 |
| 💳 *"The storage chosen for the models is not available"* | insert the SD card back or pick another location in **Models** |
| 🤷 something else | **Log** tab → copy → open an issue 🐛 |

---

## 📜 License and credits

* 🙏 **[ACE-Step](https://huggingface.co/ACE-Step/Ace-Step1.5)** - the music model. **[acestep.cpp](https://github.com/ServeurpersoCom/acestep.cpp)** (MIT) and **ggml** - the engine.
  Models from [Serveurperso/ACE-Step-1.5-GGUF](https://huggingface.co/Serveurperso/ACE-Step-1.5-GGUF). **[Chaquopy](https://chaquo.com/chaquopy/)** - Python on Android.
  Full list: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
* ⚖️ The license of this project's own code is not chosen yet - add a `LICENSE` file before publishing.
* 🎼 Cover responsibly: remake music you have the rights to. The app is a tool, not a lawyer 👩‍⚖️.

<div align="center">

Made with ☕, 🎧 and a slightly warm phone 🔥📱

</div>
