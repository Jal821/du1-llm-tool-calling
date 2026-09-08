# Homework 1 — LLM API and tool calling (function calling)

A Python script that calls an LLM API, lets the model pick a tool, executes that
tool and **sends the result back to the model**, which turns it into the final
answer.

API used: **Google Gemini** (`google-genai`), model `gemini-3.6-flash`.

## The assignment and how it is met

| Requirement | Where in the code |
| --- | --- |
| Call an LLM API | `main.py`, `client.models.generate_content()` |
| Use a tool (a calculation function) | `tools.py`, three pure calculation functions |
| Return the result back to the LLM | `main.py`, `types.Part.from_function_response()` and the loop |

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

**From a net monthly income** (works out the maximum mortgage, payment and
interest):

```bash
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

**A free-text question** instead of the flags:

```bash
uv run main.py "How much interest would I pay on a 50 000 EUR loan over 10 years at 6%?"
```

Get a key at <https://aistudio.google.com/apikey>. The `.env` file is in
`.gitignore` and never reaches the repository.

### Model and quotas

The free tier has a daily request limit **per model**. When it runs out, the
script says so in one sentence instead of a traceback:

```
Gemini API quota exhausted (the free tier has a daily limit per model,
here gemini-3.6-flash). Try later or change MODEL.
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
main.py          API call, tool declarations, agent loop, CLI
tools.py         calculation functions, no API dependency
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
