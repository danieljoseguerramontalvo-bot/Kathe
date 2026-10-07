(function () {
  'use strict';

  var NL = String.fromCharCode(10);
  var base = document.body.getAttribute('data-base') || '';
  var isEN = document.documentElement.lang === 'en';

  /* header state */
  var hdr = document.getElementById('hdr');
  /* only the home page hides its header mark; every other page has a
     small page hero and needs the brand visible from the first pixel */
  var heroEl = document.querySelector('.hero');
  if (hdr && heroEl) hdr.classList.add('has-hero');
  function onScroll() {
    if (!hdr) return;
    hdr.classList.toggle('scrolled', window.scrollY > 40);
    /* the brand fades up as you move off the hero, rather than snapping in
       once the hero is fully behind you */
    if (heroEl) {
      var h = heroEl.offsetHeight || window.innerHeight;
      var t = Math.min(1, Math.max(0, window.scrollY / (h * 0.45)));
      hdr.style.setProperty('--brand-o', t.toFixed(3));
      hdr.classList.toggle('past-hero', t > 0.02);
    }
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  /* mobile drawer */
  var burger = document.getElementById('burger');
  var drawer = document.getElementById('drawer');
  var drawerX = document.getElementById('drawerX');
  function setDrawer(open) {
    if (!drawer) return;
    drawer.classList.toggle('open', open);
    document.documentElement.style.overflow = open ? 'hidden' : '';
    if (burger) burger.setAttribute('aria-expanded', open ? 'true' : 'false');
  }
  if (burger) burger.addEventListener('click', function () { setDrawer(true); });
  if (drawerX) drawerX.addEventListener('click', function () { setDrawer(false); });
  if (drawer) {
    drawer.querySelectorAll('nav a').forEach(function (a) {
      a.addEventListener('click', function () { setDrawer(false); });
    });
  }

  /* reveal on scroll */
  var rv = document.querySelectorAll('.rv');
  if ('IntersectionObserver' in window && rv.length) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); }
      });
    }, { rootMargin: '0px 0px -10% 0px', threshold: 0.06 });
    rv.forEach(function (el) { io.observe(el); });
  } else {
    rv.forEach(function (el) { el.classList.add('in'); });
  }

  /* ---------------- sliders (home hero + unit heroes) ---------------- */
  document.querySelectorAll('.slides').forEach(function (wrap) {
    var slides = [].slice.call(wrap.querySelectorAll('.slide'));
    if (slides.length < 2) return;
    var host = wrap.closest('.hero, .phero') || wrap.parentNode;
    var ticksWrap = host.querySelector('.ticks');
    if (!ticksWrap) return;

    var cur = 0, timer = null, paused = false, ticks = [];

    function holdFor(i) {
      var v = parseInt(slides[i].getAttribute('data-hold'), 10);
      return isNaN(v) ? 6500 : v;
    }

    function playSlide(i) {
      slides.forEach(function (sl, n) {
        var v = sl.querySelector('video');
        if (!v) return;
        if (n === i) {
          try { v.currentTime = 0; var pr = v.play(); if (pr && pr.catch) pr.catch(function () {}); } catch (e) {}
        } else {
          try { v.pause(); } catch (e) {}
        }
      });
    }

    slides.forEach(function (sl, i) {
      var t = document.createElement('button');
      t.className = 'tick' + (i === 0 ? ' on' : '');
      t.type = 'button';
      t.setAttribute('aria-label', (isEN ? 'Photo ' : 'Foto ') + (i + 1));
      t.appendChild(document.createElement('i'));
      t.addEventListener('click', function () { go(i, true); });
      ticksWrap.appendChild(t);
      ticks.push(t);
    });

    function go(n, manual) {
      n = (n + slides.length) % slides.length;
      if (n === cur && !manual) return;
      slides[cur].classList.remove('on');
      ticks[cur].classList.remove('on');
      ticks[cur].classList.add('done');
      cur = n;
      slides[cur].classList.add('on');
      var t = ticks[cur];
      t.classList.remove('on', 'done');
      t.style.setProperty('--fill', (holdFor(cur) / 1000) + 's');
      void t.offsetWidth;
      t.classList.add('on');
      for (var i = 0; i < ticks.length; i++) {
        if (i !== cur) ticks[i].classList.remove('on');
        if (i > cur) ticks[i].classList.remove('done');
      }
      playSlide(cur);
      restart();
    }

    function restart() {
      if (timer) clearTimeout(timer);
      if (paused) return;
      timer = setTimeout(function () { go(cur + 1); }, holdFor(cur));
    }

    function hold(on) {
      paused = on;
      if (on) { if (timer) clearTimeout(timer); } else { restart(); }
    }

    host.addEventListener('mouseenter', function () { hold(true); });
    host.addEventListener('mouseleave', function () { hold(false); });
    document.addEventListener('visibilitychange', function () { hold(document.hidden); });

    ticks[0].style.setProperty('--fill', (holdFor(0) / 1000) + 's');
    playSlide(0);
    restart();
  });

  /* ---------------- galleries ---------------- */
  var COUNTS = { a: 12, b: 9, c: 20 };
  var ORDER = {
    a: [3, 2, 11, 4, 8, 7, 1, 5, 6, 9, 10, 12],
    b: [2, 6, 7, 3, 8, 9, 1, 4, 5],
    c: [6, 9, 7, 12, 3, 2, 5, 4, 8, 10, 11, 13, 14, 18, 15, 16, 19, 20, 1, 17]
  };

  function paths(key) {
    var out = [];
    var seq = ORDER[key] || [];
    for (var s = 0; s < seq.length; s++) {
      var i = seq[s];
      var n = i < 10 ? '0' + i : '' + i;
      out.push({
        full: base + 'assets/img/' + key + '/' + key + '-' + n + '.jpg',
        thumb: base + 'assets/img/' + key + '/' + key + '-' + n + '@480.jpg'
      });
    }
    return out;
  }

  var lb = document.getElementById('lb');
  var lbImg = document.getElementById('lbImg');
  var lbStrip = document.getElementById('lbStrip');
  var lbTitle = document.getElementById('lbTitle');
  var list = [];
  var idx = 0;
  var opener = null;
  var label = '';

  function show(i) {
    if (!list.length) return;
    idx = (i + list.length) % list.length;
    lbImg.src = list[idx].full;
    lbImg.alt = label + ' — ' + (isEN ? 'photo ' : 'foto ') + (idx + 1) + (isEN ? ' of ' : ' de ') + list.length;
    lbStrip.querySelectorAll('img').forEach(function (t, n) { t.classList.toggle('on', n === idx); });
    var on = lbStrip.querySelector('img.on');
    if (on && on.scrollIntoView) on.scrollIntoView({ block: 'nearest', inline: 'center', behavior: 'smooth' });
  }

  function openGallery(key, lbl, trigger, start) {
    if (!lb || !COUNTS[key]) return;
    opener = trigger || null;
    label = lbl;
    list = paths(key);
    lbTitle.textContent = lbl + ' — ' + list.length + (isEN ? ' photos' : ' fotos');
    lbStrip.innerHTML = '';
    list.forEach(function (p, n) {
      var t = document.createElement('img');
      t.src = p.thumb;
      t.alt = '';
      t.loading = 'lazy';
      t.addEventListener('click', function () { show(n); });
      lbStrip.appendChild(t);
    });
    lb.classList.add('open');
    document.documentElement.style.overflow = 'hidden';
    show(start || 0);
  }

  function closeGallery() {
    if (!lb) return;
    lb.classList.remove('open');
    document.documentElement.style.overflow = '';
    lbImg.removeAttribute('src');
    if (opener && opener.focus) opener.focus();
    opener = null;
  }

  document.querySelectorAll('[data-gallery]').forEach(function (el) {
    el.addEventListener('click', function () {
      var start = parseInt(el.getAttribute('data-index'), 10);
      openGallery(el.getAttribute('data-gallery'), el.getAttribute('data-label') || 'Apartamento', el,
        isNaN(start) ? 0 : start);
    });
  });

  var lbX = document.getElementById('lbX');
  var lbPrev = document.getElementById('lbPrev');
  var lbNext = document.getElementById('lbNext');
  if (lbX) lbX.addEventListener('click', closeGallery);
  if (lbPrev) lbPrev.addEventListener('click', function () { show(idx - 1); });
  if (lbNext) lbNext.addEventListener('click', function () { show(idx + 1); });
  if (lb) {
    lb.addEventListener('click', function (e) {
      if (e.target === lb || e.target.classList.contains('lb-stage')) closeGallery();
    });
  }

  document.addEventListener('keydown', function (e) {
    if (drawer && drawer.classList.contains('open') && e.key === 'Escape') { setDrawer(false); return; }
    if (!lb || !lb.classList.contains('open')) return;
    if (e.key === 'Escape') closeGallery();
    if (e.key === 'ArrowLeft') show(idx - 1);
    if (e.key === 'ArrowRight') show(idx + 1);
  });

  var x0 = null;
  if (lb) {
    lb.addEventListener('touchstart', function (e) { x0 = e.touches[0].clientX; }, { passive: true });
    lb.addEventListener('touchend', function (e) {
      if (x0 === null) return;
      var dx = e.changedTouches[0].clientX - x0;
      if (Math.abs(dx) > 48) show(dx < 0 ? idx + 1 : idx - 1);
      x0 = null;
    }, { passive: true });
  }

  /* sticky booking bar appears once the hero is scrolled past */
  var bar = document.querySelector('.bookbar');
  if (bar) {
    var ph = document.querySelector('.phero');
    function bark() {
      var past = ph ? (ph.getBoundingClientRect().bottom < 40) : (window.scrollY > 400);
      var atEnd = (window.innerHeight + window.scrollY) > (document.body.offsetHeight - 220);
      bar.classList.toggle('show', past && !atEnd);
    }
    window.addEventListener('scroll', bark, { passive: true });
    window.addEventListener('resize', bark);
    bark();
  }

  /* ---------------- signature motion ---------------- */
  (function motion() {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    if (!('IntersectionObserver' in window)) return;
    document.documentElement.classList.add('fx-on');

    /* the OBSERVED element is never the clipped one: a clip-path zeroes the
       element's own visible box and the observer would never fire. */
    var hosts = [];
    function mark(sel, cls) {
      document.querySelectorAll(sel).forEach(function (el) {
        el.classList.add('fxp', cls);
        hosts.push(el);
      });
    }
    mark('.head, .city-in, .cta .inner, .room-txt, .ovw-txt, .loc-t, .carband-h', 'fx-txt');
    mark('.card, .ovw-img, .room-img, .loc-p, .st-t, .uimg, .mt', 'fx-img');

    var io2 = new IntersectionObserver(function (es) {
      es.forEach(function (e) {
        if (!e.isIntersecting) return;
        e.target.classList.add('in');
        io2.unobserve(e.target);
      });
    }, { rootMargin: '0px 0px -5% 0px', threshold: 0.04 });

    hosts.forEach(function (el) {
      var r = el.getBoundingClientRect();
      if (r.top < window.innerHeight && r.bottom > 0) el.classList.add('in');
      else io2.observe(el);
    });

    /* Safety net: a fast scroll can outrun the observer's delivery, and a
       missed callback would leave text clipped to nothing. Sweep on scroll
       and reveal anything that has reached the viewport, whatever IO said. */
    var pending = hosts.slice();
    var sweeping = false;
    function sweep() {
      sweeping = false;
      var vh = window.innerHeight;
      var rest = [];
      for (var i = 0; i < pending.length; i++) {
        var el = pending[i];
        if (el.classList.contains('in')) { io2.unobserve(el); continue; }
        if (el.getBoundingClientRect().top < vh) {
          el.classList.add('in');
          io2.unobserve(el);
        } else {
          rest.push(el);
        }
      }
      pending = rest;
      if (!pending.length) window.removeEventListener('scroll', onSweep);
    }
    function onSweep() {
      if (sweeping) return;
      sweeping = true;
      window.requestAnimationFrame(sweep);
    }
    window.addEventListener('scroll', onSweep, { passive: true });
    window.addEventListener('resize', onSweep);

    var bands = [];
    document.querySelectorAll('.city > img, .cta > img').forEach(function (img) {
      img.classList.add('px');
      bands.push(img);
    });
    if (!bands.length) return;
    var ticking = false;
    function frame() {
      ticking = false;
      var vh = window.innerHeight;
      for (var i = 0; i < bands.length; i++) {
        var img = bands[i];
        var r = img.parentNode.getBoundingClientRect();
        if (r.bottom < -200 || r.top > vh + 200) continue;
        var p = (r.top + r.height / 2 - vh / 2) / (vh / 2 + r.height / 2);
        img.style.transform = 'translate3d(0,' + (p * 7).toFixed(2) + '%,0)';
      }
    }
    function onScroll2() { if (!ticking) { ticking = true; window.requestAnimationFrame(frame); } }
    window.addEventListener('scroll', onScroll2, { passive: true });
    window.addEventListener('resize', onScroll2);
    frame();
  })();

  /* ---------------- building elevation ---------------- */
  (function building() {
    var stack = document.querySelector('.bldg-stack');
    var panel = document.querySelector('.bldg-panel');
    if (!stack || !panel) return;
    var floors = [].slice.call(stack.querySelectorAll('.flr--on'));
    var panes = [].slice.call(panel.querySelectorAll('.bp'));
    if (!floors.length) return;

    function show(slug) {
      floors.forEach(function (f) { f.classList.toggle('act', f.getAttribute('data-unit') === slug); });
      panes.forEach(function (p) { p.classList.toggle('on', p.getAttribute('data-unit') === slug); });
    }

    floors.forEach(function (f) {
      var slug = f.getAttribute('data-unit');
      f.addEventListener('mouseenter', function () { show(slug); });
      f.addEventListener('focus', function () { show(slug); });
    });

    show(floors[0].getAttribute('data-unit'));
  })();

  /* ---------------- unit section nav ---------------- */
  (function unitNav() {
    var nav = document.getElementById('unav');
    if (!nav) return;
    var links = [].slice.call(nav.querySelectorAll('.unav-l a'));
    var targets = links.map(function (a) {
      return document.querySelector(a.getAttribute('href'));
    });
    if (!('IntersectionObserver' in window)) return;

    var seen = {};
    var io3 = new IntersectionObserver(function (es) {
      es.forEach(function (e) { seen[e.target.id] = e.isIntersecting ? e.intersectionRatio : 0; });
      var best = null, bestR = 0;
      targets.forEach(function (t) {
        if (!t) return;
        var r = seen[t.id] || 0;
        if (r > bestR) { bestR = r; best = t.id; }
      });
      links.forEach(function (a) {
        a.classList.toggle('on', best !== null && a.getAttribute('href') === '#' + best);
      });
    }, { threshold: [0, 0.15, 0.4, 0.75], rootMargin: '-70px 0px -45% 0px' });

    targets.forEach(function (t) { if (t) io3.observe(t); });
  })();

  /* ---------------- guided tour ---------------- */
  (function tour() {
    var root = document.querySelector('.htour');
    if (!root) return;
    var tabs = [].slice.call(root.querySelectorAll('.ht-tab'));
    var panes = [].slice.call(root.querySelectorAll('.ht-pane'));
    if (!panes.length) return;

    function pad(n) { return n < 10 ? '0' + n : '' + n; }

    panes.forEach(function (pane) {
      var scenes = [].slice.call(pane.querySelectorAll('.ht-scene'));
      var h3 = pane.querySelector('h3');
      var body = pane.querySelector('.ht-body');
      var count = pane.querySelector('.ht-count b');
      var at = 0;

      function caption(t, b) { h3.textContent = t; body.textContent = b; }

      /* every scene carries its own pins, so the dots always match the photo */
      scenes.forEach(function (scene) {
        var dots = [].slice.call(scene.querySelectorAll('.ht-dot'));
        scene._dots = dots;
        dots.forEach(function (d, i) {
          function pin() {
            dots.forEach(function (o, k) { o.classList.toggle('is-on', k === i); });
            var tip = d.querySelector('.ht-tip');
            caption(tip.querySelector('strong').textContent,
                    tip.querySelector('em').textContent);
          }
          d.addEventListener('mouseenter', pin);
          d.addEventListener('focus', pin);
          d.addEventListener('click', function (e) { e.preventDefault(); pin(); });
        });
      });

      /* the arrows walk the rooms: every step is a different photograph */
      function step(k) {
        at = (k + scenes.length) % scenes.length;
        scenes.forEach(function (s, i) { s.classList.toggle('is-on', i === at); });
        var s = scenes[at];
        caption(s.getAttribute('data-t'), s.getAttribute('data-b'));
        count.textContent = pad(at + 1);
        /* clear any pin selection so the new photo starts on its own caption */
        (s._dots || []).forEach(function (d) { d.classList.remove('is-on'); });
      }

      pane.querySelectorAll('.ht-arrow').forEach(function (btn) {
        btn.addEventListener('click', function () {
          step(at + (+btn.getAttribute('data-d')));
        });
      });
    });

    tabs.forEach(function (tab) {
      tab.addEventListener('click', function () {
        var i = tab.getAttribute('data-i');
        tabs.forEach(function (t) {
          var on = t === tab;
          t.classList.toggle('is-on', on);
          t.setAttribute('aria-selected', on ? 'true' : 'false');
        });
        panes.forEach(function (p) {
          p.classList.toggle('is-on', p.getAttribute('data-i') === i);
        });
      });
    });
  })();
})();
