buildscript {
    val agp_version by extra("9.2.1")
}
// Volontairement vide : chaque module déclare et applique ses propres
// plugins (voir core/build.gradle.kts et app/build.gradle.kts).
//
// Les décrire ici avec `apply false`, comme le fait le gabarit Android
// Studio standard, forcerait Gradle à résoudre le plugin Android à chaque
// configuration du projet racine — y compris pour `gradle :core:test`, qui
// ne devrait avoir besoin que d'un JDK et jamais du SDK Android. Ce module
// racine ne porte donc aucune dépendance vers l'écosystème Android.
