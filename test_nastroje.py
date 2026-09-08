"""Kontrola nastroju bez volani API.

Splatku neoverujeme stejnym vzorcem, jakym ji pocitame, protoze to by
jen zopakovalo pripadnou chybu. Misto toho uver odsimulujeme mesic po
mesici: kdyz je splatka spravna, po poslednim mesici musi byt zustatek nula.
"""

from nastroje import (
    NASOBEK_ROCNIHO_PRIJMU,
    celkove_naklady,
    max_hypoteka,
    mesicni_splatka,
)


def simuluj_zustatek(jistina, urokova_sazba, pocet_splatek, splatka):
    """Nezavisla kontrola - realne odsplaceni uveru mesic po mesici."""
    zustatek = jistina
    mesicni_sazba = urokova_sazba / 100 / 12
    for _ in range(pocet_splatek):
        zustatek = zustatek * (1 + mesicni_sazba) - splatka
    return zustatek


def povolena_odchylka(urokova_sazba, pocet_splatek):
    """Kolik smi zbyt na konci jen kvuli zaokrouhleni splatky na centy.

    Splatku zaokrouhlujeme na dve desetinna mista, takze chyba je maximalne
    pul centu. Ta se ale kazdy mesic uroci, takze na konci je nasobena
    anuitnim faktorem. U 30 let to jsou uz jednotky eur, coz je spravne
    a neni to chyba vypoctu. Pevna tolerance by tady lhala.
    """
    mesicni_sazba = urokova_sazba / 100 / 12
    if mesicni_sazba == 0:
        return 0.005 * pocet_splatek + 0.01
    anuitni_faktor = ((1 + mesicni_sazba) ** pocet_splatek - 1) / mesicni_sazba
    return 0.005 * anuitni_faktor + 0.01


def test_max_hypoteka_je_osminasobek_rocniho_prijmu():
    vysledek = max_hypoteka(2000)
    assert vysledek["cisty_rocni_prijem"] == 24_000
    assert vysledek["max_hypoteka"] == 24_000 * NASOBEK_ROCNIHO_PRIJMU == 192_000
    print(f"OK max hypoteka {vysledek['max_hypoteka']} EUR pri prijmu 2000 EUR")


def test_splatka_uveru_dosplati_na_nulu():
    vysledek = mesicni_splatka(140_000, 4.9, 25)
    zustatek = simuluj_zustatek(
        140_000, 4.9, vysledek["pocet_splatek"], vysledek["mesicni_splatka"]
    )
    limit = povolena_odchylka(4.9, vysledek["pocet_splatek"])
    assert abs(zustatek) < limit, f"zustatek {zustatek} presahl limit {limit}"
    print(
        f"OK splatka {vysledek['mesicni_splatka']} EUR, "
        f"zustatek {zustatek:.4f} EUR (limit {limit:.4f})"
    )


def test_nulovy_urok_je_jen_deleni():
    vysledek = mesicni_splatka(120_000, 0, 10)
    assert vysledek["mesicni_splatka"] == 1000.0
    print("OK nulovy urok")


def test_celkove_naklady_navazuji_na_splatku():
    splatka = mesicni_splatka(200_000, 5, 20)["mesicni_splatka"]
    naklady = celkove_naklady(splatka, 20, 200_000)
    assert naklady["zaplaceno_celkem"] > 200_000
    assert abs(naklady["uroky_celkem"] - (naklady["zaplaceno_celkem"] - 200_000)) < 0.01
    print(f"OK uroky {naklady['uroky_celkem']} EUR")


def test_cely_retez_z_prijmu_az_na_uroky():
    """Presne ta cesta, kterou jde model pri --prijem."""
    maximum = max_hypoteka(2000)["max_hypoteka"]
    splatka = mesicni_splatka(maximum, 4.9, 30)
    naklady = celkove_naklady(splatka["mesicni_splatka"], 30, maximum)

    zustatek = simuluj_zustatek(
        maximum, 4.9, splatka["pocet_splatek"], splatka["mesicni_splatka"]
    )
    limit = povolena_odchylka(4.9, splatka["pocet_splatek"])
    assert abs(zustatek) < limit, f"zustatek {zustatek} presahl limit {limit}"
    assert naklady["uroky_celkem"] > 0
    print(
        f"OK retez: {maximum} EUR -> {splatka['mesicni_splatka']} EUR/mes "
        f"-> {naklady['uroky_celkem']} EUR uroku za {naklady['doba_v_letech']} let"
    )


def test_neplatny_vstup_vraci_chybu_a_nespadne():
    for spatny in [
        max_hypoteka(0),
        max_hypoteka(-500),
        mesicni_splatka(-1, 5, 20),
        mesicni_splatka(100, -5, 20),
        mesicni_splatka(100, 5, 0),
        celkove_naklady(0, 20, 100),
    ]:
        assert "error" in spatny, spatny
    print("OK neplatne vstupy vraci error")


if __name__ == "__main__":
    test_max_hypoteka_je_osminasobek_rocniho_prijmu()
    test_splatka_uveru_dosplati_na_nulu()
    test_nulovy_urok_je_jen_deleni()
    test_celkove_naklady_navazuji_na_splatku()
    test_cely_retez_z_prijmu_az_na_uroky()
    test_neplatny_vstup_vraci_chybu_a_nespadne()
    print("\nVsechny kontroly prosly.")
