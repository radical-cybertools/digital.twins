| harness | layout | c | N | repeats | bursts 2-5 req/s | x N=1 | seq p50 ms | placement ok | errors |
|---|---|---|---|---|---|---|---|---|---|
| dt | spread | 16 | 1 | 3 | 42.7 (41.2-45.2) | 1.00 | 56.9 | 3/3 | 0 |
| dt | spread | 16 | 2 | 3 | 69.2 (67.9-69.2) | 1.62 | 57.2 | 3/3 | 0 |
| dt | spread | 16 | 3 | 3 | 86.9 (86.1-86.9) | 2.04 | 57.1 | 3/3 | 0 |
| dt | spread | 16 | 4 | 3 | 102.8 (98.0-103.5) | 2.41 | 57.2 | 3/3 | 0 |
| dt | one | 16 | 4 | 3 | 42.4 (41.6-43.0) | nan | 56.9 | 3/3 | 0 |
| xgf | spread | 16 | 1 | 3 | 45.0 (44.1-45.1) | 1.00 | 54.8 | 3/3 | 0 |
| xgf | spread | 16 | 2 | 3 | 71.8 (70.6-72.0) | 1.59 | 56.0 | 3/3 | 0 |
| xgf | spread | 16 | 3 | 3 | 93.8 (92.9-94.8) | 2.08 | 55.9 | 3/3 | 0 |
| xgf | spread | 16 | 4 | 3 | 105.9 (105.4-107.8) | 2.35 | 56.0 | 3/3 | 0 |
| xgf | one | 16 | 4 | 3 | 44.4 (43.6-44.9) | nan | 55.0 | 3/3 | 0 |

Code per site:

- dt spread N=2: `{"engine_config_entry": {"site_1": {"endpoint_name": "e3_s1", "backends": ["concurrent"]}}, "agent_sites_entry": "site_1", "lines": 2}`
- dt spread N=3: `{"engine_config_entry": {"site_2": {"endpoint_name": "e3_s2", "backends": ["concurrent"]}}, "agent_sites_entry": "site_2", "lines": 2}`
- dt spread N=4: `{"engine_config_entry": {"site_3": {"endpoint_name": "e3_s3", "backends": ["concurrent"]}}, "agent_sites_entry": "site_3", "lines": 2}`
- xgf spread N=2: `{"SITES_entry": "e3_s1", "lines": 1}`
- xgf spread N=3: `{"SITES_entry": "e3_s2", "lines": 1}`
- xgf spread N=4: `{"SITES_entry": "e3_s3", "lines": 1}`
- xgf: wiring_lines 65
