# Mobbin Auth Setup And Reuse

## First time: login and save session

```bash
cd /Users/tamerlanaltynbek/habit_to_do/habit_to_do/plugins/design-scraper

mkdir -p ~/.design-scraper/profile
chmod 700 ~/.design-scraper/profile

python3 skills/design-scraper/scripts/scrape_design.py \
  "https://mobbin.com/apps/headspace-ios-28986bf8-81b2-4af0-84df-b5654a8c98f9/f2c7edab-00b5-460c-9663-1cf64517f7db/screens" \
  --playwright-user-data-dir ~/.design-scraper/profile \
  --headed \
  --skip-post-process
```

## Later: reuse saved session

```bash
cd /Users/tamerlanaltynbek/habit_to_do/habit_to_do/plugins/design-scraper

python3 skills/design-scraper/scripts/scrape_design.py \
  "https://mobbin.com/apps/headspace-ios-28986bf8-81b2-4af0-84df-b5654a8c98f9/f2c7edab-00b5-460c-9663-1cf64517f7db/screens" \
  --playwright-user-data-dir ~/.design-scraper/profile \
  --output-dir /tmp/mobbin-headspace-auth \
  --project headspace \
  --skip-post-process
```
