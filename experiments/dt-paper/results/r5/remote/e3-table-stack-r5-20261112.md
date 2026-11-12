| harness | layout | c | N | repeats | bursts 2-5 req/s | x N=1 | seq p50 ms | placement ok | errors |
|---|---|---|---|---|---|---|---|---|---|
| dt | spread | 16 | 1 | 3 | 13.0 (13.0-13.2) | 1.00 | 392.1 | 3/3 | 0 |
| dt | spread | 16 | 2 | 3 | 19.9 (19.7-20.3) | 1.53 | 391.5 | 3/3 | 0 |
| dt | spread | 16 | 3 | 3 | 23.9 (23.8-23.9) | 1.83 | 392.3 | 3/3 | 0 |
| dt | spread | 16 | 4 | 3 | 28.8 (28.5-29.3) | 2.21 | 391.7 | 3/3 | 0 |

Code per site:

- dt spread N=2: `{"engine_config_entry": {"site_1": {"endpoint_name": "pm_e3_s1_61164117", "backends": ["concurrent"]}}, "agent_sites_entry": "site_1", "lines": 2}`
- dt spread N=3: `{"engine_config_entry": {"site_2": {"endpoint_name": "pm_e3_s2_61164117", "backends": ["concurrent"]}}, "agent_sites_entry": "site_2", "lines": 2}`
- dt spread N=4: `{"engine_config_entry": {"site_3": {"endpoint_name": "r3_site", "backends": ["concurrent"]}}, "agent_sites_entry": "site_3", "lines": 2}`
