#include "communication.h"

#include <ArduinoJson.h>

#include <stdarg.h>
#include <stdio.h>
#include <string.h>

namespace protocol {

const char* errorCodeFor(ParseStatus status) {
    switch (status) {
        case ParseStatus::Ok:
            return nullptr;
        case ParseStatus::EmptyLine:
        case ParseStatus::InvalidJson:
            return ERROR_INVALID_JSON;
        case ParseStatus::UnknownType:
            return ERROR_UNKNOWN_TYPE;
        case ParseStatus::MissingField:
            return ERROR_MISSING_FIELD;
        case ParseStatus::InvalidSpeed:
            return ERROR_INVALID_SPEED;
        case ParseStatus::InvalidSteering:
            return ERROR_INVALID_STEERING;
        case ParseStatus::InvalidConfig:
            return ERROR_INVALID_CONFIG;
        case ParseStatus::InvalidTarget:
            return ERROR_INVALID_TARGET;
        case ParseStatus::InvalidDuty:
            return ERROR_INVALID_DUTY;
        case ParseStatus::InvalidDuration:
            return ERROR_INVALID_DURATION;
    }
    return ERROR_INVALID_JSON;
}

}  // namespace protocol

namespace communication {

namespace {

// Pool d'analyse JSON, alloué sur la pile : pas de tas, donc pas de
// fragmentation dans une boucle de contrôle qui tourne en continu.
//
// Le message le plus lourd est un CONFIG complet, six champs aux noms longs.
// La ligne étant reçue comme `const char*`, ArduinoJson recopie clés et
// chaînes dans le pool au lieu de pointer dedans : il faut donc compter la
// taille des noms de champs, pas seulement le nombre de valeurs. 256 octets
// n'y suffisaient pas — et c'est le test natif qui l'a montré, un créneau
// occupant plus de place sur un PC 64 bits que sur l'ESP32. 512 laisse de la
// marge des deux côtés.
constexpr size_t JSON_DOCUMENT_SIZE = 512;

// Petit écrivain de tampon. La télémétrie est sérialisée à la main plutôt
// qu'avec ArduinoJson pour garantir l'ordre exact des champs attendu par le
// Raspberry Pi ; ce garde-fou évite d'avoir à tester la troncature après
// chaque snprintf.
class LineWriter {
   public:
    LineWriter(char* buffer, size_t size) : buffer_(buffer), size_(size) {}

    // Ajoute du texte formaté. Une fois le tampon dépassé, l'écrivain reste
    // marqué en échec et les appels suivants ne font rien.
    void printf(const char* format, ...) __attribute__((format(printf, 2, 3))) {
        if (!ok_) {
            return;
        }
        va_list args;
        va_start(args, format);
        const int written =
            vsnprintf(buffer_ + used_, size_ - used_, format, args);
        va_end(args);

        if (written < 0 || static_cast<size_t>(written) >= size_ - used_) {
            ok_ = false;
            return;
        }
        used_ += static_cast<size_t>(written);
    }

    // Ajoute un flottant à deux décimales, ou `null` si la valeur est absente.
    void floatOrNull(bool present, float value) {
        if (present) {
            printf("%.2f", static_cast<double>(value));
        } else {
            printf("null");
        }
    }

    bool ok() const { return ok_; }
    size_t used() const { return used_; }

   private:
    char* buffer_;
    size_t size_;
    size_t used_ = 0;
    bool ok_ = true;
};

}  // namespace

namespace {

// Lit un entier facultatif borné. Renvoie false si le champ est présent mais
// inexploitable ; un champ absent est un succès qui ne modifie rien.
bool readOptionalInt(const JsonDocument& doc, const char* key, int low,
                     int high, bool& present, int& value) {
    if (!doc.containsKey(key)) {
        present = false;
        return true;
    }
    if (!doc[key].is<int>()) {
        return false;
    }
    const int candidate = doc[key].as<int>();
    if (candidate < low || candidate > high) {
        return false;
    }
    present = true;
    value = candidate;
    return true;
}

bool readOptionalBool(const JsonDocument& doc, const char* key, bool& present,
                      bool& value) {
    if (!doc.containsKey(key)) {
        present = false;
        return true;
    }
    if (!doc[key].is<bool>()) {
        return false;
    }
    present = true;
    value = doc[key].as<bool>();
    return true;
}

protocol::ParseStatus parseDrive(const JsonDocument& doc,
                                 protocol::DriveMessage& out) {
    // `is<T>()` distingue « champ absent » de « champ présent mais hors
    // plage », ce qui donne au Raspberry Pi un diagnostic exploitable.
    if (!doc["sequence"].is<long>() || !doc["speed_pct"].is<int>() ||
        !doc["steering_pct"].is<int>() || !doc["emergency"].is<bool>()) {
        return protocol::ParseStatus::MissingField;
    }

    const long sequence = doc["sequence"].as<long>();
    const int speed_pct = doc["speed_pct"].as<int>();
    const int steering_pct = doc["steering_pct"].as<int>();
    const bool emergency = doc["emergency"].as<bool>();

    if (speed_pct < protocol::SPEED_MIN_PCT ||
        speed_pct > protocol::SPEED_MAX_PCT) {
        return protocol::ParseStatus::InvalidSpeed;
    }
    if (steering_pct < protocol::STEERING_MIN_PCT ||
        steering_pct > protocol::STEERING_MAX_PCT) {
        return protocol::ParseStatus::InvalidSteering;
    }

    out.sequence = sequence;
    out.speed_pct = speed_pct;
    out.steering_pct = steering_pct;
    out.emergency = emergency;
    return protocol::ParseStatus::Ok;
}

protocol::ParseStatus parseConfig(const JsonDocument& doc,
                                  protocol::ConfigMessage& out) {
    if (!doc["sequence"].is<long>()) {
        return protocol::ParseStatus::MissingField;
    }

    protocol::ConfigMessage parsed = {};
    parsed.sequence = doc["sequence"].as<long>();

    if (!readOptionalInt(doc, "steering_gain_pct", 0, 100,
                         parsed.has_steering_gain, parsed.steering_gain_pct) ||
        !readOptionalInt(doc, "min_duty_pct", 0, 100, parsed.has_min_duty,
                         parsed.min_duty_pct) ||
        !readOptionalInt(doc, "max_duty_pct", 0, 100, parsed.has_max_duty,
                         parsed.max_duty_pct) ||
        !readOptionalBool(doc, "invert_left", parsed.has_invert_left,
                          parsed.invert_left) ||
        !readOptionalBool(doc, "invert_right", parsed.has_invert_right,
                          parsed.invert_right)) {
        return protocol::ParseStatus::InvalidConfig;
    }

    // Une ligne CONFIG sans aucun réglage est acceptée : elle sert à relire la
    // configuration courante, à laquelle l'ESP32 répond de la même façon.
    out = parsed;
    return protocol::ParseStatus::Ok;
}

protocol::ParseStatus parseTest(const JsonDocument& doc,
                                protocol::TestMessage& out) {
    if (!doc["sequence"].is<long>() || !doc["duty_pct"].is<int>() ||
        !doc["duration_ms"].is<long>()) {
        return protocol::ParseStatus::MissingField;
    }

    const char* target = doc["target"];
    if (target == nullptr) {
        return protocol::ParseStatus::MissingField;
    }

    protocol::TestTarget parsed_target;
    if (strcmp(target, "LEFT") == 0) {
        parsed_target = protocol::TestTarget::Left;
    } else if (strcmp(target, "RIGHT") == 0) {
        parsed_target = protocol::TestTarget::Right;
    } else if (strcmp(target, "BOTH") == 0) {
        parsed_target = protocol::TestTarget::Both;
    } else {
        return protocol::ParseStatus::InvalidTarget;
    }

    const int duty_pct = doc["duty_pct"].as<int>();
    if (duty_pct < -protocol::TEST_MAX_DUTY_PCT ||
        duty_pct > protocol::TEST_MAX_DUTY_PCT) {
        return protocol::ParseStatus::InvalidDuty;
    }

    const long duration = doc["duration_ms"].as<long>();
    if (duration <= 0 ||
        duration > static_cast<long>(protocol::TEST_MAX_DURATION_MS)) {
        return protocol::ParseStatus::InvalidDuration;
    }

    out.sequence = doc["sequence"].as<long>();
    out.target = parsed_target;
    out.duty_pct = duty_pct;
    out.duration_ms = static_cast<uint32_t>(duration);
    return protocol::ParseStatus::Ok;
}

}  // namespace

protocol::ParseStatus parseLine(const char* line,
                                protocol::ParsedMessage& out) {
    if (line == nullptr) {
        return protocol::ParseStatus::EmptyLine;
    }

    // Ignorer les espaces de tête laissés par un émetteur bavard.
    while (*line == ' ' || *line == '\t' || *line == '\r' || *line == '\n') {
        ++line;
    }
    if (*line == '\0') {
        return protocol::ParseStatus::EmptyLine;
    }

    StaticJsonDocument<JSON_DOCUMENT_SIZE> doc;
    const DeserializationError error = deserializeJson(doc, line);
    if (error) {
        return protocol::ParseStatus::InvalidJson;
    }

    const char* type = doc["type"];
    if (type == nullptr) {
        return protocol::ParseStatus::MissingField;
    }

    if (strcmp(type, "DRIVE") == 0) {
        const protocol::ParseStatus status = parseDrive(doc, out.drive);
        out.type = protocol::MessageType::Drive;
        return status;
    }
    if (strcmp(type, "CONFIG") == 0) {
        const protocol::ParseStatus status = parseConfig(doc, out.config);
        out.type = protocol::MessageType::Config;
        return status;
    }
    if (strcmp(type, "TEST") == 0) {
        const protocol::ParseStatus status = parseTest(doc, out.test);
        out.type = protocol::MessageType::Test;
        return status;
    }

    return protocol::ParseStatus::UnknownType;
}

protocol::ParseStatus parseDriveLine(const char* line,
                                     protocol::DriveMessage& out) {
    protocol::ParsedMessage message;
    const protocol::ParseStatus status = parseLine(line, message);
    if (status != protocol::ParseStatus::Ok) {
        return status;
    }
    if (message.type != protocol::MessageType::Drive) {
        return protocol::ParseStatus::UnknownType;
    }
    out = message.drive;
    return protocol::ParseStatus::Ok;
}

size_t buildConfigLine(long sequence, int steering_gain_pct, int min_duty_pct,
                       int max_duty_pct, bool invert_left, bool invert_right,
                       char* buffer, size_t buffer_size) {
    if (buffer == nullptr || buffer_size == 0) {
        return 0;
    }

    LineWriter writer(buffer, buffer_size);
    writer.printf(
        "{\"type\":\"CONFIG\",\"sequence\":%ld,\"steering_gain_pct\":%d,"
        "\"min_duty_pct\":%d,\"max_duty_pct\":%d,\"invert_left\":%s,"
        "\"invert_right\":%s}\n",
        sequence, steering_gain_pct, min_duty_pct, max_duty_pct,
        invert_left ? "true" : "false", invert_right ? "true" : "false");

    if (!writer.ok()) {
        buffer[0] = '\0';
        return 0;
    }
    return writer.used();
}

size_t buildTelemetryLine(const protocol::TelemetryMessage& telemetry,
                          char* buffer, size_t buffer_size) {
    if (buffer == nullptr || buffer_size == 0) {
        return 0;
    }

    LineWriter writer(buffer, buffer_size);

    writer.printf("{\"type\":\"TELEMETRY\",\"sequence\":%ld,\"status\":\"%s\"",
                  telemetry.sequence, telemetry.status);

    writer.printf(",\"obstacle_distance_m\":");
    writer.floatOrNull(telemetry.has_obstacle_distance,
                       telemetry.obstacle_distance_m);

    if (telemetry.has_battery) {
        writer.printf(",\"battery_pct\":%d", telemetry.battery_pct);
    } else {
        writer.printf(",\"battery_pct\":null");
    }

    writer.printf(",\"left_rpm\":");
    writer.floatOrNull(telemetry.has_rpm, telemetry.left_rpm);
    writer.printf(",\"right_rpm\":");
    writer.floatOrNull(telemetry.has_rpm, telemetry.right_rpm);

    if (telemetry.error != nullptr) {
        writer.printf(",\"error\":\"%s\"}\n", telemetry.error);
    } else {
        writer.printf(",\"error\":null}\n");
    }

    if (!writer.ok()) {
        buffer[0] = '\0';
        return 0;
    }
    return writer.used();
}

}  // namespace communication
