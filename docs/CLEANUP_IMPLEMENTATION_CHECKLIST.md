# Transcript Cleanup Implementation Checklist

This checklist helps track implementation progress for the transcript cleanup module. Check off items as they are completed.

## Phase 1: Core Functionality (Weeks 1-2)

### Module Structure
- [ ] Create `worker/cleanup/` directory
- [ ] Create `worker/cleanup/__init__.py` with main entry points
- [ ] Create `worker/cleanup/normalizer.py` for text normalization
- [ ] Create `worker/cleanup/punctuation.py` for punctuation restoration
- [ ] Create `worker/cleanup/filler.py` for filler word removal
- [ ] Create `worker/cleanup/segmentation.py` for segmentation logic
- [ ] Create `worker/cleanup/formatter.py` for output formatting

### Text Normalization (normalizer.py)
- [ ] Implement `normalize_whitespace(text: str) -> str`
- [ ] Implement `normalize_unicode(text: str) -> str`
- [ ] Implement `remove_special_tokens(text: str, preserve_sound_events: bool) -> str`
- [ ] Implement `detect_hallucination(segments: list) -> list`
- [ ] Add Unicode normalization with NFC
- [ ] Handle zero-width characters
- [ ] Support line ending normalization

### Punctuation Restoration (punctuation.py)
- [ ] Implement `add_sentence_punctuation(text: str, is_question: bool) -> str`
- [ ] Implement `add_internal_punctuation(text: str, pause_ms: int) -> str`
- [ ] Implement `capitalize_sentences(text: str) -> str`
- [ ] Implement `fix_all_caps(text: str, min_length: int) -> str`
- [ ] Add question detection logic
- [ ] Add abbreviation dictionary
- [ ] Support "I" pronoun capitalization

### Filler Removal (filler.py)
- [ ] Implement `remove_fillers(text: str, level: int, language: str) -> str`
- [ ] Add English filler patterns (levels 1-3)
- [ ] Add Spanish filler patterns
- [ ] Add French filler patterns
- [ ] Add German filler patterns
- [ ] Implement stutter removal (level 2+)
- [ ] Test each filler level independently

### Segmentation (segmentation.py)
- [ ] Implement `split_into_sentences(text: str) -> list[str]`
- [ ] Implement `merge_segments_by_timing(segments: list, max_gap_ms: int) -> list`
- [ ] Implement `group_into_paragraphs(segments: list, max_sentences: int) -> list`
- [ ] Add abbreviation handling in sentence splitting
- [ ] Support minimum segment length enforcement
- [ ] Preserve speaker boundaries during merge

### Formatting (formatter.py)
- [ ] Implement `format_with_speakers(segments: list, format: str) -> str`
- [ ] Support "inline" speaker format
- [ ] Support "dialogue" speaker format
- [ ] Support "structured" speaker format (return JSON)
- [ ] Rename speaker labels (SPEAKER_00 → Speaker 1)

### Main Entry Point (__init__.py)
- [ ] Implement `apply_cleanup(segments: list, config: CleanupConfig) -> list`
- [ ] Integrate all cleanup functions in pipeline
- [ ] Track transformation statistics
- [ ] Return `CleanedSegment` objects
- [ ] Handle errors gracefully

### Unit Tests
- [ ] Create `tests/unit/test_normalizer.py`
  - [ ] Test whitespace normalization (Example 1)
  - [ ] Test special token removal (Example 2)
  - [ ] Test Unicode normalization (Example 3)
- [ ] Create `tests/unit/test_punctuation.py`
  - [ ] Test sentence punctuation (Example 4)
  - [ ] Test question detection (Example 5)
  - [ ] Test capitalization (Example 6)
  - [ ] Test all-caps fix (Example 7)
- [ ] Create `tests/unit/test_filler.py`
  - [ ] Test level 1 removal (Example 8)
  - [ ] Test level 2 removal (Example 9)
  - [ ] Test level 3 removal (Example 10)
- [ ] Create `tests/unit/test_segmentation.py`
  - [ ] Test sentence splitting (Example 11)
  - [ ] Test segment merging (Example 12)
  - [ ] Test hallucination detection (Example 13)
- [ ] Create `tests/unit/test_formatter.py`
  - [ ] Test structured format (Example 14)
  - [ ] Test dialogue format (Example 15)
  - [ ] Test inline format (Example 16)

### Edge Cases
- [ ] Test abbreviations handling (Example 17)
- [ ] Test mixed language (Example 19)
- [ ] Test URLs and technical terms (Example 20)
- [ ] Test empty segments (Example 21)

### API Integration
- [ ] Extend `GET /videos/{video_id}/transcript` endpoint
- [ ] Add `format` query parameter (raw/cleaned/formatted)
- [ ] Support on-demand cleanup computation
- [ ] Return `CleanedTranscriptResponse` schema
- [ ] Include cleanup statistics in response
- [ ] Add error handling for invalid configurations

### Integration Tests
- [ ] Create `tests/integration/test_cleanup_pipeline.py`
- [ ] Test with Fixture 1: YouTube tech talk
- [ ] Test with Fixture 2: Whisper hallucination
- [ ] Test with Fixture 3: Multi-speaker interview
- [ ] Test with Fixture 4: All-caps technical
- [ ] Test with Fixture 5: Heavy fillers
- [ ] Verify stats match expected values

### Documentation
- [ ] Add docstrings to all functions
- [ ] Create usage examples in code
- [ ] Update API documentation
- [ ] Add inline code comments for complex logic

---

## Phase 2: Profiles & Configuration (Week 3)

### Profile Implementation
- [ ] Create `app/cleanup_profiles.py`
- [ ] Define `CLEANUP_PROFILES` dictionary
- [ ] Implement "minimal" profile
- [ ] Implement "standard" profile (default)
- [ ] Implement "aggressive" profile
- [ ] Implement "youtube_captions" profile
- [ ] Implement "whisper_output" profile
- [ ] Implement "presentation" profile
- [ ] Implement "technical" profile
- [ ] Implement "accessibility" profile

### Profile API Endpoints
- [ ] Add `GET /cleanup/profiles` endpoint
- [ ] Add `GET /cleanup/profiles/{profile_name}` endpoint
- [ ] Add `POST /transcripts/{transcript_id}/cleanup` endpoint
- [ ] Support profile selection in cleanup calls
- [ ] Support profile overrides
- [ ] Validate profile names
- [ ] Return 404 for unknown profiles

### Profile Selection Logic
- [ ] Implement `get_cleanup_config(profile, overrides) -> CleanupConfig`
- [ ] Merge profile config with overrides
- [ ] Validate merged configuration
- [ ] Apply system defaults for missing values

### Profile Testing
- [ ] Test each profile with sample data
- [ ] Verify profile characteristics match spec
- [ ] Test profile overrides
- [ ] Test invalid profile names
- [ ] Benchmark each profile's performance

### Documentation Updates
- [ ] Add profile usage to API docs
- [ ] Create profile selection guide
- [ ] Add profile comparison table
- [ ] Document profile override mechanism

---

## Phase 3: Caching & Optimization (Week 4)

### Database Migration (Optional)
- [ ] Review migration `003_transcript_cleanup.py`
- [ ] Test migration on development database
- [ ] Test migration on staging database
- [ ] Verify indexes are created
- [ ] Test full-text search on cleaned text
- [ ] Test `cleaned_segments_view` view

### Caching Implementation
- [ ] Implement caching layer in API
- [ ] Cache default cleanup results in database
- [ ] Use hybrid approach (cache default, compute custom)
- [ ] Add Redis caching for computed results
- [ ] Implement cache key generation
- [ ] Set appropriate TTLs (1 hour for cleaned transcripts)

### Background Processing
- [ ] Add cleanup step to worker pipeline
- [ ] Apply default cleanup after transcription
- [ ] Save cleaned text to database
- [ ] Update `cleanup_applied` flag
- [ ] Track cleanup in worker metrics

### Cache Invalidation
- [ ] Invalidate cache when cleanup config changes
- [ ] Handle version upgrades gracefully
- [ ] Add cleanup re-processing API endpoint
- [ ] Support force refresh parameter

### Performance Optimization
- [ ] Profile cleanup operations
- [ ] Optimize regex patterns (compile once)
- [ ] Add batch processing for large transcripts
- [ ] Consider parallel processing for segments
- [ ] Optimize database queries
- [ ] Add query result caching

### Performance Testing
- [ ] Benchmark 1000 segments: target <500ms
- [ ] Benchmark 10,000 segments: target <5s
- [ ] Test API response time with caching
- [ ] Monitor memory usage
- [ ] Profile CPU usage
- [ ] Test concurrent cleanup operations

### Monitoring
- [ ] Add cleanup metrics to Prometheus
  - [ ] `cleanup_operations_total` counter
  - [ ] `cleanup_duration_seconds` histogram
  - [ ] `cleanup_cache_hits_total` counter
  - [ ] `cleanup_cache_misses_total` counter
- [ ] Add logging for cleanup operations
- [ ] Track cleanup errors
- [ ] Monitor cache hit rates

---

## Phase 4: Advanced Features (Week 5+)

### Model-Based Punctuation (Optional)
- [ ] Research suitable HuggingFace models
- [ ] Select model for English punctuation
- [ ] Create model loader in `punctuation.py`
- [ ] Add GPU acceleration support
- [ ] Implement model inference pipeline
- [ ] Add model caching/warmup
- [ ] Benchmark model vs rule-based
- [ ] Add model-based mode to config
- [ ] Test with various content types
- [ ] Document model setup and requirements

### Multi-Language Support
- [ ] Implement language detection integration
- [ ] Add Spanish cleanup rules
- [ ] Add French cleanup rules
- [ ] Add German cleanup rules
- [ ] Test with multi-language content
- [ ] Add language-specific test cases
- [ ] Document supported languages

### Enhanced Segmentation
- [ ] Improve sentence boundary detection
- [ ] Add paragraph grouping logic
- [ ] Implement topic-based segmentation
- [ ] Test with long-form content
- [ ] Add user configuration for paragraph length

### Additional Profiles
- [ ] Create "podcast" profile
- [ ] Create "interview" profile
- [ ] Create "lecture" profile
- [ ] Test new profiles with real data

---

## Validation & Release

### Code Quality
- [ ] Run linters (ruff, black, isort)
- [ ] Run type checker (mypy)
- [ ] Achieve >90% unit test coverage
- [ ] Achieve >80% integration test coverage
- [ ] Fix all compiler warnings
- [ ] Address all security scanner findings

### Documentation
- [ ] User guide created
- [ ] API documentation updated
- [ ] README updated with cleanup features
- [ ] Migration guide created
- [ ] Troubleshooting guide updated

### Performance Validation
- [ ] All benchmarks meet targets
- [ ] Memory usage within limits
- [ ] API response times acceptable
- [ ] No performance regression in existing features

### Security Review
- [ ] Input validation comprehensive
- [ ] No injection vulnerabilities
- [ ] Rate limiting implemented
- [ ] Audit logging in place
- [ ] No PII leakage in logs

### User Acceptance Testing
- [ ] Test with real YouTube transcripts
- [ ] Test with real Whisper transcripts
- [ ] Gather user feedback on cleanup quality
- [ ] Test all 8 profiles with users
- [ ] Validate against acceptance criteria

### Deployment
- [ ] Deploy to staging environment
- [ ] Run smoke tests on staging
- [ ] Perform load testing
- [ ] Monitor for errors/issues
- [ ] Deploy to production with feature flag
- [ ] Gradual rollout (10% → 50% → 100%)
- [ ] Monitor metrics and errors
- [ ] Collect user feedback

### Post-Release
- [ ] Monitor cleanup usage metrics
- [ ] Track error rates
- [ ] Gather user feedback
- [ ] Identify areas for improvement
- [ ] Plan Phase 5 enhancements

---

## Acceptance Criteria Verification

From the original issue, verify all criteria are met:

- [ ] ✅ Concrete, testable spec doc including examples and edge cases
- [ ] ✅ Agreed configuration and API proposal (including schemas)
- [ ] ✅ Text normalization works (whitespace, Unicode, special tokens)
- [ ] ✅ Sentence punctuation works (rule-based)
- [ ] ✅ Optional LLM model for punctuation available
- [ ] ✅ De-filler rules implemented
- [ ] ✅ Capitalization implemented
- [ ] ✅ Segmentation strategy works (sentence/phrase boundaries)
- [ ] ✅ Per-speaker formatting works
- [ ] ✅ Configuration flags functional
- [ ] ✅ API surface implemented
- [ ] ✅ Raw vs cleaned vs formatted modes work
- [ ] ✅ Implementation approach chosen (started simple with rules)
- [ ] ✅ Pluggable model for punctuation as enhancement

---

## Notes

- This checklist tracks implementation of the specification defined in `TRANSCRIPT_CLEANUP_SPEC.md`
- Check off items as they are completed
- Add notes for any deviations from the spec
- Update estimates as implementation progresses
- Link to relevant PRs for each phase

---

**Last Updated**: 2025-11-02  
**Status**: Specification Complete, Implementation Pending
