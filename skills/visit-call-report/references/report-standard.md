# Report standard

## Source and matching rules

Source priority: exact saved meeting record, current user notes, related same-customer initiative history, explicitly provided supplementary materials. Report discrepancies rather than silently choosing an incompatible value. A stale export is not newer than the meeting notes; state dates.

Inputter is `created_by`/입력자, not Owner(CE), Owner(Sales Rep) or attendee. Filter history before reading unrelated records.

An exact meeting requires matching customer/date and at least two corroborating fields: start time, location, internal attendees, customer/partner attendees, distinctive topic. Reuse its confirmed ID, Opportunity and end time, with a citation. Similar topics alone are insufficient.

For related history, compare customer aliases, initiative, solution and stage. Explain the connection with report ID/date and what was carried forward. If none is established, write `관련 기존 Visit/Call 리포트 미확인`.

Opportunity order: exact meeting → confirmed same initiative with cited prior record → ambiguous candidates marked `[확인 필요 — 후보: …]` → no applicable code: `신규 Deal 검토` and `신규 입력 필요`. Never invent a code or reuse one solely because the customer matches. `-`, `N/A`, `BD` and `account development` are not verified codes.

When only related history confirms the same existing Opportunity, use `기존` for 신규 Deal 여부 and explain the cited reuse. Do not reuse the previous meeting ID: a different meeting is a new report, even when the Opportunity is shared. If the deal status itself conflicts or is unclear, mark it `[확인 필요]` instead.

## Fields and output

Preserve the actual input/export header order and all extra fields. Without an export use this generic order:

ID; 신규 Deal 여부; 신규 Oppty #; 고객사명; 시작 일시; 종료 일시; 장소; 기술 담당자; 영업 담당자; 참석자(고객); 참석자(파트너); 참석자(내부); 지원 내용; 지원 내용 요약; Issue/Risk; Next Action; Next Action Target Date; 비고 사항; 입력자; 입력 시각.

If an Oracle export uses Owner(CE), Owner(Sales Rep), 참석자(오라클), preserve those names verbatim rather than changing the schema. Only the default template is vendor-neutral.

Output: title → complete field table → 지원 내용 (고객 현황/미팅 내용) → 지원 내용 요약 → Issue/Risk → Next Action → 참조 및 히스토리 연결 table. Escape Markdown table pipes and preserve multiline meaning. Unknown important facts use `[확인 필요]`; `-` only represents an explicitly empty source value.

Attribute interview/partner claims. Actions include owner and date only when known. Validate source fields appear once, reused opportunities have evidence, promises/completion are not invented, and saved Markdown matches displayed output.
