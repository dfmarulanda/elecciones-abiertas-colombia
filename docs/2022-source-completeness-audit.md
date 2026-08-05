# 2022 MMV source-completeness audit

**Audit basis:** read-only inspection of the two preserved Registraduría Observatorio ZIP snapshots and the normalized Parquet in `historical-2022-mmv-context-v2-705d3d71523003b8`. This is an identity and schema audit, not a claim that either source is a complete national denominator.

## Published census versus MMV snapshot identities

Registraduría's pre-election census states that the presidential election would use 102,152 mesas: 100,809 in Colombia and 1,343 in the exterior, with 12,263 and 250 respective polling places. The source is the Registraduría article [“La Registraduría Nacional entrega detalles del censo electoral en Colombia y en el exterior para las elecciones de presidente y vicepresidente del próximo domingo”](https://www.registraduria.gov.co/La-Registraduria-Nacional-entrega-detalles-del-censo-electoral-en-Colombia-y-en).

| Scope                 |  Official pre-election census | MMV ZIP / normalized Parquet identities |                 Difference |
| --------------------- | ----------------------------: | --------------------------------------: | -------------------------: |
| Colombia              | 100,809 mesas; 12,263 puestos |           100,812 mesas; 12,261 puestos |       +3 mesas; −2 puestos |
| Exterior / Consulados |      1,343 mesas; 250 puestos |              2,552 mesas; 1,000 puestos | +1,209 mesas; +750 puestos |
| Total                 | 102,152 mesas; 12,513 puestos |           103,364 mesas; 13,261 puestos | +1,212 mesas; +748 puestos |

The MMV split uses the source's `DEP` codes: `16` is `BOGOTA D.C.` and `88` is `CONSULADOS`. All other department-level MMV mesa counts match the census table; the full numerical difference is the three Bogotá identities and the 1,209 Consulados identities.

## Raw-schema and normalized-identity checks

The preserved source ZIPs are content-addressed as:

| Round | SHA-256                                                            | CSV rows | Distinct raw five-code identities | Distinct canonical identities |
| ----- | ------------------------------------------------------------------ | -------: | --------------------------------: | ----------------------------: |
| 1     | `52443174bbe5c09d73a1b0538a1a9ae5f78afb934c7b8f98f93ea52b41872769` |  727,510 |                           103,364 |                       103,364 |
| 2     | `175ad5884ee6aceb9fb36782990c2bbabb0a4f2c84e41dbbcc74c824816c1b61` |  398,386 |                           103,364 |                       103,364 |

Each ZIP has exactly one CSV member, the reviewed 16-column header, and normal 16-column records at the end of the file; it has no published footer/trailer record. The canonical mesa identity is the published five-code tuple `DEP/MUN/ZONA/PUESTO/MESA`. The Parquet artifact reproduces the same 103,364 distinct identities in each round and has zero duplicate semantic facts.

Mesa codes provide no evidence that the count arises from a zero or special mesa placeholder: every `MESA` code is decimal, ranges from `001` through `282`, and there are zero `000` or non-decimal mesa codes. The source does contain 605 identities with alphanumeric `PUESTO` codes; those are preserved as official place codes and none occurs in `MESA`.

## Round comparison

The rounds share 103,295 canonical mesa identities. Each has 69 identities not present in the other. All 69-per-round differences are in `DEP=88` (`CONSULADOS`) and are concentrated in three published exterior municipality codes: 9, 52, and 8 identities respectively. Both rounds nevertheless retain the same total identity count and the same domestic/exterior split.

## Interpretation and parser finding

There is no evidence of a parser-generated overcount. Zero-padding produced no raw-to-canonical identity collision, mesa identifiers are not invented, and the raw and normalized counts agree exactly.

The evidence supports only a bounded interpretation: the published MMV exterior hierarchy (1,000 `PUESTO` identities and 2,552 mesa identities) is not one-to-one with the pre-election census's 250 exterior polling places and 1,343 installed mesas. The source material inspected here does not provide an official MMV codebook or a physical-mesa roster that would explain the hierarchy difference. Therefore this audit does **not** claim that the 1,212 difference represents extra physical mesas, nor that either source is a complete expected-coverage denominator.
