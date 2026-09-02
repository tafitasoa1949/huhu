#include "safety.h"

#include "protocol.h"

namespace safety {

namespace {

Decision refuse(State state, const char* error) {
    Decision decision;
    decision.motors_allowed = false;
    decision.state = state;
    decision.error = error;
    return decision;
}

}  // namespace

Decision evaluate(const Inputs& inputs) {
    // L'ordre des tests est l'ordre de priorité : une cause matérielle prime
    // toujours sur une cause logicielle, et toute cause de sécurité prime sur
    // la conduite normale.

    if (inputs.button_pressed) {
        return refuse(State::ButtonPressed, protocol::ERROR_EMERGENCY_STOP);
    }

    if (inputs.has_received_command && inputs.commanded_emergency) {
        return refuse(State::EmergencyCommand, protocol::ERROR_EMERGENCY_STOP);
    }

    if (inputs.has_local_distance &&
        inputs.local_distance_m <= inputs.critical_distance_m) {
        return refuse(State::LocalObstacle, protocol::ERROR_LOCAL_OBSTACLE);
    }

    if (inputs.last_line_rejected) {
        return refuse(State::ProtocolError, protocol::ERROR_INVALID_JSON);
    }

    if (!inputs.has_received_command) {
        // Au démarrage, tant que le Raspberry Pi n'a rien envoyé, la voiture
        // reste immobile. Ce n'est pas une erreur, seulement un état d'attente.
        return refuse(State::WaitingForCommand, nullptr);
    }

    // Soustraction sur 32 bits non signés : le résultat reste correct après le
    // débordement de millis(), qui survient environ tous les 49 jours.
    const uint32_t silence_ms = inputs.now_ms - inputs.last_command_ms;
    if (silence_ms > inputs.timeout_ms) {
        return refuse(State::CommunicationLost,
                      protocol::ERROR_COMMAND_TIMEOUT);
    }

    Decision decision;
    decision.motors_allowed = true;
    decision.state = State::Active;
    decision.error = nullptr;
    return decision;
}

const char* stateName(State state) {
    switch (state) {
        case State::ButtonPressed:
            return "BUTTON_PRESSED";
        case State::EmergencyCommand:
            return "EMERGENCY_COMMAND";
        case State::LocalObstacle:
            return "LOCAL_OBSTACLE";
        case State::ProtocolError:
            return "PROTOCOL_ERROR";
        case State::WaitingForCommand:
            return "WAITING_FOR_COMMAND";
        case State::CommunicationLost:
            return "COMMUNICATION_LOST";
        case State::Active:
            return "ACTIVE";
    }
    return "UNKNOWN";
}

}  // namespace safety
