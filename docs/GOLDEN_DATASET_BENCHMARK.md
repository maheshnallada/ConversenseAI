# Golden Dataset Benchmark Report

- **Golden interactions:** 50
- **Outcome abstention rate:** 100.0%
- **Compliance false negatives:** 1
- **Compliance false positives:** 0

## Dimension Metrics

| Dimension | Accuracy | Precision | Recall | Macro F1 | Support |
|---|---:|---:|---:|---:|---:|
| correct_outcome | 10.0% | 0.100 | 0.125 | 0.023 | 50 |
| sentiment | 16.0% | 0.160 | 0.333 | 0.092 | 50 |
| emotion | 12.0% | 0.120 | 0.167 | 0.036 | 50 |
| overall_quality | 14.0% | 0.140 | 0.250 | 0.061 | 50 |

## Call-Level Outcome Reconciliation

- `01a1aadc-f2aa-700f-8ae3-d1236e08f379`: Ground truth `Not interested`; prediction `Can't tell` (Does not match ground truth).
- `01a1aad7-ed9f-7e2d-b842-8429adabd1ee`: Ground truth `Expert call booked`; prediction `Can't tell` (Does not match ground truth).
- `01a1aa8c-f864-7e10-8cd3-21f94742ee0c`: Ground truth `No outcome: customer left first`; prediction `Can't tell` (Does not match ground truth).
- `01a1aa97-bd60-712e-b7b4-828cbffa5d0e`: Ground truth `No outcome: customer left first`; prediction `Can't tell` (Does not match ground truth).
- `01a19c3e-b578-7646-9eff-9acbc94ed2c4`: Ground truth `Expert call booked`; prediction `Can't tell` (Does not match ground truth).
- `01a1aacd-9cf5-790b-9a1e-17a0685664ea`: Ground truth `Not interested`; prediction `Can't tell` (Does not match ground truth).
- `01a1aa73-fb98-7210-a085-6b3e2226a333`: Ground truth `No outcome: customer left first`; prediction `Can't tell` (Does not match ground truth).
- `01a1aa5f-aa27-7bab-99f8-6b1097830ccb`: Ground truth `No outcome: customer left first`; prediction `Can't tell` (Does not match ground truth).
- `01a1aa7d-1a4c-7e0f-84f0-662689c8b642`: Ground truth `No outcome: customer left first`; prediction `Can't tell` (Does not match ground truth).
- `01a1aac9-b78b-7152-a973-7f8d54340c7a`: Ground truth `Call later agreed`; prediction `Can't tell` (Does not match ground truth).
- `01a1aa77-39a0-7001-90a6-43a3dd13c6c9`: Ground truth `Not interested`; prediction `Can't tell` (Does not match ground truth).
- `01a19fa8-5616-7daf-931b-6ca2cf778ede`: Ground truth `No outcome: customer left first`; prediction `Can't tell` (Does not match ground truth).
- `01a1aa81-d49c-7412-95c4-b16172c0f835`: Ground truth `Can't tell`; prediction `Can't tell` (Matches ground truth).
- `01a190f3-ae8b-717c-963d-dfaf5c1e46ac`: Ground truth `No outcome: customer left first`; prediction `Can't tell` (Does not match ground truth).
- `01a1aa90-53dd-75fe-a91e-3d7064cea4e9`: Ground truth `Not interested`; prediction `Can't tell` (Does not match ground truth).
- `01a1aa8e-90ac-77cd-b649-7fac2ec18cd9`: Ground truth `No outcome: customer left first`; prediction `Can't tell` (Does not match ground truth).
- `01a190f5-2feb-7a88-9742-902affd94649`: Ground truth `No outcome: customer left first`; prediction `Can't tell` (Does not match ground truth).
- `01a1aa8a-3987-709c-a600-f2ac13543197`: Ground truth `No outcome: customer left first`; prediction `Can't tell` (Does not match ground truth).
- `01a1aa9d-7472-7c6b-b31e-9e9064984eab`: Ground truth `Not interested`; prediction `Can't tell` (Does not match ground truth).
- `01a1aa6e-fae0-7bdb-834c-d2855c967faf`: Ground truth `Call screener or machine`; prediction `Can't tell` (Does not match ground truth).
- `01a1aada-3518-79c7-bcc7-25d9fb2f2270`: Ground truth `No outcome: customer left first`; prediction `Can't tell` (Does not match ground truth).
- `01a1aad6-00d5-77c7-819d-e6b1452776bc`: Ground truth `Not interested`; prediction `Can't tell` (Does not match ground truth).
- `01a1aadd-c9a5-70ee-96ab-52c8a020beec`: Ground truth `Not interested`; prediction `Can't tell` (Does not match ground truth).
- `01a1aa89-56a5-7824-af49-5dd0c7e09d15`: Ground truth `No outcome: customer left first`; prediction `Can't tell` (Does not match ground truth).
- `01a1aad4-c4d9-739d-93b9-40bbf347a3c1`: Ground truth `Can't tell`; prediction `Can't tell` (Matches ground truth).
- `01a18c90-3924-7aa8-8998-59d5ab999807`: Ground truth `Can't tell`; prediction `Can't tell` (Matches ground truth).
- `01a1aa62-1737-74d4-bc54-fff547e88727`: Ground truth `Can't tell`; prediction `Can't tell` (Matches ground truth).
- `01a1aa86-be73-738b-b3e4-324ce0f96987`: Ground truth `Do not call`; prediction `Can't tell` (Does not match ground truth).
- `01a19fa3-db5e-7fec-8e4d-ed1333c281b7`: Ground truth `Voicemail`; prediction `Can't tell` (Does not match ground truth).
- `01a1aada-459a-7fed-ba36-583837d4531a`: Ground truth `No outcome: customer left first`; prediction `Can't tell` (Does not match ground truth).
- `01a19fa7-4433-742a-8bfb-58af835c0ab3`: Ground truth `No outcome: customer left first`; prediction `Can't tell` (Does not match ground truth).
- `01a19fa3-223c-7b60-ab55-d468c4d70a55`: Ground truth `No outcome: customer left first`; prediction `Can't tell` (Does not match ground truth).
- `01a1aae0-26d0-7cff-aabe-9636252fde07`: Ground truth `Not interested`; prediction `Can't tell` (Does not match ground truth).
- `01a1aab9-889f-7e5c-9614-4ae28aa3c1f4`: Ground truth `No outcome: customer left first`; prediction `Can't tell` (Does not match ground truth).
- `01a1aa61-cbc4-7ade-9d84-212bf5d2531f`: Ground truth `No outcome: customer left first`; prediction `Can't tell` (Does not match ground truth).
- `01a1aabd-80ea-7d4d-8d8f-92452ae7a37e`: Ground truth `No outcome: customer left first`; prediction `Can't tell` (Does not match ground truth).
- `01a1aa7f-b24f-7f7f-9717-3149c47833c5`: Ground truth `Voicemail`; prediction `Can't tell` (Does not match ground truth).
- `01a1aa91-3eeb-7fad-ac6a-e3cdc3d9dea7`: Ground truth `Not interested`; prediction `Can't tell` (Does not match ground truth).
- `01a1aacb-17c9-75d9-b187-30c8022cf0ee`: Ground truth `Not interested`; prediction `Can't tell` (Does not match ground truth).
- `01a18c92-c255-7e28-89fc-8b33df1b8b7f`: Ground truth `Not interested`; prediction `Can't tell` (Does not match ground truth).
- `01a1aac5-f918-7c35-96e0-2636e4df81f1`: Ground truth `No outcome: customer left first`; prediction `Can't tell` (Does not match ground truth).
- `01a1aac0-07ff-7f45-8851-19da66ac1c66`: Ground truth `Can't tell`; prediction `Can't tell` (Matches ground truth).
- `01a19fa8-e44c-7ce9-b4d6-5cf40066178a`: Ground truth `No outcome: customer left first`; prediction `Can't tell` (Does not match ground truth).
- `01a1aacc-002a-7c02-b50b-455a73f3840f`: Ground truth `Not interested`; prediction `Can't tell` (Does not match ground truth).
- `01a1aad5-2485-7583-8e9d-b299b17eb14b`: Ground truth `No outcome: customer left first`; prediction `Can't tell` (Does not match ground truth).
- `01a18c93-f61b-7557-ad11-67549462e296`: Ground truth `Call later agreed`; prediction `Can't tell` (Does not match ground truth).
- `01a19fa7-e5bd-79a2-9b52-2d37cd3a542d`: Ground truth `No outcome: customer left first`; prediction `Can't tell` (Does not match ground truth).
- `01a1aa67-e1fa-7053-b63f-7155e32338dd`: Ground truth `No outcome: customer left first`; prediction `Can't tell` (Does not match ground truth).
- `01a1aadc-dced-7605-b5d6-7dda4d56f66f`: Ground truth `No outcome: customer left first`; prediction `Can't tell` (Does not match ground truth).
- `01a1aad0-7cab-7f3b-b19d-412cd4bd2919`: Ground truth `Not interested`; prediction `Can't tell` (Does not match ground truth).
