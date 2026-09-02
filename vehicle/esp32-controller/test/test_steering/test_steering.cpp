#include <unity.h>

#include "steering_controller.h"

// Tests du mélangeur de direction différentielle.
// Exécution : pio test -e native

namespace {

// Configuration neutre : pas de bridage, pas de seuil de démarrage, pas
// d'inversion. Chaque test n'active que le réglage qu'il vérifie.
steering::MixerConfig neutralConfig() {
    steering::MixerConfig config;
    config.steering_gain_pct = 100;
    config.min_duty_pct = 0;
    config.max_duty_pct = 100;
    config.invert_left = false;
    config.invert_right = false;
    config.allow_pivot = false;
    return config;
}

}  // namespace

void test_straight_ahead_drives_both_sides_equally() {
    const steering::WheelDuty duty = steering::mix(45, 0, neutralConfig());

    TEST_ASSERT_EQUAL_INT(45, duty.left_pct);
    TEST_ASSERT_EQUAL_INT(45, duty.right_pct);
}

void test_negative_steering_turns_left() {
    // Contrat : steering_pct négatif = gauche. Sur un châssis différentiel,
    // cela veut dire côté gauche plus lent que le côté droit.
    const steering::WheelDuty duty = steering::mix(30, -30, neutralConfig());

    TEST_ASSERT_TRUE(duty.left_pct < duty.right_pct);
    TEST_ASSERT_EQUAL_INT(0, duty.left_pct);
    TEST_ASSERT_EQUAL_INT(60, duty.right_pct);
}

void test_positive_steering_turns_right() {
    const steering::WheelDuty duty = steering::mix(30, 30, neutralConfig());

    TEST_ASSERT_TRUE(duty.right_pct < duty.left_pct);
    TEST_ASSERT_EQUAL_INT(60, duty.left_pct);
    TEST_ASSERT_EQUAL_INT(0, duty.right_pct);
}

void test_output_is_normalised_instead_of_clipped() {
    // 60 + 80 = 140 dépasse la plage. L'écrêtage donnerait 100 et -20, soit
    // un rapport faussé ; la remise à l'échelle conserve le rayon demandé.
    const steering::WheelDuty duty = steering::mix(60, 80, neutralConfig());

    TEST_ASSERT_EQUAL_INT(100, duty.left_pct);
    TEST_ASSERT_EQUAL_INT(-14, duty.right_pct);
    TEST_ASSERT_TRUE(duty.left_pct <= 100 && duty.left_pct >= -100);
    TEST_ASSERT_TRUE(duty.right_pct <= 100 && duty.right_pct >= -100);
}

void test_zero_speed_stops_the_car() {
    // Une vitesse nulle immobilise la voiture : la direction ne doit pas la
    // faire pivoter sur place tant que allow_pivot est désactivé.
    const steering::WheelDuty duty = steering::mix(0, -80, neutralConfig());

    TEST_ASSERT_EQUAL_INT(0, duty.left_pct);
    TEST_ASSERT_EQUAL_INT(0, duty.right_pct);
}

void test_pivot_is_possible_when_explicitly_enabled() {
    steering::MixerConfig config = neutralConfig();
    config.allow_pivot = true;

    const steering::WheelDuty duty = steering::mix(0, 100, config);

    TEST_ASSERT_EQUAL_INT(100, duty.left_pct);
    TEST_ASSERT_EQUAL_INT(-100, duty.right_pct);
}

void test_max_duty_caps_the_output() {
    steering::MixerConfig config = neutralConfig();
    config.max_duty_pct = 40;

    const steering::WheelDuty duty = steering::mix(100, 0, config);

    TEST_ASSERT_EQUAL_INT(40, duty.left_pct);
    TEST_ASSERT_EQUAL_INT(40, duty.right_pct);
}

void test_min_duty_lifts_small_commands_above_the_dead_band() {
    steering::MixerConfig config = neutralConfig();
    config.min_duty_pct = 20;

    // Une consigne de 10 % ne ferait pas démarrer les moteurs : elle est
    // remontée dans [20, 100].
    const steering::WheelDuty duty = steering::mix(10, 0, config);

    TEST_ASSERT_EQUAL_INT(28, duty.left_pct);
    TEST_ASSERT_EQUAL_INT(28, duty.right_pct);
}

void test_min_duty_leaves_zero_at_zero() {
    steering::MixerConfig config = neutralConfig();
    config.min_duty_pct = 20;

    const steering::WheelDuty duty = steering::mix(0, 0, config);

    TEST_ASSERT_EQUAL_INT(0, duty.left_pct);
    TEST_ASSERT_EQUAL_INT(0, duty.right_pct);
}

void test_inversion_flips_the_matching_side_only() {
    steering::MixerConfig config = neutralConfig();
    config.invert_left = true;

    const steering::WheelDuty duty = steering::mix(50, 0, config);

    TEST_ASSERT_EQUAL_INT(-50, duty.left_pct);
    TEST_ASSERT_EQUAL_INT(50, duty.right_pct);
}

void test_steering_gain_softens_the_turn() {
    steering::MixerConfig config = neutralConfig();
    config.steering_gain_pct = 50;

    const steering::WheelDuty duty = steering::mix(40, -40, config);

    // L'écart appliqué n'est plus 40 mais 20.
    TEST_ASSERT_EQUAL_INT(20, duty.left_pct);
    TEST_ASSERT_EQUAL_INT(60, duty.right_pct);
}

void test_out_of_range_inputs_are_clamped() {
    const steering::WheelDuty duty = steering::mix(500, -500, neutralConfig());

    TEST_ASSERT_TRUE(duty.left_pct >= -100 && duty.left_pct <= 100);
    TEST_ASSERT_TRUE(duty.right_pct >= -100 && duty.right_pct <= 100);
}

void test_stopped_returns_both_sides_at_zero() {
    const steering::WheelDuty duty = steering::stopped();

    TEST_ASSERT_EQUAL_INT(0, duty.left_pct);
    TEST_ASSERT_EQUAL_INT(0, duty.right_pct);
}

void setUp() {}
void tearDown() {}

int main() {
    UNITY_BEGIN();
    RUN_TEST(test_straight_ahead_drives_both_sides_equally);
    RUN_TEST(test_negative_steering_turns_left);
    RUN_TEST(test_positive_steering_turns_right);
    RUN_TEST(test_output_is_normalised_instead_of_clipped);
    RUN_TEST(test_zero_speed_stops_the_car);
    RUN_TEST(test_pivot_is_possible_when_explicitly_enabled);
    RUN_TEST(test_max_duty_caps_the_output);
    RUN_TEST(test_min_duty_lifts_small_commands_above_the_dead_band);
    RUN_TEST(test_min_duty_leaves_zero_at_zero);
    RUN_TEST(test_inversion_flips_the_matching_side_only);
    RUN_TEST(test_steering_gain_softens_the_turn);
    RUN_TEST(test_out_of_range_inputs_are_clamped);
    RUN_TEST(test_stopped_returns_both_sides_at_zero);
    return UNITY_END();
}
