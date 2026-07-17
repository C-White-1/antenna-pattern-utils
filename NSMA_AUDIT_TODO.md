# NSMA Audit TODO

Future work for `nsma_audit.py` and its supporting audit workflow.

## Completed foundations

- [x] Use immutable, typed WG16.99.050 definitions as the runtime source of
  truth.
- [x] Generate `nsma.csv` and `nsma_schema.json` from the authoritative Python
  definition.
- [x] Warn when an external CSV schema overrides built-in validation.
- [x] Reject circularly equivalent duplicate directions such as 0/360 and
  -180/+180 degrees.

## Priority 1: Standards and structural validation

- [ ] Add regular-angle-spacing analysis for each cut.
  - Determine the normal increment from the observed points.
  - Detect unexpected gaps within an otherwise regularly sampled cut.
  - Do not assume one-degree spacing.
  - Treat irregular spacing as a warning unless it creates another explicit
    standards violation.

- [ ] Add proper multiple-frequency-block parsing.
  - Associate each `PATFRE` with its own `NUMCUT` and pattern cuts.
  - Validate `NOFREQ` against the number of actual frequency blocks.
  - Validate `NUMCUT` independently within each frequency block.
  - Include frequency context in cut-level findings.

- [ ] Improve repeated-record validation for multi-frequency files.
  - Permit fields that legitimately repeat per frequency.
  - Continue rejecting duplicate singleton metadata and duplicate `ENDFIL`
    records.

- [ ] Validate comments introduced with `!`.
  - Ignore comment text when parsing record values and lengths where required
    by WG16.99.050.
  - Retain original line numbers in findings.

## Priority 2: Character and compatibility checks

- [ ] Detect tab characters.
- [ ] Detect leading and trailing whitespace.
- [ ] Detect non-ASCII characters and report their positions.
- [ ] Detect unexpected UTF byte-order marks.
- [ ] Tighten comma/column validation.
  - Detect too many pattern-point fields.
  - Distinguish magnitude-only, magnitude-plus-phase, and malformed records.

- [ ] Add named application compatibility profiles.
  - Keep strict WG16.99.050 validation as the default.
  - Add profiles only when an application's actual import requirements are
    documented.
  - Candidate profile: Pathloss.

## Priority 3: Engineering sanity checks

Engineering checks should normally produce warnings rather than compliance
errors.

- [ ] Check pattern normalization.
  - Confirm each relative pattern peaks near `0 dBr`.
  - Flag positive peaks or cuts whose maximum is materially below zero.
  - Do not compare relative pattern values directly with absolute `MDGAIN`.

- [ ] Calculate approximate 3 dB beamwidth.
  - Compare H/AZ cuts with `AZWIDT`.
  - Compare V/EL cuts with `ELWIDT`.
  - Allow configurable tolerance.
  - Account for wrap-around at 0/360 degrees.

- [ ] Calculate approximate front-to-back ratio.
  - Define the main-beam and rear-sector calculation clearly.
  - Compare the calculated result with `FRTOBA`.
  - Allow configurable angular sector and tolerance.

- [ ] Add cut-orientation plausibility checks.
  - Flag likely H/V swaps based on declared beamwidths.
  - Keep these findings advisory because real patterns may be asymmetric.

- [ ] Add suspicious-value checks.
  - Frequencies outside plausible RF ranges.
  - Negative or zero absolute gain where inappropriate.
  - Implausible beamwidth, VSWR, power, or dimension values.

## Priority 4: Reporting

- [ ] Add JSON output.
  - Include file metadata, compliance status, findings, frequency blocks, cuts,
    point counts, and calculated metrics.
  - Provide stable field names suitable for automation and CI.
  - Suggested option: `--json-output report.json`.

- [ ] Add a concise pattern summary to terminal output.
  - Frequency
  - Cut and polarization
  - Declared and actual point counts
  - First and last angles
  - Normal angular increment
  - Pass/warning/error status

- [ ] Add optional reporting of omitted optional fields.
  - Do not report these by default.
  - Suggested option: `--report-optional`.

- [ ] Add HTML reports.
  - Overall pass/fail status
  - Grouped errors and warnings
  - Pattern summaries
  - Embedded plots
  - Link findings to source line numbers where practical

## Priority 5: Audit plots

- [ ] Connect NSMA parsing to the existing polar plotting utilities.
- [ ] Add an audit option to save plots without requiring PLANET input.
- [ ] Generate one panel per cut or a configurable grouped layout.
- [ ] Highlight suspicious regions where useful:
  - Missing or irregular angular intervals
  - Duplicate angles
  - Clipped or positive relative-gain values
- [ ] Suggested interface:

  ```console
  python nsma_audit.py antenna.nsm --plot-output audit-plots/
  ```

## Repair utility follow-up

- [ ] Keep `nsma_repair.py` conservative and separate from the auditor.
- [ ] Add repairs only when values can be derived deterministically.
- [ ] Preserve a complete change log for every output.
- [ ] Consider a machine-readable repair log.
- [ ] Add support for multi-frequency metadata repair after the auditor's
  multi-frequency model is implemented.
- [ ] Never invent missing measured pattern points.
- [ ] Add a read-only pattern-reference comparison mode to assist manual repair.
  - Identify missing angles and show candidate values from a supplied reference.
  - Compare frequency, polarization, cut orientation, tilt, angular spacing,
    and normalization before presenting a candidate.
  - Report numerical differences and optionally plot both patterns around the
    affected region.
  - Never copy, interpolate, or write pattern-point values automatically.
  - Require the user to inspect and insert any accepted value manually, then
    rerun the audit and plot the repaired pattern.

## Testing

- [ ] Add automated unit tests for:
  - Correct CRLF files
  - LF-only, CR-only, and CRCRLF files
  - Blank records
  - Missing and empty required fields
  - Field order and maximum lengths
  - Duplicate and misplaced `ENDFIL`
  - Multiple frequencies and cuts
  - One-degree and non-one-degree angular increments
  - Duplicate, decreasing, and irregular angles
  - Pattern points with and without phase
  - Comments introduced with `!`
  - Repair dry runs and post-repair audits

- [ ] Add regression fixtures created specifically for this project.
  - Avoid committing third-party standards, datasheets, or manufacturer data
    without permission.
  - Include synthetic valid and intentionally invalid NSMA examples.

## Design notes

- `FSTLST` and `NUPOIN` describe actual data; they do not imply one-degree
  sampling.
- WG16.99.050 pattern examples include a trailing comma. Strict auditing should
  retain this requirement unless an explicit compatibility profile says
  otherwise.
- `MDGAIN` is absolute antenna gain, while pattern levels are normally relative
  dBr values.
- Omitted optional fields are allowed by the standard and should not create
  default warnings.
- Compliance findings and engineering observations should remain clearly
  separated.
