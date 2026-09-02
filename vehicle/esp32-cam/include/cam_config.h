#pragma once

// Configuration de la caméra de conduite (ESP32-CAM, module AI-Thinker).
//
// Rôle dans l'architecture (docs/mobile-app.md, §1 "Caméras") : c'est la
// seule caméra du véhicule — le Raspberry Pi n'a pas de capteur CSI/USB qui
// lui soit propre. Ce module alimente à la fois la vision (Personne 1,
// détection de piste) et l'affichage relayé à l'application mobile.
// L'ESP32-CAM ne fait que du MJPEG direct sur le Wi-Fi local, sans pile
// WebRTC embarquée : latence et résolution sont donc les facteurs limitants
// de toute la chaîne de vision, pas seulement de l'affichage.
//
// Toutes les valeurs propres au déploiement (identifiants Wi-Fi) sont
// regroupées ici, sur le modèle de esp32-controller/include/pin_config.h :
// un seul fichier à modifier, aucun autre ne doit contenir de secret ni de
// numéro de broche.

// --------------------------------------------------------------------------
// Wi-Fi
// --------------------------------------------------------------------------
// WIFI_SSID / WIFI_PASSWORD vivent dans wifi_secrets.h, un fichier non
// versionné (voir wifi_secrets.example.h pour le modèle à copier). Ça évite
// qu'un vrai identifiant se retrouve dans l'historique Git par erreur.
#include "wifi_secrets.h"

// Délai maximal pour rejoindre le réseau avant de retenter (ms). En dessous
// de ce délai, l'ESP32-CAM démarre son serveur dès que la connexion
// aboutit ; au-delà, il redémarre la tentative plutôt que de rester bloqué
// indéfiniment sur un réseau hors de portée.
#define WIFI_CONNECT_TIMEOUT_MS 15000

// --------------------------------------------------------------------------
// Brochage caméra — module AI-Thinker ESP32-CAM
// --------------------------------------------------------------------------
// Brochage figé par le module (OV2640 soudé), pas par un choix de câblage :
// contrairement à esp32-controller, il n'y a rien à recâbler ici.

#define CAM_PIN_PWDN 32
#define CAM_PIN_RESET -1  // pas de broche de reset dédiée sur ce module
#define CAM_PIN_XCLK 0
#define CAM_PIN_SIOD 26
#define CAM_PIN_SIOC 27

#define CAM_PIN_D7 35
#define CAM_PIN_D6 34
#define CAM_PIN_D5 39
#define CAM_PIN_D4 36
#define CAM_PIN_D3 21
#define CAM_PIN_D2 19
#define CAM_PIN_D1 18
#define CAM_PIN_D0 5
#define CAM_PIN_VSYNC 25
#define CAM_PIN_HREF 23
#define CAM_PIN_PCLK 22

// LED intégrée (flash), utilisée uniquement comme témoin de démarrage du
// serveur — pas d'éclairage vidéo, inutile pour la conduite.
#define CAM_PIN_LED 4

// --------------------------------------------------------------------------
// Flux vidéo
// --------------------------------------------------------------------------
// Résolution volontairement modeste : point de départ prudent en attendant
// de mesurer ce dont la détection de piste a réellement besoin. Le Wi-Fi de
// l'ESP32-CAM est le facteur limitant de toute la chaîne — vision comme
// affichage (docs/mobile-app.md). FRAMESIZE_VGA (640x480) sature vite un
// module qui n'a que 4 Mo de PSRAM à partager avec les tampons JPEG.
#define CAM_FRAME_SIZE FRAMESIZE_QVGA  // 320x240
#define CAM_JPEG_QUALITY 12            // 0 (meilleure) à 63 (pire)
#define CAM_FB_COUNT 2                 // double tampon, nécessite la PSRAM

// Port HTTP du flux MJPEG.
#define STREAM_SERVER_PORT 81
