"""Shared conservative rule evaluator; unknown operators never imply eligibility."""
def evaluate(actual, expected, operator, verified=True):
    choices=[x.strip() for x in expected.split(',') if x.strip()]
    if not verified or not actual.strip() or not choices:return None
    if operator in {'in','equals'}:return actual in choices
    if operator=='contains_any':return any(x in actual for x in choices)
    return None
