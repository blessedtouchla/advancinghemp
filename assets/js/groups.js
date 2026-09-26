/* Renders data/groups.json: daily posts from Victoria's Facebook hemp groups. */
(function () {
  var s = document.currentScript, root = (s && s.getAttribute('data-root')) || './';
  var esc = function (t) { var e = document.createElement('span'); e.textContent = t == null ? '' : String(t); return e.innerHTML; };
  var dayName = function (iso) {
    var p = iso.split('-'), d = new Date(+p[0], +p[1] - 1, +p[2]);
    return d.toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric' });
  };
  var stamp = function (iso) {
    var d = new Date(iso); if (isNaN(d)) return '';
    return d.toLocaleString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit', timeZone: 'America/Los_Angeles', timeZoneName: 'short' });
  };
  var glinks = function (gs) {
    var a = gs.map(function (g) { return '<a href="' + esc(g.url) + '" target="_blank" rel="noopener">' + esc(g.name) + '</a>'; });
    return a.length > 1 ? a.slice(0, -1).join(', ') + ' and ' + a[a.length - 1] : a[0];
  };
  var mediaNote = { photo: 'Photo on Facebook', video: 'Video on Facebook', link: 'Link post' };
  var card = function (p, compact) {
    var img = p.image
      ? '<figure class="gp-img"><img src="' + esc(root + p.image) + '" alt="Photo from ' + esc(p.author) + '\u2019s post" loading="lazy" decoding="async"' +
        (p.w ? ' width="' + p.w + '" height="' + p.h + '"' : '') + ' onerror="this.parentNode.remove()"></figure>'
      : '';
    var text = p.excerpt
      ? '<p class="gp-text">' + esc(compact && p.excerpt.length > 160 ? p.excerpt.slice(0, p.excerpt.lastIndexOf(' ', 150)) + '\u2026' : p.excerpt) + '</p>'
      : '<p class="gp-text gp-empty">Shared ' + (p.media === 'video' ? 'a video' : 'a photo') + ' without a caption.</p>';
    var tag = !p.image && mediaNote[p.media] ? '<span class="tag g">' + mediaNote[p.media] + '</span>' : '';
    return '<article class="card gp-card">' + img +
      '<p class="meta">' + esc(p.groups.map(function (g) { return g.name; }).join(' \u00b7 ')) + '</p>' +
      '<h3 class="gp-author">' + esc(p.author) + '</h3>' + text + tag +
      '<p class="credit">Posted in ' + glinks(p.groups) + ' on Facebook. <a class="gp-view" href="' + esc(p.link) + '" target="_blank" rel="noopener">View on Facebook &rarr;</a></p>' +
      '</article>';
  };
  var privateList = function (items) {
    if (!items || !items.length) return '';
    return '<div class="gp-private"><h4>From private groups</h4><ul>' + items.map(function (i) {
      return '<li>' + esc(i.summary) + ' <span class="gp-in">(' + glinks(i.groups) + ')</span></li>';
    }).join('') + '</ul></div>';
  };
  fetch(root + 'data/groups.json?v=' + Date.now(), { cache: 'no-store' })
    .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(function (data) {
      var days = data.days || [];
      document.querySelectorAll('[data-groups-updated]').forEach(function (el) { el.textContent = stamp(data.updated); });
      var full = document.querySelector('[data-groups-full]');
      if (full) {
        full.innerHTML = days.length ? days.map(function (d) {
          var n = d.public.length + d.private.length;
          return '<section class="gp-day" id="d-' + esc(d.date) + '"><h2 class="gp-dayh">' + esc(dayName(d.date)) +
            ' <small>' + n + (n === 1 ? ' post' : ' posts') + '</small></h2>' +
            (d.public.length ? '<div class="gp-grid">' + d.public.map(function (p) { return card(p, false); }).join('') + '</div>' : '') +
            privateList(d.private) + '</section>';
        }).join('') : '<p>No group posts yet. Check back tomorrow.</p>';
      }
      var teaser = document.querySelector('[data-groups-teaser]');
      if (teaser) {
        var d = days[0];
        if (!d) { teaser.innerHTML = '<p>No group posts yet.</p>'; return; }
        var pick = d.public.filter(function (p) { return p.excerpt; }).concat(d.public.filter(function (p) { return !p.excerpt; })).slice(0, 3);
        var more = d.public.length + d.private.length - pick.length;
        teaser.innerHTML = '<p class="gp-dayh-sm">' + esc(dayName(d.date)) + '</p><div class="gp-grid gp-teaser">' +
          pick.map(function (p) { return card(p, true); }).join('') + '</div>' +
          '<p style="margin-top:16px"><a class="btn solid" href="' + esc(root) + 'groups/">See all posts from the groups' + (more > 0 ? ' (+' + more + ' more that day)' : '') + ' &rarr;</a></p>';
      }
    })
    .catch(function () {
      document.querySelectorAll('[data-groups-full],[data-groups-teaser]').forEach(function (el) {
        el.innerHTML = '<p>The group feed is taking a break. Please check back soon.</p>';
      });
    });
})();
