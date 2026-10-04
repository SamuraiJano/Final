# Measurement-method check

The `_ellipse` function is byte-identical between the frozen author benchmark implementation and the frozen conveyor audit implementation. Its text SHA256 is `26f1ec32cc4639f1f4eb21aac25b4ca3a19b7ac52a11cd8355026ba5042ab807`. This confirms the same pixel-moment semi-axis calculation; it does not make the different silhouette masks equivalent or ground truth.

Author algorithm SHA256: `74af29eb38afd8f2eeadc8857e310d5e018288845c4a24d1205f188e991f373c`.
Conveyor audit algorithm SHA256: `52c13a0452875653fb054053fcc0bdbb4a6ed9cb4227c697be32b62fbe811327`.

The closest fruit-type reference comprises 15 author mandarin sequences. Their median major-radius CV is 0.8035%, maximum 1.6300%; median relative range is 3.0030%, maximum 6.4293%. The complete 36-sequence comparison remains in report.json and the main report.
