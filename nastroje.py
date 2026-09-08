"""Deterministicke nastroje pro hypotecni kalkulacku.

Kazda funkce vraci slovnik. Pri neplatnem vstupu vraci klic "error",
takze chybu dostane model jako vysledek nastroje a muze na ni reagovat.
Zadna funkce nevyhazuje vyjimku do smycky agenta.
"""


def mesicni_splatka(jistina: float, urokova_sazba: float, doba_v_letech: float) -> dict:
    """Spocita mesicni anuitni splatku uveru."""
    if jistina <= 0:
        return {"error": "Jistina musi byt vetsi nez nula."}
    if urokova_sazba < 0:
        return {"error": "Urokova sazba nemuze byt negativni."}
    if doba_v_letech <= 0:
        return {"error": "Doba splaceni musi byt vetsi nez nula."}

    pocet_splatek = int(round(doba_v_letech * 12))
    mesicni_sazba = urokova_sazba / 100 / 12

    if mesicni_sazba == 0:
        splatka = jistina / pocet_splatek
    else:
        koeficient = (1 + mesicni_sazba) ** pocet_splatek
        splatka = jistina * mesicni_sazba * koeficient / (koeficient - 1)

    return {
        "mesicni_splatka": round(splatka, 2),
        "pocet_splatek": pocet_splatek,
        "jistina": jistina,
        "urokova_sazba": urokova_sazba,
    }


def celkove_naklady(mesicni_splatka: float, doba_v_letech: float, jistina: float) -> dict:
    """Spocita, kolik celkem zaplatis a kolik z toho jsou uroky."""
    if mesicni_splatka <= 0:
        return {"error": "Mesicni splatka musi byt vetsi nez nula."}
    if doba_v_letech <= 0:
        return {"error": "Doba splaceni musi byt vetsi nez nula."}
    if jistina <= 0:
        return {"error": "Jistina musi byt vetsi nez nula."}

    pocet_splatek = int(round(doba_v_letech * 12))
    zaplaceno_celkem = mesicni_splatka * pocet_splatek
    uroky = zaplaceno_celkem - jistina

    return {
        "zaplaceno_celkem": round(zaplaceno_celkem, 2),
        "uroky_celkem": round(uroky, 2),
        "uroky_v_procentech_jistiny": round(uroky / jistina * 100, 1),
        "pocet_splatek": pocet_splatek,
    }


# Mapa nazvu nastroje na skutecnou funkci. Smycka agenta hleda jen zde,
# takze model nemuze zavolat nic jineho.
DOSTUPNE_FUNKCE = {
    "mesicni_splatka": mesicni_splatka,
    "celkove_naklady": celkove_naklady,
}
