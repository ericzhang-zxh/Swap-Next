# Population, inheritance and durable briefs implementation plan

Part 3 of the framework, with the owner's neutral-exploration rule. No real
experiments are included. Use the pinned OpenEvolve APIs, without LLM calls.

1. Implement `evolve/population.py`: immutable evidence history, current parent
   eligibility, derived ProgramDatabase, source-tree identity and per-case
   evidence. Admit only fast passes as new exploratory entries.
2. Separate advancement from exploratory admission. Check normalized improvement
   above calibrated primary noise, guards, exact source evidence and line anchor.
3. Render durable briefs with PromptSampler: sampled parent or baseline,
   inspirations, relevant failures, line history and remaining pools. Persist
   sampling sequence and permit only the recorded parent choice.
4. Extend controller creation with brief-bound parent selection. A child tree
   differs from its parent's; ancestry and cumulative baseline scope are checked.
   Record parent ID/commit and generation. Preserve baseline and anchor origins.
5. Connect workflow outcomes and next briefs to the population. Report parent
   deltas separately; invalidate failed/stale parents without deleting history.
6. Exercise the whole loop through guest-free fixtures, including restart,
   equivalent-tree refusal, neutral admission, progress evidence, invalidation
   and cross-campaign advancement refusal. Run all prescribed project checks.
