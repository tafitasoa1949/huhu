plugins {
    id("com.android.application") version "8.13.2"
    id("org.jetbrains.kotlin.android") version "1.9.24"
    id("org.jetbrains.kotlin.plugin.serialization") version "1.9.24"
}

android {
    namespace = "com.smartcar.pilot"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.smartcar.pilot"
        minSdk = 26
        targetSdk = 34
        versionCode = 1
        versionName = "0.1.0"
    }

    buildFeatures {
        compose = true
    }
    composeOptions {
        kotlinCompilerExtensionVersion = "1.5.14"
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
    // Domaine + application (ports, cas d'usage, JoystickMapper) : la
    // raison d'être du découpage en modules, voir mobile-app/settings.gradle.kts.
    implementation(project(":core"))

    implementation(platform("androidx.compose:compose-bom:2024.06.00"))
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.activity:activity-compose:1.9.0")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.2")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.2")
    // viewModelScope, utilisé directement par DrivingViewModel. Il arrive
    // aussi par transitivité, mais une dépendance dont on importe
    // explicitement les symboles se déclare : une mise à jour d'un autre
    // artefact ne doit pas pouvoir la faire disparaître.
    implementation("androidx.lifecycle:lifecycle-viewmodel-ktx:2.8.2")

    // Même raison : delay, collectLatest, withContext et Dispatchers sont
    // importés directement (DrivingViewModel, RobotApiClient, DrivingScreen).
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.7.3")

    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.6.3")

    debugImplementation("androidx.compose.ui:ui-tooling")
}
