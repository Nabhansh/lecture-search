# Retrieval failure and annotation audit

Based on the final benchmark diagnostic output and transcript-context inspection preserved in the conversation. This is an audit log, not an assertion that annotation corrections have been applied.

| Query | Issue seen | Interpretation / next check |
|---|---|---|
| Q004, Q006 | Expected FCFS waiting-time explanation is around 433-463s, while `small_hi + hybrid` returned the FCFS introduction around 43-60s. | True timestamp/retrieval ranking failure.
| Q007 | SJF definition is in the expected 24-41s region. `base_auto` recognizes the term as “short test job first”; `small_hi` is heavily garbled there. | ASR quality and ranking both affect this result.
| Q013 | `base_auto` partly captures the semaphore purpose at 0.72-25s; `small_hi` intro is badly garbled. | ASR bottleneck, plus retrieval configuration differences.
| Q015 | Expected 55-70s contains the discussion of values 0 and 1 and counting semaphore; binary terminology is inconsistently transcribed. | Verify question-to-interval semantics against the video; this interval may describe counting semaphore values more than a binary semaphore definition.
| Q016, Q018 | `small_hi` around 665-672s explains that while one process uses the critical section, the other cannot enter. Retrieval failed or ranked it late. | Genuine ranking issue.
| Q023 | Both transcript configs clearly define deadlock around 0.88-12.88s, but top results point to the final lecture mention around 737s. | Strong retrieval miss.
| Q024 | Query asks about processes waiting for resources; current expected interval is a broad event-wait deadlock definition around 0.88-9.88s. | Verify semantic match and ground-truth interval manually.
| Q026 | `small_hi` explains that a process is divided into pages at 428.87-432.87s, but current relevant interval is 817.71-825.71s. | Possible missing relevant interval; verify the clip and consider adding an alternative ground-truth interval.
| Q028 | `small_hi` has a segment about dividing processes into pages at 470.87-473.87s; current labels are at 487.87-491.87 and 557.87-560.87. | Potential annotation incompleteness; the top result may be on-topic even though outside annotated windows.

Do not overwrite `queries.jsonl` until the corresponding clips have been checked manually.
