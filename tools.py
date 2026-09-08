"""Deterministic tools for the mortgage advisor.

Every function returns a dict. On invalid input it returns an "error" key,
so the model receives the problem as a tool result and can react to it.
No function raises an exception into the agent loop.
"""

# Legal ceiling on a person's TOTAL mortgage debt: eight times their net
# YEARLY income. This is not a bank's own estimate but a regulatory limit,
# and it applies to the sum of all mortgages held by that person.
INCOME_MULTIPLE = 8


def max_mortgage(net_monthly_income: float, existing_mortgages: float = 0) -> dict:
    """Work out how much more a person can still borrow before the legal cap.

    The cap is eight times net yearly income and covers all of the person's
    mortgages together, so any existing mortgage balance is subtracted.
    """
    if net_monthly_income <= 0:
        return {"error": "Net monthly income must be greater than zero."}
    if existing_mortgages < 0:
        return {"error": "Existing mortgages cannot be negative."}

    net_yearly_income = net_monthly_income * 12
    legal_cap = net_yearly_income * INCOME_MULTIPLE
    remaining = legal_cap - existing_mortgages

    result = {
        "net_monthly_income": round(net_monthly_income, 2),
        "net_yearly_income": round(net_yearly_income, 2),
        "legal_cap_total": round(legal_cap, 2),
        "existing_mortgages": round(existing_mortgages, 2),
        "max_mortgage": round(max(remaining, 0), 2),
        "multiple_used": INCOME_MULTIPLE,
    }

    if remaining <= 0:
        result["note"] = (
            "The legal cap is already used up by existing mortgages, "
            "so no further mortgage can be granted."
        )

    return result


def monthly_payment(principal: float, interest_rate: float, years: float) -> dict:
    """Work out the monthly annuity payment on a loan."""
    if principal <= 0:
        return {"error": "Principal must be greater than zero."}
    if interest_rate < 0:
        return {"error": "Interest rate cannot be negative."}
    if years <= 0:
        return {"error": "Repayment term must be greater than zero."}

    number_of_payments = int(round(years * 12))
    monthly_rate = interest_rate / 100 / 12

    if monthly_rate == 0:
        payment = principal / number_of_payments
    else:
        factor = (1 + monthly_rate) ** number_of_payments
        payment = principal * monthly_rate * factor / (factor - 1)

    return {
        "monthly_payment": round(payment, 2),
        "number_of_payments": number_of_payments,
        "years": years,
        "principal": principal,
        "interest_rate": interest_rate,
    }


def total_cost(monthly_payment: float, years: float, principal: float) -> dict:
    """Work out the total amount repaid and how much of it is interest."""
    if monthly_payment <= 0:
        return {"error": "Monthly payment must be greater than zero."}
    if years <= 0:
        return {"error": "Repayment term must be greater than zero."}
    if principal <= 0:
        return {"error": "Principal must be greater than zero."}

    number_of_payments = int(round(years * 12))
    total_paid = monthly_payment * number_of_payments
    interest = total_paid - principal

    return {
        "total_paid": round(total_paid, 2),
        "total_interest": round(interest, 2),
        "interest_as_pct_of_principal": round(interest / principal * 100, 1),
        "years": years,
        "number_of_payments": number_of_payments,
    }


# Maps a tool name to the actual function. The agent loop looks only in here,
# so the model cannot reach anything else.
AVAILABLE_FUNCTIONS = {
    "max_mortgage": max_mortgage,
    "monthly_payment": monthly_payment,
    "total_cost": total_cost,
}
