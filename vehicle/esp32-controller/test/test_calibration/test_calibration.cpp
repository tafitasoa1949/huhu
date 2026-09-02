#include <string.h>
#include <unity.h>

#include "communication.h"
#include "protocol.h"

// Tests des messages de calibration : CONFIG (réglage à chaud) et TEST
// (essai moteur roue par roue). Leurs équivalents Python sont dans
// raspberry-pi/tests/test_calibration.py.
//
// Exécution : pio test -e native

namespace {

protocol::ParseStatus parse(const char* line, protocol::ParsedMessage& out) {
    return communication::parseLine(line, out);
}

}  // namespace

// --------------------------------------------------------------------------
// Aiguillage par type
// --------------------------------------------------------------------------

void test_the_type_field_selects_the_message() {
    protocol::ParsedMessage message;

    TEST_ASSERT_EQUAL(protocol::ParseStatus::Ok,
                      parse("{\"type\":\"DRIVE\",\"sequence\":1,"
                            "\"speed_pct\":30,\"steering_pct\":0,"
                            "\"emergency\":false}",
                            message));
    TEST_ASSERT_EQUAL(protocol::MessageType::Drive, message.type);

    TEST_ASSERT_EQUAL(protocol::ParseStatus::Ok,
                      parse("{\"type\":\"CONFIG\",\"sequence\":2}", message));
    TEST_ASSERT_EQUAL(protocol::MessageType::Config, message.type);

    TEST_ASSERT_EQUAL(protocol::ParseStatus::Ok,
                      parse("{\"type\":\"TEST\",\"sequence\":3,"
                            "\"target\":\"LEFT\",\"duty_pct\":30,"
                            "\"duration_ms\":300}",
                            message));
    TEST_ASSERT_EQUAL(protocol::MessageType::Test, message.type);
}

void test_parse_drive_line_still_refuses_other_types() {
    // Le raccourci historique n'accepte qu'une commande de mouvement : un
    // appelant qui demande explicitement un DRIVE ne doit pas recevoir
    // silencieusement autre chose.
    protocol::DriveMessage drive;
    TEST_ASSERT_EQUAL(
        protocol::ParseStatus::UnknownType,
        communication::parseDriveLine("{\"type\":\"CONFIG\",\"sequence\":1}",
                                      drive));
}

// --------------------------------------------------------------------------
// CONFIG
// --------------------------------------------------------------------------

void test_config_applies_only_the_fields_it_mentions() {
    protocol::ParsedMessage message;

    TEST_ASSERT_EQUAL(
        protocol::ParseStatus::Ok,
        parse("{\"type\":\"CONFIG\",\"sequence\":4,\"invert_left\":true}",
              message));

    TEST_ASSERT_TRUE(message.config.has_invert_left);
    TEST_ASSERT_TRUE(message.config.invert_left);
    // Les autres réglages ne sont pas mentionnés, donc pas touchés.
    TEST_ASSERT_FALSE(message.config.has_invert_right);
    TEST_ASSERT_FALSE(message.config.has_min_duty);
    TEST_ASSERT_FALSE(message.config.has_max_duty);
    TEST_ASSERT_FALSE(message.config.has_steering_gain);
}

void test_config_reads_every_setting() {
    protocol::ParsedMessage message;

    TEST_ASSERT_EQUAL(
        protocol::ParseStatus::Ok,
        parse("{\"type\":\"CONFIG\",\"sequence\":5,\"steering_gain_pct\":70,"
              "\"min_duty_pct\":18,\"max_duty_pct\":55,\"invert_left\":true,"
              "\"invert_right\":false}",
              message));

    TEST_ASSERT_EQUAL_INT(70, message.config.steering_gain_pct);
    TEST_ASSERT_EQUAL_INT(18, message.config.min_duty_pct);
    TEST_ASSERT_EQUAL_INT(55, message.config.max_duty_pct);
    TEST_ASSERT_TRUE(message.config.invert_left);
    TEST_ASSERT_TRUE(message.config.has_invert_right);
    TEST_ASSERT_FALSE(message.config.invert_right);
}

void test_an_empty_config_is_a_read_request() {
    // Sans aucun réglage, la ligne sert à relire la configuration courante.
    protocol::ParsedMessage message;

    TEST_ASSERT_EQUAL(protocol::ParseStatus::Ok,
                      parse("{\"type\":\"CONFIG\",\"sequence\":6}", message));
    TEST_ASSERT_EQUAL_INT(6, message.config.sequence);
}

void test_config_out_of_range_is_rejected() {
    protocol::ParsedMessage message;

    TEST_ASSERT_EQUAL(
        protocol::ParseStatus::InvalidConfig,
        parse("{\"type\":\"CONFIG\",\"sequence\":1,\"max_duty_pct\":101}",
              message));
    TEST_ASSERT_EQUAL(
        protocol::ParseStatus::InvalidConfig,
        parse("{\"type\":\"CONFIG\",\"sequence\":1,\"min_duty_pct\":-1}",
              message));
    TEST_ASSERT_EQUAL(
        protocol::ParseStatus::InvalidConfig,
        parse("{\"type\":\"CONFIG\",\"sequence\":1,\"steering_gain_pct\":200}",
              message));
}

void test_config_with_a_wrong_type_is_rejected() {
    protocol::ParsedMessage message;

    TEST_ASSERT_EQUAL(
        protocol::ParseStatus::InvalidConfig,
        parse("{\"type\":\"CONFIG\",\"sequence\":1,\"invert_left\":\"oui\"}",
              message));
}

void test_config_without_a_sequence_is_rejected() {
    protocol::ParsedMessage message;

    TEST_ASSERT_EQUAL(protocol::ParseStatus::MissingField,
                      parse("{\"type\":\"CONFIG\"}", message));
}

void test_the_config_reply_echoes_what_was_applied() {
    // Le Raspberry Pi doit pouvoir vérifier, pas supposer.
    char buffer[protocol::MAX_TELEMETRY_LENGTH];
    const size_t written = communication::buildConfigLine(
        7, 100, 18, 40, true, false, buffer, sizeof(buffer));

    TEST_ASSERT_TRUE(written > 0);
    TEST_ASSERT_EQUAL_STRING(
        "{\"type\":\"CONFIG\",\"sequence\":7,\"steering_gain_pct\":100,"
        "\"min_duty_pct\":18,\"max_duty_pct\":40,\"invert_left\":true,"
        "\"invert_right\":false}\n",
        buffer);
    TEST_ASSERT_EQUAL_CHAR('\n', buffer[written - 1]);
}

void test_the_config_reply_fails_cleanly_on_a_small_buffer() {
    char buffer[16];
    TEST_ASSERT_EQUAL_size_t(
        0, communication::buildConfigLine(1, 100, 0, 40, false, false, buffer,
                                          sizeof(buffer)));
    TEST_ASSERT_EQUAL_STRING("", buffer);
}

// --------------------------------------------------------------------------
// TEST
// --------------------------------------------------------------------------

void test_every_target_is_accepted() {
    protocol::ParsedMessage message;

    TEST_ASSERT_EQUAL(protocol::ParseStatus::Ok,
                      parse("{\"type\":\"TEST\",\"sequence\":1,"
                            "\"target\":\"LEFT\",\"duty_pct\":30,"
                            "\"duration_ms\":300}",
                            message));
    TEST_ASSERT_EQUAL(protocol::TestTarget::Left, message.test.target);

    TEST_ASSERT_EQUAL(protocol::ParseStatus::Ok,
                      parse("{\"type\":\"TEST\",\"sequence\":1,"
                            "\"target\":\"RIGHT\",\"duty_pct\":30,"
                            "\"duration_ms\":300}",
                            message));
    TEST_ASSERT_EQUAL(protocol::TestTarget::Right, message.test.target);

    TEST_ASSERT_EQUAL(protocol::ParseStatus::Ok,
                      parse("{\"type\":\"TEST\",\"sequence\":1,"
                            "\"target\":\"BOTH\",\"duty_pct\":-30,"
                            "\"duration_ms\":300}",
                            message));
    TEST_ASSERT_EQUAL(protocol::TestTarget::Both, message.test.target);
    TEST_ASSERT_EQUAL_INT(-30, message.test.duty_pct);
}

void test_an_unknown_target_is_rejected() {
    protocol::ParsedMessage message;

    TEST_ASSERT_EQUAL(protocol::ParseStatus::InvalidTarget,
                      parse("{\"type\":\"TEST\",\"sequence\":1,"
                            "\"target\":\"MIDDLE\",\"duty_pct\":30,"
                            "\"duration_ms\":300}",
                            message));
}

void test_the_test_duty_is_bounded() {
    // La calibration cherche un seuil de démarrage, pas de la vitesse.
    protocol::ParsedMessage message;

    TEST_ASSERT_EQUAL(protocol::ParseStatus::InvalidDuty,
                      parse("{\"type\":\"TEST\",\"sequence\":1,"
                            "\"target\":\"LEFT\",\"duty_pct\":100,"
                            "\"duration_ms\":300}",
                            message));
    TEST_ASSERT_EQUAL(protocol::ParseStatus::InvalidDuty,
                      parse("{\"type\":\"TEST\",\"sequence\":1,"
                            "\"target\":\"LEFT\",\"duty_pct\":-100,"
                            "\"duration_ms\":300}",
                            message));

    // La borne elle-même reste acceptée.
    char line[128];
    snprintf(line, sizeof(line),
             "{\"type\":\"TEST\",\"sequence\":1,\"target\":\"LEFT\","
             "\"duty_pct\":%d,\"duration_ms\":300}",
             protocol::TEST_MAX_DUTY_PCT);
    TEST_ASSERT_EQUAL(protocol::ParseStatus::Ok, parse(line, message));
}

void test_the_test_duration_is_bounded() {
    // Une roue ne doit jamais pouvoir tourner indéfiniment sur un essai.
    protocol::ParsedMessage message;

    TEST_ASSERT_EQUAL(protocol::ParseStatus::InvalidDuration,
                      parse("{\"type\":\"TEST\",\"sequence\":1,"
                            "\"target\":\"LEFT\",\"duty_pct\":30,"
                            "\"duration_ms\":60000}",
                            message));
    TEST_ASSERT_EQUAL(protocol::ParseStatus::InvalidDuration,
                      parse("{\"type\":\"TEST\",\"sequence\":1,"
                            "\"target\":\"LEFT\",\"duty_pct\":30,"
                            "\"duration_ms\":0}",
                            message));
}

void test_a_test_without_a_target_is_rejected() {
    protocol::ParsedMessage message;

    TEST_ASSERT_EQUAL(protocol::ParseStatus::MissingField,
                      parse("{\"type\":\"TEST\",\"sequence\":1,"
                            "\"duty_pct\":30,\"duration_ms\":300}",
                            message));
}

void test_error_codes_are_defined_for_the_new_failures() {
    TEST_ASSERT_EQUAL_STRING(
        protocol::ERROR_INVALID_CONFIG,
        protocol::errorCodeFor(protocol::ParseStatus::InvalidConfig));
    TEST_ASSERT_EQUAL_STRING(
        protocol::ERROR_INVALID_TARGET,
        protocol::errorCodeFor(protocol::ParseStatus::InvalidTarget));
    TEST_ASSERT_EQUAL_STRING(
        protocol::ERROR_INVALID_DUTY,
        protocol::errorCodeFor(protocol::ParseStatus::InvalidDuty));
    TEST_ASSERT_EQUAL_STRING(
        protocol::ERROR_INVALID_DURATION,
        protocol::errorCodeFor(protocol::ParseStatus::InvalidDuration));
}

void setUp() {}
void tearDown() {}

int main() {
    UNITY_BEGIN();
    RUN_TEST(test_the_type_field_selects_the_message);
    RUN_TEST(test_parse_drive_line_still_refuses_other_types);
    RUN_TEST(test_config_applies_only_the_fields_it_mentions);
    RUN_TEST(test_config_reads_every_setting);
    RUN_TEST(test_an_empty_config_is_a_read_request);
    RUN_TEST(test_config_out_of_range_is_rejected);
    RUN_TEST(test_config_with_a_wrong_type_is_rejected);
    RUN_TEST(test_config_without_a_sequence_is_rejected);
    RUN_TEST(test_the_config_reply_echoes_what_was_applied);
    RUN_TEST(test_the_config_reply_fails_cleanly_on_a_small_buffer);
    RUN_TEST(test_every_target_is_accepted);
    RUN_TEST(test_an_unknown_target_is_rejected);
    RUN_TEST(test_the_test_duty_is_bounded);
    RUN_TEST(test_the_test_duration_is_bounded);
    RUN_TEST(test_a_test_without_a_target_is_rejected);
    RUN_TEST(test_error_codes_are_defined_for_the_new_failures);
    return UNITY_END();
}
