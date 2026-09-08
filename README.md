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

**Interactive** — run it with no arguments and it asks you for the question:

```
$ uv run main.py

BACKEND: gemini, model gemini-3.7-flash

Ask a mortgage question in your own words. Examples:
  - My net monthly income is 2000 EUR, how big a mortgage can I get?
  - I earn 2500 net and already owe 40000. What can I still borrow over 25 years?
  - How much interest would I pay on a 50000 EUR loan over 10 years at 6%?

Your question (blank to quit): I earn 2200 net and already owe 30000. What can I still borrow?

[step 1] TOOL CALL: max_mortgage
         arguments: {'net_monthly_income': 2200, 'existing_mortgages': 30000}
         result:    {'legal_cap_total': 211200, 'max_mortgage': 181200, ...}

[step 2] TOOL CALL: monthly_payment
         arguments: {'principal': 181200, 'interest_rate': 4.9, 'years': 30}
         result:    {'monthly_payment': 961.68, ...}

[step 3] TOOL CALL: total_cost
         result:    {'total_paid': 346204.8, 'total_interest': 165004.8, ...}

[step 4] model wants no more tools, leaving the loop

FINAL ANSWER FROM THE MODEL:
- Maximum mortgage: €181,200
- Monthly payment: €961.68
- Total interest over 30 years: €165,004.80
- Repayment term: 30 years (assumed)

Assumptions used: annual interest rate of 4.9% and a 30-year term.

Your question (blank to quit):
```

The model works the numbers out of plain language itself; nothing has to be
typed in a fixed format. Ask as many questions as you like — a blank line,
`exit` or Ctrl+C ends the session. If the API fails on one question, the
session says so and returns to the prompt rather than dying.

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
