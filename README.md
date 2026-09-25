# Advancing Hemp

Victoria Imtanes's hemp building hub: hempcrete, codes and permits, builders, suppliers, community and daily hemp news. It replaces the 2022 blog at advancinghemp.wordpress.com.

Live: https://blessedtouchla.com/advancinghemp/

- Static HTML/CSS with a little JS. All links are relative, so a custom domain can be added later.
- Each page is a plain `index.html` in its own folder. Edit the HTML directly; shared styles are in `assets/css/site.css`. The header and footer are repeated on every page, so update them everywhere.
- `news.json` is refreshed daily by `.github/workflows/news.yml`, which runs `scripts/fetch_news.py` (Python stdlib only). If a feed fails, the last good items for that source are kept.
- Photos are hotlinked from Wikimedia Commons, with attribution next to each image.

Contact: advancinghemp@gmail.com
