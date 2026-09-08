"""Domaci ukol 1 - LLM API + volani nastroju (function calling).

Skript zavola Gemini API, model si sam vybere nastroj, skript nastroj
vykona a vysledek posle zpet modelu. Smycka bezi tak dlouho, dokud model
chce volat dalsi nastroje.

Nastroje se retezi: z cisteho prijmu se spocita maximalni hypoteka,
z ni mesicni splatka a z te celkove uroky. Kazdy krok pracuje s vystupem
predchoziho, takze nejde o jedno izolovane volani.
"""

import argparse
import os
import sys

from dotenv import load_dotenv
from google import genai
from google.genai import types

from nastroje import DOSTUPNE_FUNKCE

load_dotenv()

# Windows konzole jede v cp1252 a na ceske diakritice by spadla
# na UnicodeEncodeError. Vystup proto prepneme na UTF-8.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

MODEL = "gemini-3.6-flash"
MAX_KROKU = 8  # pojistka proti nekonecne smycce

VYCHOZI_SAZBA = 4.9
VYCHOZI_DOBA = 30

# Deklarace nastroju pro model. Popisy jsou to jedine, podle ceho se model
# rozhoduje, ktery nastroj zavolat, takze musi byt konkretni.
NASTROJE = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="max_hypoteka",
            description=(
                "Spocita maximalni vysi hypoteky, kterou uzivatel dostane, "
                "z jeho cisteho mesicniho prijmu. Pouzij vzdy, kdyz uzivatel "
                "uvede svuj cisty prijem a chce vedet, na kolik ma narok. "
                "Pokud uzivatel uvede rocni prijem, vydel ho dvanacti."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "cisty_mesicni_prijem": types.Schema(
                        type=types.Type.NUMBER,
                        description="Cisty mesicni prijem v eurech, napr. 2000",
                    ),
                },
                required=["cisty_mesicni_prijem"],
            ),
        ),
        types.FunctionDeclaration(
            name="mesicni_splatka",
            description=(
                "Spocita mesicni anuitni splatku uveru nebo hypoteky. "
                "Pouzij vzdy, kdyz se uzivatel pta na vysi mesicni splatky. "
                "Jako jistinu muzes pouzit vysledek nastroje max_hypoteka."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "jistina": types.Schema(
                        type=types.Type.NUMBER,
                        description="Vyse uveru v eurech, napr. 192000",
                    ),
                    "urokova_sazba": types.Schema(
                        type=types.Type.NUMBER,
                        description="Rocni urokova sazba v procentech, napr. 4.9",
                    ),
                    "doba_v_letech": types.Schema(
                        type=types.Type.NUMBER,
                        description="Doba splaceni v letech, napr. 30",
                    ),
                },
                required=["jistina", "urokova_sazba", "doba_v_letech"],
            ),
        ),
        types.FunctionDeclaration(
            name="celkove_naklady",
            description=(
                "Spocita, kolik uzivatel za cely uver zaplati celkem a kolik "
                "z toho jsou uroky. Vyzaduje jiz znamou mesicni splatku, "
                "takze ji nejdriv ziskej nastrojem mesicni_splatka."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "mesicni_splatka": types.Schema(
                        type=types.Type.NUMBER,
                        description="Mesicni splatka v eurech",
                    ),
                    "doba_v_letech": types.Schema(
                        type=types.Type.NUMBER,
                        description="Doba splaceni v letech",
                    ),
                    "jistina": types.Schema(
                        type=types.Type.NUMBER,
                        description="Puvodni vyse uveru v eurech",
                    ),
                },
                required=["mesicni_splatka", "doba_v_letech", "jistina"],
            ),
        ),
    ]
)

SYSTEMOVA_INSTRUKCE = (
    "Jsi hypotecni poradce. Cisla nikdy nepocitej sam, vzdy pouzij dostupne "
    "nastroje. Pokud potrebujes vysledek jednoho nastroje jako vstup pro "
    "druhy, zavolej je postupne. "
    "Kdyz uzivatel uvede cisty prijem, vzdy dojdi az na konec vypoctu a "
    "uved vsechny ctyri hodnoty: maximalni vysi hypoteky, mesicni splatku, "
    "uroky celkem a dobu splaceni v letech. "
    "Odpovidej cesky, kratce a s konkretnimi cisly v eurech (EUR). "
    "Pokud nastroj vrati klic error, vysvetli uzivateli, co je spatne, "
    "a nehadej vysledek."
)


def vykonej_nastroj(nazev: str, argumenty: dict) -> dict:
    """Zavola nastroj podle nazvu. Neznamy nazev vrati chybu, nikoli vyjimku."""
    funkce = DOSTUPNE_FUNKCE.get(nazev)
    if funkce is None:
        return {"error": f"Nastroj {nazev} neexistuje."}
    try:
        return funkce(**argumenty)
    except TypeError as chyba:
        return {"error": f"Spatne argumenty pro {nazev}: {chyba}"}


def spust_agenta(dotaz: str) -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit("Chybi GEMINI_API_KEY. Zkopiruj .env.example do .env a vypln klic.")

    client = genai.Client(api_key=api_key)
    config = types.GenerateContentConfig(
        tools=[NASTROJE],
        system_instruction=SYSTEMOVA_INSTRUKCE,
    )

    obsah = [types.Content(role="user", parts=[types.Part.from_text(text=dotaz)])]

    print(f"DOTAZ UZIVATELE:\n  {dotaz}\n")

    for krok in range(1, MAX_KROKU + 1):
        odpoved = client.models.generate_content(
            model=MODEL, contents=obsah, config=config
        )
        kandidat = odpoved.candidates[0]

        # Odpoved modelu se musi vratit do historie, jinak model v dalsim
        # kroku nevi, ze uz nastroj zavolal.
        obsah.append(kandidat.content)

        volani = [
            cast.function_call
            for cast in (kandidat.content.parts or [])
            if cast.function_call
        ]

        if not volani:
            print(f"[krok {krok}] model uz nechce zadny nastroj, koncim smycku\n")
            return odpoved.text

        odpovedi_nastroju = []
        for hovor in volani:
            argumenty = dict(hovor.args or {})
            vysledek = vykonej_nastroj(hovor.name, argumenty)

            print(f"[krok {krok}] VOLANI NASTROJE: {hovor.name}")
            print(f"           argumenty: {argumenty}")
            print(f"           vysledek:  {vysledek}\n")

            odpovedi_nastroju.append(
                types.Part.from_function_response(name=hovor.name, response=vysledek)
            )

        # Vysledky nastroju posilame zpet modelu jako dalsi vstup.
        obsah.append(types.Content(role="user", parts=odpovedi_nastroju))

    return "Dosazen limit kroku, model nedospel k finalni odpovedi."


def sestav_dotaz(args) -> str:
    """Z prijmu poskladá dotaz, jinak vezme volny text z prikazove radky."""
    if args.prijem is not None:
        return (
            f"Muj cisty mesicni prijem je {args.prijem} EUR. "
            f"Na jak velkou hypoteku mam narok, jaka bude mesicni splatka "
            f"a kolik celkem zaplatim na urocich, pri sazbe {args.sazba} % p.a. "
            f"a dobe splaceni {args.roky} let?"
        )
    if args.dotaz:
        return " ".join(args.dotaz)
    return (
        "Beru hypoteku 140 000 EUR na 25 let pri urokove sazbe 4,9 % p.a. "
        "Jaka bude mesicni splatka a kolik celkem zaplatim na urocich?"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Hypotecni poradce - LLM s volanim nastroju."
    )
    parser.add_argument(
        "--prijem",
        type=float,
        help=(
            "Cisty mesicni prijem v EUR. Spocita maximalni hypoteku "
            "(8x cisty rocni prijem), splatku i uroky."
        ),
    )
    parser.add_argument(
        "--sazba",
        type=float,
        default=VYCHOZI_SAZBA,
        help=f"Rocni urokova sazba v procentech (vychozi {VYCHOZI_SAZBA})",
    )
    parser.add_argument(
        "--roky",
        type=float,
        default=VYCHOZI_DOBA,
        help=f"Doba splaceni v letech (vychozi {VYCHOZI_DOBA})",
    )
    parser.add_argument(
        "dotaz", nargs="*", help="Volny dotaz misto parametru --prijem"
    )
    args = parser.parse_args()

    vysledek = spust_agenta(sestav_dotaz(args))
    print("FINALNI ODPOVED MODELU:")
    print(vysledek)
