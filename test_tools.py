"""Checks on the tools without calling the API.

The payment is deliberately NOT verified with the same formula that
computes it, because that would only repeat any mistake. Instead the loan
is simulated month by month: if the payment is right, the balance after the
last month must be zero.
"""

from tools import INCOME_MULTIPLE, max_mortgage, monthly_payment, total_cost


def simulate_balance(principal, interest_rate, number_of_payments, payment):
    """Independent check - actually repaying the loan month by month."""
    balance = principal
    monthly_rate = interest_rate / 100 / 12
    for _ in range(number_of_payments):
        balance = balance * (1 + monthly_rate) - payment
    return balance


def allowed_drift(interest_rate, number_of_payments):
    """How much may be left at the end purely from rounding the payment.

    The payment is rounded to two decimals, so the error is at most half a
    cent. That error earns interest every month, so by the end it has been
    multiplied by the annuity factor. Over 30 years that is already a few
    euros, which is correct and not a calculation error. A fixed tolerance
    would lie here.
    """
    monthly_rate = interest_rate / 100 / 12
    if monthly_rate == 0:
        return 0.005 * number_of_payments + 0.01
    annuity_factor = ((1 + monthly_rate) ** number_of_payments - 1) / monthly_rate
    return 0.005 * annuity_factor + 0.01


def test_max_mortgage_is_eight_times_yearly_income():
    result = max_mortgage(2000)
    assert result["net_yearly_income"] == 24_000
    assert result["legal_cap_total"] == 24_000 * INCOME_MULTIPLE
    assert result["max_mortgage"] == 192_000
    print(f"OK max mortgage {result['max_mortgage']} EUR on an income of 2000 EUR")


def test_existing_mortgage_is_subtracted_from_the_cap():
    """The cap covers all of a person's mortgages, not each one separately."""
    result = max_mortgage(2000, existing_mortgages=50_000)
    assert result["legal_cap_total"] == 192_000
    assert result["max_mortgage"] == 142_000
    print(f"OK with 50 000 EUR already held, {result['max_mortgage']} EUR remains")


def test_exhausted_cap_returns_zero_and_a_note():
    result = max_mortgage(2000, existing_mortgages=250_000)
    assert result["max_mortgage"] == 0
    assert "note" in result
    assert "error" not in result  # an exhausted cap is a valid result, not an error
    print("OK exhausted cap returns 0 EUR and a note")


def test_loan_repays_down_to_zero():
    result = monthly_payment(140_000, 4.9, 25)
    balance = simulate_balance(
        140_000, 4.9, result["number_of_payments"], result["monthly_payment"]
    )
    limit = allowed_drift(4.9, result["number_of_payments"])
    assert abs(balance) < limit, f"balance {balance} exceeded the limit {limit}"
    print(
        f"OK payment {result['monthly_payment']} EUR, "
        f"balance {balance:.4f} EUR (limit {limit:.4f})"
    )


def test_zero_interest_is_plain_division():
    result = monthly_payment(120_000, 0, 10)
    assert result["monthly_payment"] == 1000.0
    print("OK zero interest")


def test_total_cost_follows_from_the_payment():
    payment = monthly_payment(200_000, 5, 20)["monthly_payment"]
    cost = total_cost(payment, 20, 200_000)
    assert cost["total_paid"] > 200_000
    assert abs(cost["total_interest"] - (cost["total_paid"] - 200_000)) < 0.01
    print(f"OK interest {cost['total_interest']} EUR")


def test_whole_chain_from_income_to_interest():
    """Exactly the path the model takes when given --income."""
    cap = max_mortgage(2000)["max_mortgage"]
    payment = monthly_payment(cap, 4.9, 30)
    cost = total_cost(payment["monthly_payment"], 30, cap)

    balance = simulate_balance(
        cap, 4.9, payment["number_of_payments"], payment["monthly_payment"]
    )
    limit = allowed_drift(4.9, payment["number_of_payments"])
    assert abs(balance) < limit, f"balance {balance} exceeded the limit {limit}"
    assert cost["total_interest"] > 0
    print(
        f"OK chain: {cap} EUR -> {payment['monthly_payment']} EUR/month "
        f"-> {cost['total_interest']} EUR interest over {cost['years']} years"
    )


def test_invalid_input_returns_an_error_and_does_not_crash():
    for bad in [
        max_mortgage(0),
        max_mortgage(-500),
        max_mortgage(2000, existing_mortgages=-1),
        monthly_payment(-1, 5, 20),
        monthly_payment(100, -5, 20),
        monthly_payment(100, 5, 0),
        total_cost(0, 20, 100),
    ]:
        assert "error" in bad, bad
    print("OK invalid inputs return an error")


if __name__ == "__main__":
    test_max_mortgage_is_eight_times_yearly_income()
    test_existing_mortgage_is_subtracted_from_the_cap()
    test_exhausted_cap_returns_zero_and_a_note()
    test_loan_repays_down_to_zero()
    test_zero_interest_is_plain_division()
    test_total_cost_follows_from_the_payment()
    test_whole_chain_from_income_to_interest()
    test_invalid_input_returns_an_error_and_does_not_crash()
    print("\nAll checks passed.")
