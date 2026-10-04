# Final author profile: same-label comparison

Match all497author labels by fruit group, object and annotation line; require identical source/target frames, pixel coordinates and split. Separate common-label errors from availability changes. Report every gained/lost/unavailable label and all three fruit groups. No estimator/model is run here.

Development data repeatedly inspected during algorithm work, not held-out evaluation. Settings and source differ, so this is a profile comparison, not an isolated causal comparison. Publication Table4 used a different label subset; this is not a reproduction or comparison on an identical published subset. Conditional RMS uses only returned predictions; counts over all497labels remain visible.

Final profile predicts457/497labels: conditional RMS5.224579pixels,372labels within5pixels (74.849% of all497). More within5 does not establish a general accuracy improvement.

| Archived profile | Common returned | Archived RMS (px) | Final RMS (px) | Newly returned | Lost | Both unavailable | Improved / worsened / unchanged |
|---|---:|---:|---:|---:|---:|---:|---|
| operational_profile_v1 | 450 | 4.912064 | 4.887740 | 7 | 8 | 32 | 124 / 99 / 227 |
| hybrid_wobble_profile_20261002 | 454 | 5.225545 | 5.240480 | 3 | 8 | 32 | 103 / 100 / 251 |

Worst final returned error: 39.559958pixels, mandarins/obj0004, annotation line61. This result is retained and shown below. JSON includes per-group comparisons, every individual label and all source/settings/report hashes.

![All common labels](same_label_accuracy.png)

![Worst final author prediction](worst_candidate_author_error.png)
