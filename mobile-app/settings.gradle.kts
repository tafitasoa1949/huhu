pluginManagement {
    repositories {
        google()
        gradlePluginPortal()
        mavenCentral()
    }
}
plugins {
    id("org.gradle.toolchains.foojay-resolver-convention") version "1.0.0"
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "smart-car-pilot"

// "core" est un module Kotlin/JVM pur (protocole, mapping joystick) : il ne
// dépend pas du SDK Android et se teste avec `gradle :core:test`, sans
// émulateur. "app" est l'application Android proprement dite, qui en
// dépend. Le découpage suit le même principe que vehicle/esp32-controller : séparer
// ce qui est testable sur PC de ce qui ne l'est pas.
include(":core")
include(":app")
