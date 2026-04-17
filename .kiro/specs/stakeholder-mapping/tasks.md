# Implementation Plan: Stakeholder Mapping

## Overview

Extend the Velaris decision intelligence engine with first-class Stakeholder modeling. Implementation proceeds bottom-up: data models → registry CRUD → map building → conflict detection → negotiation → engine integration → curve tracking → backward compatibility. All new code is pure Python with Pydantic v2 under `src/velaris_agent/memory/`. Tests use Hypothesis for property-based testing and pytest for unit tests.

## Tasks

- [x] 1. Add Stakeholder data models to `memory/types.py`
  - [x] 1.1 Define `PreferenceDirection` enum, `StakeholderRole` enum, `InterestDimension` model, `Stakeholder` model, `PairwiseAlignment` model, `Conflict` model, `NegotiationProposal` model, `StakeholderContext` model, and `StakeholderMapModel` model in `src/velaris_agent/memory/types.py`
    - Add all Pydantic v2 models with Field constraints (ge, le) as specified in the design
    - Ensure `Stakeholder.influence_weights` values are validated in [0.0, 1.0]
    - Ensure `InterestDimension.weight` is in [0.0, 1.0]
    - _Requirements: 1.1, 1.3, 1.4, 8.1, 8.2_

  - [x] 1.2 Write property test for serialization round-trip
    - **Property 28: Serialization round-trip**
    - **Validates: Requirements 8.1, 8.2, 8.3**

  - [x] 1.3 Write property tests for parser error handling
    - **Property 29: Parser rejects missing required fields**
    - **Validates: Requirements 8.4**
    - **Property 30: Parser rejects invalid field types**
    - **Validates: Requirements 8.5**

- [x] 2. Implement `StakeholderRegistry` in `memory/stakeholder.py`
  - [x] 2.1 Create `src/velaris_agent/memory/stakeholder.py` with `StakeholderRegistry` class
    - Implement in-memory dict storage keyed by `(stakeholder_id, scenario)`
    - Implement `register()` with validation, duplicate check, and persistence
    - Implement `get()`, `update()` (version increment + field merge), `remove()` (soft-delete with active map check)
    - Implement `list_active()` with scenario and optional role filtering
    - Implement `_validate_stakeholder()`, `_check_duplicate()`, `_check_relationship_refs()`, `_check_in_use()`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 2.2 Write property tests for StakeholderRegistry
    - **Property 1: Stakeholder structural completeness**
    - **Validates: Requirements 1.1**
    - **Property 2: Relationship stakeholder requires exactly two references**
    - **Validates: Requirements 1.2**
    - **Property 3: Stakeholder field validation invariants**
    - **Validates: Requirements 1.3, 1.4**
    - **Property 4: Duplicate stakeholder rejection**
    - **Validates: Requirements 1.5**
    - **Property 5: Register then retrieve round-trip**
    - **Validates: Requirements 2.1**
    - **Property 6: Update increments version and merges fields**
    - **Validates: Requirements 2.2**
    - **Property 7: Soft-delete preserves record**
    - **Validates: Requirements 2.3**
    - **Property 8: List filtering correctness**
    - **Validates: Requirements 2.4**
    - **Property 9: Referential integrity on remove**
    - **Validates: Requirements 2.5**

  - [x] 2.3 Write unit tests for StakeholderRegistry CRUD
    - Create `tests/test_memory/test_stakeholder.py`
    - Test register known stakeholder and verify fields
    - Test relationship stakeholder with missing refs raises ValueError
    - Test duplicate id+scenario raises ValueError
    - Test update increments version
    - Test remove sets active=False
    - Test list_active filters by scenario and role
    - _Requirements: 1.1, 1.2, 1.5, 2.1, 2.2, 2.3, 2.4, 2.5_

- [x] 3. Checkpoint - Ensure registry tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement `StakeholderMapBuilder` in `memory/stakeholder_map.py`
  - [x] 4.1 Create `src/velaris_agent/memory/stakeholder_map.py` with `StakeholderMapBuilder` class
    - Implement `build(scenario)` that retrieves active stakeholders from registry and computes pairwise alignment matrix
    - Implement `compute_pairwise_alignment(a, b)` using the design's algorithm: shared dims, direction_match * 0.6 + weight_similarity * 0.4, influence_factor weighting
    - Handle edge case: fewer than 2 stakeholders returns valid map with empty alignment matrix
    - Handle edge case: no shared dimensions returns neutral score 0.5
    - Implement `export_as_alignment_report()` for backward-compatible two-party AlignmentReport extraction
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 9.4_

  - [x] 4.2 Write property tests for StakeholderMapBuilder
    - **Property 10: Map includes all active stakeholders**
    - **Validates: Requirements 3.1**
    - **Property 11: Pairwise alignment count**
    - **Validates: Requirements 3.2**
    - **Property 12: Classification consistency with score**
    - **Validates: Requirements 3.3**
    - **Property 13: Map traceability fields**
    - **Validates: Requirements 3.5**
    - **Property 34: Two-party export produces valid AlignmentReport**
    - **Validates: Requirements 9.4**

  - [x] 4.3 Write unit tests for StakeholderMapBuilder
    - Create `tests/test_memory/test_stakeholder_map.py`
    - Test build with 0 stakeholders, 1 stakeholder, 2+ stakeholders
    - Test pairwise alignment with identical stakeholders (score near 1.0)
    - Test pairwise alignment with opposing directions (score near 0.0)
    - Test classification thresholds at boundaries (0.3, 0.7)
    - Test export_as_alignment_report produces valid AlignmentReport
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 9.4_

- [x] 5. Implement `ConflictDetectionEngine` in `memory/conflict_engine.py`
  - [x] 5.1 Create `src/velaris_agent/memory/conflict_engine.py` with `ConflictDetectionEngine` class
    - Implement `detect(map_model)` that identifies direction conflicts and weight conflicts
    - Direction conflict: opposite PreferenceDirection on same dimension, severity = influence_A * influence_B
    - Weight conflict: same direction but weight diff > 0.3, severity = influence_A * influence_B * abs(weight_A - weight_B)
    - Clamp severity to [0.0, 1.0]
    - Return conflicts sorted by severity descending
    - Return empty list when no conflicts found
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x] 5.2 Write property tests for ConflictDetectionEngine
    - **Property 14: Direction conflict detection completeness**
    - **Validates: Requirements 4.1**
    - **Property 15: Weight conflict detection completeness**
    - **Validates: Requirements 4.2**
    - **Property 16: Conflict severity range and formula**
    - **Validates: Requirements 4.3**
    - **Property 17: Conflicts sorted by severity descending**
    - **Validates: Requirements 4.4**

- [x] 6. Implement `NegotiationStrategy` in `memory/negotiation.py`
  - [x] 6.1 Create `src/velaris_agent/memory/negotiation.py` with `NegotiationStrategy` class
    - Implement `generate(conflicts, map_model, org_policy)` producing one NegotiationProposal per conflicting dimension
    - Implement inverse-influence concession formula: lower influence concedes more
    - Clamp compromise_weight between min and max weights of conflicting parties
    - Compute feasibility score as 1.0 - (total_concession / max_possible_concession), clamped to [0, 1]
    - Handle hard constraints from OrgPolicy: set non_negotiable=True, constraint holder concession = 0
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [x] 6.2 Write property tests for NegotiationStrategy
    - **Property 18: One proposal per conflicting dimension**
    - **Validates: Requirements 5.1**
    - **Property 19: Lower influence concedes more**
    - **Validates: Requirements 5.2**
    - **Property 20: Negotiation proposal invariants**
    - **Validates: Requirements 5.3, 5.4**
    - **Property 21: Hard constraint non-negotiability**
    - **Validates: Requirements 5.5**

  - [x] 6.3 Write unit tests for NegotiationStrategy
    - Create `tests/test_memory/test_negotiation.py`
    - Test proposal generation with known conflict values
    - Test concession proportionality with asymmetric influence weights
    - Test hard constraint dimension produces non_negotiable=True
    - Test feasibility score range
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [x] 7. Checkpoint - Ensure core module tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Integrate stakeholder context into `biz/engine.py`
  - [x] 8.1 Add optional `stakeholder_map` parameter to `build_capability_plan()` in `src/velaris_agent/biz/engine.py`
    - Add `stakeholder_map: StakeholderMapModel | None = None` parameter
    - Implement `_build_stakeholder_context(stakeholder_map)` helper to produce StakeholderContext
    - Implement `_merge_stakeholder_weights(decision_weights, stakeholder_map)` helper to average stakeholder influence weights with scenario weights
    - When stakeholder_map is provided, inject `stakeholder_context` and merged weights into the plan
    - When stakeholder_map is None, preserve existing behavior unchanged
    - Append warning strings to explanation when conflicts have severity > 0.5
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x] 8.2 Write property tests for engine integration
    - **Property 22: Stakeholder weight merge affects output**
    - **Validates: Requirements 6.2**
    - **Property 23: High-severity conflicts produce warnings**
    - **Validates: Requirements 6.4**
    - **Property 24: No stakeholder map preserves existing behavior**
    - **Validates: Requirements 6.5**

- [x] 9. Implement `DecisionCurveTracker` in `memory/stakeholder.py` or a dedicated module
  - [x] 9.1 Add `DecisionCurveTracker` class to `src/velaris_agent/memory/stakeholder.py`
    - Implement `__init__(memory, registry)` with DecisionMemory and StakeholderRegistry dependencies
    - Implement `update(record, map_model)` to create/update DecisionCurvePoint per stakeholder
    - Implement `get_curve(stakeholder_id, scenario, window_days=30)` returning time-ordered list of DecisionCurvePoints
    - Implement `detect_trends(stakeholder_a_id, stakeholder_b_id, scenario)` returning "convergence", "divergence", or "stable"
    - Compute per-stakeholder metrics: decision_count, acceptance_rate, bias_count, weight_stability
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [x] 9.2 Write property tests for DecisionCurveTracker
    - **Property 25: Per-stakeholder curve point completeness**
    - **Validates: Requirements 7.1, 7.2**
    - **Property 26: Decision curve time ordering**
    - **Validates: Requirements 7.4**
    - **Property 27: Convergence and divergence trend detection**
    - **Validates: Requirements 7.5**

- [x] 10. Add migration helpers and backward compatibility
  - [x] 10.1 Add `from_user_preferences()` and `from_org_policy()` to `StakeholderRegistry`
    - `from_user_preferences(prefs)`: map UserPreferences.weights → InterestDimension list (all higher_is_better), confidence → uniform influence weight
    - `from_org_policy(policy)`: map OrgPolicy.weights → InterestDimension list, constraints keys → non-negotiable dimensions
    - _Requirements: 9.1, 9.2_

  - [x] 10.2 Verify `PreferenceLearner.compute_alignment()` backward compatibility
    - Ensure existing two-parameter signature (user_id, org_policy) still returns valid AlignmentReport with all fields
    - Ensure old DecisionRecords without stakeholder_context in env_snapshot load without error
    - _Requirements: 9.3, 9.5_

  - [x] 10.3 Write property tests for migration helpers
    - **Property 31: UserPreferences migration preserves weights**
    - **Validates: Requirements 9.1**
    - **Property 32: OrgPolicy migration preserves weights and constraints**
    - **Validates: Requirements 9.2**
    - **Property 33: compute_alignment backward compatibility**
    - **Validates: Requirements 9.3**

- [x] 11. Create Hypothesis strategies and property test file
  - [x] 11.1 Create `tests/test_memory/test_stakeholder_properties.py` with shared Hypothesis strategies
    - Define composite strategies for generating valid Stakeholder, InterestDimension, StakeholderMapModel, UserPreferences, OrgPolicy objects
    - Ensure relationship stakeholders reference existing user+org stakeholders in generated data
    - Configure `@settings(max_examples=100)` for all property tests
    - Wire all 34 property tests (Properties 1–34) into this file
    - _Requirements: 1.1–9.5 (all)_

- [x] 12. Create end-to-end integration tests
  - [x] 12.1 Write integration test for full stakeholder flow
    - Create `tests/test_memory/test_stakeholder_integration.py`
    - Test full flow: register stakeholders → build map → detect conflicts → generate negotiation → inject into engine → update curve tracker
    - Test backward compatibility: load old DecisionRecord, call existing compute_alignment() signature
    - Test edge cases: 0 stakeholders, 1 stakeholder, relationship with missing refs
    - _Requirements: 1.1–9.5 (all)_

- [x] 13. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design (34 total)
- Unit tests validate specific examples and edge cases
- All property tests go in `tests/test_memory/test_stakeholder_properties.py`
- All new modules are under `src/velaris_agent/memory/`
- Integration changes to `biz/engine.py` are additive only (new optional parameter)
