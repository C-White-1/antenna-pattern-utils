# Development Guidelines

## Design principles

Apply SOLID principles pragmatically:

- Keep modules and functions focused on one clear responsibility.
- Separate parsing, validation, transformation, serialization, reporting,
  plotting, and command-line handling where practical.
- Prefer extending behaviour through focused functions or abstractions instead
  of repeatedly modifying stable parsing and serialization logic.
- Keep shared models independent of individual input formats.
- Depend on small, explicit interfaces and plain data structures.
- Avoid introducing classes, interfaces, factories, or dependency injection
  unless they materially improve testing, reuse, or maintainability.
- Do not refactor working code solely to make it appear more object-oriented.
- Preserve simple procedural code when it remains clear and cohesive.

## Project boundaries

- Source-format parsers must not write NSMA files directly.
- NSMA auditing must remain read-only.
- Repair logic must remain separate from auditing.
- Plotting must not alter antenna or pattern data.
- Command-line modules should coordinate workflows rather than contain core
  parsing or validation logic.
- Shared NSMA rules should have one authoritative definition.

## Changes and review

When changing code:

- Preserve existing behaviour unless the task explicitly changes it.
- Add or update tests for parsing, conversion, auditing, and repair rules.
- Avoid duplicating NSMA field definitions or validation rules.
- Prefer small, reviewable changes over broad speculative refactoring.
- Mention any SOLID trade-off when a simpler design is deliberately chosen.
