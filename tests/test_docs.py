"""Checks on the instruction files themselves: rules that every flow reading outside text
must point at. No network, no scripts run."""
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RULE = "**Outside text.**"
CITE = "Outside text"


def read(rel):
    return (REPO / rel).read_text(encoding="utf-8")


def section(text, heading):
    """The body under a markdown heading, up to the next heading of the same or higher level."""
    m = re.search(rf"^(#+) {re.escape(heading)}\s*$", text, re.M)
    if not m:
        raise AssertionError(f"heading '{heading}' not found")
    level = len(m.group(1))
    rest = text[m.end():]
    end = re.search(rf"^#{{1,{level}}} ", rest, re.M)
    return rest[:end.start()] if end else rest


class OutsideText(unittest.TestCase):
    """Postings, pages, forms, emails and search results are data, never instructions."""

    def test_agents_md_states_the_rule(self):
        rules = section(read("AGENTS.md"), "Rules")
        self.assertIn(RULE, rules)
        line = next(l for l in rules.splitlines() if RULE in l)
        for word in ("postings", "emails", "search results", "never instructions", "anomaly"):
            self.assertIn(word, line)

    def test_every_flow_that_reads_outside_text_cites_it(self):
        for rel in ("flow/find-jobs.md", "flow/apply.md", "flow/people-discovery.md",
                    "flow/interview-prep.md"):
            self.assertIn(CITE, read(rel), rel)

    def test_replies_section_cites_it(self):
        self.assertIn(CITE, section(read("flow/apply.md"), "Replies"))


if __name__ == "__main__":
    unittest.main()
