"""Homework 1 - LLM API with tool calling (function calling).

The script calls the Gemini API, the model picks a tool itself, the script
executes that tool and sends the result back to the model. The loop keeps
running as long as the model wants to call more tools.

The tools chain: net income gives the maximum mortgage, that gives the
monthly payment, and that gives the total interest. Each step works on the
output of the previous one, so this is real chaining rather than a single
isolated call.
"""

import argparse
import os
import sys

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

from tools import AVAILABLE_FUNCTIONS

load_dotenv()

# The Windows console runs in cp1252 and would die with a UnicodeEncodeError
# on non-ASCII output, so switch stdout to UTF-8.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# The model can be overridden through .env or an environment variable, in
# case the free tier runs out of daily quota on this particular model.
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.7-flash")
MAX_STEPS = 8  # guard against an endless loop

DEFAULT_RATE = 4.9
DEFAULT_YEARS = 30

# Tool declarations for the model. The descriptions are the only thing the
# model uses to decide which tool to call, so they have to be specific.
TOOLS = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="max_mortgage",
            description=(
                "Work out how large a mortgage the user can still get. The "
                "legal cap is eight times their net YEARLY income and it "
                "applies to the sum of all mortgages that person holds, so "
                "any existing mortgage balance is subtracted from the cap. "
                "Use this whenever the user states their net income and "
                "wants to know how much they qualify for. If the user gives "
                "a yearly income, divide it by twelve."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "net_monthly_income": types.Schema(
                        type=types.Type.NUMBER,
                        description="Net monthly income in euros, e.g. 2000",
                    ),
                    "existing_mortgages": types.Schema(
                        type=types.Type.NUMBER,
                        description=(
                            "Outstanding balance of the person's existing "
                            "mortgages in euros. Use 0 if they have none."
                        ),
                    ),
                },
                required=["net_monthly_income"],
            ),
        ),
        types.FunctionDeclaration(
            name="monthly_payment",
            description=(
                "Work out the monthly annuity payment on a loan or mortgage. "
                "Use this whenever the user asks how much they would pay per "
                "month. You may pass the result of max_mortgage as the "
                "principal."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "principal": types.Schema(
                        type=types.Type.NUMBER,
                        description="Loan amount in euros, e.g. 192000",
                    ),
                    "interest_rate": types.Schema(
                        type=types.Type.NUMBER,
                        description="Annual interest rate in percent, e.g. 4.9",
                    ),
                    "years": types.Schema(
                        type=types.Type.NUMBER,
                        description="Repayment term in years, e.g. 30",
                    ),
                },
                required=["principal", "interest_rate", "years"],
            ),
        ),
        types.FunctionDeclaration(
            name="total_cost",
            description=(
                "Work out how much the user pays over the whole loan and how "
                "much of that is interest. It needs a known monthly payment, "
                "so get that from monthly_payment first."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "monthly_payment": types.Schema(
                        type=types.Type.NUMBER,
                        description="Monthly payment in euros",
                    ),
                    "years": types.Schema(
                        type=types.Type.NUMBER,
                        description="Repayment term in years",
                    ),
                    "principal": types.Schema(
                        type=types.Type.NUMBER,
                        description="Original loan amount in euros",
                    ),
                },
                required=["monthly_payment", "years", "principal"],
            ),
        ),
    ]
)

SYSTEM_INSTRUCTION = (
    "You are a mortgage advisor. Never do the arithmetic yourself, always "
    "use the tools available to you. If you need the result of one tool as "
    "input for another, call them in sequence. "
    "When the user states their net income, always follow the calculation "
    "through to the end and report all four values: the maximum mortgage, "
    "the monthly payment, the total interest and the repayment term in years. "
    "Answer briefly, with concrete figures in euros (EUR). "
    "If a tool returns an error key, explain to the user what is wrong and "
    "do not guess the result."
)


def execute_tool(name: str, arguments: dict) -> dict:
    """Call a tool by name. An unknown name returns an error, not an exception."""
    function = AVAILABLE_FUNCTIONS.get(name)
    if function is None:
        return {"error": f"Tool {name} does not exist."}
    try:
        return function(**arguments)
    except TypeError as problem:
        return {"error": f"Bad arguments for {name}: {problem}"}


def run_agent(question: str) -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit("GEMINI_API_KEY is missing. Copy .env.example to .env and fill it in.")

    client = genai.Client(api_key=api_key)
    config = types.GenerateContentConfig(
        tools=[TOOLS],
        system_instruction=SYSTEM_INSTRUCTION,
    )

    history = [types.Content(role="user", parts=[types.Part.from_text(text=question)])]

    print(f"USER QUESTION:\n  {question}\n")

    for step in range(1, MAX_STEPS + 1):
        try:
            response = client.models.generate_content(
                model=MODEL, contents=history, config=config
            )
        except errors.ClientError as problem:
            # Usually an exhausted free-tier quota (429) or a bad key (400).
            if problem.code == 429:
                sys.exit(
                    "Gemini API quota exhausted (the free tier has a daily "
                    f"limit per model, here {MODEL}). Try later or change MODEL."
                )
            sys.exit(f"Gemini API rejected the request ({problem.code}): {problem.message}")
        except errors.ServerError as problem:
            sys.exit(
                f"Gemini API is temporarily unavailable ({problem.code}). "
                "This is overload on Google's side, try again shortly."
            )

        candidate = response.candidates[0]

        # The model's own reply has to go back into the history, otherwise on
        # the next step it does not know it already called a tool.
        history.append(candidate.content)

        calls = [
            part.function_call
            for part in (candidate.content.parts or [])
            if part.function_call
        ]

        if not calls:
            print(f"[step {step}] model wants no more tools, leaving the loop\n")
            return response.text

        tool_results = []
        for call in calls:
            arguments = dict(call.args or {})
            result = execute_tool(call.name, arguments)

            print(f"[step {step}] TOOL CALL: {call.name}")
            print(f"         arguments: {arguments}")
            print(f"         result:    {result}\n")

            tool_results.append(
                types.Part.from_function_response(name=call.name, response=result)
            )

        # Send the tool results back to the model as the next input.
        history.append(types.Content(role="user", parts=tool_results))

    return "Step limit reached, the model did not produce a final answer."


def build_question(args) -> str:
    """Build a question from the income, or take free text from the command line."""
    if args.income is not None:
        current = (
            f"I already hold mortgages with a balance of {args.debts} EUR. "
            if args.debts
            else "I hold no mortgage yet. "
        )
        return (
            f"My net monthly income is {args.income} EUR. {current}"
            f"How large a mortgage do I qualify for, what would the monthly "
            f"payment be, and how much interest would I pay in total, at a "
            f"rate of {args.rate}% p.a. over {args.years} years?"
        )
    if args.question:
        return " ".join(args.question)
    return (
        "I am taking a mortgage of 140 000 EUR over 25 years at an interest "
        "rate of 4.9% p.a. What is the monthly payment and how much interest "
        "will I pay in total?"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Mortgage advisor - an LLM with tool calling."
    )
    parser.add_argument(
        "--income",
        type=float,
        help=(
            "Net monthly income in EUR. Works out the maximum mortgage "
            "(8x net yearly income), the payment and the interest."
        ),
    )
    parser.add_argument(
        "--debts",
        type=float,
        default=0,
        help=(
            "Outstanding balance of existing mortgages in EUR. Subtracted "
            "from the legal cap, which applies to all mortgages a person "
            "holds together (default 0)."
        ),
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=DEFAULT_RATE,
        help=f"Annual interest rate in percent (default {DEFAULT_RATE})",
    )
    parser.add_argument(
        "--years",
        type=float,
        default=DEFAULT_YEARS,
        help=f"Repayment term in years (default {DEFAULT_YEARS})",
    )
    parser.add_argument(
        "question", nargs="*", help="A free-text question instead of --income"
    )
    args = parser.parse_args()

    answer = run_agent(build_question(args))
    print("FINAL ANSWER FROM THE MODEL:")
    print(answer)
