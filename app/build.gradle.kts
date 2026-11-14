plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
    id("com.chaquo.python")
}

val aceArmArch: String = (project.findProperty("aceArmArch") as String?) ?: "armv8.2-a+dotprod+fp16"

android {
    namespace = "com.acemusicgen"
    compileSdk = 35
    ndkVersion = "27.2.12479018"

    defaultConfig {
        applicationId = "com.acemusicgen"
        minSdk = 29                 // Android 10: scoped storage (MediaStore), FGS types, thermal API
        targetSdk = 35
        versionCode = 1
        versionName = "1.0.0"

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
    kotlinOptions {
        jvmTarget = "17"
    }
    buildFeatures {
        compose = true
        buildConfig = true
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
    implementation("androidx.core:core-ktx:1.19.1")
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
