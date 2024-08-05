# dobrofon_dev_bot
This is repository for dobrofon_dev_bot which is used to alarm and notify server activity for our team
**DO NOT FORGET .ENV FILE WITH**
.env example:
```
TELEGRAM_API_TOKEN=YOUR_TOKEN
PROD_URL=URL_WITH_HEALTHCHECK_API
SERVICES_URL=SECOND_URL_WITH_HEALTHCHECK_API
```

To run simply do
```
docker-compose build && docker-compose up
```
