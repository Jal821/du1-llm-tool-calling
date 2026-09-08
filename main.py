"""Homework 1 - LLM API with tool calling (function calling).

The script calls an LLM API, the model picks a tool itself, the script
executes that tool and sends the result back to the model. The loop keeps
running as long as the model wants to call more tools.

The tools chain: net income gives the maximum mortgage, that gives the
monthly payment, and that gives the total interest. Each step works on the
output of the previous one, so this is real chaining rather than a single
isolated call.

Two backends, both driven by the same tool definitions in tools.py:

  gemini  Google Gemini through the google-genai SDK (native protocol)
  openai  any OpenAI-compatible endpoint, e.g. a local LiteLLM proxy

The point of having both is that tool calling is the same idea in two
different wire formats, and the calculation layer does not care which one
is in use.
"""

import argparse
import json
import os
import sys

from dotenv import load_dotenv

from tools import TOOL_SCHEMAS, execute_tool

load_dotenv()

# The Windows console runs in cp1252 and would die with a UnicodeEncodeError
# on non-ASCII output, so switch stdout to UTF-8.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Gemini backend. The model can be overridden in case the free tier runs out
# of daily quota on this particular one.
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.7-flash")

# OpenAI-compatible backend. Set OPENAI_BASE_URL to switch to it, e.g. a
# local proxy at http://localhost:20128/v1
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "auto/best-fast")

MAX_STEPS = 8  # guard against an endless loop

DEFAULT_RATE = 4.9
DEFAULT_YEARS = 30

SYSTEM_INSTRUCTION = (
    "You are a mortgage advisor. Never do the arithmetic yourself, always "
    "use the tools available to you. If you need the result of one tool as "
    "input for another, call them in sequence. "
    "When the user states their net income, always follow the calculation "
    "through to the end and report all four values: the maximum mortgage, "
    "the monthly payment, the total interest and the repayment term in years. "
    f"If the user does not give an interest rate, assume {DEFAULT_RATE}% p.a. "
    f"If they do not give a term, assume {DEFAULT_YEARS} years. Say which "
    "assumption you used. Never ask the user whether you should continue the "
    "calculation: finish it in the same answer using those assumptions. "
    "Answer briefly, with concrete figures in euros (EUR). "
    "If a tool returns an error key, explain to the user what is wrong and "
    "do not guess the result."
)


class BackendError(RuntimeError):
    """The API refused or failed a request.

    Raised rather than exiting, so that in interactive mode a transient
    failure such as a 503 ends one question instead of the whole session.
    """


def report_call(step: int, name: str, arguments: dict, result: dict) -> None:
    """Print one tool call so the whole chain is visible in the output."""
    print(f"[step {step}] TOOL CALL: {name}")
    print(f"         arguments: {arguments}")
    print(f"         result:    {result}\n")


# --------------------------------------------------------------------------
# Gemini backend (native google-genai protocol)
# --------------------------------------------------------------------------


def run_agent_gemini(question: str) -> str:
    from google import genai
    from google.genai import errors, types

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit("GEMINI_API_KEY is missing. Copy .env.example to .env and fill it in.")

    def to_schema(node: dict) -> types.Schema:
        """Turn plain JSON Schema from tools.py into a genai Schema."""
        return types.Schema(
            type=types.Type.OBJECT,
            properties={
                key: types.Schema(
                    type=types.Type.NUMBER, description=value["description"]
                )
                for key, value in node["properties"].items()
            },
            required=node["required"],
        )

    declarations = types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name=tool["name"],
                description=tool["description"],
                parameters=to_schema(tool["parameters"]),
            )
            for tool in TOOL_SCHEMAS
        ]
    )

    client = genai.Client(api_key=api_key)
    config = types.GenerateContentConfig(
        tools=[declarations],
        system_instruction=SYSTEM_INSTRUCTION,
    )

    history = [types.Content(role="user", parts=[types.Part.from_text(text=question)])]

    for step in range(1, MAX_STEPS + 1):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL, contents=history, config=config
            )
        except errors.ClientError as problem:
            # Usually an exhausted free-tier quota (429) or a bad key (400).
            if problem.code == 429:
                raise BackendError(
                    "Gemini API quota exhausted (the free tier has a daily "
                    f"limit per model, here {GEMINI_MODEL}). Try later or "
                    "change GEMINI_MODEL."
                ) from problem
            raise BackendError(
                f"Gemini API rejected the request ({problem.code}): {problem.message}"
            ) from problem
        except errors.ServerError as problem:
            raise BackendError(
                f"Gemini API is temporarily unavailable ({problem.code}). "
                "This is overload on Google's side, try again shortly."
            ) from problem

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

        results = []
        for call in calls:
            arguments = dict(call.args or {})
            result = execute_tool(call.name, arguments)
            report_call(step, call.name, arguments, result)
            results.append(
                types.Part.from_function_response(name=call.name, response=result)
            )

        # Send the tool results back to the model as the next input.
        history.append(types.Content(role="user", parts=results))

    return "Step limit reached, the model did not produce a final answer."


# --------------------------------------------------------------------------
# OpenAI-compatible backend (works against a LiteLLM or similar proxy)
# --------------------------------------------------------------------------


def run_agent_openai(question: str) -> str:
    from openai import APIError, OpenAI

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        sys.exit("OPENAI_API_KEY is missing. Put the proxy key in .env.")
    if not OPENAI_BASE_URL:
        sys.exit("OPENAI_BASE_URL is missing, e.g. http://localhost:20128/v1")

    declarations = [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["parameters"],
            },
        }
        for tool in TOOL_SCHEMAS
    ]

    client = OpenAI(api_key=api_key, base_url=OPENAI_BASE_URL)
    messages = [
        {"role": "system", "content": SYSTEM_INSTRUCTION},
        {"role": "user", "content": question},
    ]

    for step in range(1, MAX_STEPS + 1):
        try:
            response = client.chat.completions.create(
                model=OPENAI_MODEL, messages=messages, tools=declarations
            )
        except APIError as problem:
            raise BackendError(
                f"The endpoint at {OPENAI_BASE_URL} rejected the request: "
                f"{getattr(problem, 'message', problem)}"
            ) from problem

        reply = response.choices[0].message

        if not reply.tool_calls:
            print(f"[step {step}] model wants no more tools, leaving the loop\n")
            return reply.content

        # Rebuild the assistant turn explicitly rather than pushing the SDK
        # object back. Proxies add extra fields such as reasoning_content,
        # and some of them reject their own output on the next request.
        messages.append(
            {
                "role": "assistant",
                "content": reply.content or "",
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.function.name,
                            "arguments": call.function.arguments,
                        },
                    }
                    for call in reply.tool_calls
                ],
            }
        )

        for call in reply.tool_calls:
            try:
                arguments = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                arguments = {}
                result = {"error": "The model sent arguments that are not valid JSON."}
            else:
                result = execute_tool(call.function.name, arguments)

            report_call(step, call.function.name, arguments, result)

            # The tool result goes back in a tool-role message, keyed to the
            # call id. That is this protocol's equivalent of Gemini's
            # from_function_response.
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(result),
                }
            )

    return "Step limit reached, the model did not produce a final answer."


YES_WORDS = {"y", "yes", "ano", "a"}
NO_WORDS = {"n", "no", "ne", "nie"}


class UserQuit(Exception):
    """The user pressed Ctrl+C or stdin ran out during the interview."""


def ask_line(prompt: str) -> str:
    """Ask one question and return the raw answer."""
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        raise UserQuit from None


def ask_number(prompt: str, default: float | None = None) -> float:
    """Ask for a number and keep asking until the answer is one.

    A blank answer takes the default where there is one. Commas are accepted
    as decimal separators, since that is how the amount is written locally.
    """
    suffix = f" [{default}]" if default is not None else ""
    while True:
        answer = ask_line(f"{prompt}{suffix}: ")

        if not answer and default is not None:
            return default
        if not answer:
            print("  Please enter a number.")
            continue

        try:
            return float(answer.replace(",", ".").replace(" ", ""))
        except ValueError:
            print(f"  '{answer}' is not a number. Try again, digits only.")


def ask_yes_no(prompt: str) -> bool:
    """Ask a yes or no question and keep asking until the answer is one."""
    while True:
        answer = ask_line(f"{prompt} (yes/no): ").lower()
        if answer in YES_WORDS:
            return True
        if answer in NO_WORDS:
            return False
        print("  Please answer yes or no.")


def tidy(number: float) -> str:
    """Drop the pointless .0 so the composed question reads like a person wrote it."""
    return str(int(number)) if number == int(number) else str(number)


def run_interview() -> str:
    """Ask the questions one by one, then compose the question for the model."""
    income = ask_number("What is your monthly income? This is your NET income, in EUR")

    existing = []
    if ask_yes_no("\nDo you already have any mortgages?"):
        while True:
            index = len(existing) + 1
            print(f"\nMortgage number {index}:")
            existing.append(
                {
                    "balance": ask_number("  How much is still outstanding, in EUR"),
                    "years": ask_number("  How many years does it still run"),
                    "rate": ask_number("  At what interest rate, in % per year"),
                }
            )
            if not ask_yes_no("\nDo you have another mortgage?"):
                break

    print("\nNow the mortgage you are asking about:")
    rate = ask_number("  What interest rate do you expect, in % per year", DEFAULT_RATE)
    years = ask_number("  Over how many years do you want to repay it", DEFAULT_YEARS)

    # Compose one plain-language question. The model then decides which tools
    # to call and in what order; nothing here prescribes the calculation.
    if existing:
        parts = [
            f"{tidy(item['balance'])} EUR outstanding over "
            f"{tidy(item['years'])} more years at {tidy(item['rate'])}% p.a."
            for item in existing
        ]
        # The parts already end in "p.a.", so no extra full stop here.
        held = (
            f"I already hold {len(existing)} mortgage"
            f"{'s' if len(existing) > 1 else ''}: " + "; ".join(parts) + " "
        )
        also = (
            " Also tell me the monthly payment on the mortgages I already hold "
            "and what my total monthly payment across all of them would be."
        )
    else:
        held = "I hold no mortgage yet. "
        also = ""

    return (
        f"My net monthly income is {tidy(income)} EUR. {held}"
        f"How large a mortgage do I qualify for, what would the monthly payment "
        f"be, and how much interest would I pay in total, at a rate of "
        f"{tidy(rate)}% p.a. over {tidy(years)} years?{also}"
    )


def question_from_flags(args) -> str | None:
    """Build a question from the flags, or None if the user gave none."""
    if args.income is not None:
        current = (
            f"I already hold mortgages with a balance of {tidy(args.debts)} EUR. "
            if args.debts
            else "I hold no mortgage yet. "
        )
        return (
            f"My net monthly income is {tidy(args.income)} EUR. {current}"
            f"How large a mortgage do I qualify for, what would the monthly "
            f"payment be, and how much interest would I pay in total, at a "
            f"rate of {tidy(args.rate)}% p.a. over {tidy(args.years)} years?"
        )
    if args.question:
        return " ".join(args.question)
    return None


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
        "--backend",
        choices=["auto", "gemini", "openai"],
        default="auto",
        help=(
            "Which API to talk to. auto picks openai when OPENAI_BASE_URL is "
            "set, gemini otherwise (default auto)."
        ),
    )
    parser.add_argument(
        "question",
        nargs="*",
        help="A free-text question. Omit it and the script will ask you.",
    )
    args = parser.parse_args()

    backend = args.backend
    if backend == "auto":
        backend = "openai" if OPENAI_BASE_URL else "gemini"

    model = OPENAI_MODEL if backend == "openai" else GEMINI_MODEL
    where = f" at {OPENAI_BASE_URL}" if backend == "openai" else ""
    print(f"BACKEND: {backend}, model {model}{where}\n")

    run_agent = run_agent_gemini if backend == "gemini" else run_agent_openai

    supplied = question_from_flags(args)
    if supplied:
        # Non-interactive: one question from the flags, then exit. Keeps the
        # script usable from a script or a CI job.
        print(f"USER QUESTION:\n  {supplied}\n")
        # Assign before printing the header: run_agent prints the tool trace
        # as it goes, and that has to appear above the final answer.
        try:
            answer = run_agent(supplied)
        except BackendError as problem:
            sys.exit(str(problem))
        print("FINAL ANSWER FROM THE MODEL:")
        print(answer)
        raise SystemExit(0)

    # Interactive: walk the user through the questions one at a time.
    print("I am a mortgage calculator.")
    print("I will ask you a few questions, one at a time.\n")

    while True:
        try:
            question = run_interview()
        except UserQuit:
            print("Bye.")
            break

        print(f"\nPUTTING THIS TO THE MODEL:\n  {question}\n")

        try:
            answer = run_agent(question)
        except BackendError as problem:
            # One bad request should not end the session.
            print(f"Could not answer that one: {problem}")
        else:
            print("FINAL ANSWER FROM THE MODEL:")
            print(answer)

        print()
        try:
            if not ask_yes_no("Another calculation?"):
                print("Bye.")
                break
        except UserQuit:
            print("Bye.")
            break
        print()
