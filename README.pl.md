<div align="center">

# 🎵 AI Music Generator and Cover Maker 🎸

**Całe studio muzyczne AI w kieszeni. Bez chmury, bez abonamentu, bez czarnej magii w Termuksie.** 🪄

[![Android build](https://github.com/Kurzoczek/Ace_AI_Music_generator_and_covering/actions/workflows/android.yml/badge.svg)](https://github.com/Kurzoczek/Ace_AI_Music_generator_and_covering/actions/workflows/android.yml)
![Android 10+](https://img.shields.io/badge/Android-10%2B-3DDC84?logo=android&logoColor=white)
![arm64](https://img.shields.io/badge/CPU-arm64%20ARMv8.2-blue)
![Offline](https://img.shields.io/badge/działa-w%20100%25%20na%20telefonie-purple)

[🇬🇧 English](README.md) · 🇵🇱 Polski

</div>

---

## 📦 Do pobrania

| Co | Gdzie | Dla kogo |
|---|---|---|
| 📱 **APK (instalacja na telefonie)** | [**Releases → najnowsze**](https://github.com/Kurzoczek/Ace_AI_Music_generator_and_covering/releases/latest) → `AceMusicGen-vX.Y.Z.apk` | dla zwykłych ludzi 🙂 |
| 🏪 **AAB (paczka do Sklepu Play)** | to samo wydanie → `AceMusicGen-vX.Y.Z.aab` | dla przyszłej gwiazdy Sklepu Play 🦸 |
| 🧪 **Świeży build testowy** | [Actions](https://github.com/Kurzoczek/Ace_AI_Music_generator_and_covering/actions) → najnowszy zielony przebieg → *Artifacts* → `AceMusicGen-debug` | dla niecierpliwych ⚡ |
| 🧑‍💻 **Kod źródłowy** | `git clone --recurse-submodules https://github.com/Kurzoczek/Ace_AI_Music_generator_and_covering.git` | dla majsterkowiczów 🔧 |
| 🗜️ **Źródła jako ZIP** | [main.zip](https://github.com/Kurzoczek/Ace_AI_Music_generator_and_covering/archive/refs/heads/main.zip) ⚠️ *bez silnika (submodułu) - patrz [Budowanie](#-budowanie-samemu)* | do przeglądania 👀 |

> 🔒 Repozytorium jest na razie prywatne, więc linki działają tylko dla osób z dostępem.
> 🏷️ Nie ma jeszcze wydania? Ktoś musi najpierw kliknąć **Actions → Release → Run workflow** (patrz [Wydanie](#-robienie-wydania)).

---

## 🤔 Co to właściwie jest?

Dajesz piosenkę 🎶 - dostajesz **jej nową wersję**. Albo dajesz zdanie w stylu *„smutna polka na akordeonie
o poniedziałkowych porankach”* - i aplikacja komponuje **zupełnie nowy utwór** 🪗😭.

Pod maską pracuje **[ACE-Step 1.5](https://huggingface.co/ACE-Step/Ace-Step1.5)** - poważna AI do generowania muzyki -
przez błyskawiczny silnik C++ **[acestep.cpp](https://github.com/ServeurpersoCom/acestep.cpp)** 🏎️. Wszystko dzieje się
**na Twoim telefonie**: Twoja muzyka nigdzie nie wychodzi. Przez internet leci tylko sam model AI, pobierany raz
(i dopiero gdy powiesz „tak, wiem, że jest duży”) 📥.

To dorosła wersja dawnych skryptów do Termuksa (`generate_*_ace_android.py`, `menu_ace_android.py`,
`install_android.sh`): bez Termuksa, bez proota, bez wklejania komend o 2 w nocy 🌙

---

## ✨ Funkcje

### 🎤 Dwa tryby twórcze

| Tryb | Co robi | Ciekawostka |
|---|---|---|
| 🔁 **Cover** | Bierze Twój utwór i przerabia go w nowym stylu, zachowując duszę (tempo, tonację, strukturę) | Nagranie spod prysznica może w końcu zostać symfonią 🚿➡️🎻 |
| ✍️ **Tekst** | Tworzy zupełnie nowy utwór z opisu (i opcjonalnie tekstu piosenki) | Opisujesz, dostajesz. Jak zamawianie pizzy, tylko że to muzyka 🍕 |

* 🎛️ **Siła coveru** - od „ledwo dotknięte” do „a to w ogóle kto?”
* ✂️ **Fragmenty** - przerób tylko `0:30-1:15; 2:00-2:45` i wstaw z powrotem albo zapisz osobno.
* 🎨 **Wzorce stylu** (opcjonalnie) - kilka utworów w roli „ma brzmieć jak to”.
* 🎙️ **Instrumentalnie albo ze słowami** - Twój wybór, Twoja poezja.
* 🎲 **Seed** - ten sam seed = ten sam wynik, więc odtworzysz ten jeden szczęśliwy take 🍀.

### 🧠 Muzyczny mózg (analiza i eksport)

* 🥁 Rozpoznaje **tempo, tonację, akordy i strukturę** utworu (intro, zwrotka, refren... wiadomo).
* 🎼 Eksportuje **MIDI** i **nuty** (MusicXML, LilyPond, tekst) - gdy chcesz udawać, że to Ty napisałeś 😎
* 🧩 Zapisuje **sekcje, pętle/sample, stemy** i **wycinki Twojego nagrania**, które zostały użyte.
* 🔊 Wynik w **mono, stereo, a nawet surround** - dla Twojego kuchennego kina domowego 5.1.
* 🔬 **Analiza PRO** - rozdziela część harmoniczną i perkusyjną na telefonie (wolniej, ale mądrzej).

### 🤖 Modele do wyboru

* 🏃 **turbo** (szybki, 8 kroków), 🎯 **sft** i 🧱 **base** (32 kroki, staranniejsze) - każdy w zwykłym i **XL** rozmiarze.
* 🗜️ Kwantyzacja od **Q4_K_M** (domyślna, najmniejszy apetyt na RAM) do **BF16** (dla telefonów z większą ilością RAM niż rozsądku).
* 💬 Opcjonalny **model językowy** (0.6B / 1.7B / 4B), który pomaga trybowi tekstowemu zrozumieć, co miałeś na myśli.
* 📏 Dokładne rozmiary i sumy SHA-256 pobierane z serwera - żadnego „mniej więcej jakieś 2 GB”.

### 🛡️ Najpierw bezpieczeństwo: okno „na pewno?”

Zanim ruszy cokolwiek ciężkiego, aplikacja uczciwie mówi:

* 📥 **ile pobierze i skąd** (Hugging Face, HTTPS, dokładny rozmiar),
* 💾 **ile miejsca** zajmie model i ile Ci zostanie,
* 🧮 **ile RAM-u** potrzebuje wybrany model,
* 🔥 że telefon **może się nagrzać** - w końcu komponuje symfonię, a nie sprawdza pogodę.

### 🧮 Pamięć: sprytnie nawet wtedy, gdy jej mało

* 🎚️ **Limit RAM**: automatyczny albo dowolny - **żadnego sztucznego sufitu 10 GB**.
* 🧩 Ustawisz mniej, niż model potrzebuje? Aplikacja **się nie poddaje** 💪: krótsze przebiegi, mniej wątków, bez
  modelu językowego, mniejsze kawałki dekodowania... a jeśli Android i tak ubije silnik, **czeka na wolną pamięć
  i wznawia od ostatniego punktu kontrolnego**. Uparta jak kot o 5 rano 🐈

### 🔥 Procesor i temperatura pod kontrolą

* 🧵 **Wątki** - automatycznie albo ręcznie.
* 🏋️ **Rdzenie** - wszystkie, tylko energooszczędne 🐢 albo tylko wydajne 🐇.
* ⏱️ **Maks. użycie CPU w %** - silnik pracuje krótkimi zrywami z przerwami, jak rozsądny pracownik.
* 🌡️ **Ochrona przed przegrzaniem** - pauza, gdy telefon się grzeje, i wznowienie po ostygnięciu. Bez przypalonych kieszeni 🍞
* 🚦 **Priorytet procesu, jak w Windowsie:**

| Poziom | Linux nice | Po ludzku |
|---|---|---|
| 🐢 Niski | 19 | pracuje tylko, gdy telefon się nudzi |
| 🚶 Poniżej normalnego *(domyślnie)* | 10 | inne aplikacje mają pierwszeństwo, telefon pozostaje płynny |
| 🚗 Normalny | 0 | uczciwie po równo |
| 🏎️ Powyżej normalnego | -5 | najpierw muzyka, Instagram później |
| 🚀 Wysoki | -10 | telefon może trochę zwolnić |
| ☄️ Czasu rzeczywistego | -20 | najwyższy poziom, na jaki Android pozwala aplikacji. Prawdziwy SCHED_FIFO jest zarezerwowany dla systemu i szczerze - dobrze 😅 |

> Jeśli telefon nie pozwoli podnieść priorytetu, silnik działa na Normalnym, a zakładka **Log** to pokaże:
> `[PRIORITY] nice requested -10, active 0`.

### 📁 Ty decydujesz, gdzie co trafia

* 🗂️ **8 rodzajów plików** (gotowy utwór, sekcje, sample, stemy, użyte wycinki, MIDI, nuty, metadane) - każdy może
  iść do własnego folderu. Albo **„Jeden folder na wszystko”**, jeśli lubisz porządek 🧹.
* 🧭 Domyślne miejsca są zawsze widoczne, więc nic nie zginie w czeluściach systemu plików.
* 🆘 Folder zniknął (wyjęta karta SD)? Pliki trafią do lokalizacji domyślnej - **żaden wynik nie przepada**.

### 🗄️ Gdzie mieszkają modele

* 📍 Pamięć wewnętrzna aplikacji 🔐, folder aplikacji w pamięci telefonu *(domyślnie)* albo folder aplikacji na **karcie SD** 💳.
* 🚚 **Przenoszenie modeli** między nimi z paskiem postępu, anulowaniem i sprawdzaniem miejsca. Przerwane przenoszenie nie gubi plików.
* 📥 **Import plików .gguf**, które już masz (np. pobrane na komputerze) - sprawdzane z oficjalnym rozmiarem i sumą kontrolną.

> 🤓 *Czemu nie dowolny folder?* Silnik C++ czyta modele bezpośrednio jako pliki, a bez uprawnienia „dostęp do
> wszystkich plików” (którego Sklep Play prawie nikomu nie daje) Android pozwala na to tylko we własnych folderach aplikacji.

### 🌍 I wisienki na torcie 🍒

* 🇬🇧🇵🇱 **Interfejs po angielsku i po polsku**, do zmiany w Ustawienia → Język (na Androidzie 13+ także w ustawieniach aplikacji w telefonie).
* 🚩 Przycisk **Zgłoś treść** przy każdym wyniku - wymagany przez Sklep Play dla generatorów AI, a poza tym zwyczajnie przyzwoity.
* 🔔 Powiadomienie z postępem, 📶 pobieranie „tylko przez Wi-Fi”, ⏯️ wznawianie pobierania po zerwaniu połączenia.
* 📜 Zakładka **Log** dla ciekawskich i do zgłaszania błędów.

---

## 📲 Instalacja

1. 📥 Pobierz najnowszy **`AceMusicGen-vX.Y.Z.apk`** z [Releases](https://github.com/Kurzoczek/Ace_AI_Music_generator_and_covering/releases/latest).
2. 📂 Otwórz go. Android zapyta, czy przeglądarka / menedżer plików może instalować aplikacje - wybierz **Zezwól** (tylko dla tego źródła).
3. ✅ **Zainstaluj**, otwórz, zezwól na powiadomienia (opcjonalnie, ale chcesz wiedzieć, kiedy Twój hit będzie gotowy 🔔).

**Wymagania:** Android 10+ 🤖, 64-bitowy telefon ARM z mniej więcej 2018-2019 roku lub nowszy (ARMv8.2 z dot-product),
kilka GB wolnego miejsca na model 💾. Ile RAM-u potrzebuje wybrany model, pokazuje okno ostrzeżenia przed startem.

### 🔄 Aktualizacja

Po prostu zainstaluj nowe APK na starym - ustawienia i pobrane modele zostają ✨.

> 😬 *„Aplikacja nie została zainstalowana, ponieważ pakiet powoduje konflikt z istniejącym pakietem”?* Ta wersja jest
> podpisana innym kluczem (starsze buildy testowe miały losowy klucz). Odinstaluj raz i zainstaluj ponownie. Chcesz
> zachować modele (kilka GB)? Z `adb` na komputerze:
>
> ```powershell
> ./adb pull /sdcard/Android/data/com.acemusicgen/files/models .     # 💾 modele na komputer
> ./adb uninstall com.acemusicgen
> ./adb install AceMusicGen-vX.Y.Z.apk                                # potem uruchom aplikację raz
> ./adb push models /sdcard/Android/data/com.acemusicgen/files/       # 🔙 modele z powrotem, bez pobierania
> ```
>
> Albo po reinstalacji użyj **Modele → Importuj pliki .gguf**.

---

## 🎬 Jak używać (w 60 sekund)

1. 🎵 Zakładka **Generuj** → **Dodaj utwory** (każdy dźwięk, który Android odtworzy: mp3, opus, flac, wav, m4a...).
2. 🎨 *(opcjonalnie)* **Dodaj wzorce** - utwory, których styl Ci się podoba.
3. 🔁 Wybierz **Cover** albo ✍️ **Tekst**, wpisz krótki opis po angielsku (np. *„anime-like opening, energetic”*).
4. ▶️ **Start** → przeczytaj okno ostrzeżenia (tak, naprawdę 😉) → potwierdź.
5. ☕ Zrób kawę. Pierwsze uruchomienie pobiera model, kolejne od razu generują.
6. 🎉 Wyniki lądują w `Music/ACE_music_gen/` i `Download/ACE_music_gen/` (albo tam, gdzie im kazałeś).

### 📂 Gdzie trafiają wyniki

Każdy utwór dostaje własny folder `<utwór>_<BPM>bpm_<data>_<godzina>`:

| Pliki | Domyślnie |
|---|---|
| 🏆 gotowy utwór | `Music/ACE_music_gen/<utwór>/final/` |
| 🧩 sekcje, 🔁 sample, 🎚️ stemy, ✂️ użyte wycinki | `Music/ACE_music_gen/<utwór>/parts/`, `samples/`, `stems/`, `used_sounds/` |
| 🎹 MIDI | `Download/ACE_music_gen/<utwór>/midi/` |
| 🎼 nuty (MusicXML, LilyPond, tekst) | `Download/ACE_music_gen/<utwór>/notation/` |
| 🗒️ metadata.json | `Download/ACE_music_gen/<utwór>/` |

---

## 🔨 Budowanie samemu

### 🧑‍💻 Na komputerze

Potrzebujesz: **JDK 17** ☕ (Java 8 przywita Cię komunikatem *„This build uses a Java 8 JVM”* 🙅), Android SDK **36**,
NDK **27.2.12479018**, CMake **3.22.1**. Android Studio doinstaluje brakujące elementy samo.

```bash
git clone --recurse-submodules https://github.com/Kurzoczek/Ace_AI_Music_generator_and_covering.git
cd Ace_AI_Music_generator_and_covering
./gradlew assembleDebug        # 🎁 app/build/outputs/apk/debug/app-debug.apk
```

Sklonowane bez submodułów? `git submodule update --init --recursive` 🩹

**Windows bez Android Studio** (PowerShell):

```powershell
$env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"
$env:Path = "$env:JAVA_HOME\bin;$env:Path"
java -version                  # musi pokazać 17 lub nowszą
.\gradlew.bat assembleDebug
```

Lokalizacja SDK idzie do `local.properties` (`sdk.dir=...`) albo zmiennej `ANDROID_HOME`.

🧰 **Pokrętła** w `gradle.properties`:

* `aceArmArch=armv8.2-a+dotprod+fp16` - szybki silnik dla nowoczesnych telefonów. Masz skamielinę 🦕 z samymi Cortex-A53/A73? Ustaw `armv8-a`.
* `aceReportEmail=` - dokąd „Zgłoś treść” wysyła zgłoszenia. Puste = nowe zgłoszenie (issue) w tym repozytorium.
* Chaquopy nie ma `numpy` dla Pythona 3.12? Ustaw `version = "3.11"` w bloku `chaquopy` w `app/build.gradle.kts`.

### ☁️ W chmurze: GitHub Actions (komputer niepotrzebny!)

| Workflow | Kiedy | Co dostajesz |
|---|---|---|
| 🧪 `android.yml` | każdy push do `main`, każdy pull request | APK debug w *Artifacts* + sprawdzenie, że rdzeń Pythona zgadza się ze skryptem desktopowym |
| 📦 `import-zip.yml` | wgrywasz ZIP z projektem | rozpakowuje, robi commit, usuwa ZIP i buduje APK - w jednym przebiegu |
| 🏷️ `release.yml` | **Run workflow** z numerem wersji albo tag `v*` | podpisane APK + AAB opublikowane jako wydanie na GitHubie |

### 📱 Aktualizacja repozytorium z telefonu (import ZIP)

Programujesz w autobusie? Spokojnie 🚌:

1. W repozytorium: **Add file → Upload files** → wrzuć ZIP z projektem (główny folder albo `incoming/`) → **Commit changes**.
2. ☕ Przebieg **Import project ZIP** rozpakowuje, robi commit, usuwa ZIP i buduje APK (etap *build*).
3. 📥 APK jest w *Artifacts* tego przebiegu.

Celowo pomijane: `.git`, klucze podpisu (`*.p12`, `*.jks`, `*.keystore` - ich miejsce jest w sekretach 🔐), submoduł
silnika, foldery buildu i `.github/workflows/` (GitHub nie pozwala workflowom zmieniać workflowów, więc takie pliki są
wypisywane jako ostrzeżenie do ręcznego wgrania). Pliki usunięte z projektu nie są usuwane z repozytorium przez import.

### 🚀 Robienie wydania

**Actions → Release → Run workflow** → wpisz wersję, np. `1.1.1` → **Run workflow** → 🍿. Powstaje wydanie
`v1.1.1` z plikami APK i AAB.

### 🔐 Klucze podpisu (sekrety repozytorium)

*Settings → Secrets and variables → Actions*:

| Sekret | Do czego |
|---|---|
| `ACE_DEBUG_KEYSTORE_BASE64`, `ACE_DEBUG_KEYSTORE_PASSWORD` | 🧪 stały klucz dla buildów testowych i wydań instalowanych z GitHuba - aktualizacje zachowują dane (PKCS12, alias `acedebug`) |
| `ACE_KEYSTORE_BASE64`, `ACE_KEYSTORE_PASSWORD`, `ACE_KEY_ALIAS`, `ACE_KEY_PASSWORD` | 🏪 klucz wydania do Sklepu Play (gdy jest, wydania używają go zamiast klucza debug) |

Tworzenie klucza: `keytool -genkeypair -keystore ace-debug.p12 -storetype PKCS12 -alias acedebug -keyalg RSA -keysize 2048 -validity 10950`,
potem `base64 -w0 ace-debug.p12` → wklej jako sekret. 🗝️ **Zachowaj kopię pliku klucza** - bez niej kolejny build nie
zaktualizuje zainstalowanej aplikacji. W repozytorium nie ma żadnego klucza.

`versionCode` w CI = minuty od 2026-01-01, więc każdy build jest „nowszy” od poprzedniego ⏫.

---

## 🔒 Prywatność i bezpieczeństwo

* 🙈 **Bez konta, reklam, analityki i własnego serwera.** Szczegóły: [PRIVACY.md](PRIVACY.md) (EN + PL).
* 📂 **Pliki**: otwierane tylko przez systemowe okno wyboru, zero uprawnień do pamięci. Wyniki przez MediaStore albo do wybranych folderów.
* 🌐 **Sieć**: tylko HTTPS, tylko certyfikaty systemowe, SHA-256 dla każdego modelu, opcja „tylko Wi-Fi”.
  Żaden kod wykonywalny nie jest pobierany - silnik jest w APK.
* 🔔 **Powiadomienia**: pytanie w trakcie działania na Androidzie 13+, opcjonalne.
* ⚙️ **Praca w tle**: usługa pierwszoplanowa (`dataSync` dla pobierania, `mediaProcessing` dla generowania na Androidzie 15+),
  blokada uśpienia tylko podczas generowania, limit czasu Androida 15 obsłużony punktami kontrolnymi.
* 🧱 **Kod natywny**: uruchamiany tylko z `nativeLibraryDir` (zgodnie z W^X), wyrównany do stron 16 KB.
* 💾 **Kopia zapasowa**: tylko ustawienia - żadnych wielogigabajtowych modeli na Twoim Dysku Google 😅.

## 🏪 Gotowość do Sklepu Play

* 🎯 `targetSdk` / `compileSdk` **36** (Android 16), zgodnie z wymogami Google Play.
* 📦 **AAB** budowane przez workflow Release.
* 🚩 Przycisk **Zgłoś treść** (zasady dotyczące treści generowanych przez AI).
* 📜 [PRIVACY.md](PRIVACY.md) - uzupełnij imię i e-mail kontaktowy i opublikuj pod **publicznym** adresem.
* 📝 Play Console: zadeklaruj usługi `dataSync` i `mediaProcessing` (każdą z krótkim nagraniem ekranu), bezpieczeństwo
  danych: nic nie jest zbierane ani udostępniane. Nowe konta osobiste potrzebują też testu zamkniętego (12 testerów, 14 dni) 🧑‍🤝‍🧑.

---

## 🏗️ Architektura (dla ciekawskich 🔍)

| Część | Gdzie | Co robi |
|---|---|---|
| 🖼️ Interfejs | `ui/` (Jetpack Compose) | utwory/wzorce, tryb i opis, ustawienia, modele, log, zgłaszanie; EN + PL |
| ⚠️ Okno ostrzeżenia | `ui/PreflightDialog.kt`, `data/Preflight.kt` | rozmiar i źródło pobierania, miejsce, RAM, temperatura - przed startem |
| 🤖 Modele | `data/ModelCatalog.kt`, `ModelDownloader.kt`, `ModelStorage.kt`, `ModelFiles.kt` | dokładne rozmiary + SHA-256, wznawiane pobieranie HTTPS, miejsca przechowywania, przenoszenie i import |
| 🧮 Pamięć | `data/MemoryPlanner.kt` | szacowanie RAM dla modelu, kalibrowane zmierzonymi szczytami; plan przy małej pamięci |
| ⚙️ Usługa | `engine/GenerationService.kt` | usługa pierwszoplanowa: dekodowanie → pobieranie → generowanie → zapis |
| 🌡️ CPU/ciepło | `engine/ResourceGovernor.kt` | wątki, rdzenie, priorytet, limit % CPU (SIGSTOP/SIGCONT), pauza termiczna |
| 🐍 Analiza | `app/src/main/python/` (Chaquopy) | tempo/tonacja/akordy/struktura, nuty, MIDI, logika coveru |
| 🏎️ Silnik | `app/src/main/cpp/` | acestep.cpp `ace-synth` / `ace-lm` zbudowane NDK, uruchamiane jako osobne procesy |

`ace_core.py` jest generowany ze skryptu desktopowego (CI pilnuje, żeby były zgodne):

```bash
python tools/build_ace_core.py tools/generate_small_pro_ace_android.py app/src/main/python/ace_core.py
```

Zostaje kod analizy i eksportu, a odpada to, co nie zadziała w aplikacji (instalatory, PyTorch, Ollama, Demucs, AST);
zamienniki dla Androida są w `tools/ace_core_android.py`.

### 📥 Co jest pobierane

Tylko pliki modeli GGUF, tylko po Twoim potwierdzeniu, tylko z
[`huggingface.co/Serveurperso/ACE-Step-1.5-GGUF`](https://huggingface.co/Serveurperso/ACE-Step-1.5-GGUF).
Typowe rozmiary: model muzyczny 1,45 GB (Q4_K_M) - 9,3 GB (XL BF16), koder tekstu 0,78 GB, VAE 0,34 GB, opcjonalny
model językowy 0,7 - 4,2 GB. Okno ostrzeżenia pokazuje dokładne liczby przed pobraniem.

---

## 🆘 Gdy coś nie działa

| Objaw | Lekarstwo |
|---|---|
| 😵 *„This build uses a Java 8 JVM”* | ustaw `JAVA_HOME` na JDK 17 (patrz [Budowanie](#-budowanie-samemu)) |
| 🚫 *„konflikt z istniejącym pakietem”* | inny klucz podpisu - odinstaluj raz (patrz [Aktualizacja](#-aktualizacja)) |
| 🔥 telefon gorący jak patelnia do naleśników | zmniejsz *Maks. użycie CPU*, wybierz rdzenie energooszczędne, nie wyłączaj ochrony przed przegrzaniem |
| 🐌 bardzo wolno | model turbo, Q4_K_M, priorytet Normalny lub wyższy, rdzenie wydajne |
| 💥 silnik ubity z braku pamięci | nic nie rób - aplikacja poczeka i wznowi od punktu kontrolnego. Albo wybierz mniejszy model 😉 |
| 💳 *„Miejsce wybrane na modele jest niedostępne”* | włóż kartę SD z powrotem albo wybierz inne miejsce w **Modele** |
| 🤷 coś innego | zakładka **Log** → skopiuj → załóż zgłoszenie (issue) 🐛 |

---

## 📜 Licencja i podziękowania

* 🙏 **[ACE-Step 1.5](https://huggingface.co/ACE-Step/Ace-Step1.5)** - model muzyczny. **[acestep.cpp](https://github.com/ServeurpersoCom/acestep.cpp)** (MIT) i **ggml** - silnik.
  Modele z [Serveurperso/ACE-Step-1.5-GGUF](https://huggingface.co/Serveurperso/ACE-Step-1.5-GGUF). **[Chaquopy](https://chaquo.com/chaquopy/)** - Python na Androidzie.
  Pełna lista: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
* ⚖️ Licencja własnego kodu projektu nie jest jeszcze wybrana - dodaj plik `LICENSE` przed publikacją.
* 🎼 Coveruj odpowiedzialnie: przerabiaj muzykę, do której masz prawa. Aplikacja to narzędzie, nie prawnik 👩‍⚖️.

<div align="center">

Zrobione z ☕, 🎧 i lekko ciepłym telefonem 🔥📱

</div>
