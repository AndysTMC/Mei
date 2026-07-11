# Mei Implementation Plan

This checklist tracks the current remediation pass so progress can be resumed safely if interrupted.

## Requested UI Improvements

- [x] Remove the old audit tracker file.
- [x] Smooth the small-popup to big-popup transition with long responses.
- [x] Make response details scrollable with a bounded height.
- [x] Preserve the user's response scroll position while streaming.
- [x] Keep the big popup reopenable after outside-click close during streaming.
- [x] Show the panel Stop control only while streaming in the small popup.
- [x] Hide the Stop control and panel activity animation while the big popup is open.
- [x] Show the existing panel activity animation while streaming and the popup is closed.

## Codebase Review And Cleanup

- [x] Re-review source, schemas, scripts, docs, packaging, and generated build drift.
- [x] Implement only critical or low-risk quality fixes needed after the review.
- [x] Remove dead code or duplication where it is clearly safe.
- [x] Improve documentation to match the current project behavior.

## Validation

- [x] Run available automated tests.
- [x] Run type checking.
- [x] Run linting.
- [x] Run formatting checks.
- [x] Run the production build.
- [x] Run dependency metadata and vulnerability checks.
- [x] Document any runtime checks that cannot be completed in this environment.

Validation completed:

- `npm test` passed: 29 tests across 7 test files.
- `npm run typecheck` passed.
- `npm run lint` passed.
- `node scripts/check-format.js` passed.
- `npm run build` passed.
- `npm ls --depth=0` passed.
- `npm audit --json` reported 0 vulnerabilities.
- `npm run smoke:providers` ran and skipped live provider checks because no provider API credentials were present.

Runtime limitation:

- Interactive GNOME Shell UI smoke testing was not run in this non-interactive pass; the popup animation and streaming interaction changes should be verified manually in Shell.

## Completion

- [x] Review the final diff for unintended behavior changes.
- [x] Create one comprehensive commit containing all changes since the previous commit.
