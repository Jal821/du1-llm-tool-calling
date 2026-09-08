"""Kontrola nastroju bez volani API.

Splatku neoverujeme stejnym vzorcem, jakym ji pocitame, protoze to by
jen zopakovalo pripadnou chybu. Misto toho uver odsimulujeme mesic po
mesici: kdyz je splatka spravna, po poslednim mesici musi byt zustatek nula.
"""

from nastroje import celkove_naklady, mesicni_splatka


def simuluj_zustatek(jistina, urokova_sazba, pocet_splatek, splatka):
    """Nezavisla kontrola - realne odsplaceni uveru mesic po mesici."""
    zustatek = jistina
    mesicni_sazba = urokova_sazba / 100 / 12
    for _ in range(pocet_splatek):
        zustatek = zustatek * (1 + mesicni_sazba) - splatka
    return zustatek


def test_splatka_uveru_dosplati_na_nulu():
    vysledek = mesicni_splatka(140_000, 4.9, 25)
    zustatek = simuluj_zustatek(
        140_000, 4.9, vysledek["pocet_splatek"], vysledek["mesicni_splatka"]
    )
    assert abs(zustatek) < 1.0, f"zustatek po poslednim mesici je {zustatek}"
    print(f"OK splatka {vysledek['mesicni_splatka']} EUR, zustatek {zustatek:.4f} EUR")


def test_nulovy_urok_je_jen_deleni():
    vysledek = mesicni_splatka(120_000, 0, 10)
    assert vysledek["mesicni_splatka"] == 1000.0
    print("OK nulovy urok")


def test_celkove_naklady_navazuji_na_splatku():
    splatka = mesicni_splatka(200_000, 5, 20)["mesicni_splatka"]
    naklady = celkove_naklady(splatka, 20, 200_000)
    assert naklady["zaplaceno_celkem"] > 200_000
    assert (
        abs(naklady["uroky_celkem"] - (naklady["zaplaceno_celkem"] - 200_000)) < 0.01
    )
    print(f"OK uroky {naklady['uroky_celkem']} EUR")


def test_neplatny_vstup_vraci_chybu_a_nespadne():
    for spatny in [
        mesicni_splatka(-1, 5, 20),
        mesicni_splatka(100, -5, 20),
        mesicni_splatka(100, 5, 0),
        celkove_naklady(0, 20, 100),
    ]:
        assert "error" in spatny, spatny
    print("OK neplatne vstupy vraci error")


if __name__ == "__main__":
    test_splatka_uveru_dosplati_na_nulu()
    test_nulovy_urok_je_jen_deleni()
    test_celkove_naklady_navazuji_na_splatku()
    test_neplatny_vstup_vraci_chybu_a_nespadne()
    print("\nVsechny kontroly prosly.")
