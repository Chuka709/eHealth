# Android emulator — E: диск дээр суулгах (Windows)

> 2026.10.29-нд шалгасан төлөв: C: 5.7 GB сул (98% дүүрсэн), E: 67 GB сул. WHPX (Windows Hypervisor
> Platform) **идэвхтэй, ашиглах боломжтой** — emulator Docker-той зэрэг ажиллана.
> ⚠️ Emulator "Please disable Hyper-V" гэж хэлж болно — **бүү унтраа** (Docker зогсоно). WHPX ажиллаж байгаа.
> Хуучин SDK `C:\Users\PC\AppData\Local\Android\Sdk`-д байна (Flutter-ийнх), Java суугаагүй.

## Бүтэц (бүгд E: дээр)
```
E:\Android\
  Android Studio\   ← програм (JDK буюу "jbr" дотроо агуулна)
  Sdk\              ← ANDROID_HOME: platform-tools, emulator, system image
  .android\         ← ANDROID_USER_HOME: adb түлхүүр, тохиргоо
  avd\              ← ANDROID_AVD_HOME: виртуал утаснууд (тус бүр 6–10 GB)
  gradle\           ← GRADLE_USER_HOME: локал build-ийн кэш (5–15 GB)
  studio-config\, studio-system\  ← Android Studio-ийн кэш (C: биш)
```

## 1. Орчны хувьсагч (админ эрх хэрэггүй) — Android Studio суулгахаас ӨМНӨ
PowerShell (энгийн эрхээр):
```powershell
New-Item -ItemType Directory -Force E:\Android\Sdk, E:\Android\.android, E:\Android\avd, E:\Android\gradle | Out-Null
[Environment]::SetEnvironmentVariable("ANDROID_HOME",      "E:\Android\Sdk",      "User")
[Environment]::SetEnvironmentVariable("ANDROID_SDK_ROOT",  "E:\Android\Sdk",      "User")
[Environment]::SetEnvironmentVariable("ANDROID_USER_HOME", "E:\Android\.android", "User")
[Environment]::SetEnvironmentVariable("ANDROID_AVD_HOME",  "E:\Android\avd",      "User")
[Environment]::SetEnvironmentVariable("GRADLE_USER_HOME",  "E:\Android\gradle",   "User")
$p = [Environment]::GetEnvironmentVariable("Path","User")
$p = ($p -split ';' | Where-Object { $_ -notlike '*AppData\Local\Android\Sdk*' }) -join ';'
[Environment]::SetEnvironmentVariable("Path", "$p;E:\Android\Sdk\platform-tools;E:\Android\Sdk\emulator", "User")
```
Дараа нь **бүх терминал, VS Code, Claude Code-г хааж дахин нээ** (хувьсагч шинэчлэгдэнэ).

## 2. Android Studio (E: руу)
1. https://developer.android.com/studio — Windows installer (.exe) татна.
2. Суулгахдаа **Install location: `E:\Android\Android Studio`**. "Android Virtual Device" сонголт ✓.
3. Анх нээхээс өмнө `E:\Android\Android Studio\bin\idea.properties` файлын төгсгөлд нэм (кэш C: руу бичихгүй):
   ```
   idea.config.path=E:/Android/studio-config
   idea.system.path=E:/Android/studio-system
   ```
4. Setup Wizard → **Custom** → **Android SDK Location: `E:\Android\Sdk`** (C:\Users\… биш эсэхийг шалга).

## 3. SDK багцууд
Android Studio → **More Actions → SDK Manager**:
- SDK Platforms: **Android 16 (API 36)** (Expo SDK 58-ийн compile SDK; "Show Package Details"-ээс
  `Google APIs Intel x86_64 Atom System Image`-ийг мөн сонго).
- SDK Tools: Android SDK Build-Tools, Platform-Tools, Emulator, Command-line Tools (latest).
  NDK, CMake — зөвхөн локал build (5-р алхмын Б) хийх бол.

## 4. Виртуал утас (AVD)
**More Actions → Virtual Device Manager → Create**:
| Нэр | Төхөөрөмж | Image | RAM | Зорилго |
|---|---|---|---|---|
| `Pixel_API36` | Pixel 8 | API 36 Google APIs x86_64 | 4 GB | өдөр тутмын хөгжүүлэлт |
| `Small_API30` (дараа) | Pixel 4a / 5" | API 30 x86_64 | 2 GB | хямд утас, том фонт, сануулгын тест (docs/09 H6) |

Advanced → Graphics: **Hardware**. Шалгах:
```powershell
emulator -list-avds
emulator -avd Pixel_API36
adb devices          # emulator-5554  device
```

## 5. Апп-ыг emulator дээр ажиллуулах
Апп native модультай тул **Expo Go биш, development build** хэрэгтэй. API нь emulator-оос
`http://10.0.2.2:8080` (компьютерийн localhost → Caddy) — `mobile/src/lib/api.ts`-д анхдагчаар тохируулсан.
`just up` ажиллаж байх ёстой.

**А. Санал болгох — EAS cloud build** (Java, NDK, Gradle-ийн кэш шаардлагагүй, диск хэмнэнэ):
```powershell
npm install -g eas-cli
eas login                       # үнэгүй Expo аккаунт
cd "F:\My Projects\eHealth\mobile"
eas init                        # нэг удаа: projectId app.config-д бичигдэнэ
eas build --profile development --platform android
```
Build дуусахад гарах линкээс `.apk` татаад emulator-ийн цонх руу чирж оруулна (эсвэл `adb install файл.apk`).
Дараа нь:
```powershell
cd "F:\My Projects\eHealth"; just mobile     # Metro; emulator дээр апп нээгдээд холбогдоно
```
JS өөрчлөлт бүр шууд харагдана; native модуль нэмсэн үед л дахин `eas build`.

**Б. Локал build** (интернэтгүй давтах хэрэгтэй бол): SDK Manager-ээс NDK + CMake нэмээд
```powershell
$env:JAVA_HOME = "E:\Android\Android Studio\jbr"
cd "F:\My Projects\eHealth\mobile"; npx expo run:android
```
Эхний build 10–20 мин, `E:\Android\gradle`-д ~10 GB кэш үүснэ.

## 6. C: дискийг чөлөөлөх (сонголттой, бүгд ажилласны дараа)
- Flutter-ийг шинэ SDK руу заах: `flutter config --android-sdk E:\Android\Sdk`
- Хуучин `C:\Users\PC\AppData\Local\Android\Sdk`-ийг устгах (хэдэн GB чөлөөлнө).

## Түгээмэл асуудал
| Шинж тэмдэг | Шийдэл |
|---|---|
| "Please disable Hyper-V" | Үл тоо — WHPX ажиллаж байна. `emulator -accel-check` → "WHPX … usable" |
| Apps "network error" | `just up` ажиллаж буй эсэх; апп-д `10.0.2.2:8080` (localhost биш) |
| SDK C: руу буцаж татагдаад байна | `echo $env:ANDROID_HOME` → `E:\Android\Sdk`; Studio → Settings → Android SDK Location |
| Emulator удаан | Graphics = Hardware, RAM 4 GB, Docker-ийн санах ойг хязгаарла |
