#pragma once

// Configuration matérielle du contrôleur moteur.
//
// IMPORTANT : le matériel n'étant pas encore monté, toutes les valeurs de ce
// fichier sont provisoires. Elles sont regroupées ici pour qu'un seul fichier
// soit à corriger le jour du câblage réel. Aucun autre fichier ne doit
// contenir de numéro de broche.
//
// Châssis visé : traction différentielle (skid steer), deux canaux moteur
// gauche / droite pilotés par un pont en H L298N. Il n'y a pas de servo de
// direction : la direction est obtenue en faisant varier la vitesse relative
// des deux côtés (voir steering_controller.h).

// --------------------------------------------------------------------------
// Brochage L298N
// --------------------------------------------------------------------------
// ENA/ENB reçoivent le PWM (vitesse), INx définissent le sens de rotation.
// Les broches choisies évitent les broches de strapping de l'ESP32
// (0, 2, 5, 12, 15) et les broches d'entrée seule (34-39).

#define PIN_MOTOR_LEFT_PWM 25   // ENA
#define PIN_MOTOR_LEFT_IN1 26   // IN1
#define PIN_MOTOR_LEFT_IN2 27   // IN2

#define PIN_MOTOR_RIGHT_PWM 33  // ENB
#define PIN_MOTOR_RIGHT_IN1 32  // IN3
#define PIN_MOTOR_RIGHT_IN2 14  // IN4

// --------------------------------------------------------------------------
// Sens de rotation
// --------------------------------------------------------------------------
// À valider moteur par moteur, roues levées, avant tout essai au sol
// (annexe D du plan de développement). Si un moteur tourne à l'envers,
// basculer la valeur correspondante à 1 plutôt que de recâbler.

#define MOTOR_LEFT_INVERT 0
#define MOTOR_RIGHT_INVERT 0

// --------------------------------------------------------------------------
// PWM (LEDC)
// --------------------------------------------------------------------------
// 20 kHz place le hachage au-dessus de la bande audible : le L298N ne siffle
// pas. 10 bits donnent 1024 pas de réglage, largement suffisant pour un
// consigne exprimée en pourcentage.

#define MOTOR_PWM_FREQ_HZ 20000
#define MOTOR_PWM_RESOLUTION_BITS 10
#define MOTOR_PWM_CHANNEL_LEFT 0
#define MOTOR_PWM_CHANNEL_RIGHT 1

// --------------------------------------------------------------------------
// Calibration de la commande
// --------------------------------------------------------------------------
// MOTOR_MIN_DUTY_PCT : en dessous d'un certain rapport cyclique, un moteur à
// courant continu chargé ne démarre pas et se contente de chauffer. Une fois
// le châssis monté, relever la valeur minimale qui fait effectivement tourner
// les roues au sol et la reporter ici : les consignes non nulles seront
// remises à l'échelle dans [MOTOR_MIN_DUTY_PCT, 100]. Laisser 0 tant que la
// mesure n'a pas été faite, la réponse reste alors linéaire.
#define MOTOR_MIN_DUTY_PCT 0

// MOTOR_MAX_DUTY_PCT : plafond de sécurité appliqué après tous les calculs.
// Le plan impose de brider la vitesse pendant les premiers essais ; 40 %
// permet de rattraper la voiture à la main. À remonter progressivement.
#define MOTOR_MAX_DUTY_PCT 40

// STEERING_GAIN_PCT : autorité de la direction différentielle, en pourcentage
// de l'écart appliqué entre les deux côtés. 100 = un steering_pct de ±100
// provoque un demi-tour sur place ; une valeur plus faible adoucit la
// réponse sans toucher au moteur de décision.
#define STEERING_GAIN_PCT 100

// --------------------------------------------------------------------------
// Capteurs et entrées locales (optionnels)
// --------------------------------------------------------------------------
// Chaque bloc est désactivé par défaut : le firmware compile et tourne sur une
// carte ESP32 nue, sans aucun périphérique branché. Passer à 1 au fur et à
// mesure que le matériel arrive.

// Bouton d'arrêt d'urgence câblé à la masse (INPUT_PULLUP, actif à l'état bas).
#define ENABLE_EMERGENCY_BUTTON 0
#define PIN_EMERGENCY_BUTTON 13

// Télémètre à ultrasons HC-SR04 : arrêt local sans attendre le Raspberry Pi.
#define ENABLE_ULTRASONIC 0
#define PIN_ULTRASONIC_TRIG 4
#define PIN_ULTRASONIC_ECHO 36  // entrée seule, acceptable pour ECHO
                                // ATTENTION : ECHO sort en 5 V, prévoir un
                                // pont diviseur vers 3,3 V.

// Distance en dessous de laquelle l'ESP32 coupe les moteurs de sa propre
// initiative, en mètres. Le plan retient 0,40 m côté décision ; on garde une
// marge plus serrée en local pour ne déclencher qu'en dernier recours.
#define ULTRASONIC_CRITICAL_DISTANCE_M 0.25f
#define ULTRASONIC_MAX_DISTANCE_M 4.0f

// Encodeurs à effet Hall ou optiques, pour remonter left_rpm / right_rpm.
#define ENABLE_ENCODERS 0
#define PIN_ENCODER_LEFT 18
#define PIN_ENCODER_RIGHT 19
#define ENCODER_TICKS_PER_REVOLUTION 20

// Mesure de tension batterie par pont diviseur sur une entrée ADC.
#define ENABLE_BATTERY_MONITOR 0
#define PIN_BATTERY_ADC 39
// Rapport du pont diviseur : Vbat = Vadc * BATTERY_DIVIDER_RATIO.
#define BATTERY_DIVIDER_RATIO 5.7f
// Bornes de la plage utile, pour convertir des volts en pourcentage.
// Valeurs pour un pack 2S lithium-ion (2 x 3,0 V à 2 x 4,2 V).
#define BATTERY_EMPTY_V 6.0f
#define BATTERY_FULL_V 8.4f
