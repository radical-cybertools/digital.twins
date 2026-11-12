| harness | layout | c | N | repeats | bursts 2-5 req/s | x N=1 | seq p50 ms | placement ok | errors |
|---|---|---|---|---|---|---|---|---|---|
| dt | spread | 64 | 1 | 5 | 16.0 (15.9-16.2) | 1.00 | 403.3 | 5/5 | 126 |
| dt | spread | 64 | 2 | 5 | 26.9 (26.6-27.2) | 1.69 | 404.1 | 5/5 | 0 |
| dt | spread | 64 | 3 | 5 | 35.2 (35.0-35.7) | 2.21 | 404.2 | 5/5 | 0 |
| dt | spread | 64 | 4 | 5 | 45.9 (45.8-46.1) | 2.87 | 404.4 | 5/5 | 0 |

Code per site:

- dt spread N=2: `{"engine_config_entry": {"site_1": {"endpoint_name": "pm_e3_s1_61187855", "backends": ["concurrent"]}}, "agent_sites_entry": "site_1", "lines": 2}`
- dt spread N=3: `{"engine_config_entry": {"site_2": {"endpoint_name": "pm_e3_s2_61187855", "backends": ["concurrent"]}}, "agent_sites_entry": "site_2", "lines": 2}`
- dt spread N=4: `{"engine_config_entry": {"site_3": {"endpoint_name": "r3_site", "backends": ["concurrent"]}}, "agent_sites_entry": "site_3", "lines": 2}`
