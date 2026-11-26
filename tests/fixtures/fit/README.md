# Fit fixtures

`golden.json`: 21 fictional postings for the example persona (Dana Levi, product marketing in the Tel Aviv area: `examples/brief.md`), each with the verdict she would give (`golden`) and the rule-based gate that must stop it (`rules`). `tests/test_fit.py` → `Golden` runs them through `jobs.py`'s title, place and date filters (with the search patterns in `search`) and through `triage.py check`.

What they test: that the gates which are code stop exactly the postings they should, and never a job the owner would apply to or consider. Add a posting here whenever a gate changes or a real miss or leak teaches something a rule could have caught.

What they cannot test: the assistant's 1-5 score. It is judgement over the posting and the brief, not code; the five skips marked `"rules": "pass"` rest on it (two of them deal-breakers the brief does not turn into a gate). The real measure is the owner's own labels: `fit.py label` while they review a list, `fit.py report` in `flow/review.md`.
