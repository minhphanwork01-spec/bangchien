# Final review notes

This package keeps the existing database schema and migrations unchanged.

Validated:
- `python manage.py check`
- Python compile
- Django template compile
- Public and leader route smoke tests with demo data
- Party board route, feedback route, member request route, admin route

Final UX fixes:
- Semantic status surfaces: joined green, absent red, no response gray.
- Removed decorative top rings from summary metrics.
- Restored the Feedback action on war public-result pages.
- Strategy-note sheet stays hidden until a note is opened.
- Mobile leader status select no longer truncates "Không tham gia".
- Public attendance names continue to use faction colors.
