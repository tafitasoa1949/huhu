#include <unity.h>

#include "protocol.h"
#include "safety.h"

// Tests de l'arbitrage de sécurité local : watchdog de communication, arrêt
// d'urgence, bouton physique, obstacle vu par le capteur local.
// Couvre les scénarios S08 et S12 du plan côté ESP32.
//
// Exécution : pio test -e native

namespace {

// Situation nominale : une commande valide vient d'être reçue, aucun capteur
// en alerte. Chaque test ne modifie que l'entrée qu'il vérifie.
safety::Inputs nominalInputs() {
    safety::Inputs inputs;
    inputs.now_ms = 10000;
    inputs.timeout_ms = protocol::COMMAND_TIMEOUT_MS;
    inputs.has_received_command = true;
    inputs.last_command_ms = 10000;
    inputs.commanded_emergency = false;
    inputs.last_line_rejected = false;
    inputs.button_pressed = false;
    inputs.has_local_distance = false;
    inputs.local_distance_m = 0.0f;
    inputs.critical_distance_m = 0.25f;
    return inputs;
}

}  // namespace

void test_recent_valid_command_allows_driving() {
    const safety::Decision decision = safety::evaluate(nominalInputs());

    TEST_ASSERT_TRUE(decision.motors_allowed);
    TEST_ASSERT_EQUAL(safety::State::Active, decision.state);
    TEST_ASSERT_NULL(decision.error);
}

void test_no_command_yet_keeps_the_car_still() {
    safety::Inputs inputs = nominalInputs();
    inputs.has_received_command = false;

    const safety::Decision decision = safety::evaluate(inputs);

    TEST_ASSERT_FALSE(decision.motors_allowed);
    TEST_ASSERT_EQUAL(safety::State::WaitingForCommand, decision.state);
    // L'attente d'une première commande n'est pas une erreur.
    TEST_ASSERT_NULL(decision.error);
}

void test_silence_beyond_the_timeout_stops_the_car() {
    // Scénario S12 : silence supérieur à 500 ms.
    safety::Inputs inputs = nominalInputs();
    inputs.last_command_ms = 10000;
    inputs.now_ms = 10000 + protocol::COMMAND_TIMEOUT_MS + 1;

    const safety::Decision decision = safety::evaluate(inputs);

    TEST_ASSERT_FALSE(decision.motors_allowed);
    TEST_ASSERT_EQUAL(safety::State::CommunicationLost, decision.state);
    TEST_ASSERT_EQUAL_STRING(protocol::ERROR_COMMAND_TIMEOUT, decision.error);
}

void test_silence_exactly_at_the_timeout_is_still_allowed() {
    // La règle est « au-delà de 500 ms », la borne elle-même reste valide.
    safety::Inputs inputs = nominalInputs();
    inputs.last_command_ms = 10000;
    inputs.now_ms = 10000 + protocol::COMMAND_TIMEOUT_MS;

    TEST_ASSERT_TRUE(safety::evaluate(inputs).motors_allowed);
}

void test_timeout_survives_the_millis_rollover() {
    // millis() repasse à zéro environ tous les 49 jours. La soustraction non
    // signée doit rester juste de part et d'autre du débordement, sinon la
    // voiture se croirait en perte de communication au pire moment.
    safety::Inputs inputs = nominalInputs();
    inputs.last_command_ms = 0xFFFFFF00UL;

    // 100 ms après la dernière commande, à cheval sur le débordement.
    inputs.now_ms = 0x00000064UL;
    TEST_ASSERT_TRUE(safety::evaluate(inputs).motors_allowed);

    // 600 ms après : au-delà du délai.
    inputs.now_ms = 0x000002BCUL;
    const safety::Decision decision = safety::evaluate(inputs);
    TEST_ASSERT_FALSE(decision.motors_allowed);
    TEST_ASSERT_EQUAL(safety::State::CommunicationLost, decision.state);
}

void test_emergency_command_stops_the_car() {
    safety::Inputs inputs = nominalInputs();
    inputs.commanded_emergency = true;

    const safety::Decision decision = safety::evaluate(inputs);

    TEST_ASSERT_FALSE(decision.motors_allowed);
    TEST_ASSERT_EQUAL(safety::State::EmergencyCommand, decision.state);
    TEST_ASSERT_EQUAL_STRING(protocol::ERROR_EMERGENCY_STOP, decision.error);
}

void test_local_obstacle_stops_the_car_without_the_raspberry_pi() {
    // Scénario S08 vu depuis l'ESP32 : le capteur local décide seul.
    safety::Inputs inputs = nominalInputs();
    inputs.has_local_distance = true;
    inputs.local_distance_m = 0.20f;

    const safety::Decision decision = safety::evaluate(inputs);

    TEST_ASSERT_FALSE(decision.motors_allowed);
    TEST_ASSERT_EQUAL(safety::State::LocalObstacle, decision.state);
    TEST_ASSERT_EQUAL_STRING(protocol::ERROR_LOCAL_OBSTACLE, decision.error);
}

void test_distant_obstacle_does_not_stop_the_car() {
    safety::Inputs inputs = nominalInputs();
    inputs.has_local_distance = true;
    inputs.local_distance_m = 1.50f;

    TEST_ASSERT_TRUE(safety::evaluate(inputs).motors_allowed);
}

void test_unknown_distance_does_not_stop_the_car() {
    // Pas de capteur branché : la distance est inconnue, pas nulle. Lire
    // « inconnu » comme « obstacle à 0 m » bloquerait la voiture en
    // permanence sur une carte nue.
    safety::Inputs inputs = nominalInputs();
    inputs.has_local_distance = false;
    inputs.local_distance_m = 0.0f;

    TEST_ASSERT_TRUE(safety::evaluate(inputs).motors_allowed);
}

void test_button_stops_the_car() {
    safety::Inputs inputs = nominalInputs();
    inputs.button_pressed = true;

    const safety::Decision decision = safety::evaluate(inputs);

    TEST_ASSERT_FALSE(decision.motors_allowed);
    TEST_ASSERT_EQUAL(safety::State::ButtonPressed, decision.state);
}

void test_button_wins_over_every_other_input() {
    // Le bouton physique est le dernier recours : il doit primer même si
    // toutes les autres entrées disent que la conduite est possible.
    safety::Inputs inputs = nominalInputs();
    inputs.button_pressed = true;
    inputs.commanded_emergency = true;
    inputs.has_local_distance = true;
    inputs.local_distance_m = 0.10f;

    TEST_ASSERT_EQUAL(safety::State::ButtonPressed,
                      safety::evaluate(inputs).state);
}

void test_rejected_line_keeps_the_car_stopped() {
    // Scénario S11 : après une ligne invalide, la voiture reste à l'arrêt
    // jusqu'à réception d'une commande valide.
    safety::Inputs inputs = nominalInputs();
    inputs.last_line_rejected = true;

    const safety::Decision decision = safety::evaluate(inputs);

    TEST_ASSERT_FALSE(decision.motors_allowed);
    TEST_ASSERT_EQUAL(safety::State::ProtocolError, decision.state);
}

void test_emergency_wins_over_protocol_error() {
    safety::Inputs inputs = nominalInputs();
    inputs.commanded_emergency = true;
    inputs.last_line_rejected = true;

    TEST_ASSERT_EQUAL(safety::State::EmergencyCommand,
                      safety::evaluate(inputs).state);
}

void test_state_names_are_defined() {
    TEST_ASSERT_EQUAL_STRING("ACTIVE", safety::stateName(safety::State::Active));
    TEST_ASSERT_EQUAL_STRING(
        "COMMUNICATION_LOST",
        safety::stateName(safety::State::CommunicationLost));
}

void setUp() {}
void tearDown() {}

int main() {
    UNITY_BEGIN();
    RUN_TEST(test_recent_valid_command_allows_driving);
    RUN_TEST(test_no_command_yet_keeps_the_car_still);
    RUN_TEST(test_silence_beyond_the_timeout_stops_the_car);
    RUN_TEST(test_silence_exactly_at_the_timeout_is_still_allowed);
    RUN_TEST(test_timeout_survives_the_millis_rollover);
    RUN_TEST(test_emergency_command_stops_the_car);
    RUN_TEST(test_local_obstacle_stops_the_car_without_the_raspberry_pi);
    RUN_TEST(test_distant_obstacle_does_not_stop_the_car);
    RUN_TEST(test_unknown_distance_does_not_stop_the_car);
    RUN_TEST(test_button_stops_the_car);
    RUN_TEST(test_button_wins_over_every_other_input);
    RUN_TEST(test_rejected_line_keeps_the_car_stopped);
    RUN_TEST(test_emergency_wins_over_protocol_error);
    RUN_TEST(test_state_names_are_defined);
    return UNITY_END();
}
