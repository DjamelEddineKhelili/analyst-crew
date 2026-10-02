"""
MILESTONE 2a — Decide if an agent's answer is correct.

The idea: for every question you wrote the correct ("gold") SQL yourself.
We run the gold SQL and the agent's SQL, and compare the RESULTS, not the SQL text.
Two different queries can be equally correct; what matters is that they return the same data.

Check:  python checks/check_m2.py
"""



def normalize_value(v):
    """Make one cell comparable.
    TODO: floats -> round to 2 decimals. Strings -> strip spaces and lowercase. Everything else unchanged.
    """
    raise NotImplementedError


def results_match(gold_rows: list[list], agent_rows: list[list], ordered: bool = False) -> bool:
    """True if both results contain the same data.

    Rules (checks/check_m2.py tests each one):
      - same number of rows
      - each row compared cell by cell after normalize_value()
      - if ordered=False, row order does not matter   (HINT: sort both lists of normalized rows)
      - if ordered=True, row order matters            (for "top 5 ..." questions)
      - column NAMES are ignored (the agent may call a column 'n' or 'total', both fine)

    Known limitation, write it in your README later: if the agent returns extra columns, this says False.
    """
    raise NotImplementedError
