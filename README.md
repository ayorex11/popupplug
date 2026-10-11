# PopUp Plug

Lagos pop-up events directory. Django 5.2, server-rendered, one deployable service.

* `events/` public pages, event posting and moderation fields
* `vendors/` vendor accounts (log in with email)
* `desk/` your approval dashboard (`/desk/`): vendors, events, Instagram queue
* `core/` email notifications, health check, setup commands
* `social/` Instagram cards, captions and posting
* `render.yaml` + `build.sh` one-step Render deploy. See **DEPLOY.md**.

Quick start: `pip install -r requirements.txt && python manage.py bootstrap && python manage.py seed_demo && python manage.py runserver`
