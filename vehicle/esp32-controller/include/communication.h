#pragma once

#include <stddef.h>

#include "protocol.h"

// Encodage et décodage des messages du protocole série.
//
// Volontairement sans dépendance à Arduino : ces fonctions manipulent des
// chaînes C et sont donc compilables et testables en natif sur PC
// (`pio test -e native`), sans carte ESP32 ni matériel.

namespace communication {

// Analyse une ligne reçue, quelle que soit sa nature.
//
// La validation couvre la section 5.5 du plan : JSON malformé, type inconnu,
// champ obligatoire absent, valeurs hors plage. `out` n'est modifié que si le
// retour vaut ParseStatus::Ok.
protocol::ParseStatus parseLine(const char* line, protocol::ParsedMessage& out);

// Raccourci pour le cas courant : n'accepte qu'une commande DRIVE.
//
// Une ligne CONFIG ou TEST valide est signalée UnknownType, puisque
// l'appelant a explicitement demandé une commande de mouvement.
protocol::ParseStatus parseDriveLine(const char* line,
                                     protocol::DriveMessage& out);

// Sérialise la configuration effectivement appliquée, saut de ligne compris.
//
// Émise en réponse à chaque ligne CONFIG : le Raspberry Pi doit pouvoir
// vérifier ce que l'ESP32 a retenu, et non supposer que sa demande a été
// suivie. Les valeurs renvoyées sont celles après bornage.
size_t buildConfigLine(long sequence, int steering_gain_pct, int min_duty_pct,
                       int max_duty_pct, bool invert_left, bool invert_right,
                       char* buffer, size_t buffer_size);

// Sérialise une télémétrie sur une ligne JSON, saut de ligne final compris.
//
// Renvoie le nombre de caractères écrits, ou 0 si le tampon est trop petit.
// L'ordre des champs suit exactement l'exemple de la section 5.3.
size_t buildTelemetryLine(const protocol::TelemetryMessage& telemetry,
                          char* buffer, size_t buffer_size);

}  // namespace communication
