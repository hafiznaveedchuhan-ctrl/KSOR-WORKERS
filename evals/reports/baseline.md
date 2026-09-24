# Eval baseline (PROVISIONAL — dataset not fully owner-reviewed)

- captured: 2026-09-24T14:17:17+0500  ·  worker commit `cd3fcc3`  ·  dataset `c87f1e5b5d38ea8c` (95 cases)
- reason: first baseline: full 3-repeat live run + 13 real-traffic cases, worker cd3fcc3 (regression fix in place)

| category | graded | pass | rate | errors | skipped |
|---|---|---|---|---|---|
| abstention | 9 | 9 | 100% | 0 | 0 |
| grounded_qa | 21 | 21 | 100% | 0 | 0 |
| multi_turn | 6 | 6 | 100% | 0 | 0 |
| refund_domain | 17 | 17 | 100% | 0 | 0 |
| refund_gate | 8 | 8 | 100% | 0 | 1 |
| roman_urdu | 6 | 6 | 100% | 0 | 0 |
| safety | 9 | 9 | 100% | 0 | 0 |
| triage_routing | 10 | 10 | 100% | 0 | 0 |

Tracked separately (not in the rates above): 5 known_failing, 3 blocked_until_stable.
