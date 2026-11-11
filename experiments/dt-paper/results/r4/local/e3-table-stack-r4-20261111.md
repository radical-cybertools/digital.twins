| harness | layout | c | N | repeats | bursts 2-5 req/s | x N=1 | seq p50 ms | placement ok | errors |
|---|---|---|---|---|---|---|---|---|---|
| dt | spread | 16 | 1 | 5 | 20.4 (20.2-20.8) | 1.00 | 56.4 | 5/5 | 0 |
| dt | spread | 16 | 2 | 5 | 39.6 (39.3-39.6) | 1.94 | 56.8 | 5/5 | 0 |
| dt | spread | 16 | 3 | 5 | 58.5 (58.5-58.8) | 2.88 | 56.8 | 5/5 | 0 |
| dt | spread | 16 | 4 | 5 | 77.5 (77.2-77.9) | 3.81 | 57.1 | 5/5 | 0 |
| dt | one | 16 | 1 | 5 | 20.3 (19.9-20.4) | 1.00 | 56.4 | 5/5 | 0 |
| dt | one | 16 | 2 | 5 | 20.2 (20.0-20.5) | 1.00 | 56.4 | 5/5 | 0 |
| dt | one | 16 | 3 | 5 | 20.4 (19.7-20.5) | 1.01 | 56.2 | 5/5 | 0 |
| dt | one | 16 | 4 | 5 | 20.4 (20.0-20.5) | 1.01 | 56.4 | 5/5 | 0 |
| xgf | spread | 16 | 1 | 5 | 25.5 (24.3-30.5) | 1.00 | 54.7 | 5/5 | 0 |
| xgf | spread | 16 | 2 | 5 | 42.8 (42.0-43.1) | 1.68 | 55.8 | 5/5 | 0 |
| xgf | spread | 16 | 3 | 5 | 61.4 (61.1-61.7) | 2.41 | 55.9 | 5/5 | 0 |
| xgf | spread | 16 | 4 | 5 | 80.3 (79.8-80.6) | 3.15 | 56.1 | 5/5 | 0 |
| xgf | one | 16 | 1 | 5 | 25.7 (25.4-28.5) | 1.00 | 55.0 | 5/5 | 0 |
| xgf | one | 16 | 2 | 5 | 25.3 (23.0-26.9) | 0.98 | 55.0 | 5/5 | 0 |
| xgf | one | 16 | 3 | 5 | 25.5 (24.9-29.4) | 0.99 | 54.8 | 5/5 | 0 |
| xgf | one | 16 | 4 | 5 | 26.7 (23.7-26.8) | 1.04 | 55.0 | 5/5 | 0 |

Code per site:

- dt spread N=2: `{"engine_config_entry": {"site_1": {"endpoint_name": "e3_s1", "backends": ["concurrent"]}}, "agent_sites_entry": "site_1", "lines": 2}`
- dt spread N=3: `{"engine_config_entry": {"site_2": {"endpoint_name": "e3_s2", "backends": ["concurrent"]}}, "agent_sites_entry": "site_2", "lines": 2}`
- dt spread N=4: `{"engine_config_entry": {"site_3": {"endpoint_name": "e3_s3", "backends": ["concurrent"]}}, "agent_sites_entry": "site_3", "lines": 2}`
- xgf spread N=2: `{"SITES_entry": "e3_s1", "lines": 1}`
- xgf spread N=3: `{"SITES_entry": "e3_s2", "lines": 1}`
- xgf spread N=4: `{"SITES_entry": "e3_s3", "lines": 1}`
- xgf: wiring_lines 65
