# Changelog

All notable changes to this repository will be documented here.

## [Unreleased]

### Added

- detailed idempotency guidance for `X-GitHub-Delivery`, including claim/process/complete-fail flow, leases, retries and failure windows.
- webhook receiver threat model covering trust boundaries, replay, business authorization, resource exhaustion, secret handling, logging, least privilege and incident response.
- PHP and Node.js regression coverage for empty secrets, wrong signature algorithms and malformed SHA-256 signature headers.

### Changed

- GitHub Actions test workflow is manual-only while repository checks are run locally to control CI consumption.

## [0.1.0] - 2026-08-07

### Added

- initial public webhook signature validation guide;
- PHP HMAC SHA-256 example;
- Node.js HMAC SHA-256 example;
- tests for valid, invalid and tampered payload signatures;
- defense-in-depth checklist;
- security policy, contribution guide and code of conduct;
- MIT license.
