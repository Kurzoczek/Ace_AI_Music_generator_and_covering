# Changelog / Historia zmian

Every version has an English and a Polish part. The Release workflow publishes the section of the released version
(or, if it has none yet, the **Unreleased** section) as the description on the Releases page.
Each version: `## [x.y.z] - date`, newest first.

Każda wersja ma część angielską i polską. Workflow Release publikuje sekcję wydawanej wersji (a jeśli jej jeszcze
nie ma - sekcję **Unreleased**) jako opis na stronie Releases.

## [Unreleased]

### 🇬🇧 What's new

- 🔁 **Nothing is lost when Android ends the app.** The picked tracks are remembered, and a job interrupted by the
  system shows a **Resume** card (with the reason Android gave) that continues from the last finished pass.
  Fixes the input track disappearing after the app was paused for a while.
- 🧹 Engine processes left frozen in memory by a killed app are found and stopped at the next start.
- 🩺 **Diagnostics** (Settings → Diagnostics): optional log files with exact times, task and file durations,
  errors, system events (screen, charger, battery saver, doze, overheating, memory warnings) and a state snapshot
  every 10 minutes (temperatures, CPU speeds, memory, power state). Folder of your choice, default
  `Download/ACE_music_gen/app logs`.
- 🧯 **State dumps, Windows-style**: (none) / small / extended / complete / automatic - on crashes, unexpected ends,
  errors or pauses, plus a **Dump now** button in the Log tab. Only the app's own processes are dumped.
- 📖 **Model descriptions** under the model, quantization and language model choices: speed, quality, size, RAM
  and when to use each.

### 🇵🇱 Co nowego

- 🔁 **Nic nie ginie, gdy Android zamknie aplikację.** Wybrane utwory są pamiętane, a zadanie przerwane przez system
  pokazuje kartę **Wznów** (z powodem podanym przez Androida), która kontynuuje od ostatniego ukończonego przebiegu.
  Naprawia znikanie utworu wejściowego po dłuższym wstrzymaniu aplikacji.
- 🧹 Procesy silnika, które zostały zamrożone w pamięci po ubitej aplikacji, są wykrywane i zamykane przy następnym starcie.
- 🩺 **Diagnostyka** (Ustawienia → Diagnostyka): opcjonalne pliki dziennika z dokładnym czasem, czasem trwania zadań
  i plików, błędami, zdarzeniami systemowymi (ekran, ładowarka, oszczędzanie baterii, uśpienie, przegrzanie,
  ostrzeżenia o pamięci) i migawką stanu co 10 minut (temperatury, taktowanie, pamięć, zasilanie). Folder do wyboru,
  domyślnie `Download/ACE_music_gen/logi aplikacji`.
- 🧯 **Zrzuty stanu jak w Windowsie**: (brak) / mały / rozszerzony / kompletny / automatyczny - przy awarii,
  nieoczekiwanym zamknięciu, błędzie albo pauzie, plus przycisk **Zrzut teraz** w zakładce Log. Zrzucane są tylko
  procesy samej aplikacji.
- 📖 **Opisy modeli** pod wyborem modelu, kwantyzacji i modelu językowego: szybkość, jakość, rozmiar, RAM i kiedy
  którego używać.

## [1.1.1] - 2026-11-14

### 🇬🇧 Fixes

- 🛠️ Release builds no longer stop on the backup rules check (only settings are backed up, as before).
- 🚀 One-tap releases: **Actions → Release → Run workflow**.

### 🇵🇱 Poprawki

- 🛠️ Wersja release nie zatrzymuje się już na kontroli reguł kopii zapasowej (kopia nadal obejmuje tylko ustawienia).
- 🚀 Wydanie jednym przyciskiem: **Actions → Release → Run workflow**.

## [1.1.0] - 2026-11-14

### 🇬🇧 What's new

- 🗄️ Choose where the models are stored (internal storage, phone storage, SD card), move them between locations
  and import `.gguf` files you already have.
- 🚦 Six process priority levels, like in Windows: Low ... Realtime.
- 🇬🇧🇵🇱 English and Polish interface, switchable in Settings.
- 🚩 **Report content** button on results.
- 🎯 Targets Android 16 (API 36).
- 🐛 Fixed: "Starting FGS with type none ... has been prohibited" stopping the generation on Android 15.
- 🔑 Updates install over the previous version and keep your data (fixed signing key).

### 🇵🇱 Co nowego

- 🗄️ Wybór miejsca na modele (pamięć wewnętrzna, pamięć telefonu, karta SD), przenoszenie modeli między nimi i import
  posiadanych plików `.gguf`.
- 🚦 Sześć poziomów priorytetu procesu, jak w Windowsie: od Niskiego do Czasu rzeczywistego.
- 🇬🇧🇵🇱 Interfejs po angielsku i polsku, do przełączenia w Ustawieniach.
- 🚩 Przycisk **Zgłoś treść** przy wynikach.
- 🎯 Kierowana na Androida 16 (API 36).
- 🐛 Naprawione: błąd „Starting FGS with type none ... has been prohibited” przerywający generowanie na Androidzie 15.
- 🔑 Aktualizacje instalują się na poprzednią wersję z zachowaniem danych (stały klucz podpisu).

## [1.0.0] - 2026-11-14

### 🇬🇧 First version

- 🎵 Native Android app replacing the Termux scripts: cover and text-to-music with ACE-Step 1.5 on the phone.
- ⚠️ Warning before start: download size and source, storage, RAM need, possible overheating.
- 🧮 Adjustable RAM limit (no 10 GB cap) with graceful work below the model's need; CPU limit, cores, overheating protection.
- 📁 Choice of save location for every kind of result.

### 🇵🇱 Pierwsza wersja

- 🎵 Natywna aplikacja na Androida w miejsce skryptów do Termuksa: cover i tworzenie muzyki z opisu z ACE-Step 1.5 na telefonie.
- ⚠️ Ostrzeżenie przed startem: rozmiar i źródło pobierania, miejsce, potrzebny RAM, możliwe przegrzanie.
- 🧮 Regulowany limit RAM (bez limitu 10 GB) z pracą także poniżej potrzeb modelu; limit CPU, rdzenie, ochrona przed przegrzaniem.
- 📁 Wybór miejsca zapisu dla każdego rodzaju wyników.
