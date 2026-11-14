plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
    id("com.chaquo.python")
}

val aceArmArch: String = (project.findProperty("aceArmArch") as String?) ?: "armv8.2-a+dotprod+fp16"
// Where "Report content" sends reports: an e-mail address if set, otherwise a new GitHub issue in this repository.
val aceReportEmail: String = (project.findProperty("aceReportEmail") as String?)?.trim() ?: ""
val aceReportUrl: String = (project.findProperty("aceReportUrl") as String?)?.trim()
    ?: "https://github.com/Kurzoczek/Ace_AI_Music_generator_and_covering/issues/new"
// Google Play needs a higher versionCode for every upload: CI builds use the run number, local builds 2.
val aceVersionCode: Int = System.getenv("GITHUB_RUN_NUMBER")?.toIntOrNull()?.plus(100) ?: 2

android {
    namespace = "com.acemusicgen"
    compileSdk = 36
    ndkVersion = "27.2.12479018"

    defaultConfig {
        applicationId = "com.acemusicgen"
        minSdk = 29                 // Android 10: scoped storage (MediaStore), FGS types, thermal API
        targetSdk = 36             // Google Play: new apps and updates must target Android 16 (API 36)
        versionCode = aceVersionCode
        versionName = "1.1.0"
        buildConfigField("String", "REPORT_EMAIL", "\"$aceReportEmail\"")
        buildConfigField("String", "REPORT_URL", "\"$aceReportUrl\"")

        ndk {
            // acestep.cpp needs 64-bit; x86_64 only for the emulator
            abiFilters += listOf("arm64-v8a", "x86_64")
        }
        externalNativeBuild {
            cmake {
                arguments += listOf(
                    "-DANDROID_STL=c++_static",
                    "-DACE_ARM_ARCH=$aceArmArch",
                )
                targets += listOf("ace-synth", "ace-lm")
            }
        }
    }

    externalNativeBuild {
        cmake {
            path = file("src/main/cpp/CMakeLists.txt")
            version = "3.22.1"
        }
    }

    // Release signing from environment variables (GitHub Actions secrets, see README). Without them the release
    // build is unsigned; debug builds always work.
    val keystoreFile = System.getenv("ACE_KEYSTORE_FILE")
    signingConfigs {
        // Debug key from GitHub secrets (ACE_DEBUG_KEYSTORE_*), so every CI build is signed with the same key and installs
        // as an update keeping the app data. No key in the repository; without the secrets (local / Dependabot builds)
        // the standard Android debug key of that machine is used.
        val debugKeystore = System.getenv("ACE_DEBUG_KEYSTORE_FILE")
        if (debugKeystore != null && file(debugKeystore).exists()) {
            getByName("debug") {
                storeFile = file(debugKeystore)
                storePassword = System.getenv("ACE_DEBUG_KEYSTORE_PASSWORD")
                keyAlias = "acedebug"
                keyPassword = System.getenv("ACE_DEBUG_KEYSTORE_PASSWORD")
            }
        }
        if (keystoreFile != null && file(keystoreFile).exists()) {
            create("release") {
                storeFile = file(keystoreFile)
                storePassword = System.getenv("ACE_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("ACE_KEY_ALIAS")
                keyPassword = System.getenv("ACE_KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        release {
            signingConfigs.findByName("release")?.let { signingConfig = it }
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }

    packaging {
        jniLibs {
            // The acestep.cpp programs are packaged as lib*.so and started as separate processes.
            // They must be extracted to nativeLibraryDir (the only app location Android lets us execute from).
            useLegacyPackaging = true
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
    }
}

chaquopy {
    defaultConfig {
        version = "3.12"
        pip {
            install("numpy")
        }
    }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2024.12.01")
    implementation(composeBom)
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.7")
    implementation("androidx.lifecycle:lifecycle-service:2.8.7")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")
    debugImplementation("androidx.compose.ui:ui-tooling")
}
