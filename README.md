# DÚ 1 — LLM API a volání nástrojů (function calling)

Python skript, který zavolá LLM API, model si sám vybere nástroj, skript nástroj
vykoná a **výsledek pošle zpět modelu**, který z něj složí finální odpověď.

Použité API: **Google Gemini** (`google-genai`), model `gemini-3.6-flash`.

## Zadání a jak je splněno

| Požadavek | Kde v kódu |
| --- | --- |
| Volání LLM API | `main.py`, `client.models.generate_content()` |
| Použití nástroje (výpočetní funkce) | `nastroje.py`, tři čistě výpočetní funkce |
| Vrácení výsledku zpět LLM | `main.py`, `types.Part.from_function_response()` a smyčka |

## Doména: hypoteční poradce

Tři nástroje, přičemž **každý pracuje s výstupem předchozího**. To je jádro
úkolu — nejde o jedno izolované volání, ale o skutečné zřetězení.

| Nástroj | Vstupy | Výstup |
| --- | --- | --- |
| `max_hypoteka` | čistý měsíční příjem, zůstatek existujících hypoték | kolik ještě zbývá do zákonného stropu (8× čistý roční příjem) |
| `mesicni_splatka` | jistina, úroková sazba p.a., doba v letech | měsíční anuitní splátka |
| `celkove_naklady` | měsíční splátka, doba v letech, jistina | celkem zaplaceno, úroky celkem |

## Jak to běží

```
--prijem 2000
      │
      ▼
Gemini  ──▶ chce nástroj max_hypoteka(2000)
      │
      ▼
Skript vykoná funkci ──▶ {"max_hypoteka": 192000, ...}
      │
      ▼
Výsledek zpět do Gemini ──▶ chce nástroj mesicni_splatka(192000, 4.9, 30)
      │
      ▼
Skript vykoná funkci ──▶ {"mesicni_splatka": 1019.0, ...}
      │
      ▼
Výsledek zpět do Gemini ──▶ chce nástroj celkove_naklady(1019.0, 30, 192000)
      │
      ▼
Skript vykoná funkci ──▶ {"uroky_celkem": 174840.0, ...}
      │
      ▼
Výsledek zpět do Gemini ──▶ už nechce nástroj, píše finální odpověď
```

Smyčka běží, dokud model chce volat nástroje, s pojistkou `MAX_KROKU = 8`
proti nekonečnému cyklu. Model si pořadí volání vybírá sám, skript ho nikde
nepředepisuje.

## Spuštění

```bash
uv sync
cp .env.example .env      # a vyplň GEMINI_API_KEY
```

**Z čistého měsíčního příjmu** (spočítá maximální hypotéku, splátku i úroky):

```bash
uv run main.py --prijem 2000
uv run main.py --prijem 2000 --dluhy 50000
uv run main.py --prijem 2500 --sazba 5.2 --roky 25
```

| Parametr | Význam | Výchozí |
| --- | --- | --- |
| `--prijem` | čistý měsíční příjem v EUR | — |
| `--dluhy` | zůstatek už splácených hypoték v EUR, odečte se od stropu | 0 |
| `--sazba` | roční úroková sazba v % | 4.9 |
| `--roky` | doba splácení v letech | 30 |

Existující hypotéky se odečítají, protože zákonný strop platí na **součet
všech** hypoték osoby:

```
$ uv run main.py --prijem 2000 --dluhy 50000

[krok 1] max_hypoteka  → {'zakonny_strop_celkem': 192000,
                          'existujici_hypoteky': 50000,
                          'max_hypoteka': 142000}
[krok 2] mesicni_splatka(142000, 4.9, 30)  → 753.63 EUR
[krok 3] celkove_naklady(753.63, 30, 142000) → 129 306.80 EUR uroku
```

**Volný dotaz** místo parametrů:

```bash
uv run main.py "Kolik zaplatim na urocich u uveru 50 000 EUR na 10 let pri 6 %?"
```

Klíč se získá na <https://aistudio.google.com/apikey>. Soubor `.env` je
v `.gitignore` a do repozitáře se nikdy nedostane.

### Model a kvóty

Free tier má denní limit na požadavky **na jeden model**. Když se vyčerpá,
skript to řekne jednou větou místo tracebacku:

```
Vycerpana kvota Gemini API (free tier ma denni limit na model gemini-3.6-flash).
Zkus to pozdeji nebo zmen MODEL.
```

Model se dá přepnout bez zásahu do kódu:

```bash
GEMINI_MODEL=gemini-3.5-flash uv run main.py --prijem 2000
```

Ošetřeno je i 503 (přetížení na straně Google) a neplatný klíč.

## Ukázkový výstup

```
$ uv run main.py --prijem 2000

DOTAZ UZIVATELE:
  Muj cisty mesicni prijem je 2000.0 EUR. Na jak velkou hypoteku mam narok,
  jaka bude mesicni splatka a kolik celkem zaplatim na urocich, pri sazbe
  4.9 % p.a. a dobe splaceni 30 let?

[krok 1] VOLANI NASTROJE: max_hypoteka
           argumenty: {'cisty_mesicni_prijem': 2000}
           vysledek:  {'cisty_rocni_prijem': 24000, 'max_hypoteka': 192000, ...}

[krok 2] VOLANI NASTROJE: mesicni_splatka
           argumenty: {'jistina': 192000, 'urokova_sazba': 4.9, 'doba_v_letech': 30}
           vysledek:  {'mesicni_splatka': 1019.0, 'pocet_splatek': 360, ...}

[krok 3] VOLANI NASTROJE: celkove_naklady
           argumenty: {'mesicni_splatka': 1019, 'doba_v_letech': 30, 'jistina': 192000}
           vysledek:  {'zaplaceno_celkem': 366840, 'uroky_celkem': 174840, ...}

[krok 4] model uz nechce zadny nastroj, koncim smycku

FINALNI ODPOVED MODELU:
Na základě vašeho čistého měsíčního příjmu 2 000 EUR jsou výsledky následující:

* Maximální výše hypotéky: 192 000 EUR
* Měsíční splátka: 1 019 EUR
* Úroky celkem: 174 840 EUR
* Doba splácení: 30 let
```

## Ošetření chyb

Nástroje nikdy nevyhazují výjimku do smyčky. Při neplatném vstupu vrátí slovník
s klíčem `error`, takže chybu dostane **model** jako výsledek nástroje a může na
ni reagovat slovy místo pádu skriptu:

```
$ uv run main.py --prijem 0

[krok 1] VOLANI NASTROJE: max_hypoteka
           argumenty: {'cisty_mesicni_prijem': 0}
           vysledek:  {'error': 'Cisty mesicni prijem musi byt vetsi nez nula.'}

FINALNI ODPOVED MODELU:
Při čistém měsíčním příjmu 0 EUR nelze hypotéku poskytnout.
Čistý měsíční příjem musí být větší než nula.
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
OK max hypoteka 192000 EUR pri prijmu 2000 EUR
OK pri 50 000 EUR existujici hypoteky zbyva 142000 EUR
OK vycerpany strop vraci 0 EUR a poznamku
OK splatka 810.29 EUR, zustatek 0.0327 EUR (limit 2.9435)
OK nulovy urok
OK uroky 116778.4 EUR
OK retez: 192000 EUR -> 1019.0 EUR/mes -> 174840.0 EUR uroku za 30 let
OK neplatne vstupy vraci error
```

Tolerance není pevné číslo. Splátka se zaokrouhluje na centy, ta půlcentová
odchylka se ale každý měsíc úročí, takže na konci je vynásobená anuitním
faktorem — u 30 let přibližně 817×, tedy jednotky eur. Funkce
`povolena_odchylka()` proto limit počítá z délky a sazby úvěru. Pevná tolerance
by u dlouhých úvěrů hlásila chybu tam, kde žádná není.

## Struktura

```
main.py             volání API, deklarace nástrojů, smyčka agenta, CLI
nastroje.py         výpočetní funkce, bez závislosti na API
test_nastroje.py    nezávislá kontrola výpočtu, bez volání API
.env.example        šablona pro API klíč
```

Výpočet je záměrně oddělen od API vrstvy — `nastroje.py` je testovatelný
bez sítě a bez klíče.

## Poznámka k pravidlu 8× roční příjem

Osminásobek čistého **ročního** příjmu je regulatorní strop na **celkové
hypoteční zadlužení jedné osoby**, nikoli odhad konkrétní banky. Protože platí
na součet všech hypoték, nástroj od stropu odečítá zůstatek už splácených
hypoték — parametr `--dluhy`.

Násobek je v `nastroje.py` konstanta `NASOBEK_ROCNIHO_PRIJMU = 8`, takže se dá
změnit na jednom místě, kdyby se limit posunul.

Strop je horní hranice, ne příslib. Banka nad ním posuzuje ještě DSTI (podíl
splátky na příjmu) a LTV (podíl k hodnotě nemovitosti), takže výsledná
schválená částka může být nižší, nikdy ne vyšší.
