# DisasterMesh Security Findings

## PostgreSQL 17

Image: postgres:17
Database version: 17.11

Docker Scout results:
- Critical: 4
- High: 34
- Medium: 31
- Low: 55

## Go-related vulnerabilities

Affected component:
- /usr/local/bin/gosu
- Go standard library 1.24.6

Assessment:
The Go findings originate from the gosu executable
used by PostgreSQL's container startup process.

Next action:
Perform reachability analysis using the gosu
maintainers' recommended vulnerability checker.

Status: Under investigation.
Not yet classified as fixed or false positive.

## Other findings

Debian zlib and libxml2 findings require separate
review for patched packages and runtime exposure.