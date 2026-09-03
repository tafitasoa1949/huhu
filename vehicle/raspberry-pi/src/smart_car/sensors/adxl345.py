"""Accéléromètre ADXL345 (I2C) — lecture des trois axes en m/s².

Le composant ne rend pas des m/s² : il rend trois entiers signés 16 bits,
en *comptes*, qu'il faut convertir. En mode pleine résolution (le mode
utilisé ici), la fiche technique annonce une échelle constante de
256 comptes par g — quelle que soit la plage ±2/4/8/16 g choisie, le capteur
ajoute des bits plutôt que d'élargir le pas, donc un seul facteur suffit et
il ne change pas avec la plage. Ce facteur vit dans
`hardware.ADXL345_COUNTS_PER_G` : la valeur de la fiche technique ne vaut
que pour un composant authentique, et l'exemplaire câblé ici n'en est pas
un (voir le commentaire là-bas).

**Au repos, la norme vaut ~9,81 m/s², pas 0** : un accéléromètre mesure la
gravité comme n'importe quelle autre accélération. Un module posé à plat
lit donc ~0, ~0, ~9,81 — c'est le test de bon fonctionnement le plus rapide,
et non un biais à corriger.

`bus` est injectable : une doublure suffit à vérifier toute la conversion
comptes -> m/s² sans matériel ni Raspberry Pi, même principe que
`pulse_sender` dans `motors/gpio_driver.py`.

**Dépendance** : `smbus2`, fourni par le système sur Raspberry Pi OS
(`apt install python3-smbus2`) — comme `lgpio`, il est vu par le `.venv`
grâce à `include-system-site-packages = true`.
"""

from __future__ import annotations

import struct
import time
from dataclasses import dataclass
from typing import Protocol

from smart_car.config import hardware

# Registres (fiche technique ADXL345, table 19).
REG_DEVID = 0x00
REG_BW_RATE = 0x2C
REG_POWER_CTL = 0x2D
REG_DATA_FORMAT = 0x31
REG_DATAX0 = 0x32

DEVID_EXPECTED = 0xE5  # valeur figée en usine : sert à confirmer qu'on parle bien à un ADXL345

# POWER_CTL bit 3 (« Measure ») : sans lui le composant répond correctement
# sur le bus mais reste en veille et renvoie éternellement les mêmes valeurs.
POWER_CTL_MEASURE = 0x08

# DATA_FORMAT bit 3 (« FULL_RES ») + plage ±16 g sur les bits 1:0. La plage
# large ne coûte rien en résolution en pleine résolution (voir le module) et
# évite la saturation sur les à-coups d'une voiture RC.
DATA_FORMAT_FULL_RES = 0x08
DATA_FORMAT_RANGE_16G = 0x03

# Correspondance fréquence -> code du registre BW_RATE (fiche technique,
# table 7). Limitée aux cadences réalistes ici ; une valeur absente est un
# vrai bug de configuration, pas quelque chose à arrondir en silence.
_BW_RATE_CODES = {12: 0x07, 25: 0x08, 50: 0x09, 100: 0x0A, 200: 0x0B, 400: 0x0C}

STANDARD_GRAVITY_M_S2 = 9.80665


@dataclass(frozen=True)
class Acceleration:
    """Accélération instantanée des trois axes, en m/s²."""

    x: float
    y: float
    z: float

    @property
    def magnitude(self) -> float:
        """Norme du vecteur — ~9,81 au repos, quelle que soit l'orientation
        du module. C'est la grandeur à surveiller pour un choc ; les axes
        pris isolément dépendent de la façon dont la carte est vissée."""
        return (self.x**2 + self.y**2 + self.z**2) ** 0.5


class I2cBus(Protocol):
    """Ce que le pilote attend d'un bus — le sous-ensemble de `smbus2.SMBus`
    réellement utilisé, et donc tout ce qu'une doublure de test doit fournir."""

    def read_byte_data(self, addr: int, register: int) -> int: ...

    def write_byte_data(self, addr: int, register: int, value: int) -> None: ...

    def read_i2c_block_data(self, addr: int, register: int, length: int) -> list[int]: ...

    def close(self) -> None: ...


class Adxl345:
    def __init__(
        self,
        *,
        bus: I2cBus | None = None,
        address: int = hardware.ADXL345_I2C_ADDRESS,
        output_rate_hz: int = hardware.ADXL345_OUTPUT_RATE_HZ,
        counts_per_g: float = hardware.ADXL345_COUNTS_PER_G,
    ) -> None:
        self._counts_per_g = counts_per_g
        if bus is None:
            from smbus2 import SMBus  # import différé : inutile sur un poste de dev

            bus = SMBus(hardware.I2C_BUS)
            self._owns_bus = True
        else:
            self._owns_bus = False
        self._bus = bus
        self._address = address

        devid = self._bus.read_byte_data(self._address, REG_DEVID)
        if devid != DEVID_EXPECTED:
            # Un module absent ou mal câblé se manifeste ici plutôt que par
            # des zéros silencieux, qui ressembleraient à une voiture à
            # l'arrêt — l'échec le plus trompeur possible pour ce capteur.
            raise RuntimeError(
                f"pas d'ADXL345 à l'adresse 0x{self._address:02x} : DEVID lu 0x{devid:02x}, "
                f"attendu 0x{DEVID_EXPECTED:02x} (vérifier le câblage SDA/SCL et `i2cdetect -y {hardware.I2C_BUS}`)"
            )

        try:
            rate_code = _BW_RATE_CODES[output_rate_hz]
        except KeyError:
            raise ValueError(
                f"cadence {output_rate_hz} Hz non gérée ; valeurs possibles : "
                f"{sorted(_BW_RATE_CODES)}"
            ) from None
        self._bus.write_byte_data(self._address, REG_BW_RATE, rate_code)
        self._bus.write_byte_data(
            self._address, REG_DATA_FORMAT, DATA_FORMAT_FULL_RES | DATA_FORMAT_RANGE_16G
        )
        # Mise en mesure en dernier : la fiche technique demande que la
        # configuration soit posée avant, sinon les premiers échantillons
        # sortent avec l'ancien réglage.
        self._bus.write_byte_data(self._address, REG_POWER_CTL, POWER_CTL_MEASURE)
        # Les registres de données valent 0 tant que le premier échantillon
        # n'est pas converti : sans cette attente, la toute première lecture
        # rendait 0,0,0 — soit exactement ce qu'affiche un capteur en panne.
        self._settle(2 / output_rate_hz)

    @staticmethod
    def _settle(duration_s: float) -> None:
        """Attente du premier échantillon — isolée pour que les tests, qui
        n'ont pas de capteur à attendre, la neutralisent."""
        time.sleep(duration_s)

    def read(self) -> Acceleration:
        """Lit les trois axes d'un coup, en m/s².

        Les 6 octets partent en **une seule** transaction I2C : lus axe par
        axe, X pourrait venir d'un échantillon et Z du suivant, ce qui
        fausserait la norme sur un mouvement rapide — exactement le cas où
        elle sert.
        """
        raw = self._bus.read_i2c_block_data(self._address, REG_DATAX0, 6)
        x, y, z = struct.unpack("<hhh", bytes(raw))  # 16 bits signés, petit-boutiste
        scale = STANDARD_GRAVITY_M_S2 / self._counts_per_g
        return Acceleration(x=x * scale, y=y * scale, z=z * scale)

    def close(self) -> None:
        # Remise en veille : le capteur reste alimenté par le Pi même une
        # fois le programme terminé, autant ne pas le laisser échantillonner
        # dans le vide.
        self._bus.write_byte_data(self._address, REG_POWER_CTL, 0x00)
        if self._owns_bus:
            self._bus.close()

    def __enter__(self) -> "Adxl345":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
