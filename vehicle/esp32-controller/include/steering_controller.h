#pragma once

// Direction différentielle (skid steer).
//
// Le châssis n'a pas de servo : il tourne en faisant varier la vitesse des
// roues gauche et droite. Ce module traduit le couple officiel
// (speed_pct, steering_pct) du contrat en deux consignes signées, une par
// côté. C'est le ticket ESP-08 du plan, adapté au châssis retenu.
//
// Aucune dépendance à Arduino ni au matériel : arithmétique entière pure,
// donc testable en natif sur PC (`pio test -e native`).

namespace steering {

// Consignes par côté, en pourcentage signé de la puissance disponible.
// Négatif = marche arrière. Ce sont des rapports cycliques, prêts à être
// envoyés au pont en H.
struct WheelDuty {
    int left_pct;
    int right_pct;
};

// Paramètres de calibration. Les valeurs par défaut correspondent à
// pin_config.h ; les tests les surchargent pour vérifier chaque étape.
struct MixerConfig {
    // Autorité de la direction, en pourcentage. 100 = un steering_pct de
    // ±100 met les deux côtés en opposition complète.
    int steering_gain_pct = 100;

    // Rapport cyclique en dessous duquel les moteurs chargés ne démarrent
    // pas. Toute consigne non nulle est remise à l'échelle au-dessus de ce
    // seuil. 0 = réponse linéaire, tant que la mesure n'a pas été faite.
    int min_duty_pct = 0;

    // Plafond de sécurité appliqué à la consigne maximale.
    int max_duty_pct = 100;

    // Inversion logicielle si un moteur est câblé à l'envers.
    bool invert_left = false;
    bool invert_right = false;

    // Autorise ou non la rotation sur place (les deux côtés en sens opposé
    // alors que speed_pct vaut 0). Désactivé dans le MVP : le moteur de
    // décision n'associe jamais une vitesse nulle à une direction non nulle,
    // et « speed_pct = 0 » doit vouloir dire « la voiture ne bouge pas ».
    bool allow_pivot = false;
};

// Convertit une commande du contrat en consignes par roue.
//
// `speed_pct` est attendu dans [0, 100] et `steering_pct` dans [-100, 100] ;
// les valeurs hors plage sont ramenées aux bornes plutôt que rejetées, la
// validation stricte étant faite en amont par le décodeur du protocole.
//
// Convention du contrat : steering_pct négatif = virage à gauche, donc côté
// gauche ralenti et côté droit accéléré.
WheelDuty mix(int speed_pct, int steering_pct, const MixerConfig& config);

// Consigne d'arrêt : les deux côtés à zéro.
WheelDuty stopped();

}  // namespace steering
