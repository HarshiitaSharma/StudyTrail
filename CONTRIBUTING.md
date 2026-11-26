# Contributing

1. Pick an issue (see `ISSUES.md` for ideas), create a branch: `git checkout -b issue-12-edit-sessions`.
2. Set up: `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements-dev.txt`.
3. Make the change **and add a test**. Run `python -m pytest -q` before you push.
4. Open a pull request with `closes #12` in the description.

## Rules for this codebase
- Every query that touches user data must include `user_id = ?` from `g.user`. Add an isolation test for new endpoints.
- Never build SQL with string formatting of user input. Use `?` parameters.
- Never use `innerHTML` with data from the API. Use `textContent`.
- New write endpoints are protected automatically (CSRF + JSON); do not add exemptions without a reason.
- Business logic that does not need Flask or the database goes in `app/stats.py` style pure functions so it is easy to test.
