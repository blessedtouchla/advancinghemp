/* Renders news.json (refreshed daily by GitHub Actions). */
(function () {
  var s = document.currentScript, root = (s && s.getAttribute('data-root')) || './';
  var fmt = function (iso, withTime) {
    if (!iso) return '';
    var d = new Date(iso); if (isNaN(d)) return '';
    var o = { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'America/Los_Angeles' };
    if (withTime) { o.hour = 'numeric'; o.minute = '2-digit'; o.timeZoneName = 'short'; }
    return d.toLocaleString('en-US', o);
  };
  var esc = function (t) { var e = document.createElement('span'); e.textContent = t || ''; return e.innerHTML; };
  var item = function (i, showSummary) {
    var pub = i.publisher ? ' · ' + esc(i.publisher) : '';
    return '<li><a href="' + esc(i.link) + '" rel="noopener nofollow" target="_blank">' + esc(i.title) + '</a>' +
      '<span class="d">' + esc(fmt(i.date)) + pub + '</span>' +
      (showSummary && i.summary ? '<span class="s">' + esc(i.summary) + '</span>' : '') + '</li>';
  };
  fetch(root + 'news.json?v=' + Date.now(), { cache: 'no-store' })
    .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(function (data) {
      document.querySelectorAll('[data-news-updated]').forEach(function (el) { el.textContent = fmt(data.updated, true); });
      var full = document.querySelector('[data-news-full]');
      if (full) {
        full.innerHTML = data.sources.map(function (src) {
          var list = src.items && src.items.length
            ? '<ul class="news-list">' + src.items.map(function (i) { return item(i, true); }).join('') + '</ul>'
            : '<p class="s">This feed couldn\u2019t be reached on the last refresh. <a href="' + esc(src.site) + '" target="_blank" rel="noopener">Visit it directly</a>.</p>';
          var stale = src.ok === false && src.items && src.items.length ? '<p class="s" style="font-size:.8rem;color:var(--muted)">Showing the last successful fetch (' + esc(fmt(src.fetched)) + ').</p>' : '';
          return '<article class="card news-src"><h3><a href="' + esc(src.site) + '" target="_blank" rel="noopener">' + esc(src.name) + '</a></h3>' + stale + list + '</article>';
        }).join('');
      }
      var orgBox = document.querySelector('[data-org-news]');
      if (orgBox) {
        var og = [];
        (data.orgs || []).forEach(function (src) { (src.items || []).forEach(function (i) { og.push(Object.assign({}, i, { publisher: src.name, site: src.site })); }); });
        og.sort(function (a, b) { return (b.date || '').localeCompare(a.date || ''); });
        orgBox.innerHTML = og.length
          ? '<ul class="news-list">' + og.slice(0, 12).map(function (i) { return item(i, false); }).join('') + '</ul>'
          : '<p class="s">Headlines from hemp organizations will appear here after the next refresh.</p>';
      }
      var teaser = document.querySelector('[data-news-teaser]');
      if (teaser) {
        var all = [];
        data.sources.forEach(function (src) { (src.items || []).forEach(function (i) { all.push(Object.assign({ publisher: i.publisher || src.name }, i, { publisher: i.publisher || src.name })); }); });
        all.sort(function (a, b) { return (b.date || '').localeCompare(a.date || ''); });
        teaser.innerHTML = '<ul class="news-list">' + all.slice(0, 4).map(function (i) { return item(i, false); }).join('') + '</ul>';
      }
    })
    .catch(function () {
      document.querySelectorAll('[data-news-full],[data-news-teaser],[data-org-news]').forEach(function (el) {
        el.innerHTML = '<p>News is taking a break. Please check back soon.</p>';
      });
    });
})();
