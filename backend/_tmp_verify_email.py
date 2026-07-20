import sys
sys.path.insert(0, '.')
import core.shared.workflow_notifications as wn

captured = []

def fake_safe_send(*, event, category, subject, html_body, triggered_by_user_id=None, metadata=None, db=None):
    captured.append((event, subject, html_body))
    class R:
        sent = True
        skipped = False
        failed = False
        detail = 'mock'
    return R()

wn._safe_operational_send = fake_safe_send
wn.is_smtp_configured = lambda: True
wn.user_wants_notifications = lambda uid, db: True


class FakeDB:
    pass


# EXACT real payload from the most recent production job (sub_id NEW-20260720130145-F57797)
payload = {
    'sub_id': 'NEW-20260720130145-F57797',
    'sub_type': 'New Launch',
    'product_name': 'curry cut',
    'product_id': 'cxx',
    'launch_dates': ['2026-07-27'],
    'cities': ['Bangalore'],
    'hub_count': 34,
    'submitted_by': 'chandramita.s@licious.com',
    'user_id': 8,
    'stats': {
        'total_weekly_qty': 550.0,
        'total_weekly_revenue': 109450.0,
        'avg_mrp': 199.0,
        'city_breakdown': [{'city': 'Bangalore', 'qty': 550.0, 'revenue': 109450.0}],
    },
}

res = wn.notify_npl_submitted(
    sub_id=payload['sub_id'],
    sub_type=payload['sub_type'],
    product_name=payload['product_name'],
    product_id=payload['product_id'],
    launch_dates=payload['launch_dates'],
    cities=payload['cities'],
    hub_count=payload['hub_count'],
    submitted_by=payload['submitted_by'],
    user_id=payload['user_id'],
    stats=payload['stats'],
    db=FakeDB(),
)
print('result:', res)
for event, subject, html in captured:
    print('===', event, '===')
    print('contains "Hub rows":', 'Hub rows' in html)
    print('contains "Weekly volume":', 'Weekly volume' in html)
    print('contains "550 units":', '550 units' in html)
    print('contains "Est. weekly revenue":', 'Est. weekly revenue' in html)
    print('contains "109,450":', '109,450' in html)
    print('contains "Revenue by city":', 'Revenue by city' in html)
    with open(f'/tmp/final_{event}.html', 'w', encoding='utf-8') as f:
        f.write(html)
