"""Focused regression tests for recorded query-intent behavior."""

import importlib.util
import sys
import types
from pathlib import Path

# Import the module without installing heavy retrieval dependencies in this test process.
faiss_stub = types.ModuleType("faiss")
fastembed_stub = types.ModuleType("fastembed")
fastembed_stub.TextEmbedding = object
sys.modules.setdefault("faiss", faiss_stub)
sys.modules.setdefault("fastembed", fastembed_stub)

try:
    import numpy  # noqa: F401
except ImportError:
    numpy_stub = types.ModuleType("numpy")
    sys.modules["numpy"] = numpy_stub

spec = importlib.util.spec_from_file_location(
    "search_hybrid_under_test", Path(__file__).parents[1] / "scripts" / "search_hybrid.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_sjf_selection_precedes_definition():
    assert module.sjf_query_intent("SJF में सबसे पहले कौन सा प्रोसेस execute होता है?") == "selection"


def test_sjf_tie_break():
    assert module.sjf_query_intent("Agar do processes ka arrival time same ho to SJF mein kaise select karte hain?") == "tie_break"


def test_sjf_question_fragment_not_promoted():
    score = module.segment_intent_match_score(
        "How does SJF choose the next process?",
        "why are you selecting",
        "P1 P2 burst time because less",
    )
    assert score == 2


def test_sjf_actual_selection_gets_high_score():
    score = module.segment_intent_match_score(
        "How does SJF choose the next process?",
        "so we will select",
        "P1 P3 burst time because less",
    )
    assert score == 11


def test_fcfs_does_not_promote_unanchored_arrival_time():
    score = module.segment_intent_match_score(
        "How does FCFS scheduling select the next process?",
        "arrival time",
        "SJF scheduling chooses the process",
    )
    assert score == 0


def test_fcfs_arrival_criterion_with_fcfs_context():
    score = module.segment_intent_match_score(
        "How does FCFS scheduling select the next process?",
        "The criteria is arrival time",
        "FCFS works by first come first serve",
    )
    assert score == 10


def test_binary_semaphore_hindi_query_detection():
    query = "बाइनरी सेमाफोर क्या होता?"

    assert module.is_binary_semaphore_definition_query(query)


def test_binary_semaphore_expands_zero_and_one_phrases():
    phrases = module.query_phrase_expansions(
        "बाइनरी सेमाफोर क्या होता है?"
    )

    assert "zero and one" in phrases
    assert "only zero and one" in phrases
    assert "two values" in phrases


def test_binary_semaphore_scores_direct_explanation():
    score = module.segment_intent_match_score(
        "बाइनरी सेमाफोर क्या होता है?",
        "zero and one",
        "The binary semaphore has two values, zero and one.",
    )

    assert score == 12


def test_binary_semaphore_handles_asr_corrupted_terms():
    score = module.segment_intent_match_score(
        "बाइनरी सेमाफोर क्या होता है?",
        "zero and one",
        "bindrye sama 4 values zero and one",
    )

    assert score == 12


def test_binary_semaphore_rejects_unrelated_numeric_example():
    score = module.segment_intent_match_score(
        "बाइनरी सेमाफोर क्या होता है?",
        "zero to one",
        "A process arrived at zero and the CPU becomes idle.",
    )

    assert score == 0


def test_deadlock_definition_query_detection():
    assert module.is_deadlock_definition_query("Deadlock kab hota hai?")
    assert module.is_deadlock_definition_query("What is deadlock?")
    assert module.is_deadlock_definition_query("डेडलॉक क्या होता है?")


def test_deadlock_waiting_question_is_not_definition_intent():
    assert not module.is_deadlock_definition_query(
        "Why can processes wait indefinitely in deadlock?"
    )


def test_deadlock_definition_gets_high_intent_score():
    score = module.segment_intent_match_score(
        "Deadlock kab hota hai?",
        "but that event doesn't happen, that is called the deadlock",
        "Deadlock is what if two and more processes are waiting "
        "on happening of some event",
    )
    assert score == 12


def test_deadlock_generic_mention_is_not_promoted():
    score = module.segment_intent_match_score(
        "Deadlock kab hota hai?",
        "Deadlock occurs",
        "These four conditions are very important.",
    )
    assert score == 0


def test_deadlock_circular_wait_without_definition_is_not_promoted():
    score = module.segment_intent_match_score(
        "Deadlock kab hota hai?",
        "so that is what again called a deadlock situation",
        "P1 has taken S1 and is waiting for S2. P2 has taken S2.",
    )
    assert score == 0


def test_paging_query_intent_distinguishes_reason_and_division():
    assert module.paging_query_intent(
        "Process ko pages mein kaise divide karte hain?"
    ) == "division"

    assert module.paging_query_intent(
        "प्रोसेस को पेजों में क्यों बाँटा जाता है?"
    ) == "reason"


def test_paging_division_expands_relevant_phrases():
    phrases = module.query_phrase_expansions(
        "Process ko pages mein kaise divide karte hain?"
    )

    assert "secondary memory" in phrases
    assert "process into pages" in phrases
    assert "partition we call pages" in phrases


def test_paging_reason_expands_efficiency_phrases():
    phrases = module.query_phrase_expansions(
        "प्रोसेस को पेजों में क्यों बाँटा जाता है?"
    )

    assert "more efficiently" in phrases
    assert "memory in a more efficient way" in phrases
    assert "non contiguous manner" in phrases


def test_paging_division_scores_page_creation_explanation():
    score = module.segment_intent_match_score(
        "Process ko pages mein kaise divide karte hain?",
        "We will first divide the processes in the secondary memory.",
        "Every partition is called a page. Every process is divided into pages.",
    )

    assert score == 12


def test_paging_reason_scores_memory_efficiency_explanation():
    score = module.segment_intent_match_score(
        "प्रोसेस को पेजों में क्यों बाँटा जाता है?",
        "So that I can use the memory in a more efficient way.",
        "The page will fit into a frame, allowing memory to be used more efficiently.",
    )

    assert score == 12


def test_paging_does_not_promote_unrelated_numeric_example():
    score = module.segment_intent_match_score(
        "Process ko pages mein kaise divide karte hain?",
        "zero to one",
        "A process arrived at zero and the CPU becomes idle.",
    )

    assert score == 0


def test_fcfs_waiting_time_intent_detection():
    assert module.is_fcfs_waiting_time_query(
        "How is waiting time calculated in FCFS?"
    )
    assert module.is_fcfs_waiting_time_query(
        "FCFS में वेटिंग टाइम कैसे निकाला जाता है?"
    )
    assert not module.is_fcfs_waiting_time_query(
        "How does FCFS scheduling select the next process?"
    )


def test_fcfs_waiting_time_phrase_expansion():
    phrases = module.query_phrase_expansions(
        "How is waiting time calculated in FCFS?"
    )
    assert "turn around time" in phrases
    assert "burst time" in phrases
    assert "turn around time minus burst time" in phrases


def test_fcfs_waiting_time_scores_formula_explanation():
    score = module.segment_intent_match_score(
        "How is waiting time calculated in FCFS?",
        "Waiting time is",
        "Turn around time minus burst time gives the waiting time.",
    )
    assert score == 12


def test_critical_section_concurrency_intent_detection():
    assert module.is_critical_section_concurrency_query(
        "क्रिटिकल सेक्शन में एक समय पर कितने प्रोसेस जा सकते हैं?"
    )
    assert module.is_critical_section_concurrency_query(
        "Critical section ko ek time par kitne processes access kar sakte hain?"
    )
    assert not module.is_critical_section_concurrency_query(
        "Why do operating systems use semaphores for synchronization?"
    )


def test_critical_section_concurrency_phrase_expansion():
    phrases = module.query_phrase_expansions(
        "How many processes can access the critical section at one time?"
    )
    assert "mutual exclusion" in phrases
    assert "one process at a time" in phrases
    assert "another process is blocked" in phrases


def test_critical_section_concurrency_scores_mutual_exclusion():
    score = module.segment_intent_match_score(
        "How many processes can access the critical section at one time?",
        "We are using critical section",
        "Mutual exclusion means one process is inside. Another process is blocked.",
    )
    assert score == 12


def test_deadlock_resource_wait_intent_detection():
    assert module.is_deadlock_resource_wait_query(
        "Processes resources ke liye wait karte rahein to kya situation banti hai?"
    )
    assert not module.is_deadlock_resource_wait_query(
        "What is deadlock?"
    )


def test_deadlock_resource_wait_phrase_expansion():
    phrases = module.query_phrase_expansions(
        "Processes resources ke liye wait karte rahein to kya situation banti hai?"
    )
    assert "P1 has taken one resource" in phrases
    assert "R2 is already taken by P2" in phrases
    assert "P2 is requesting R1" in phrases


def test_deadlock_resource_wait_scores_circular_resource_dependencies():
    score = module.segment_intent_match_score(
        "Processes resources ke liye wait karte rahein to kya situation banti hai?",
        "R2 is already taken by P2",
        "P1 has taken R1 and is waiting for R2. "
        "P2 has taken R2 and is requesting R1.",
    )
    assert score == 12


def test_deadlock_resource_wait_rejects_generic_resource_sentence():
    score = module.segment_intent_match_score(
        "Processes resources ke liye wait karte rahein to kya situation banti hai?",
        "Processes request resources",
        "A process may wait for memory to become available.",
    )
    assert score == 0


def test_fcfs_waiting_time_does_not_promote_sjf_lecture():
    query = "How is waiting time calculated in FCFS?"
    segment = "Waiting time is"
    context = "Turn around time minus burst time gives the waiting time."

    assert module.segment_intent_match_score(
        query, segment, context, lecture_id="os_l24_sjf"
    ) == 0

    assert module.segment_intent_match_score(
        query, segment, context, lecture_id="os_l23_fcfs"
    ) == 12

def test_critical_section_definition_intent_detection():
    assert module.is_critical_section_definition_query(
        "What is the critical section in process synchronization?"
    )
    assert module.is_critical_section_definition_query(
        "Define the critical section."
    )
    assert not module.is_critical_section_definition_query(
        "How many processes can access the critical section at one time?"
    )


def test_critical_section_definition_phrase_expansion():
    phrases = module.query_phrase_expansions(
        "What is the critical section in process synchronization?"
    )
    assert "mutual exclusion" in phrases
    assert "another process is blocked" in phrases


def test_critical_section_definition_semantic_expansion():
    expanded = module.semantic_query_text(
        "What is the critical section in process synchronization?"
    )
    normalized = expanded.casefold()
    assert "mutual exclusion" in normalized
    assert "shared resources" in normalized


def test_critical_section_definition_scores_actual_explanation():
    score = module.segment_intent_match_score(
        "What is the critical section in process synchronization?",
        "Mutual exclusion means,",
        (
            "One process is inside the critical section; "
            "another process is blocked and cannot enter."
        ),
        lecture_id="os_l39",
    )
    assert score == 12


def test_critical_section_definition_rejects_unrelated_synchronization():
    score = module.segment_intent_match_score(
        "What is the critical section in process synchronization?",
        "then in synchronization",
        "Two processes are waiting for resources.",
        lecture_id="os_l41_deadlock",
    )
    assert score == 0
