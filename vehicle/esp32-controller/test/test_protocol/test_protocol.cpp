#include <string.h>
#include <unity.h>

#include "communication.h"
#include "protocol.h"

// Tests du protocole série : décodage des commandes DRIVE et sérialisation de
// la télémétrie. Ces tests fixent le contrat de la section 5 du plan côté
// ESP32 ; leurs équivalents Python sont dans raspberry-pi/tests/.
//
// Exécution : pio test -e native

namespace {

protocol::TelemetryMessage emptyTelemetry() {
    protocol::TelemetryMessage telemetry;
    telemetry.sequence = 0;
    telemetry.status = protocol::STATUS_OK;
    telemetry.error = nullptr;
    telemetry.has_obstacle_distance = false;
    telemetry.obstacle_distance_m = 0.0f;
    telemetry.has_battery = false;
    telemetry.battery_pct = 0;
    telemetry.has_rpm = false;
    telemetry.left_rpm = 0.0f;
    telemetry.right_rpm = 0.0f;
    return telemetry;
}

protocol::ParseStatus parse(const char* line) {
    protocol::DriveMessage message;
    return communication::parseDriveLine(line, message);
}

}  // namespace

// --------------------------------------------------------------------------
// Décodage
// --------------------------------------------------------------------------

void test_official_drive_line_is_accepted() {
    // Ligne exacte de la section 5.2 du plan.
    const char* line =
        "{\"type\":\"DRIVE\",\"sequence\":18,\"speed_pct\":35,"
        "\"steering_pct\":-25,\"emergency\":false}";

    protocol::DriveMessage message;
    TEST_ASSERT_EQUAL(protocol::ParseStatus::Ok,
                      communication::parseDriveLine(line, message));
    TEST_ASSERT_EQUAL_INT(18, message.sequence);
    TEST_ASSERT_EQUAL_INT(35, message.speed_pct);
    TEST_ASSERT_EQUAL_INT(-25, message.steering_pct);
    TEST_ASSERT_FALSE(message.emergency);
}

void test_emergency_flag_is_decoded() {
    const char* line =
        "{\"type\":\"DRIVE\",\"sequence\":7,\"speed_pct\":0,"
        "\"steering_pct\":0,\"emergency\":true}";

    protocol::DriveMessage message;
    TEST_ASSERT_EQUAL(protocol::ParseStatus::Ok,
                      communication::parseDriveLine(line, message));
    TEST_ASSERT_TRUE(message.emergency);
}

void test_boundary_values_are_accepted() {
    // Scénario S09 : la limite gauche est valide.
    TEST_ASSERT_EQUAL(protocol::ParseStatus::Ok,
                      parse("{\"type\":\"DRIVE\",\"sequence\":1,"
                            "\"speed_pct\":0,\"steering_pct\":-100,"
                            "\"emergency\":false}"));
    TEST_ASSERT_EQUAL(protocol::ParseStatus::Ok,
                      parse("{\"type\":\"DRIVE\",\"sequence\":1,"
                            "\"speed_pct\":100,\"steering_pct\":100,"
                            "\"emergency\":false}"));
}

void test_steering_out_of_range_is_rejected() {
    // Scénario S10 : -101 doit être refusé.
    TEST_ASSERT_EQUAL(protocol::ParseStatus::InvalidSteering,
                      parse("{\"type\":\"DRIVE\",\"sequence\":1,"
                            "\"speed_pct\":30,\"steering_pct\":-101,"
                            "\"emergency\":false}"));
    TEST_ASSERT_EQUAL(protocol::ParseStatus::InvalidSteering,
                      parse("{\"type\":\"DRIVE\",\"sequence\":1,"
                            "\"speed_pct\":30,\"steering_pct\":101,"
                            "\"emergency\":false}"));
}

void test_speed_out_of_range_is_rejected() {
    TEST_ASSERT_EQUAL(protocol::ParseStatus::InvalidSpeed,
                      parse("{\"type\":\"DRIVE\",\"sequence\":1,"
                            "\"speed_pct\":-1,\"steering_pct\":0,"
                            "\"emergency\":false}"));
    TEST_ASSERT_EQUAL(protocol::ParseStatus::InvalidSpeed,
                      parse("{\"type\":\"DRIVE\",\"sequence\":1,"
                            "\"speed_pct\":101,\"steering_pct\":0,"
                            "\"emergency\":false}"));
}

void test_malformed_json_is_rejected() {
    // Scénario S11 : ligne incomplète.
    TEST_ASSERT_EQUAL(protocol::ParseStatus::InvalidJson,
                      parse("{\"type\":\"DRIVE\",\"sequence\":1,\"speed_pct\""));
    TEST_ASSERT_EQUAL(protocol::ParseStatus::InvalidJson, parse("pas du json"));
}

void test_empty_line_is_reported_separately() {
    TEST_ASSERT_EQUAL(protocol::ParseStatus::EmptyLine, parse(""));
    TEST_ASSERT_EQUAL(protocol::ParseStatus::EmptyLine, parse("   \r\n"));
    TEST_ASSERT_EQUAL(protocol::ParseStatus::EmptyLine, parse(nullptr));
}

void test_unknown_type_is_rejected() {
    TEST_ASSERT_EQUAL(protocol::ParseStatus::UnknownType,
                      parse("{\"type\":\"PING\",\"sequence\":1,"
                            "\"speed_pct\":0,\"steering_pct\":0,"
                            "\"emergency\":false}"));
}

void test_missing_field_is_rejected() {
    // steering_pct absent.
    TEST_ASSERT_EQUAL(protocol::ParseStatus::MissingField,
                      parse("{\"type\":\"DRIVE\",\"sequence\":1,"
                            "\"speed_pct\":30,\"emergency\":false}"));
    // type absent.
    TEST_ASSERT_EQUAL(protocol::ParseStatus::MissingField,
                      parse("{\"sequence\":1,\"speed_pct\":30,"
                            "\"steering_pct\":0,\"emergency\":false}"));
}

void test_rejected_command_leaves_the_output_untouched() {
    // Une commande refusée ne doit pas écraser la dernière commande valide :
    // c'est ce qui permet au firmware de garder un état cohérent.
    protocol::DriveMessage message = {5, 40, -10, false};
    communication::parseDriveLine("{\"type\":\"DRIVE\"}", message);

    TEST_ASSERT_EQUAL_INT(5, message.sequence);
    TEST_ASSERT_EQUAL_INT(40, message.speed_pct);
    TEST_ASSERT_EQUAL_INT(-10, message.steering_pct);
}

void test_leading_whitespace_is_tolerated() {
    TEST_ASSERT_EQUAL(protocol::ParseStatus::Ok,
                      parse("  {\"type\":\"DRIVE\",\"sequence\":1,"
                            "\"speed_pct\":30,\"steering_pct\":0,"
                            "\"emergency\":false}"));
}

// --------------------------------------------------------------------------
// Codes d'erreur
// --------------------------------------------------------------------------

void test_error_codes_match_the_protocol() {
    TEST_ASSERT_NULL(protocol::errorCodeFor(protocol::ParseStatus::Ok));
    TEST_ASSERT_EQUAL_STRING(
        protocol::ERROR_INVALID_STEERING,
        protocol::errorCodeFor(protocol::ParseStatus::InvalidSteering));
    TEST_ASSERT_EQUAL_STRING(
        protocol::ERROR_INVALID_SPEED,
        protocol::errorCodeFor(protocol::ParseStatus::InvalidSpeed));
    TEST_ASSERT_EQUAL_STRING(
        protocol::ERROR_INVALID_JSON,
        protocol::errorCodeFor(protocol::ParseStatus::InvalidJson));
    TEST_ASSERT_EQUAL_STRING(
        protocol::ERROR_MISSING_FIELD,
        protocol::errorCodeFor(protocol::ParseStatus::MissingField));
    TEST_ASSERT_EQUAL_STRING(
        protocol::ERROR_UNKNOWN_TYPE,
        protocol::errorCodeFor(protocol::ParseStatus::UnknownType));
}

// --------------------------------------------------------------------------
// Sérialisation de la télémétrie
// --------------------------------------------------------------------------

void test_telemetry_matches_the_official_example() {
    // Ligne exacte de la section 5.3 du plan.
    protocol::TelemetryMessage telemetry = emptyTelemetry();
    telemetry.sequence = 18;
    telemetry.status = protocol::STATUS_OK;
    telemetry.has_obstacle_distance = true;
    telemetry.obstacle_distance_m = 1.42f;
    telemetry.has_battery = true;
    telemetry.battery_pct = 82;
    telemetry.has_rpm = true;
    telemetry.left_rpm = 118.0f;
    telemetry.right_rpm = 120.0f;

    char buffer[protocol::MAX_TELEMETRY_LENGTH];
    const size_t written =
        communication::buildTelemetryLine(telemetry, buffer, sizeof(buffer));

    TEST_ASSERT_TRUE(written > 0);
    TEST_ASSERT_EQUAL_STRING(
        "{\"type\":\"TELEMETRY\",\"sequence\":18,\"status\":\"OK\","
        "\"obstacle_distance_m\":1.42,\"battery_pct\":82,"
        "\"left_rpm\":118.00,\"right_rpm\":120.00,\"error\":null}\n",
        buffer);
}

void test_telemetry_serialises_absent_values_as_null() {
    // Cas d'une carte ESP32 nue : aucun capteur branché.
    protocol::TelemetryMessage telemetry = emptyTelemetry();
    telemetry.sequence = 3;

    char buffer[protocol::MAX_TELEMETRY_LENGTH];
    communication::buildTelemetryLine(telemetry, buffer, sizeof(buffer));

    TEST_ASSERT_EQUAL_STRING(
        "{\"type\":\"TELEMETRY\",\"sequence\":3,\"status\":\"OK\","
        "\"obstacle_distance_m\":null,\"battery_pct\":null,"
        "\"left_rpm\":null,\"right_rpm\":null,\"error\":null}\n",
        buffer);
}

void test_telemetry_reports_errors() {
    // Ligne exacte de la section 5.4 du plan.
    protocol::TelemetryMessage telemetry = emptyTelemetry();
    telemetry.sequence = 18;
    telemetry.status = protocol::STATUS_ERROR;
    telemetry.error = protocol::ERROR_INVALID_STEERING;

    char buffer[protocol::MAX_TELEMETRY_LENGTH];
    communication::buildTelemetryLine(telemetry, buffer, sizeof(buffer));

    TEST_ASSERT_EQUAL_STRING(
        "{\"type\":\"TELEMETRY\",\"sequence\":18,\"status\":\"ERROR\","
        "\"obstacle_distance_m\":null,\"battery_pct\":null,"
        "\"left_rpm\":null,\"right_rpm\":null,"
        "\"error\":\"INVALID_STEERING\"}\n",
        buffer);
}

void test_telemetry_line_ends_with_a_newline() {
    protocol::TelemetryMessage telemetry = emptyTelemetry();

    char buffer[protocol::MAX_TELEMETRY_LENGTH];
    const size_t written =
        communication::buildTelemetryLine(telemetry, buffer, sizeof(buffer));

    TEST_ASSERT_EQUAL_CHAR('\n', buffer[written - 1]);
    TEST_ASSERT_EQUAL_size_t(strlen(buffer), written);
}

void test_telemetry_fails_cleanly_on_a_small_buffer() {
    // Un tampon trop court doit donner une chaîne vide et un retour nul,
    // jamais une ligne JSON tronquée que le Raspberry Pi essaierait de lire.
    protocol::TelemetryMessage telemetry = emptyTelemetry();

    char buffer[16];
    const size_t written =
        communication::buildTelemetryLine(telemetry, buffer, sizeof(buffer));

    TEST_ASSERT_EQUAL_size_t(0, written);
    TEST_ASSERT_EQUAL_STRING("", buffer);
}

void setUp() {}
void tearDown() {}

int main() {
    UNITY_BEGIN();
    RUN_TEST(test_official_drive_line_is_accepted);
    RUN_TEST(test_emergency_flag_is_decoded);
    RUN_TEST(test_boundary_values_are_accepted);
    RUN_TEST(test_steering_out_of_range_is_rejected);
    RUN_TEST(test_speed_out_of_range_is_rejected);
    RUN_TEST(test_malformed_json_is_rejected);
    RUN_TEST(test_empty_line_is_reported_separately);
    RUN_TEST(test_unknown_type_is_rejected);
    RUN_TEST(test_missing_field_is_rejected);
    RUN_TEST(test_rejected_command_leaves_the_output_untouched);
    RUN_TEST(test_leading_whitespace_is_tolerated);
    RUN_TEST(test_error_codes_match_the_protocol);
    RUN_TEST(test_telemetry_matches_the_official_example);
    RUN_TEST(test_telemetry_serialises_absent_values_as_null);
    RUN_TEST(test_telemetry_reports_errors);
    RUN_TEST(test_telemetry_line_ends_with_a_newline);
    RUN_TEST(test_telemetry_fails_cleanly_on_a_small_buffer);
    return UNITY_END();
}
