# Same-label comparison of transverse bounds

Match every label by (fruit class, object ID, annotation line); assert identical source/target frame and pixel coordinates. Paired accuracy uses only labels returned by BOTH frozen profiles; availability is separately counted over all 497 labels. No model or rotation estimator is run.

| Evaluation | Common returned labels | Alpha 10 RMS, px | Alpha 20 RMS, px | Newly returned | Lost | Improved / worsened / unchanged |
| --- | --- | --- | --- | --- | --- | --- |
| independent_pairs | 455 | 5.10965 | 5.08041 | 7 | 0 | 17 / 7 / 431 |
| retained_segment | 344 | 4.99766 | 5.22752 | 24 | 4 | 13 / 7 / 324 |

The alpha 20 independent and retained subsets both include a returned 39.55996-pixel error. Worst-case actual image evidence is included below. These outcomes are retained; more available predictions are not a general accuracy claim.

Development author images used during tuning, not held-out evaluation. Common-label accuracy and newly available predictions must both be reported; a larger returned subset alone does not show improved accuracy.

![Matched-label accuracy](same_label_accuracy.png)

![Returned worst-case author error](independent_pairs_worst_alpha20.png)

![Returned worst-case author error](retained_segment_worst_alpha20.png)
