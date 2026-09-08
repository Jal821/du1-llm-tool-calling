# Homework 1 — LLM API and tool calling (function calling)

A Python script that calls an LLM API, lets the model pick a tool, executes that
tool and **sends the result back to the model**, which turns it into the final
answer.

Two interchangeable backends, both driven by the same tool definitions:

| Backend | API | Protocol |
| --- | --- | --- |
| `gemini` (default) | Google Gemini via `google-genai` | Gemini native function calling |
| `openai` | any OpenAI-compatible endpoint, e.g. a local LiteLLM proxy | OpenAI `tools` / `tool_calls` |

Tool calling is the same idea in two different wire formats. The tools live in
`tools.py` as plain JSON Schema and each backend converts them to its own shape,
so a tool is described in exactly one place and the two cannot drift apart.

## The assignment and how it is met

| Requirement | Where in the code |
| --- | --- |
| Call an LLM API | `main.py`, `client.models.generate_content()` (Gemini) or `client.chat.completions.create()` (OpenAI-compatible) |
| Use a tool (a calculation function) | `tools.py`, three pure calculation functions plus their schemas |
| Return the result back to the LLM | `main.py`, `types.Part.from_function_response()` (Gemini) or a `tool`-role message keyed to the call id (OpenAI-compatible) |

## Domain: mortgage advisor

Three tools, where **each one works on the output of the previous one**. That is
the core of the assignment: not a single isolated call, but real chaining.

| Tool | Inputs | Output |
| --- | --- | --- |
| `max_mortgage` | net monthly income, balance of existing mortgages | how much is left before the legal cap (8× net yearly income) |
| `monthly_payment` | principal, annual interest rate, years | monthly annuity payment |
| `total_cost` | monthly payment, years, principal | total repaid, total interest |

## How a run flows

```
--income 2000
      │
      ▼
Gemini  ──▶ wants max_mortgage(2000)
      │
      ▼
Script executes it ──▶ {"max_mortgage": 192000, ...}
      │
      ▼
Result back to Gemini ──▶ wants monthly_payment(192000, 4.9, 30)
      │
      ▼
Script executes it ──▶ {"monthly_payment": 1019.0, ...}
      │
      ▼
Result back to Gemini ──▶ wants total_cost(1019.0, 30, 192000)
      │
      ▼
Script executes it ──▶ {"total_interest": 174840.0, ...}
      │
      ▼
Result back to Gemini ──▶ wants no more tools, writes the final answer
```

The loop runs as long as the model wants tools, with `MAX_STEPS = 8` as a guard
against an endless cycle. The model chooses the order of calls itself; the
script never prescribes it.

## Running it

```bash
uv sync
cp .env.example .env      # then fill in GEMINI_API_KEY
```

**Interactive** — run it with no arguments and it interviews you, one question
at a time:

```
$ uv run main.py

BACKEND: gemini, model gemini-3.7-flash

I am a mortgage calculator.
I will ask you a few questions, one at a time.

What is your monthly income? This is your NET income, in EUR: 2500

Do you already have any mortgages? (yes/no): yes

Mortgage number 1:
  How much is still outstanding, in EUR: 40000
  How many years does it still run: 12
  At what interest rate, in % per year: 3,5

Do you have another mortgage? (yes/no): yes

Mortgage number 2:
  How much is still outstanding, in EUR: 15000
  How many years does it still run: 5
  At what interest rate, in % per year: 6

Do you have another mortgage? (yes/no): no

Now the mortgage you are asking about:
  What interest rate do you expect, in % per year [4.9]: 5.2
  Over how many years do you want to repay it [30]: 25
```

The answers are turned into one plain-language question, which is printed so
you can see exactly what the model was asked:

```
PUTTING THIS TO THE MODEL:
  My net monthly income is 2500 EUR. I already hold 2 mortgages: 40000 EUR
  outstanding over 12 more years at 3.5% p.a.; 15000 EUR outstanding over 5
  more years at 6% p.a. How large a mortgage do I qualify for, ...
```

The model then picks the tools. With existing mortgages it also prices each of
them, so the answer includes the total monthly burden:

```
Maximum mortgage you qualify for   185,000 EUR   (cap 240,000 less the 55,000 held)
Monthly payment                    1,103.16 EUR
Total interest paid                145,948.00 EUR
Repayment term                     25 years

Existing: 40,000 @ 3.5% over 12y -> 340.58 EUR
          15,000 @ 6.0% over 5y  -> 289.99 EUR
Total monthly across all mortgages 1,733.73 EUR
```

Details of the interview:

- Every amount is asked for separately, and a non-numeric answer is rejected
  and asked again rather than crashing.
- A comma works as a decimal separator, so `3,5` is accepted as well as `3.5`.
- The last two questions have defaults in square brackets; a blank line takes
  them.
- Existing mortgages are asked for one at a time and can be listed as many as
  you hold. Their balances are summed, because the legal cap applies to all of
  them together.
- After an answer it offers another calculation. Ctrl+C ends the session.
- If the API fails on one question, the session says so and carries on rather
  than dying.

**Non-interactive** — give the question up front and it answers once and exits,
which is what you want from a script or a CI job:

```bash
uv run main.py "How much interest would I pay on a 50000 EUR loan over 10 years at 6%?"
uv run main.py --income 2000
uv run main.py --income 2000 --debts 50000
uv run main.py --income 2500 --rate 5.2 --years 25
```

| Flag | Meaning | Default |
| --- | --- | --- |
| `--income` | net monthly income in EUR | — |
| `--debts` | balance of existing mortgages in EUR, subtracted from the cap | 0 |
| `--rate` | annual interest rate in percent | 4.9 |
| `--years` | repayment term in years | 30 |

The `--income` flags just assemble a question for you. Anything they can ask,
you can also type in your own words.

Existing mortgages are subtracted because the legal cap applies to the **sum of
all** mortgages a person holds:

```
$ uv run main.py --income 2000 --debts 50000

[step 1] max_mortgage  → {'legal_cap_total': 192000,
                          'existing_mortgages': 50000,
                          'max_mortgage': 142000}
[step 2] monthly_payment(142000, 4.9, 30)  → 753.63 EUR
[step 3] total_cost(753.63, 30, 142000)    → 129,306.80 EUR interest
```

Get a key at <https://aistudio.google.com/apikey>. The `.env` file is in
`.gitignore` and never reaches the repository.

### Choosing a backend

By default the script talks straight to Google Gemini, which only needs a free
key from AI Studio. That is the path to use if you just want to run this.

To use an OpenAI-compatible endpoint instead, set `OPENAI_BASE_URL` in `.env`:

```
OPENAI_BASE_URL=http://localhost:20128/v1
OPENAI_API_KEY=sk-...
OPENAI_MODEL=auto/best-fast
```

The backend is then picked automatically, and `--backend` forces either one:

```bash
uv run main.py --backend gemini --income 2000
uv run main.py --backend openai --income 2000
```

The first line of the output always says which backend and model ran:

```
BACKEND: openai, model auto/best-fast at http://localhost:20128/v1
```

Note that the calculation layer is identical either way. Both backends produce
the same figures because `tools.py` never touches an API.

### Model and quotas

On the Gemini backend the free tier has a daily request limit **per model**.
When it runs out, the script says so in one sentence instead of a traceback:

```
Gemini API quota exhausted (the free tier has a daily limit per model,
here gemini-3.7-flash). Try later or change GEMINI_MODEL.
```

The model can be switched without touching the code:

```bash
GEMINI_MODEL=gemini-3.5-flash uv run main.py --income 2000
```

A 503 (overload on Google's side) and an invalid key are handled the same way.

## Sample output

```
$ uv run main.py --income 2000

USER QUESTION:
  My net monthly income is 2000.0 EUR. I hold no mortgage yet. How large a
  mortgage do I qualify for, what would the monthly payment be, and how much
  interest would I pay in total, at a rate of 4.9% p.a. over 30 years?

[step 1] TOOL CALL: max_mortgage
         arguments: {'net_monthly_income': 2000, 'existing_mortgages': 0}
         result:    {'net_yearly_income': 24000, 'legal_cap_total': 192000,
                     'max_mortgage': 192000, ...}

[step 2] TOOL CALL: monthly_payment
         arguments: {'principal': 192000, 'interest_rate': 4.9, 'years': 30}
         result:    {'monthly_payment': 1019.0, 'number_of_payments': 360, ...}

[step 3] TOOL CALL: total_cost
         arguments: {'monthly_payment': 1019, 'years': 30, 'principal': 192000}
         result:    {'total_paid': 366840, 'total_interest': 174840, ...}

[step 4] model wants no more tools, leaving the loop

FINAL ANSWER FROM THE MODEL:
Based on your monthly net income of 2,000 EUR, here are the details for your
mortgage:

* Maximum mortgage: 192,000 EUR
* Monthly payment: 1,019 EUR
* Total interest: 174,840 EUR
* Repayment term: 30 years
```

## Error handling

The tools never raise an exception into the loop. On invalid input they return a
dict with an `error` key, so the **model** receives the problem as a tool result
and can answer in words instead of the script crashing:

```
$ uv run main.py --income 0

[step 1] TOOL CALL: max_mortgage
         arguments: {'net_monthly_income': 0, 'existing_mortgages': 0}
         result:    {'error': 'Net monthly income must be greater than zero.'}

FINAL ANSWER FROM THE MODEL:
Based on the information provided, a mortgage cannot be calculated because your
net monthly income must be greater than zero to qualify for a loan.
```

An unknown tool name and bad arguments are handled the same way.

An exhausted cap is treated as a valid answer rather than an error — the model
correctly stops the chain instead of calling the remaining two tools:

```
$ uv run main.py --income 1500 --debts 200000

[step 1] max_mortgage → {'legal_cap_total': 144000, 'max_mortgage': 0,
                         'note': 'The legal cap is already used up ...'}

FINAL ANSWER FROM THE MODEL:
Maximum new mortgage: 0 EUR (your legal cap is 144,000 EUR and you already
hold 200,000 EUR, so the cap is used up).
```

## Verifying the calculation

```bash
uv run test_tools.py
```

The payment is **not verified with the same formula** that computes it, since
that would only repeat any mistake. Instead the loan is simulated month by month
and the check is that the balance after the last payment is zero:

```
OK max mortgage 192000 EUR on an income of 2000 EUR
OK with 50 000 EUR already held, 142000 EUR remains
OK exhausted cap returns 0 EUR and a note
OK payment 810.29 EUR, balance 0.0327 EUR (limit 2.9435)
OK zero interest
OK interest 116778.4 EUR
OK chain: 192000 EUR -> 1019.0 EUR/month -> 174840.0 EUR interest over 30 years
OK invalid inputs return an error
```

The tolerance is not a fixed number. The payment is rounded to cents, and that
half-cent earns interest every month, so by the end it has been multiplied by
the annuity factor — over 30 years roughly 817×, which is a few euros. The
`allowed_drift()` function therefore derives the limit from the term and the
rate. A fixed tolerance would report an error on long loans where there is none.

## Layout

```
main.py          both backends, agent loops, CLI
tools.py         calculation functions plus the shared tool schemas
test_tools.py    independent verification, no API calls
.env.example     template for the API key
```

The calculation is deliberately separated from the API layer, so `tools.py` is
testable without a network or a key.

## A note on the 8× yearly income rule

Eight times net **yearly** income is a regulatory ceiling on a person's **total
mortgage debt**, not one bank's estimate. Because it applies to the sum of all
mortgages, the tool subtracts the outstanding balance of existing ones — the
`--debts` flag.

The multiple lives in `tools.py` as the constant `INCOME_MULTIPLE = 8`, so it can
be changed in one place should the limit move.

The cap is an upper bound, not a promise. On top of it a bank also assesses DSTI
(payment as a share of income) and LTV (loan against property value), so the
amount actually approved can be lower, never higher.
