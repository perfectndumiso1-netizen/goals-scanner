// Build marker: 2026-10-20 archive restore + team goals + 3x videos. Comment only.
import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

val appVersionCode = (System.getenv("APP_VERSION_CODE") ?: "88").toInt()
val appVersionName = System.getenv("APP_VERSION_NAME") ?: "1.6.88"
val keystorePath = System.getenv("KEYSTORE_PATH")

android {
    namespace = "com.playreport.app"
    // API 36 (Android 16) — Play Protect warns when an app is built two or more SDK generations behind the
    // device (Google's own guidance), and the Play deadline for API 36 has already passed (31 Aug 2026).
    compileSdk = 36

    defaultConfig {
        applicationId = "com.playreport.app"
        minSdk = 26
        targetSdk = 36
        versionCode = appVersionCode
        versionName = appVersionName
        buildConfigField("String", "REPO", "\"${System.getenv("APP_REPO") ?: "perfectndumiso1-netizen/goals-scanner"}\"")
    }

    signingConfigs {
        create("release") {
            if (keystorePath != null && file(keystorePath).exists()) {
                storeFile = file(keystorePath)
                storePassword = System.getenv("KEYSTORE_PASSWORD")
                keyAlias = System.getenv("KEY_ALIAS")
                keyPassword = System.getenv("KEY_PASSWORD")
                enableV1Signing = true
                enableV2Signing = true
                enableV3Signing = true
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("release")
        }
    }

    lint {
        // this app is distributed as a raw APK and inspected by Play Protect on every install, so a lint
        // error blocks the release instead of being a note in the log
        abortOnError = true
        // version-nag checks are not code problems: everything else stays on
        disable += setOf("GradleDependency", "OldTargetApi", "AndroidGradlePluginVersion", "NewerVersionAvailable")
    }

    buildFeatures {
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.webkit:webkit:1.11.0")
    implementation("androidx.swiperefreshlayout:swiperefreshlayout:1.1.0")
    implementation("androidx.activity:activity-ktx:1.9.1")
    implementation("com.google.android.material:material:1.12.0")
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.work:work-runtime-ktx:2.9.1")
    testImplementation("junit:junit:4.13.2")
}
