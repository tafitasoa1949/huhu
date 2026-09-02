#pragma once

// Modèle pour les identifiants Wi-Fi réels.
//
// 1. Copier ce fichier en `wifi_secrets.h` (même dossier).
// 2. Renseigner le SSID et le mot de passe du réseau de démonstration —
//    le même que celui utilisé par le Raspberry Pi et le téléphone.
// 3. Ne jamais committer `wifi_secrets.h` : il est exclu par .gitignore.
//    `cam_config.h` l'inclut, aucun autre fichier ne doit contenir ces
//    valeurs.

#define WIFI_SSID "CHANGE_ME_SSID"
#define WIFI_PASSWORD "CHANGE_ME_PASSWORD"
