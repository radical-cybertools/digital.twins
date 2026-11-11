| harness | layout | c | N | repeats | bursts 2-5 req/s | x N=1 | seq p50 ms | placement ok | errors |
|---|---|---|---|---|---|---|---|---|---|
| dt | spread | 16 | 1 | 5 | 6.1 (6.0-7.2) | 1.00 | 394.3 | 5/5 | 0 |
| dt | spread | 16 | 2 | 5 | 10.6 (10.4-11.0) | 1.75 | 393.2 | 5/5 | 0 |
| dt | spread | 16 | 3 | 5 | 15.5 (15.2-15.7) | 2.55 | 395.0 | 5/5 | 0 |
| dt | spread | 16 | 4 | 5 | 19.7 (19.4-19.8) | 3.25 | 396.9 | 5/5 | 0 |

Code per site:

- dt spread N=2: `{"engine_config_entry": {"site_1": {"endpoint_name": "pm_e3_s1_61145516", "backends": ["concurrent"]}}, "agent_sites_entry": "site_1", "lines": 2}`
- dt spread N=3: `{"engine_config_entry": {"site_2": {"endpoint_name": "pm_e3_s2_61145516", "backends": ["concurrent"]}}, "agent_sites_entry": "site_2", "lines": 2}`
- dt spread N=4: `{"engine_config_entry": {"site_3": {"endpoint_name": "r3_site", "backends": ["concurrent"]}}, "agent_sites_entry": "site_3", "lines": 2}`
