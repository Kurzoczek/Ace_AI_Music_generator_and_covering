# AI Music Generator and Cover Maker - Android app

On-device music generation with **ACE-Step 1.5** (via [acestep.cpp](https://github.com/ServeurpersoCom/acestep.cpp), MIT)
for Android 10+ (arm64). It replaces the Termux scripts `generate_*_ace_android.py`, `menu_ace_android.py` and
`install_android.sh`: no Termux, no proot, no manual installation.

## Get the code

```bash
git clone --recurse-submodules <repository URL>
# already cloned without submodules:
git submodule update --init --recursive
```

The native engine [acestep.cpp](https://github.com/ServeurpersoCom/acestep.cpp) is a git submodule in
`app/src/main/cpp/acestep.cpp`, pinned to a tested commit. Model files are never stored in the repository - the app
downloads them at runtime after the user confirms.

## Build

Requirements: **JDK 17** (Gradle must run on Java 17; Java 8 fails with "This build uses a Java 8 JVM"),
Android Studio Ladybug or newer, Android SDK 35, NDK 27.2.12479018, CMake 3.22.1.

Building from the command line on Windows without Android Studio: point `JAVA_HOME` at a JDK 17 first, e.g. the one
bundled with Android Studio:

```powershell
$env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"
$env:Path = "$env:JAVA_HOME\bin;$env:Path"
java -version                    # must say 17 or newer
.\gradlew.bat assembleDebug
```

The Android SDK location goes into `local.properties` (`sdk.dir=C\:\\Users\\<you>\\AppData\\Local\\Android\\Sdk`)
or the `ANDROID_HOME` environment variable.

```bash
./gradlew assembleDebug          # app/build/outputs/apk/debug/app-debug.apk
```

The engine is built for ARMv8.2 with dot-product and fp16 instructions (`aceArmArch=armv8.2-a+dotprod+fp16` in
`gradle.properties`): phones from about 2018-2019 on (Cortex-A55/A75 and newer cores). Very old phones with only
Cortex-A53/A73 cores are not supported by this build; set `aceArmArch=armv8-a` if you ever need them.

If Chaquopy reports that no `numpy` wheel matches Python 3.12, set `version = "3.11"` in the `chaquopy` block of
`app/build.gradle.kts` (the Python code runs on 3.11 and 3.12).

## GitHub Actions

`.github/workflows/android.yml`:

* every push to `main` and every pull request: builds the debug APK (downloadable from the run's *Artifacts*) and
  checks that `app/src/main/python/ace_core.py` matches the desktop script;
* a tag `v*` (e.g. `git tag v1.0.0 && git push --tags`): builds a signed release APK and publishes a GitHub Release -
  only when these repository secrets exist (*Settings → Secrets and variables → Actions*):

| Secret | Value |
|---|---|
| `ACE_KEYSTORE_BASE64` | the keystore file in base64 (`base64 -w0 release.jks`, on Windows: `certutil -encode`) |
| `ACE_KEYSTORE_PASSWORD` | keystore password |
| `ACE_KEY_ALIAS` | key alias |
| `ACE_KEY_PASSWORD` | key password |

Create a keystore once with `keytool -genkeypair -v -keystore release.jks -keyalg RSA -keysize 4096 -validity 10000 -alias acemusicgen`
and keep it outside the repository (`*.jks` is in `.gitignore`). Dependabot checks Gradle, Actions and the submodule monthly.

## Updating the repository from a phone (ZIP import)

`.github/workflows/import-zip.yml`: upload a ZIP of the whole project (GitHub web -> Add file -> Upload files) to the
main folder of the repository or to `incoming/`. The workflow unpacks it over the repository (the ZIP may contain the
project directly or inside one folder such as `AceMusicGen/`), commits the changes, deletes the ZIP and builds the
APK in the same run (job "build" calls `android.yml`, so the build is listed under the import run). Skipped: `.git`, signing keys (`*.p12`, `*.jks`, `*.keystore`), the `acestep.cpp` submodule, build
folders, and `.github/workflows/` - GitHub does not let a workflow change workflow files, so changed workflow files
are listed as a warning and must be uploaded by hand. Files deleted from the project are not deleted from the
repository by an import.

## Updating an installed debug build

GitHub Actions signs debug APKs with a fixed key taken from two repository secrets (Settings -> Secrets and variables ->
Actions), so a newer APK installs over the old one and keeps all app data (settings, downloaded models):

| Secret | Value |
|---|---|
| `ACE_DEBUG_KEYSTORE_BASE64` | PKCS12 keystore (alias `acedebug`) encoded with `base64 -w0` |
| `ACE_DEBUG_KEYSTORE_PASSWORD` | its password (store and key) |

Create a key yourself with
`keytool -genkeypair -keystore ace-debug.p12 -storetype PKCS12 -alias acedebug -keyalg RSA -keysize 2048 -validity 10950`.
No key is stored in the repository. Without the secrets (local builds, Dependabot PRs) the machine's own debug key is
used and the APK will not install over a CI build. Keep a copy of the keystore: if it is lost, the next build cannot
update the installed app.

Builds made before this key was introduced must be uninstalled once; to keep the downloaded models:

```powershell
./adb pull /sdcard/Android/data/com.acemusicgen/files/models .      # save the models (a few GB) to the PC
./adb uninstall com.acemusicgen
./adb install app-debug.apk                                          # then open the app once
./adb push models /sdcard/Android/data/com.acemusicgen/files/        # models back, no new download
```

## Google Play

* `targetSdk` / `compileSdk` 36 (Android 16), as Google Play requires for new apps and updates.
* `versionCode` = GitHub run number + 100 in CI, so every uploaded build is higher than the previous one.
* Signed release tags (`v*`) also build an **AAB** (`app-release.aab`) - the format Google Play accepts - attached to
  the GitHub Release and to the workflow artifacts.
* **Report content** button on the results (Google Play AI-Generated Content policy). Set `aceReportEmail=` in
  `gradle.properties` to receive reports by e-mail; when empty, reports open a new GitHub issue in this repository
  (`aceReportUrl`).
* `PRIVACY.md` - privacy policy (EN + PL). Fill in the name and contact e-mail and publish it at a public URL
  (Google Play needs a public link; a private repository is not public).
* Play Console declarations: foreground service types `dataSync` (model download) and `mediaProcessing` (generation),
  each with a short screen recording of the flow; Data safety: no data collected or shared.

## License

The license of this project's own code is not chosen yet - add a `LICENSE` file before publishing. Third-party
components and their licenses: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Architecture

| Part | Where | What it does |
|---|---|---|
| UI | `ui/` (Jetpack Compose) | tracks / templates picker, mode and prompt, settings, models, log; EN + PL strings |
| Warning dialog | `ui/PreflightDialog.kt`, `data/Preflight.kt` | before anything starts: download size and source, storage, RAM need, overheating |
| Models | `data/ModelCatalog.kt`, `data/ModelDownloader.kt` | exact sizes + SHA-256 from the Hugging Face API, resumable HTTPS download, checksum verification |
| Memory | `data/MemoryPlanner.kt` | RAM estimate per model/quantization, calibrated from measured peaks; low-memory plan |
| Service | `engine/GenerationService.kt` | foreground service: decode → download → generate → save to Music/ and Download/ |
| CPU / heat | `engine/ResourceGovernor.kt` | thread count, core selection, low priority, CPU % duty cycle (SIGSTOP/SIGCONT), thermal pause |
| Analysis | `app/src/main/python/` (Chaquopy) | the scripts' tempo/key/chords/structure analysis, notation, MIDI, cover logic |
| Engine | `app/src/main/cpp/` | acestep.cpp `ace-synth` / `ace-lm` built with the NDK, packaged as `lib*.so`, run as separate processes |

`app/src/main/python/ace_core.py` is generated from the desktop script:

```bash
python tools/build_ace_core.py tools/generate_small_pro_ace_android.py app/src/main/python/ace_core.py
```

It keeps the analysis/export code and drops what cannot run in an app (installers, PyTorch, Ollama, Demucs, AST);
Android replacements are in `tools/ace_core_android.py`. `ace_android.py` is the entry point called from Kotlin.

## Data that is downloaded

Only GGUF model files, only after the user confirms the warning dialog, only from
`https://huggingface.co/Serveurperso/ACE-Step-1.5-GGUF` (HTTPS, Hugging Face redirects to its download CDN).
Typical sizes: music model 1.45 GB (2B Q4_K_M) - 9.3 GB (XL BF16), text encoder 0.78 GB, VAE 0.34 GB,
optional language model 0.7 - 4.2 GB. The dialog shows the exact sizes read from the server before downloading.
No executable code is ever downloaded - the engine is inside the APK.

## Android security model

* **Files**: input tracks and templates are opened with the system picker (Storage Access Framework); results are
  written through MediaStore (default) or into folders the user picked with the system folder picker. No storage
  permission at all.
* **Network**: `INTERNET` + `ACCESS_NETWORK_STATE`; HTTPS only, system CAs only (`network_security_config.xml`);
  warning on metered networks and an optional "Wi-Fi only" switch; SHA-256 check of every model file.
* **Notifications**: `POST_NOTIFICATIONS` requested at runtime on Android 13+ (optional).
* **Background work**: foreground service (`dataSync` for downloads, `mediaProcessing` on Android 15+), partial wake
  lock only while generating; the Android 15 service time limit is handled (`onTimeout`) - progress is checkpointed.
* **Native code**: executed only from `nativeLibraryDir` (W^X compliant), 16 KB page aligned.
* **Components**: only the launcher activity is exported; the service is private.
* **Backup**: only settings; models, checkpoints and results are excluded.

## Where the results are saved

Every track gets its own folder `<track>_<BPM>bpm_<date>_<time>`. Defaults (Settings → Save locations shows them too):

| Files | Default location |
|---|---|
| final track | `Music/ACE_music_gen/<track>/final/` |
| sections, loops/samples, stems, used input slices | `Music/ACE_music_gen/<track>/parts/`, `samples/`, `stems/`, `used_sounds/` |
| MIDI | `Download/ACE_music_gen/<track>/midi/` |
| notation (MusicXML, LilyPond, text) | `Download/ACE_music_gen/<track>/notation/` |
| metadata.json | `Download/ACE_music_gen/<track>/` |

Each of these 8 kinds of files can be sent to a folder of your choice (system folder picker, permission kept until
you reset it); the files then go to `<your folder>/<track>/`. If the folder is no longer accessible, the default
location is used and the log says so. Temporary files, checkpoints and logs stay in app-private storage.

## Memory and processor settings

* **RAM limit**: "Automatic" (phone RAM minus a reserve for Android) or any value from 0.5 GB up to the phone's RAM -
  there is no other cap. If the limit is below what the model needs, the app does not stop: it splits the work into
  shorter passes, lowers the thread count, drops the language model, and when Android still kills the engine for lack
  of memory it waits for free memory and continues from the last finished pass (checkpoints on disk).
* **Processor**: thread count, core type (all / efficiency / performance), maximum CPU use in % (duty cycle), low
  process priority, and overheating protection (pause at moderate / severe / critical thermal status, resume after cooling).
* **Process priority** (like the Windows Task Manager levels), applied to the engine processes as a Linux nice value:

  | Level | nice | Effect |
  |---|---|---|
  | Low | 19 | runs only when the phone is idle |
  | Below normal (default) | 10 | other apps first, phone stays smooth |
  | Normal | 0 | same as other apps |
  | Above normal | -5 | engine first |
  | High | -10 | engine first, phone may get sluggish |
  | Realtime | -20 | highest level Android allows an app; true real-time scheduling (SCHED_FIFO) is system-only |

  Raising above normal is allowed on most phones; if the system refuses, the engine runs at normal and the Log says so
  (`[PRIORITY] nice requested -10, active 0`).

## Language

The UI is in English and Polish (`res/values`, `res/values-pl`). Settings -> **Language**: phone language (default),
English or Polski. On Android 13+ this is the system per-app language (also in the phone's Settings > Apps > Language,
declared in `res/xml/locales_config.xml`); on Android 10-12 the app applies it itself. Engine log lines stay in English.

## Where the models are stored

Models tab -> **Where models are stored**: internal app storage, phone storage app folder (default,
`Android/data/com.acemusicgen/files/models`) or the app folder on an SD card. The native engine opens the models as
plain files, and those are the only folders an app can use that way without the "all files access" permission (which
Google Play restricts), so arbitrary folders are not offered. Switching asks whether to move the downloaded models
(with progress, cancel and a free-space check; an interrupted move never loses a file). **Import .gguf files** copies
models you already have (e.g. downloaded on a computer) into the model folder, verified against the official size and
SHA-256 when known. Models in app folders are removed when the app is uninstalled.
