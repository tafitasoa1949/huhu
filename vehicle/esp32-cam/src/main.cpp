#include <Arduino.h>
#include <WiFi.h>
#include <esp_camera.h>
#include <esp_http_server.h>

#include "cam_config.h"

// Firmware de la caméra de conduite (ESP32-CAM).
//
// Rôle : rejoindre le Wi-Fi local et exposer un flux MJPEG en HTTP. C'est la
// seule caméra du véhicule (docs/mobile-app.md, §1) : le Raspberry Pi lit ce
// flux à la fois pour la vision (détection de piste, Personne 1) et pour
// l'affichage relayé à l'application mobile. Contrairement à
// esp32-controller, cette carte ne parle jamais à l'ESP32 de contrôle ; le
// lien avec le pilotage passe entièrement par le Raspberry Pi. Une perte de
// ce flux n'est donc pas un simple incident d'affichage : c'est une perte de
// piste, que le moteur de décision doit traiter comme telle
// (lane.detected = false).

namespace {

// Séparateur multipart utilisé par le flux "motion JPEG" et sa syntaxe
// répétée : navigateurs et lecteurs vidéo la reconnaissent nativement,
// aucun décodage particulier n'est requis côté client.
constexpr const char* STREAM_CONTENT_TYPE =
    "multipart/x-mixed-replace;boundary=frame";
constexpr const char* STREAM_BOUNDARY = "\r\n--frame\r\n";
constexpr const char* STREAM_PART_HEADER =
    "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

httpd_handle_t stream_server = nullptr;

// Débit d'images lissé (moyenne mobile exponentielle) et horodatage de la
// dernière frame effectivement envoyée — mis à jour dans handleStream(),
// lu dans handleStatus(). Reflète le débit *livré*, pas la cadence de
// capture : c'est ce qui compte pour juger si le Wi-Fi tient la charge.
float stream_fps = 0.0f;
uint32_t last_frame_sent_ms = 0;

void recordFrameSent() {
    const uint32_t now_ms = millis();
    if (last_frame_sent_ms != 0) {
        const uint32_t delta_ms = now_ms - last_frame_sent_ms;
        if (delta_ms > 0) {
            const float instant_fps = 1000.0f / static_cast<float>(delta_ms);
            stream_fps = stream_fps * 0.8f + instant_fps * 0.2f;
        }
    }
    last_frame_sent_ms = now_ms;
}

// La résolution effective peut différer de CAM_FRAME_SIZE si le firmware
// est retombé en QQVGA faute de PSRAM (voir initCamera) : on l'interroge au
// capteur plutôt que de dupliquer un état qui pourrait diverger.
void currentFrameDimensions(int& width, int& height) {
    sensor_t* sensor = esp_camera_sensor_get();
    if (sensor == nullptr) {
        width = 0;
        height = 0;
        return;
    }
    switch (sensor->status.framesize) {
        case FRAMESIZE_QQVGA:
            width = 160;
            height = 120;
            break;
        case FRAMESIZE_QVGA:
            width = 320;
            height = 240;
            break;
        case FRAMESIZE_VGA:
            width = 640;
            height = 480;
            break;
        default:
            width = 0;
            height = 0;
            break;
    }
}

bool initCamera() {
    camera_config_t config = {};
    config.ledc_channel = LEDC_CHANNEL_0;
    config.ledc_timer = LEDC_TIMER_0;
    config.pin_d0 = CAM_PIN_D0;
    config.pin_d1 = CAM_PIN_D1;
    config.pin_d2 = CAM_PIN_D2;
    config.pin_d3 = CAM_PIN_D3;
    config.pin_d4 = CAM_PIN_D4;
    config.pin_d5 = CAM_PIN_D5;
    config.pin_d6 = CAM_PIN_D6;
    config.pin_d7 = CAM_PIN_D7;
    config.pin_xclk = CAM_PIN_XCLK;
    config.pin_pclk = CAM_PIN_PCLK;
    config.pin_vsync = CAM_PIN_VSYNC;
    config.pin_href = CAM_PIN_HREF;
    config.pin_sscb_sda = CAM_PIN_SIOD;
    config.pin_sscb_scl = CAM_PIN_SIOC;
    config.pin_pwdn = CAM_PIN_PWDN;
    config.pin_reset = CAM_PIN_RESET;
    config.xclk_freq_hz = 20000000;
    config.pixel_format = PIXFORMAT_JPEG;
    // CAMERA_GRAB_LATEST : en cas de flux plus lent que la capture, on jette
    // les anciennes frames plutôt que de les mettre en file. Pour un flux
    // vidéo en direct, une image récente vaut mieux qu'une file de retard.
    config.grab_mode = CAMERA_GRAB_LATEST;

    if (psramFound()) {
        config.frame_size = CAM_FRAME_SIZE;
        config.jpeg_quality = CAM_JPEG_QUALITY;
        config.fb_count = CAM_FB_COUNT;
        config.fb_location = CAMERA_FB_IN_PSRAM;
    } else {
        // Sans PSRAM utilisable, le double tampon ne tient pas en DRAM.
        // Retomber sur une image plus petite et un seul tampon vaut mieux
        // qu'un échec d'initialisation : un flux dégradé (QQVGA) laisse au
        // moins une chance à la vision, alors qu'une carte qui refuse de
        // démarrer n'en laisse aucune.
        Serial.println("PSRAM absente, repli en QQVGA sur un seul tampon");
        config.frame_size = FRAMESIZE_QQVGA;
        config.jpeg_quality = CAM_JPEG_QUALITY + 6;
        config.fb_count = 1;
        config.fb_location = CAMERA_FB_IN_DRAM;
    }

    const esp_err_t result = esp_camera_init(&config);
    if (result != ESP_OK) {
        Serial.printf("esp_camera_init a échoué : 0x%x\n", result);
        return false;
    }
    return true;
}

// GET /stream : le flux continu, consommé par la vision (Raspberry Pi) et
// l'affichage (application mobile).
esp_err_t handleStream(httpd_req_t* request) {
    esp_err_t result = httpd_resp_set_type(request, STREAM_CONTENT_TYPE);
    if (result != ESP_OK) {
        return result;
    }

    char part_header[64];

    while (true) {
        camera_fb_t* frame = esp_camera_fb_get();
        if (frame == nullptr) {
            Serial.println("esp_camera_fb_get a renvoyé nullptr, arrêt du flux");
            return ESP_FAIL;
        }

        result = httpd_resp_send_chunk(request, STREAM_BOUNDARY,
                                        strlen(STREAM_BOUNDARY));
        if (result == ESP_OK) {
            const int header_length = snprintf(
                part_header, sizeof(part_header), STREAM_PART_HEADER,
                static_cast<unsigned>(frame->len));
            result = httpd_resp_send_chunk(request, part_header, header_length);
        }
        if (result == ESP_OK) {
            result = httpd_resp_send_chunk(
                request, reinterpret_cast<const char*>(frame->buf), frame->len);
        }

        esp_camera_fb_return(frame);

        if (result != ESP_OK) {
            // Le client s'est déconnecté (téléphone verrouillé, appli
            // fermée) : ce n'est pas une erreur, juste la fin de cette
            // requête. httpd_resp_send_chunk(..., 0) ci-dessous fermerait
            // une connexion déjà morte, donc on sort directement.
            break;
        }

        recordFrameSent();
    }

    return ESP_OK;
}

// GET /snapshot : une seule JPEG, hors du flux continu. Un `curl` ou un
// navigateur suffisent à vérifier que la caméra voit quelque chose, sans
// avoir à parser du multipart pour une simple sonde de débogage.
esp_err_t handleSnapshot(httpd_req_t* request) {
    camera_fb_t* frame = esp_camera_fb_get();
    if (frame == nullptr) {
        Serial.println("esp_camera_fb_get a renvoyé nullptr (snapshot)");
        httpd_resp_send_500(request);
        return ESP_FAIL;
    }

    esp_err_t result = httpd_resp_set_type(request, "image/jpeg");
    if (result == ESP_OK) {
        result = httpd_resp_send(request, reinterpret_cast<const char*>(frame->buf),
                                  frame->len);
    }

    esp_camera_fb_return(frame);
    return result;
}

// GET /status : télémétrie minimale de la carte — pas de la voiture. Sert à
// diagnostiquer "le Wi-Fi tient-il la charge ?" (fps, RSSI) et "la carte
// tient-elle dans la durée ?" (uptime, tas libre), indépendamment de ce que
// fait le Raspberry Pi avec les frames.
esp_err_t handleStatus(httpd_req_t* request) {
    int width = 0;
    int height = 0;
    currentFrameDimensions(width, height);

    char body[192];
    const int length = snprintf(
        body, sizeof(body),
        "{\"uptime_ms\":%lu,\"rssi_dbm\":%d,\"free_heap_bytes\":%lu,"
        "\"fps\":%.1f,\"frame_width\":%d,\"frame_height\":%d,\"jpeg_quality\":%d}",
        static_cast<unsigned long>(millis()), WiFi.RSSI(),
        static_cast<unsigned long>(ESP.getFreeHeap()), stream_fps, width, height,
        CAM_JPEG_QUALITY);

    esp_err_t result = httpd_resp_set_type(request, "application/json");
    if (result == ESP_OK) {
        result = httpd_resp_send(request, body, length);
    }
    return result;
}

bool startStreamServer() {
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.server_port = STREAM_SERVER_PORT;
    config.ctrl_port = STREAM_SERVER_PORT;

    const esp_err_t result = httpd_start(&stream_server, &config);
    if (result != ESP_OK) {
        Serial.printf("httpd_start a échoué : 0x%x\n", result);
        return false;
    }

    const httpd_uri_t stream_uri = {
        .uri = "/stream",
        .method = HTTP_GET,
        .handler = handleStream,
        .user_ctx = nullptr,
    };
    httpd_register_uri_handler(stream_server, &stream_uri);

    const httpd_uri_t snapshot_uri = {
        .uri = "/snapshot",
        .method = HTTP_GET,
        .handler = handleSnapshot,
        .user_ctx = nullptr,
    };
    httpd_register_uri_handler(stream_server, &snapshot_uri);

    const httpd_uri_t status_uri = {
        .uri = "/status",
        .method = HTTP_GET,
        .handler = handleStatus,
        .user_ctx = nullptr,
    };
    httpd_register_uri_handler(stream_server, &status_uri);

    return true;
}

void connectWifi() {
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    Serial.printf("Connexion au réseau %s", WIFI_SSID);
    const uint32_t start_ms = millis();
    while (WiFi.status() != WL_CONNECTED) {
        if (millis() - start_ms > WIFI_CONNECT_TIMEOUT_MS) {
            // Pas de mise en veille silencieuse : on redémarre la carte
            // pour repartir d'un état propre plutôt que de rester bloqué
            // dans une tentative de connexion qui n'aboutira pas.
            Serial.println("\nDélai de connexion Wi-Fi dépassé, redémarrage");
            ESP.restart();
        }
        delay(250);
        Serial.print(".");
    }
    Serial.printf("\nConnecté, adresse IP : %s\n", WiFi.localIP().toString().c_str());
    Serial.printf("Flux MJPEG : http://%s:%d/stream\n",
                   WiFi.localIP().toString().c_str(), STREAM_SERVER_PORT);
    Serial.printf("Instantané : http://%s:%d/snapshot\n",
                   WiFi.localIP().toString().c_str(), STREAM_SERVER_PORT);
    Serial.printf("État : http://%s:%d/status\n",
                   WiFi.localIP().toString().c_str(), STREAM_SERVER_PORT);
}

}  // namespace

void setup() {
    Serial.begin(115200);
    Serial.println();

    pinMode(CAM_PIN_LED, OUTPUT);
    digitalWrite(CAM_PIN_LED, LOW);

    if (!initCamera()) {
        // Sans caméra fonctionnelle, il n'y a rien à servir : on le signale
        // en boucle plutôt que de démarrer un serveur qui ne renverrait que
        // des erreurs à chaque requête.
        while (true) {
            Serial.println("Caméra indisponible, vérifier le câblage OV2640");
            delay(2000);
        }
    }

    connectWifi();

    if (startStreamServer()) {
        // Témoin « serveur prêt » : trois clignotements brefs, puis extinction.
        // La LED de la carte AI-Thinker est un flash très puissant — la
        // laisser allumée en continu chaufferait et éblouirait la scène
        // filmée, alors qu'elle n'a aucun rôle d'éclairage ici.
        for (int i = 0; i < 3; ++i) {
            digitalWrite(CAM_PIN_LED, HIGH);
            delay(80);
            digitalWrite(CAM_PIN_LED, LOW);
            delay(120);
        }
    }
}

void loop() {
    // Le serveur HTTP tourne dans sa propre tâche FreeRTOS ; il n'y a rien à
    // faire dans la boucle principale au-delà de surveiller le Wi-Fi.
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("Wi-Fi perdu, reconnexion");
        connectWifi();
    }
    delay(1000);
}
