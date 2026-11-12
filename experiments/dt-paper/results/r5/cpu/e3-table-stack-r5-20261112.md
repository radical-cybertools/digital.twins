| harness | layout | c | N | repeats | bursts 2-5 req/s | x N=1 | seq p50 ms | placement ok | errors |
|---|---|---|---|---|---|---|---|---|---|
| dt | spread | 16 | 1 | 3 | 19.5 (19.5-19.5) | 1.00 | 56.8 | 3/3 | 0 |
| dt | spread | 16 | 2 | 3 | 38.3 (38.3-38.4) | 1.96 | 57.3 | 3/3 | 0 |
| dt | spread | 16 | 3 | 3 | 56.1 (55.8-56.2) | 2.88 | 57.2 | 3/3 | 0 |
| dt | spread | 16 | 4 | 3 | 75.3 (75.2-75.6) | 3.86 | 57.5 | 3/3 | 0 |
| dt | one | 16 | 4 | 3 | 19.5 (19.4-19.5) | nan | 56.8 | 3/3 | 0 |
| xgf | spread | 16 | 1 | 3 | 19.6 (19.6-19.6) | 1.00 | 55.0 | 3/3 | 0 |
| xgf | spread | 16 | 2 | 3 | 38.5 (38.4-38.6) | 1.97 | 56.1 | 3/3 | 0 |
| xgf | spread | 16 | 3 | 3 | 56.4 (56.3-56.5) | 2.88 | 56.4 | 3/3 | 0 |
| xgf | spread | 16 | 4 | 3 | 75.7 (75.6-75.8) | 3.87 | 56.2 | 3/3 | 0 |
| xgf | one | 16 | 4 | 3 | 19.6 (19.6-19.6) | nan | 55.1 | 3/3 | 0 |

Code per site:

- dt spread N=2: `{"engine_config_entry": {"site_1": {"endpoint_name": "e3_s1", "backends": ["concurrent"]}}, "agent_sites_entry": "site_1", "lines": 2}`
- dt spread N=3: `{"engine_config_entry": {"site_2": {"endpoint_name": "e3_s2", "backends": ["concurrent"]}}, "agent_sites_entry": "site_2", "lines": 2}`
- dt spread N=4: `{"engine_config_entry": {"site_3": {"endpoint_name": "e3_s3", "backends": ["concurrent"]}}, "agent_sites_entry": "site_3", "lines": 2}`
- xgf spread N=2: `{"SITES_entry": "e3_s1", "lines": 1}`
- xgf spread N=3: `{"SITES_entry": "e3_s2", "lines": 1}`
- xgf spread N=4: `{"SITES_entry": "e3_s3", "lines": 1}`
- xgf: wiring_lines 65
