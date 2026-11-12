| harness | layout | c | N | repeats | bursts 2-5 req/s | x N=1 | seq p50 ms | placement ok | errors |
|---|---|---|---|---|---|---|---|---|---|
| dt | spread | 16 | 1 | 5 | 19.5 (19.3-19.5) | 1.00 | 58.3 | 5/5 | 0 |
| dt | spread | 16 | 2 | 5 | 38.4 (38.3-38.5) | 1.97 | 58.9 | 5/5 | 0 |
| dt | spread | 16 | 3 | 5 | 57.0 (56.9-57.2) | 2.93 | 58.6 | 5/5 | 0 |
| dt | spread | 16 | 4 | 5 | 75.2 (74.7-75.4) | 3.87 | 58.9 | 5/5 | 0 |
| dt | one | 16 | 1 | 5 | 19.5 (19.3-19.5) | 1.00 | 58.3 | 5/5 | 0 |
| dt | one | 16 | 2 | 5 | 19.5 (19.2-19.5) | 1.00 | 58.2 | 5/5 | 0 |
| dt | one | 16 | 3 | 5 | 19.5 (19.3-19.5) | 1.00 | 58.2 | 5/5 | 0 |
| dt | one | 16 | 4 | 5 | 19.5 (19.4-19.5) | 1.00 | 58.3 | 5/5 | 0 |
| xgf | spread | 16 | 1 | 5 | 19.6 (19.5-19.6) | 1.00 | 55.4 | 5/5 | 0 |
| xgf | spread | 16 | 2 | 5 | 38.5 (38.5-38.7) | 1.97 | 56.5 | 5/5 | 0 |
| xgf | spread | 16 | 3 | 5 | 57.3 (57.1-57.4) | 2.93 | 56.5 | 5/5 | 0 |
| xgf | spread | 16 | 4 | 5 | 75.9 (75.2-76.1) | 3.88 | 56.6 | 5/5 | 0 |
| xgf | one | 16 | 1 | 5 | 19.6 (19.5-19.6) | 1.00 | 55.6 | 5/5 | 0 |
| xgf | one | 16 | 2 | 5 | 19.6 (19.6-19.6) | 1.00 | 56.0 | 5/5 | 0 |
| xgf | one | 16 | 3 | 5 | 19.6 (19.5-19.6) | 1.00 | 55.9 | 5/5 | 0 |
| xgf | one | 16 | 4 | 5 | 19.6 (19.5-19.6) | 1.00 | 56.1 | 5/5 | 0 |

Code per site:

- dt spread N=2: `{"engine_config_entry": {"site_1": {"endpoint_name": "e3_s1", "backends": ["concurrent"]}}, "agent_sites_entry": "site_1", "lines": 2}`
- dt spread N=3: `{"engine_config_entry": {"site_2": {"endpoint_name": "e3_s2", "backends": ["concurrent"]}}, "agent_sites_entry": "site_2", "lines": 2}`
- dt spread N=4: `{"engine_config_entry": {"site_3": {"endpoint_name": "e3_s3", "backends": ["concurrent"]}}, "agent_sites_entry": "site_3", "lines": 2}`
- xgf spread N=2: `{"SITES_entry": "e3_s1", "lines": 1}`
- xgf spread N=3: `{"SITES_entry": "e3_s2", "lines": 1}`
- xgf spread N=4: `{"SITES_entry": "e3_s3", "lines": 1}`
- xgf: wiring_lines 65
