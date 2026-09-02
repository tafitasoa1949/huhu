package com.smartcar.pilot.domain.model

/** Le Gateway a répondu, mais a refusé la revendication (`409`, docs/mobile-protocol.md). */
class CarAlreadyClaimedException(carId: String) : Exception("voiture '$carId' déjà revendiquée par un autre pilote")

/** Le Gateway n'a pas répondu (réseau, timeout, service arrêté). */
class GatewayUnreachableException(cause: Throwable) : Exception("Gateway injoignable", cause)
