"""Teste `Adxl345` sans matériel : une doublure de bus I2C suffit à vérifier
la conversion comptes -> m/s², qui est la seule chose que ce module décide.
Même principe que `tests/motors/test_gpio_driver.py`, aucun Raspberry Pi
requis.

Les assertions portent sur des **m/s²** et sur les octets réellement écrits
dans les registres — c'est-à-dire les deux frontières du module.
"""

import struct

import pytest

from smart_car.config import hardware
from smart_car.sensors.adxl345 import (
    DATA_FORMAT_FULL_RES,
    DEVID_EXPECTED,
    POWER_CTL_MEASURE,
    REG_BW_RATE,
    REG_DATA_FORMAT,
    REG_DATAX0,
    REG_DEVID,
    REG_POWER_CTL,
    STANDARD_GRAVITY_M_S2,
    Adxl345,
)

# Les tests de conversion fixent eux-mêmes la sensibilité : ils vérifient
# l'arithmétique du pilote, pas la valeur calibrée d'un exemplaire précis
# (`hardware.ADXL345_COUNTS_PER_G`, qui bougera au prochain module câblé).
DATASHEET_COUNTS_PER_G = 256


def make_sensor(bus: "FakeBus", **kwargs) -> Adxl345:
    kwargs.setdefault("counts_per_g", DATASHEET_COUNTS_PER_G)
    return Adxl345(bus=bus, **kwargs)


class FakeBus:
    """Doublure de bus : retient les registres écrits, sert des comptes fixés."""

    def __init__(self, *, devid: int = DEVID_EXPECTED, counts: tuple[int, int, int] = (0, 0, 0)) -> None:
        self.devid = devid
        self.counts = counts
        self.writes: list[tuple[int, int]] = []
        self.closed = False
        self.block_reads = 0

    def read_byte_data(self, addr: int, register: int) -> int:
        assert register == REG_DEVID
        return self.devid

    def write_byte_data(self, addr: int, register: int, value: int) -> None:
        self.writes.append((register, value))

    def read_i2c_block_data(self, addr: int, register: int, length: int) -> list[int]:
        assert (register, length) == (REG_DATAX0, 6)
        self.block_reads += 1
        return list(struct.pack("<hhh", *self.counts))

    def close(self) -> None:
        self.closed = True

    def value_written(self, register: int) -> int:
        return next(value for reg, value in reversed(self.writes) if reg == register)


def test_repos_a_plat_lit_environ_une_gravite_sur_z():
    # 256 comptes = 1 g en pleine résolution : c'est ce que rend un module
    # posé à plat, et le test de bon fonctionnement le plus rapide au banc.
    sensor = make_sensor(FakeBus(counts=(0, 0, 256)))
    accel = sensor.read()
    assert accel.z == pytest.approx(STANDARD_GRAVITY_M_S2, abs=0.01)
    assert accel.magnitude == pytest.approx(STANDARD_GRAVITY_M_S2, abs=0.01)


def test_comptes_negatifs_donnent_une_acceleration_negative():
    # Les axes sont signés : module retourné = -1 g sur Z. Une lecture non
    # signée rendrait ici +2 g, une erreur silencieuse et plausible.
    sensor = make_sensor(FakeBus(counts=(-256, 0, 0)))
    assert sensor.read().x == pytest.approx(-STANDARD_GRAVITY_M_S2, abs=0.01)


def test_les_trois_axes_viennent_d_une_seule_transaction():
    bus = FakeBus(counts=(128, -128, 256))
    sensor = make_sensor(bus)
    accel = sensor.read()
    assert bus.block_reads == 1
    assert (accel.x, accel.y) == pytest.approx(
        (STANDARD_GRAVITY_M_S2 / 2, -STANDARD_GRAVITY_M_S2 / 2), abs=0.01
    )


def test_configuration_posee_avant_la_mise_en_mesure():
    # POWER_CTL en dernier : la fiche technique demande que la plage et la
    # cadence soient déjà écrites, sinon les premiers échantillons sortent
    # avec l'ancien réglage.
    bus = FakeBus()
    make_sensor(bus)
    registres = [reg for reg, _ in bus.writes]
    assert registres.index(REG_POWER_CTL) > registres.index(REG_DATA_FORMAT)
    assert registres.index(REG_POWER_CTL) > registres.index(REG_BW_RATE)
    assert bus.value_written(REG_POWER_CTL) == POWER_CTL_MEASURE
    assert bus.value_written(REG_DATA_FORMAT) & DATA_FORMAT_FULL_RES


def test_capteur_absent_echoue_au_lieu_de_rendre_des_zeros():
    # Sans ce contrôle, un module débranché rendrait 0,0,0 — indiscernable
    # d'une voiture à l'arrêt.
    with pytest.raises(RuntimeError, match="0x53"):
        make_sensor(FakeBus(devid=0xFF))


def test_cadence_non_geree_refusee():
    with pytest.raises(ValueError):
        make_sensor(FakeBus(), output_rate_hz=7)


def test_close_remet_en_veille_et_ferme_le_bus_possede():
    bus = FakeBus()
    sensor = make_sensor(bus)
    sensor.close()
    assert bus.value_written(REG_POWER_CTL) == 0x00
    # Bus fourni par l'appelant : à lui de le fermer, pas au pilote.
    assert not bus.closed


def test_adresse_par_defaut_celle_du_cablage():
    assert hardware.ADXL345_I2C_ADDRESS == 0x53


def test_la_sensibilite_calibree_est_bien_appliquee():
    # Le pilote lit `hardware.ADXL345_COUNTS_PER_G` par défaut, sinon
    # l'exemplaire non conforme câblé ici afficherait 40 % de trop.
    sensor = Adxl345(bus=FakeBus(counts=(0, 0, round(hardware.ADXL345_COUNTS_PER_G))))
    assert sensor.read().magnitude == pytest.approx(STANDARD_GRAVITY_M_S2, abs=0.02)
