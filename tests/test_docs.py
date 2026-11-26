"""Checks on the instruction files themselves: rules that every flow reading outside text
must point at. No network, no scripts run."""
import json
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


class AnswerBank(unittest.TestCase):
    """A free-text form question gets a drafted, checked answer the owner approves; approved
    answers are kept for reuse. The Handoff rule still stops for it."""

    def test_apply_drafts_checks_and_keeps_answers(self):
        submit = section(read("flow/apply.md"), "2. Submit the application")
        for word in ("profile/answers.md", "validate.py --answers", "Approved:", "checklist"):
            self.assertIn(word, submit)

    def test_handoff_rule_names_the_bank(self):
        rules = section(read("AGENTS.md"), "Rules")
        line = next(l for l in rules.splitlines() if "**Handoff.**" in l)
        self.assertIn("profile/answers.md", line)

    def test_playbook_points_to_the_bank(self):
        self.assertIn("profile/answers.md", read("playbooks/ats.md"))


class Connections(unittest.TestCase):
    """The LinkedIn export is offered once at onboarding, never required, and read before
    writing to strangers."""

    def test_onboarding_offers_the_export_once(self):
        line = next(l for l in section(read("ONBOARDING.md"), "6. Coaching interview").splitlines()
                    if "**Who they know.**" in l)
        for word in ("profile/connections.csv", "network.py match", "once", "declined"):
            self.assertIn(word, line)

    def test_referral_check_reads_the_connections(self):
        preflight = section(read("flow/apply.md"), "0. Preflight")
        self.assertIn("network.py match", preflight)


class Offer(unittest.TestCase):
    """An offer is read clause by clause in plain words, judged by nobody but the owner and their
    lawyer; negotiation uses only figures the checker can trace."""

    def test_agents_md_routes_offers(self):
        self.assertIn("flow/offer.md", section(read("AGENTS.md"), "Start of every session"))

    def test_the_flow_reads_without_verdicts_and_ends_with_a_lawyer(self):
        flow = read("flow/offer.md")
        for word in ("clause", "not legal advice", "verdict", "lawyer", "validate.py --answers", CITE):
            self.assertIn(word, flow)

    def test_an_offer_reply_leads_to_the_flow(self):
        self.assertIn("offer.md", section(read("flow/apply.md"), "Replies"))



class KitCv(unittest.TestCase):
    """The agent can print a CV itself in a plain ATS-safe layout: offered once, the owner's own
    design kept when they prefer it, the handoff kept as the fallback."""

    def test_template_is_ats_safe(self):
        page = read("playbooks/cv-template.html")
        self.assertIn("@page", page)
        for risky in ("<table", "<img", "column-count", "display: grid", "display:grid", "float:", "<svg"):
            self.assertNotIn(risky, page)

    def test_browser_setup_turns_on_pdf(self):
        self.assertIn("--caps=pdf", read("flow/tools.md"))

    def test_apply_prints_or_hands_off(self):
        tailor = section(read("flow/apply.md"), "0. Preflight")
        for word in ("cv layout: kit", "cv.py serve", "browser_pdf_save", "handoff"):
            self.assertIn(word, tailor)

    def test_onboarding_offers_the_layout_once(self):
        line = next(l for l in section(read("ONBOARDING.md"), "6. Coaching interview").splitlines()
                    if "**CV fit.**" in l)
        for word in ("once", "cv layout: kit", "cv layout: own", "playbooks/cv-template.html"):
            self.assertIn(word, line)


class SendRoutes(unittest.TestCase):
    """The default route is drafts the owner sends; the code from the preview page is the proof
    only on the opt-in script route. Every promise to the owner says so."""

    def green_light(self):
        rules = section(read("AGENTS.md"), "Rules")
        return next(l for l in rules.splitlines() if "**Green light.**" in l)

    def test_agents_md_names_the_proof_of_each_route(self):
        line = self.green_light()
        for word in ("drafts route", "default", "presses Send", "script route", "one-time code",
                     "mail.py preview"):
            self.assertIn(word, line)

    def test_onboarding_promise_covers_the_drafts_route(self):
        intro = read("ONBOARDING.md").split("## Interview style")[0]
        self.assertIn("press Send", intro)
        self.assertIn("script route", intro)

    def test_onboarding_closing_sentences_fit_the_route(self):
        last = section(read("ONBOARDING.md"), "10. First run, supervised").strip().splitlines()[-1]
        self.assertIn('"the drafts are sent"', last)
        self.assertIn("script route", last)
        self.assertIn('"send <code>"', last)

    def test_onboarding_offers_the_script_route_as_the_opt_in(self):
        sending = next(l for l in section(read("ONBOARDING.md"), "8. Email finding and sending")
                       .splitlines() if "**Sending.**" in l)
        for word in ("Recommend B", "script route (A)", "preview page", "code"):
            self.assertIn(word, sending)

    def test_readme_promise_matches_the_default_route(self):
        line = next(l for l in read("README.md").splitlines() if "**Sends only after you say so.**" in l)
        self.assertIn("Drafts folder", line)
        self.assertIn("press Send", line)


class ConnectorSendBan(unittest.TestCase):
    """A mail connector's send functions stay unused; in Claude Code the settings file blocks
    them, while drafts stay allowed. Other assistants rely on the rule alone."""

    SEND = ("mcp__claude_ai_Gmail__send_message", "mcp__claude_ai_Gmail__reply",
            "mcp__claude_ai_Gmail__forward")
    DRAFT = ("mcp__claude_ai_Gmail__create_draft", "mcp__claude_ai_Gmail__update_draft")

    def deny(self):
        return json.loads(read(".claude/settings.json"))["permissions"]["deny"]

    def test_settings_deny_the_gmail_connector_send_tools(self):
        for tool in self.SEND:
            self.assertIn(tool, self.deny())

    def test_settings_keep_drafts_allowed(self):
        settings = json.loads(read(".claude/settings.json"))
        blocked = settings["permissions"]["deny"] + settings["permissions"].get("ask", [])
        def covers(rule, tool):
            server = tool.rsplit("__", 1)[0]
            return rule in (tool, server) or (rule.endswith("*") and tool.startswith(rule[:-1]))
        for tool in self.DRAFT:
            self.assertEqual([r for r in blocked if covers(r, tool)], [], tool)

    def test_tools_md_says_other_assistants_rely_on_the_rule(self):
        tools = read("flow/tools.md")
        self.assertIn(".claude/settings.json", tools)
        self.assertIn("rule alone", tools)


class SubmitWindow(unittest.TestCase):
    """Before the owner's OK the visible window never rests on a filled form with Submit in
    reach: an owner glancing at it can submit by mistake."""

    def test_apply_moves_the_window_off_the_filled_form(self):
        submit = section(read("flow/apply.md"), "2. Submit the application")
        for word in ("Submit in reach", "blank tab", "Wait for their OK"):
            self.assertIn(word, submit)

    def test_playbook_rule_matches(self):
        self.assertIn("Submit in reach", read("playbooks/ats.md").split("Observations below")[0])


class Updating(unittest.TestCase):
    """An owner who downloaded the ZIP can move to a new version without losing their data, and
    knows to report breakage to their assistant."""

    def test_readme_explains_both_update_paths(self):
        update = section(read("README.md"), "Updating")
        for word in ("Download ZIP", "profile", "outreach", ".env", "hidden", "git pull"):
            self.assertIn(word, update)

    def test_readme_says_to_report_breakage(self):
        update = section(read("README.md"), "Updating")
        self.assertIn("new", update)
        self.assertIn("tell your assistant", update)


class OwnerSteps(unittest.TestCase):
    """Every step the owner does by hand has a click path and a fallback, so someone who has
    never used a terminal can finish it."""

    def test_cv_placement_has_a_path_and_a_fallback(self):
        cv = section(read("ONBOARDING.md"), "2. Get the CV")
        for word in ("Finder", "File Explorer", "tell you where it is"):
            self.assertIn(word, cv)

    def test_env_file_has_an_editor_fallback(self):
        keys = section(read("ONBOARDING.md"), "8. Email finding and sending")
        for word in ("Cmd + S", "Ctrl + S", "Open With", "Show → Hidden items", "never in chat"):
            self.assertIn(word, keys)

    def test_finder_keys_have_a_path(self):
        line = next(l for l in section(read("ONBOARDING.md"), "8. Email finding and sending")
                    .splitlines() if "**Optional finders" in l)
        self.assertIn("controlled browser", line)
        self.assertIn("API", line)

    def test_linkedin_url_has_a_path(self):
        line = next(l for l in section(read("ONBOARDING.md"), "6. Coaching interview").splitlines()
                    if "**Their LinkedIn profile.**" in l)
        self.assertIn("View Profile", line)

    def test_tools_md_gives_node_install_and_restart_paths(self):
        fast = section(read("flow/tools.md"), "Claude Code fast path")
        for word in ("LTS", "installer", "desktop app", "new session"):
            self.assertIn(word, fast)


class LinkedInSignedOut(unittest.TestCase):
    """Signed out, LinkedIn's public guest pages read without any account use, spaced out."""

    def test_accounts_rule_points_at_the_guest_pages(self):
        line = next(l for l in section(read("AGENTS.md"), "Rules").splitlines() if "**Accounts.**" in l)
        self.assertIn("guest", line)
        self.assertIn("playbooks/sources.md", line)
        self.assertIn("jobs-guest", read("playbooks/sources.md"))


class TablesByCommand(unittest.TestCase):
    """log.md, replies.md and followups.md change only through tracker.py's writing commands: no flow
    tells the assistant to set a Status, an Outcome or a Done cell by hand."""
    HAND = (r"set `Status` =", r"`Status` = `(?:handoff-pending|submitted|sent|closed)`", r"Append the log row",
            r"Append `\|", r"Edit that application's row", r"mark its follow-up rows done \(`Done`",
            r"Set `Emails`", r"Complete the application's row")

    def test_no_flow_says_edit_a_table_by_hand(self):
        for rel in ("flow/apply.md", "flow/send.md", "flow/review.md", "AGENTS.md"):
            for pat in self.HAND:
                self.assertIsNone(re.search(pat, read(rel)), f"{rel}: {pat}")

    def test_each_step_names_its_command(self):
        apply = read("flow/apply.md")
        for heading, cmd in (("0. Preflight", "tracker.py start"), ("2. Submit the application", "tracker.py status"),
                             ("8. Log", "tracker.py followup"), ("Replies", "tracker.py reply"),
                             ("Replies", "tracker.py status <slug> closed"), ("Sweep", "tracker.py reply")):
            self.assertIn(cmd, section(apply, heading), heading)
        self.assertIn("tracker.py status <slug> sent", read("flow/send.md"))

    def test_agents_md_says_the_tables_change_by_command(self):
        layout = section(read("AGENTS.md"), "Layout")
        line = next(l for l in layout.splitlines() if "`tracker.py`" in l)
        for word in ("start", "status", "reply", "followup", "normalize", "never by hand"):
            self.assertIn(word, line)


if __name__ == "__main__":
    unittest.main()


class Portfolio(unittest.TestCase):
    """Each job gets the project that best proves it, chosen by the owner from a ranked, quoted
    list; the pick and its approved link are recorded, and the catalog is filled at onboarding."""

    def test_apply_ranks_shows_two_and_records_the_pick(self):
        prep = section(read("flow/apply.md"), "0. Preflight")
        line = next(l for l in prep.splitlines() if "**Map.**" in l)
        for word in ("portfolio.py rank", "top two", "owner picks", "base CV", "cv-tailoring.md"):
            self.assertIn(word, line)
        write = section(read("flow/apply.md"), "5. Write the messages")
        for word in ("portfolio:", "portfolio_link:"):
            self.assertIn(word, write)

    def test_onboarding_fills_the_catalog(self):
        first = section(read("ONBOARDING.md"), "4. Write the first profile")
        for word in ("portfolio", "portfolio.py github", "portfolio.py migrate"):
            self.assertIn(word, first)
        line = next(l for l in section(read("ONBOARDING.md"), "6. Coaching interview").splitlines()
                    if "**Hooks, in full.**" in l)
        for word in ("shareable", "portfolio.py check"):
            self.assertIn(word, line)

    def test_messages_cite_one_project_with_its_approved_link(self):
        msgs = read("flow/messages.md")
        for word in ("portfolio_link", "shareable"):
            self.assertIn(word, section(msgs, "T1 Manager email (120 to 180 words)"))

    def test_agents_md_lists_the_script_and_the_catalog(self):
        agents = read("AGENTS.md")
        self.assertIn("`portfolio.py`", section(agents, "Layout"))
        hook = next(l for l in section(agents, "Vocabulary").splitlines() if l.startswith("| **Hook**"))
        self.assertIn("portfolio", hook)

    def test_brief_template_leaves_links_to_the_catalog(self):
        hooks = section(read("profile/brief.example.md"), "Hooks")
        self.assertIn("profile.json", hooks)
        self.assertNotIn("<link if public>", hooks)
