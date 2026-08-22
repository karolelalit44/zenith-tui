import sqlite3, json

SESSION = '2e950bf0-4e5c-4981-8dd8-db3229cd3288'
con = sqlite3.connect('data/zenith.db')
con.row_factory = sqlite3.Row
cur = con.cursor()

rows = cur.execute(
    "SELECT id, role, content, token_count FROM messages WHERE session_id=?", (SESSION,)
).fetchall()
print("message rows:", len(rows))
for r in rows:
    print(r['id'], r['role'], 'tokens=', r['token_count'], repr(r['content'])[:120])
    print('---')

# dump events_json of the assistant message for this session
rows = cur.execute(
    "SELECT id, role, events_json FROM messages WHERE session_id=? AND role='assistant'", (SESSION,)
).fetchall()
for r in rows:
    try:
        evts = json.loads(r['events_json'])
    except Exception as e:
        print("parse err", e)
        continue
    print("== assistant msg", r['id'], "events:", len(evts))
    for e in evts:
        kind = e.get('kind')
        d = e.get('data', {})
        if kind in ('success', 'error'):
            print(">>>", json.dumps(e, indent=1)[:2500])
    print()
