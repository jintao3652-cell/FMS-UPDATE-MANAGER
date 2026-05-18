# Backend SQL Safety Notes

All queries in `backup_auth/app/main.py` and `admin_panel/app/main.py` go
through SQLAlchemy ORM (`select(Model).where(...)`, `db.scalar`, `db.add`,
etc.) which is parameter-bound by default. **Do not** introduce raw SQL with
f-strings.

## Rules

1. Always prefer ORM expressions: `db.scalars(select(User).where(User.username == x))`.
2. If you must drop to raw SQL (migrations, ad-hoc admin tooling), use
   `sqlalchemy.text` with bound parameters:

   ```python
   from sqlalchemy import text
   db.execute(text("UPDATE users SET enabled = :v WHERE id = :id"), {"v": True, "id": user_id})
   ```

   **Never** do `text(f"... = {value} ...")` or string concatenation.

3. The `ensure_schema_compat()` helpers use `text(...)` to issue DDL. DDL
   strings here are static (no user input interpolated) — keep it that way.

4. Pydantic models on request bodies (`schemas.py`) provide an additional
   validation layer. Always go through the typed body parameter rather than
   reading raw `request.json()` for SQL-bound fields, except where the
   endpoint explicitly accepts free-form JSON (`archive_hashes`, etc.).

5. `LIKE` patterns built from user input must wrap with `%`, not be
   concatenated into the SQL: use `Column.like(f"%{q}%")` only after `q`
   is whitelisted/length-checked, since SQLAlchemy still parameter-binds
   the value but a malicious `%` in `q` could cause a denial-of-service
   pattern. Current `admin_logs` and `email_logs` endpoints already do
   `q.strip()` on the raw value — this is safe.

## Outbound HTML

`mailer.py` / inline `send_verification_email` build HTML with Python
f-strings. The values interpolated (verification code, cycle number) are
generated server-side from constrained alphabets, so HTML injection isn't
reachable from user input. If you ever start interpolating user-controlled
fields into the email HTML, run them through `html.escape()` first.
