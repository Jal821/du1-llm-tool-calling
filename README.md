# DÚ 1 — LLM API a volání nástrojů (function calling)

Python skript, který zavolá LLM API, model si sám vybere nástroj, skript nástroj
vykoná a **výsledek pošle zpět modelu**, který z něj složí finální odpověď.

Použité API: **Google Gemini** (`google-genai`), model `gemini-3.6-flash`.

## Zadání a jak je splněno

| Požadavek | Kde v kódu |
| --- | --- |
| Volání LLM API | `main.py`, `client.models.generate_content()` |
| Použití nástroje (výpočetní funkce) | `nastroje.py`, dvě čistě výpočetní funkce |
| Vrácení výsledku zpět LLM | `main.py`, `types.Part.from_function_response()` a smyčka |

## Doména: hypoteční kalkulačka

Dva nástroje, přičemž **druhý pracuje s výstupem prvního**. To je jádro úkolu —
nejde o jedno izolované volání, ale o skutečné zřetězení.

| Nástroj | Vstupy | Výstup |
| --- | --- | --- |
| `mesicni_splatka` | jistina, úroková sazba p.a., doba v letech | měsíční anuitní splátka |
| `celkove_naklady` | měsíční splátka, doba v letech, jistina | celkem zaplaceno, úroky celkem |

## Jak to běží

```
Dotaz uživatele
      │
      ▼
Gemini  ──▶ chce nástroj mesicni_splatka(140000, 4.9, 25)
      │
      ▼
Skript vykoná funkci ──▶ {"mesicni_splatka": 810.29, ...}
      │
      ▼
Výsledek zpět do Gemini ──▶ chce nástroj celkove_naklady(810.29, 25, 140000)
      │
      ▼
Skript vykoná funkci ──▶ {"uroky_celkem": 103087.0, ...}
      │
      ▼
Výsledek zpět do Gemini ──▶ už nechce nástroj, píše finální odpověď
```

Smyčka běží, dokud model chce volat nástroje, s pojistkou `MAX_KROKU = 6`
proti nekonečnému cyklu.

## Spuštění

```bash
uv sync
cp .env.example .env      # a vyplň GEMINI_API_KEY
uv run main.py
```

Vlastní dotaz:

```bash
uv run main.py "Kolik zaplatim na urocich u uveru 50 000 EUR na 10 let pri 6 %?"
```

Klíč se získá na <https://aistudio.google.com/apikey>. Soubor `.env` je
v `.gitignore` a do repozitáře se nikdy nedostane.

## Ukázkový výstup

```
DOTAZ UZIVATELE:
  Beru hypoteku 140 000 EUR na 25 let pri urokove sazbe 4,9 % p.a. Jaka bude
  mesicni splatka a kolik celkem zaplatim na urocich?

[krok 1] VOLANI NASTROJE: mesicni_splatka
           argumenty: {'jistina': 140000, 'urokova_sazba': 4.9, 'doba_v_letech': 25}
           vysledek:  {'mesicni_splatka': 810.29, 'pocet_splatek': 300, ...}

[krok 2] VOLANI NASTROJE: celkove_naklady
           argumenty: {'mesicni_splatka': 810.29, 'doba_v_letech': 25, 'jistina': 140000}
           vysledek:  {'zaplaceno_celkem': 243087.0, 'uroky_celkem': 103087.0, ...}

[krok 3] model uz nechce zadny nastroj, koncim smycku

FINALNI ODPOVED MODELU:
Vaše měsíční splátka bude 810,29 EUR.
Za celou dobu 25 let zaplatíte na úrocích celkem 103 087 EUR
(celkově zaplatíte 243 087 EUR).
```

## Ošetření chyb

Nástroje nikdy nevyhazují výjimku do smyčky. Při neplatném vstupu vrátí slovník
s klíčem `error`, takže chybu dostane **model** jako výsledek nástroje a může na
ni reagovat slovy místo pádu skriptu:

```
$ uv run main.py "Jaka bude splatka u hypoteky 3 000 000 EUR na 0 let pri 5 %?"

[krok 1] VOLANI NASTROJE: mesicni_splatka
           argumenty: {'jistina': 3000000, 'urokova_sazba': 5, 'doba_v_letech': 0}
           vysledek:  {'error': 'Doba splaceni musi byt vetsi nez nula.'}

FINALNI ODPOVED MODELU:
Měsíční splátku nelze spočítat, protože doba splácení musí být větší než 0 let.
```

Stejně tak je ošetřen neznámý název nástroje a špatné argumenty.

## Kontrola výpočtu

```bash
uv run test_nastroje.py
```

Splátka se **neověřuje stejným vzorcem**, kterým se počítá — to by jen zopakovalo
případnou chybu. Místo toho se úvěr odsimuluje měsíc po měsíci a kontroluje se,
že po poslední splátce je zůstatek nula:

```
OK splatka 810.29 EUR, zustatek 0.0327 EUR
OK nulovy urok
OK uroky 116778.4 EUR
OK neplatne vstupy vraci error
```

Zbytkových 3 centy je zaokrouhlení splátky na dvě desetinná místa, což odpovídá
tomu, jak se úvěr splácí v praxi.

## Struktura

```
main.py             volání API, deklarace nástrojů, smyčka agenta
nastroje.py         výpočetní funkce, bez závislosti na API
test_nastroje.py    nezávislá kontrola výpočtu, bez volání API
.env.example        šablona pro API klíč
```

Výpočet je záměrně oddělen od API vrstvy — `nastroje.py` je testovatelný
bez sítě a bez klíče.
