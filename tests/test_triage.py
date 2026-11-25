from ocp import config
from ocp.domain import Alert
from ocp.kit.queue import Queue, Team
from ocp.kit.triage import Draft, Evidence, check_draft, draft_checked, route, template_draft

EV = [Evidence("E1", "alert", "indirect on mixer, severity 2, EUR 1,250"), Evidence("E2", "exposure", "40% at 1 hops"), Evidence("E6", "model score", "0.12 chance")]
A = Alert("1:indirect", 3, 1, 10, "indirect", "indirect", "mixer", 2, 0.4, 1, 1250.0)


def test_template_draft_passes_its_own_check() -> None:
    assert check_draft(template_draft(A, EV, 0.12, 0.3), EV) == []


def test_a_hallucinating_drafter_is_replaced() -> None:
    def liar(a: Alert, ev: list[Evidence], p: float, t: float) -> Draft:
        return Draft("close", (("The customer moved EUR 9,999 to an exchange.", ("E1",)), ("Looks fine.", ())), "llm")

    d, problems = draft_checked(A, EV, 0.12, 0.3, liar)
    assert d.drafter == "template" and any("9,999" in p for p in problems) and any("uncited" in p for p in problems)
    bad_cite = Draft("escalate", (("Exposure is high.", ("E9",)),), "llm")
    assert check_draft(bad_cite, EV)


def test_hard_rules_beat_the_score() -> None:
    kit = config.kit()
    sanction = Alert("2:direct", 3, 2, 10, "direct", "direct", "sanctions", 3, 0, 0, 10.0)
    assert route(sanction, 0.01, kit) == "priority"
    big = Alert("3:indirect", 3, 3, 10, "indirect", "indirect", "mixer", 2, 0.1, 2, 50_000.0)
    assert route(big, 0.01, kit) == "normal"
    behav = Alert("4:structuring-7d", 3, 4, 10, "structuring-7d", "behavioral", "structuring", 2)
    assert route(behav, 0.01, kit) == "normal"
    assert route(A, 0.01, kit) == "fast"
    assert route(sanction, 0.01, kit, governed=False) == "auto_close"  # what the ungoverned ablation does


def test_team_works_office_hours_on_weekdays() -> None:
    t = Team(2, 240, (9, 17))
    assert t.minutes_in_hour(10) == 60 and t.minutes_in_hour(20) == 0 and t.minutes_in_hour(5 * 24 + 10) == 0
    assert t.working_hours(4 * 24 + 16, 7 * 24 + 10) == 2  # Friday 16:00 to Monday 10:00


def test_priority_queue_reserves_room_for_the_fast_lane() -> None:
    q = Queue("priority")
    q.push("slow", 12, "normal", 0, 0.2)
    q.push("urgent", 12, "priority", 1, 0.9)
    q.push("quick", 3, "fast", 0, 0.01)
    done = [i.key for i in q.work(20)]
    assert done == ["quick", "urgent"]
    f = Queue("fifo")
    f.push("a", 12, "normal", 0)
    f.push("b", 12, "priority", 1)
    assert [i.key for i in f.work(12)] == ["a"]
