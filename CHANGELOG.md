# UI Consolidation Release

- Replaced the accumulated patch stylesheet with five scoped CSS modules.
- Unified mobile table scrolling for events, feedback, and member requests.
- Rebuilt leader attendance mobile rows for compact monitoring while preserving update time.
- Added immediate `updated_at` refresh after leader saves attendance.
- Unified public and leader party boards around readable 5 x 6 grids with local horizontal scrolling.
- Replaced `window.prompt` personal-note editing with a Bootstrap modal.
- Reduced leader page hero size into compact workspace headers.
- Kept database models and migrations unchanged.
- Preserved original party-board class colors and note indicators.

# BangCheck Jade Mist mobile/UX polish

- Removed class image icons from runtime UI to reduce load and avoid broken icon states.
- Replaced brand image with robust text mark fallback.
- Removed redundant brand/guild subtitle lines and Django Admin rail link.
- Improved leader attendance mobile layout via card-style table rows.
- Party board slots now hide slot numbers; assigned member chips fill the whole slot.
- Simplified check-in action buttons to only 'Tham gia' and 'Không tham gia'.


## Latest cleanup / deploy update

Changed:
- Removed public/member attendance reason input. Check-in now only has `Tham gia` and `Không tham gia`.
- Removed attendance note from leader dashboard, CSV export, and admin main attendance form.
- Added migration `0004_clear_attendance_note` to clear old check-in notes.
- Kept strategy/team notes for squad planning.
- Kept public squad board and mobile horizontal scrolling.
- Added env-based settings for easier deploy to PythonAnywhere/Render/Koyeb/Railway-like hosting.
- Added `Procfile`, `.env.example`, and `README_DEPLOY.md`.
- Removed generated `__pycache__` files from packaged zip.
- Changed logout link to POST form for Django 5 compatibility.

Notes:
- `Attendance.note` remains as a legacy DB field for migration compatibility but is no longer used by UI/export/admin flow.

# Changelog – BangCheck

## [1.0.0] – MVP Initial Release

### Added

**Models**
- `Member`: display_name, search_name (auto-normalize), class_name, role, team, note, active
- `WarEvent`: title, event_date, deadline_at, status (draft/open/closed/archived), is_current
- `Attendance`: war_event + member (UniqueConstraint), status 4 loại, note, device_id, source
- `AttendanceAuditLog`: ghi lịch sử thay đổi, actor_type (member/admin/system)
- `MemberRequest`: yêu cầu thêm thành viên, status (pending/approved/rejected)

**Business Rules implemented**
- BR1/BR2: Attendance lưu bằng member_id (ForeignKey), không lưu text name
- BR3: Search text chỉ dùng để lọc client-side (JavaScript), submit dùng member_id
- BR4/BR5: Member chỉ tạo được qua Admin hoặc approve MemberRequest
- BR6: UniqueConstraint (war_event, member) đảm bảo 1 record/member/event
- BR7: Audit log tạo khi member đổi trạng thái (actor_type=member)
- BR8: Audit log tạo khi admin sửa (actor_type=admin)
- BR9/BR10: Cookie là UX convenience, invalid cookie → chọn lại từ danh sách
- BR11: Public result chỉ show display_name, class, role, team, note
- BR12: Leader có thể sửa nhanh từ dashboard

**Views & URLs**
- `GET /checkin/` – auto detect cookie, show select hoặc status page
- `POST /checkin/select-member/` – validate + set cookie
- `POST /checkin/submit/` – create/update attendance + audit log
- `POST /checkin/clear-member/` – xóa cookie
- `GET/POST /member-request/` – gửi yêu cầu thêm thành viên
- `GET /public/result/` – kết quả công khai, không cần login
- `GET /leader/dashboard/` – dashboard với filter, summary, inline edit
- `POST /leader/attendance/<id>/update/` – admin update, returns JSON
- `POST /leader/attendance/set/` – admin create/update by member_id, returns JSON
- `GET /leader/export-csv/` – xuất CSV có BOM (Excel-friendly)
- `GET /leader/copy-summary/` – plain text để copy
- `GET /leader/events/` – danh sách WarEvent, set current
- `POST /leader/events/<id>/set-current/` – set current event
- `GET /leader/member-requests/` – xem yêu cầu thành viên
- `POST /leader/member-requests/<id>/approve/` – duyệt, tạo Member
- `POST /leader/member-requests/<id>/reject/` – từ chối

**Templates (Django + Bootstrap 5.3 CDN)**
- `base.html` – navbar, messages, blocks
- `checkin_select.html` – search member với client-side JS filtering
- `checkin_status.html` – 4 status buttons lớn, mobile-first
- `member_request.html` – form yêu cầu thành viên
- `member_request_done.html` – xác nhận
- `public_result.html` – kết quả chia nhóm theo status
- `leader_dashboard.html` – summary cards, filter bar, table inline edit, AJAX save
- `leader_events.html` – list + set current
- `leader_member_requests.html` – approve/reject
- `registration/login.html` – login page override

**Static**
- `static/css/style.css` – mobile-first, 4 status colors, table row colors

**Management command**
- `seed_demo_data` – tạo 20 members (3 đội) + 1 WarEvent + attendance mẫu
- Hỗ trợ flag `--reset`

**Admin**
- Đầy đủ cho tất cả 5 models
- Inline AuditLog trong Attendance admin
- Bulk action "approve_requests" trong MemberRequest admin

### Technical decisions
- Dùng TextChoices cho tất cả enum fields (type-safe, readable)
- `normalize_search_name()` xử lý dấu tiếng Việt kể cả ký tự đ/Đ đặc biệt
- `WarEvent.save()` tự unset is_current cho các event khác
- `Member.save()` tự generate search_name từ display_name
- Inline edit dashboard dùng Fetch API + CSRF meta tag (không cần form HTML)
- Export CSV có BOM `\ufeff` để Excel đọc UTF-8 đúng
- SQLite cho dev, cấu trúc sẵn sàng đổi PostgreSQL

---

## Planned: [1.1.0] – Next Steps

- [ ] Thêm WarEvent creation form trong leader area (không phụ thuộc Admin)
- [ ] Thêm thống kê lịch sử: tỉ lệ tham gia theo tuần, theo member
- [ ] Thêm QR code link đến /checkin/ để chia sẻ
- [ ] Thêm thông báo (Telegram bot webhook) khi leader mở event
- [ ] Timezone display chuẩn hóa trong templates
- [ ] Bulk import members từ CSV
- [ ] Xuất kết quả định dạng table ảnh (screenshot)
- [ ] Docker Compose setup cho deploy dễ dàng hơn
- [ ] Rate limiting cho /checkin/submit/ (chống spam)
- [ ] Đổi SQLite → PostgreSQL + deploy lên Railway / Render

## Update – Party board & Nghịch Thủy Hàn class cleanup

- Added Nghịch Thủy Hàn class choices: Thiết Y, Huyết Hà, Toái Mộng, Thần Tương, Cửu Linh, Long Ngâm, Tố Vấn.
- Added optional class branch/variant field for Thiết Y/Tố Vấn style modes: Phá, Ngự, Thiên Vấn, Tố Tâm.
- Improved member search normalization to handle Vietnamese accents, mixed case, spaces, and compact forms such as `Minh ABC` vs `MinhABC` while still saving attendance by `member_id` only.
- Added leader party-board page at `/leader/party-board/`.
- Added drag/drop team planning with 3 boards:
  - Team thủ: 12 slots
  - Team công: 18 slots
  - Team mid: 30 slots
- Added class-colored draggable member chips with class icons.
- Added `battle_team` and `battle_position` fields on Member to persist team layout.
- Updated export CSV to include class variant and party-board placement.
- Updated demo seed data to use Nghịch Thủy Hàn classes.

## UX Fix – Party board drag/drop no reload
- Removed automatic page reload after dragging a member into a party slot.
- Drag/drop now saves via AJAX and updates the DOM in place.
- Active party tab is preserved in localStorage when the page is manually refreshed.
- Team counts and unassigned pool count now update without reloading.

## 2026-05-22 - Party board UX/class variant cleanup

### Changed
- Party board capacity is now 30 slots for every tab: Team thủ, Team công, Team mid.
- Drag-and-drop party board keeps the current tab and does not reload after moving members.
- Removed temporary explanatory text from party board UI.
- Phái are now distinguished by color only; class icons are no longer shown.
- Variant/status icons are shown only for special systems:
  - Thiết Y / Ngự: 🛡️
  - Thiết Y / Phá: 👊
  - Tố Vấn / Thiên Vấn: 🦋
  - Tố Vấn / Tố Tâm: 🌸
- Role is hidden from main admin/member request/dashboard UI because phái/hệ already implies role for this use case.

### Fixed
- `class_variant` is now restricted logically:
  - Thiết Y can only use Ngự or Phá.
  - Tố Vấn can only use Thiên Vấn or Tố Tâm.
  - Other phái automatically clear variant on save.
- Admin and public member-request forms now disable/filter the variant dropdown based on selected phái.
- Export CSV no longer includes the unused Role column.

### Notes
- The `role` database field is kept for compatibility; no migration is required for hiding it from UI.
- No new database migration is required for this patch.

## Latest squad/attendance update

### Changed
- Check-in statuses reduced to two options: `Tham gia` and `Không tham gia`.
- Removed `Chưa chắc` and `Đến muộn` from active UI flows; old records are migrated to `Tham gia`.
- Squad placement is now stored on `Attendance`, not `Member`, so leader can arrange teams differently for each event/week.
- Added fourth squad tab: `Team vật tư`, also 30 slots.
- Added per-team tactical notes stored on `WarEvent.team_notes` and shown publicly as read-only.
- Added per-member squad skill note stored on `Attendance.strategy_note` and shown on squad chips.
- Public result page now uses compact attendance pills and read-only squad view.
- Member fixed team is hidden from main UI because weekly squad assignment is leader/event-specific.

### Migration
- Added `WarEvent.team_notes`.
- Added `Attendance.strategy_note`, `Attendance.battle_team`, and `Attendance.battle_position`.
- Copied previous Member party positions into current event attendance where possible.


## Latest update

### Changed
- Squad board layout changed to 30 slots as 5 columns x 6 players, matching the game party format where each small party is one vertical column of 6.
- Removed class/variant text under names in squad chips; class is now represented by color and variant by icon only.
- Public compact attendance list now displays smaller name-only pills while still keeping Tham gia / Không tham gia / Chưa điểm danh groups.

### Kept
- Public result page still includes read-only squad board.
- Public result still shows chưa điểm danh/no response members.
- Team-level notes and per-player strategy notes remain visible on public result.
- Mobile scale uses horizontal scroll for squad board.

## Team note per tab verification update
- Moved leader team note editor from the shared left pool to each squad tab.
- Each tab now has its own note box: Team thủ, Team công, Team mid, Team vật tư.
- Public result already renders the matching note inside each read-only squad tab.


## Mobile UX patch

Changed:
- Added mobile/touch fallback for leader party board: tap a member chip, then tap a squad cell/pool to move it.
- Kept desktop drag-and-drop behavior unchanged.
- Made leader unassigned pool compact on mobile using a 2-column grid instead of full-width long chips.
- Reduced mobile squad chip font sizes and increased note line-height/padding so descenders in letters such as g/q are not clipped.
- Improved mobile navbar/buttons/tabs wrapping and horizontal scroll for public/leader squad boards.
- Kept desktop layout/scale unchanged as much as possible.

## Feedback sau bang chiến

Added:
- Public/member feedback text page at `/feedback/`.
- Feedback automatically attaches to the latest war event that has reached battle time.
- `WarEvent.battle_start_at` for exact feedback opening time; fallback is 19:00 on `event_date`.
- One feedback per browser/device token per event; reopening `/feedback/` on the same browser lets the user edit/update previous feedback.
- Leader feedback list at `/leader/feedback/` and event detail at `/leader/feedback/<event_id>/`.
- Leader view shows event, content, created time, updated time only.
- Hidden technical audit hashes are stored in DB but not shown in leader UI.
- Management command `export_feedback_audit` for server owner/dev shell export.
- Lightweight profanity filter for explicit Vietnamese/English words.

Changed:
- Check-in and public result pages show feedback button when feedback is open.
- Attendance submit now stores a soft browser/device cookie for future audit/feedback UX.

Migration:
- `0005_feedback.py` adds `WarEvent.battle_start_at` and `BattleFeedback`.

## Scrim + Mobile Note Popup Update

Added:
- Added event type support: `Bang chiến` (`war`) and `Scrim` (`scrim`).
- Added separate current event per event type. Creating/current-setting Scrim no longer overrides current Bang chiến.
- Added `/checkin/` activity selection page.
- Added `/checkin/war/` and `/checkin/scrim/` for separate check-in flows.
- Added `/public/result/war/` and `/public/result/scrim/` for separate public result pages.
- Added leader dashboard routes for both flows: `/leader/dashboard/war/` and `/leader/dashboard/scrim/`.
- Added event type filter/list display in event management/admin.
- Added Scrim demo event in seed command.
- Added mobile-only strategy note popup/bottom sheet in public squad view.

Changed:
- Party board remains Bang chiến only.
- Feedback remains Bang chiến only.
- Public Scrim result only shows Tham gia / Không tham gia / Chưa điểm danh, no squad.
- Mobile squad chips show compact `Note: ...`; tapping a noted member opens full note popup.
- Existing events are migrated as Bang chiến by default.


## Feedback profanity filter disabled

Changed:
- Disabled banned-word/profanity filter for feedback submission.
- Feedback now only validates non-empty content and trims content to 2000 characters.
- This avoids false positives for Vietnamese/English text and keeps anonymous feedback easy to submit.

## Clean Operations UI Pass

- Refined the previous Clean Guild OS pass into a more professional operations-console UI.
- Kept database schema, models, migrations, and existing data flow unchanged.
- Reduced visual bulk: lighter shadows, smaller radii, calmer typography, cleaner table spacing.
- Preserved original-leaning party-board class colors for member chips only.
- Tightened leader dashboard, public result, feedback, scrim/events, member request, and check-in surfaces through shared CSS tokens.
- Shortened dashboard copy action labels and improved table cell padding for readability.



## Operations UI mobile regression fix

- Fixed leader dashboard status select clipping.
- Restored original-style mobile public result behavior: page does not overflow; party board scrolls horizontally inside its panel.
- Kept database/models/migrations unchanged.


## Jade Mist Asset Integration Final
- Added user-generated Jade Mist assets to static/img and wired them into UI.
- Rebuilt CSS around actual background, ornament, brand, crest and class icon assets.
- Preserved database schema, models and migrations.
- Preserved party board 5 columns x 6 slots and exact class color identity.
- Improved mobile containment for dashboard, result and party board.


## Layout spacing correction
- Fixed check-in/search panel padding so headings and inputs no longer stick to the card border.
- Adjusted hero action alignment and mobile spacing.


## Party board density fix
- Party page leader nav is horizontal to free width.
- Pool is compact like original tool.
- Board is the primary region and keeps 5x6.
- Placed member chips fill entire slots.


## Public mobile result board and CTA alignment fix
- Fixed public result CTA alignment and consistent button sizing.
- Reduced mobile public metrics density so counts are compact.
- Restored horizontal-scroll public party board on mobile with readable 5-column slots.
- Compacted public squad tabs and team note so board/member names are the focus.


## Party tabs + Django Admin link fix
- Giữ tab Thủ/Công/Mid/Vật tư dạng hàng ngang, không bị rule filter pill mobile ép thành cột dọc.
- Thêm lại link Django Admin trong dropdown Leader và leader rail.


## Final UX review patch
- Replaced metric top rings with semantic green/red/gray/jade surfaces.
- Restored the public Feedback action for war result pages.
- Hid the strategy-note sheet until a member note is opened.
- Fixed leader attendance status select clipping on narrow mobile screens.
- Preserved class colors in public attendance lists.


## Feedback action placement fix
- Added `Gửi feedback` directly below `Xem kết quả` on the check-in home page.
- Added the same stacked action pattern to Bang chiến member selection and status pages.
- Removed the duplicate feedback link from the bottom of the member search panel.
- Kept Scrim pages free of the Bang chiến feedback action.
