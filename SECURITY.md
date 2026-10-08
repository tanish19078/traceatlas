# Source and data boundaries

The initial connector only requests the fixed HTTPS Brønnøysundregistrene entity
endpoint. User-provided URLs are never fetched, redirects are disabled, response
sizes are bounded, and no credentials are needed. A registry website field is
stored as a candidate, never treated as evidence that all domain content belongs
to that entity. Search snippets cannot support published claims.

Collected data and immutable source bodies belong in ignored `runs/` directories.
Do not commit personal data, API credentials or local databases. The viewer escapes
all source values and only makes HTTPS evidence URLs clickable. It has no remote
scripts or analytics. Official public data still carries attribution and reuse
conditions; document the applicable licence for every future connector.

External discovery is a later milestone. Before enabling a connector, record its
access rights, robots policy, permitted endpoints, request limits and exact-entity
publication rules. Denied access must be represented as blocked, not bypassed.

Report sensitive security problems privately to the repository owner rather than
including secrets or exploitable private-data examples in a public issue.
