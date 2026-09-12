# Activity API

All endpoints use `/api` with no trailing slash. Auth uses existing JWT `Authorization: Bearer ACCESS_TOKEN`. Successful responses: `{success:true,data:...,message:""}`. Validation failures return HTTP 400 with field messages; missing/foreign-owned objects return 404. GET reviews/companions are public; remaining operations require login.

| Endpoint | Operations and data |
|---|---|
| `/me` | GET profile; PATCH nickname, preferred_categories string array, preferences object |
| `/reviews` | GET `{items:[...]}` filters `place_id`, `mine=true`; POST multipart place_id,text,rating 1–5 (default 5), optional photo JPEG/PNG/WEBP <=10MB |
| `/reviews/{id}` | PATCH text/rating/photo owner only; DELETE owner only |
| `/reviews/{id}/like` | POST add, DELETE remove, both idempotent |
| `/companions` | GET `{items:[...]}` filters date YYYY-MM-DD,mine=true; POST place_id,title,text,capacity 2–30, optional date YYYY-MM-DD and time HH:MM |
| `/companions/{id}` | GET detail; owner PATCH fields / DELETE |
| `/companions/{id}/join` | POST join, DELETE leave; owner occupies one slot, cannot leave without deleting post |
| `/points` | GET `{balance,items:[{id,amount,reason,created_at}]}` |
| `/rewards` | GET `{items:[]}`; no contracted redemption provider available |
| `/recent-places` | GET `{place_ids:[...]}` newest first max 50; POST place_id; DELETE clear own history |
| `/plans` | GET `{items:[...]}`; POST title,date,stops `[{time:"HH:MM",place:"place name"}]` |
| `/plans/{id}` | DELETE own plan |
| `/inquiries` | GET `{items:[...]}`; POST subject,text; fields status,answer,updated_at are server owned |
| `/notifications` | GET `{items:[{id,title,body,created_at}]}` actual review likes, joins and answered inquiries, latest 50 |

Review item: id,place_id,place_name,author_id,author_nickname,text,rating,photo_url,created_at,like_count,is_liked,is_mine,visit_verified=false. Creation returns `{review: ITEM, points_awarded: NUMBER}`; update/like returns ITEM directly. Photos are uploads, not verified visits. Award: 50 points once per user/place for `review_created`; deleting/recreating or editing does not award again. Ledger survives review deletion. Place average rating recalculates on create/update/delete.

Companion item: id,place_id,place_name,place_address,author_id,author_nickname,title,text,date,time,capacity,member_count,is_joined,is_mine,created_at. Date and time are independently nullable: omitted values on creation or explicit null mean undecided; PATCH null clears the selected value. Time is returned as HH:MM. Exact-date filtering excludes undecided dates; default ordering puts undecided dates/times last. An undecided date remains joinable. Capacity includes owner; joining is idempotent; closed dates/full groups rejected. Capacity updates cannot drop below membership. Atomic conditional membership counter plus transactions prevent overbooking.

Inquiries persist for staff review in Django `/admin/` (Inquiry). Staff fills answer; status changes to answered automatically. No email or push is sent. Notification preferences are persisted; notification list is in-app on request. Plans are user-entered itinerary notes, without routing/time feasibility estimates.

`latest_crowd.is_demo` is true for records with raw_data.dev_seed; clients must visibly label these as example data. Missing observations remain null.

## Run

Use Python >=3.12 supported by installed Django build, install requirements.txt, `python manage.py migrate`, then `python manage.py runserver`. Development media served only when DEBUG. Production must serve MEDIA_ROOT through the deployment's media host. CORS allows loopback localhost/127.0.0.1 dynamic ports only with DEBUG; production must set explicit comma-separated CORS_ALLOWED_ORIGINS. Do not use wildcard.

Tests: `python manage.py test` and `python manage.py makemigrations --check --dry-run`.
