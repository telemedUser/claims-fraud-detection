TEST SCENARIO DATA
Generated on 19-Nov-2026. Re-run: python scripts/generate_test_scenarios.py

Each folder has claim_form.txt (what to type, step by step) and the four documents to upload.

Folder                                         Agent                        Expected score (weighted rules)
01 Small claim auto-approved                   None (every agent passes)    ~0
02 Genuine claim                               None (every agent passes)    ~0
03 Suspicious claim                            All agents                   ~100
04 Claimed more than billed                    Invoice Validation           ~90
05 Bill number already used                    Invoice Validation           ~56
06 Bill not fully paid                         Invoice Validation           ~53
07 Details differ across documents             Document Forensics           ~38
08 Files saved by Photoshop                    Document Forensics           ~75
09 Treatment does not fit the diagnosis        Medical Review               ~30
10 Lab report altered, wrong ICD code          Medical Review               ~42
11 Wrong GSTIN, doctor outside specialty       Provider Profile             ~45
12 Earlier denied claim, frequent claims       User Profile                 ~32
