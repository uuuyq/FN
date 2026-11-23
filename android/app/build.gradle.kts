plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}
android {
    namespace = "online.uuuf.fnote"
    compileSdk = 35
    defaultConfig {
        applicationId = "online.uuuf.fnote"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "1.0.0"
    }
    signingConfigs {
        create("release") {
            storeFile = file(System.getenv("FNOTE_KEYSTORE") ?: "../../runtime/android-signing/release.p12")
            storePassword = System.getenv("FNOTE_STORE_PASSWORD")
            keyAlias = "fnote"
            keyPassword = System.getenv("FNOTE_STORE_PASSWORD")
        }
    }
    buildTypes { getByName("release") { signingConfig = signingConfigs.getByName("release") } }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    buildFeatures { buildConfig = true }
}
