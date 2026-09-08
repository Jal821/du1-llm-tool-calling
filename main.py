"""Domaci ukol 1 - LLM API + volani nastroju (function calling).

Skript zavola Gemini API, model si sam vybere nastroj, skript nastroj
vykona a vysledek posle zpet modelu. Smycka bezi tak dlouho, dokud model
chce volat dalsi nastroje. Druhy nastroj pracuje s vystupem prvniho,
takze jde o skutecne zretezeni, ne o jedno volani.
"""

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
MAX_KROKU = 6  # pojistka proti nekonecne smycce

DOTAZ = (
    "Beru hypoteku 140 000 EUR na 25 let pri urokove sazbe 4,9 % p.a. "
    "Jaka bude mesicni splatka a kolik celkem zaplatim na urocich?"
)

# Deklarace nastroju pro model. Popisy jsou to jedine, podle ceho se model
# rozhoduje, ktery nastroj zavolat, takze musi byt konkretni.
NASTROJE = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="mesicni_splatka",
            description=(
                "Spocita mesicni anuitni splatku uveru nebo hypoteky. "
                "Pouzij vzdy, kdyz se uzivatel pta na vysi mesicni splatky."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "jistina": types.Schema(
                        type=types.Type.NUMBER,
                        description="Vyse uveru v eurech, napr. 140000",
                    ),
                    "urokova_sazba": types.Schema(
                        type=types.Type.NUMBER,
                        description="Rocni urokova sazba v procentech, napr. 4.9",
                    ),
                    "doba_v_letech": types.Schema(
                        type=types.Type.NUMBER,
                        description="Doba splaceni v letech, napr. 25",
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
    "Jsi financni asistent. Cisla nikdy nepocitej sam, vzdy pouzij dostupne "
    "nastroje. Pokud potrebujes vysledek jednoho nastroje jako vstup pro "
    "druhy, zavolej je postupne. Odpovidej cesky, kratce a s konkretnimi cisly v eurech (EUR). "
    "Pokud nastroj vrati klic 'error', vysvetli uzivateli, co je spatne, "
    "a nehadej vysledek."
)


def vykonej_nastroj(nazev: str, argumenty: dict) -> dict:
    """Zavola nastroj podle nazvu. Neznamy nazev vrati chybu, nikoli vyjimku."""
    funkce = DOSTUPNE_FUNKCE.get(nazev)
    if funkce is None:
        return {"error": f"Nastroj '{nazev}' neexistuje."}
    try:
        return funkce(**argumenty)
    except TypeError as chyba:
        return {"error": f"Spatne argumenty pro '{nazev}': {chyba}"}


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


if __name__ == "__main__":
    # Dotaz lze predat i z prikazove radky: uv run main.py "muj dotaz"
    dotaz = " ".join(sys.argv[1:]) or DOTAZ
    vysledek = spust_agenta(dotaz)
    print("FINALNI ODPOVED MODELU:")
    print(vysledek)
