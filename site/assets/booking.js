/* Booking picker: apartment cards, a range calendar and a guest stepper.
   Replaces the native select/date controls everywhere they appeared. */
(function () {
  'use strict';

  var NL = String.fromCharCode(10);
  var isEN = document.documentElement.lang === 'en';
  var wa = document.body.getAttribute('data-wa') || '';

  var L = isEN
    ? {
        months: ['January', 'February', 'March', 'April', 'May', 'June', 'July',
                 'August', 'September', 'October', 'November', 'December'],
        days: ['M', 'T', 'W', 'T', 'F', 'S', 'S'],
        pickIn: 'Pick your arrival', pickOut: 'Pick your departure',
        night: 'night', nights: 'nights', none: 'No dates yet',
        need: 'Please choose your arrival and departure dates.',
        ok: 'WhatsApp will open with the message already written. Nothing is sent until you confirm.',
        intro: 'Hello, I would like to check availability at Apart Hotel Aruba (Edificio K58, Barranquilla).',
        unit: 'Apartment: ', arr: 'Arrival: ', dep: 'Departure: ', pax: 'Guests: ',
        close: 'Could you confirm availability and the rate? Thank you.',
        any: 'Any', guest: 'guest', guests: 'guests', plus: '5 or more',
        wants: 'While we are there we would like:', quoted: '(we understand these are quoted separately)'
      }
    : {
        months: ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio',
                 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'],
        days: ['L', 'M', 'X', 'J', 'V', 'S', 'D'],
        pickIn: 'Elige la llegada', pickOut: 'Elige la salida',
        night: 'noche', nights: 'noches', none: 'Sin fechas',
        need: 'Elige la fecha de llegada y la de salida.',
        ok: 'Se abrirá WhatsApp con el mensaje ya escrito. Nada se envía sin que lo confirmes.',
        intro: 'Hola, quisiera consultar disponibilidad en Apart Hotel Aruba (Edificio K58, Barranquilla).',
        unit: 'Apartamento: ', arr: 'Llegada: ', dep: 'Salida: ', pax: 'Huéspedes: ',
        close: '¿Me confirman disponibilidad y tarifa? Gracias.',
        any: 'Cualquiera', guest: 'huésped', guests: 'huéspedes', plus: '5 o más',
        wants: 'Durante la estadía nos gustaría:', quoted: '(entendemos que se cotiza aparte)'
      };

  function iso(d) {
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') +
      '-' + String(d.getDate()).padStart(2, '0');
  }
  function parse(s) {
    var p = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s || '');
    return p ? new Date(+p[1], +p[2] - 1, +p[3]) : null;
  }
  function midnight() { var d = new Date(); d.setHours(0, 0, 0, 0); return d; }
  function nightsBetween(a, b) { return Math.round((b - a) / 86400000); }
  function pretty(d) {
    return d.getDate() + ' ' + L.months[d.getMonth()].toLowerCase().slice(0, 3) + '.';
  }
  function plural(n, one, many) { return n + ' ' + (n === 1 ? one : many); }
  function months() { return window.matchMedia('(min-width:820px)').matches ? 2 : 1; }

  /* ------------------------------------------------------------------
     Range calendar. Renders count() months from a cursor and reports
     the chosen range through onChange.
     ------------------------------------------------------------------ */
  function Calendar(mount, count, onChange) {
    var today = midnight();
    var cursor = new Date(today.getFullYear(), today.getMonth(), 1);
    var from = null, to = null, hover = null;

    function inRange(d) {
      var end = to || hover;
      return from && end && d > from && d < end;
    }

    function month(base) {
      var y = base.getFullYear(), m = base.getMonth();
      var lead = (new Date(y, m, 1).getDay() + 6) % 7;   /* weeks start Monday */
      var len = new Date(y, m + 1, 0).getDate();
      var h = '<div class="cal-m"><div class="cal-ml">' + L.months[m] + ' ' + y + '</div>' +
        '<div class="cal-w">';
      for (var i = 0; i < 7; i++) h += '<span>' + L.days[i] + '</span>';
      h += '</div><div class="cal-d">';
      for (var b = 0; b < lead; b++) h += '<span class="d d--pad"></span>';
      for (var n = 1; n <= len; n++) {
        var d = new Date(y, m, n);
        var cls = 'd';
        if (d < today) cls += ' d--off';
        if (from && +d === +from) cls += ' d--a';
        if (to && +d === +to) cls += ' d--b';
        if (inRange(d)) cls += ' d--in';
        h += '<button type="button" class="' + cls + '" data-d="' + iso(d) + '"' +
          (d < today ? ' disabled' : '') + '>' + n + '</button>';
      }
      return h + '</div></div>';
    }

    function render() {
      var h = '<div class="cal-hd">' +
        '<button type="button" class="cal-nav" data-m="-1" aria-label="&#8592;">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="m15 18-6-6 6-6"/></svg></button>' +
        '<span class="cal-hint">' + (from && !to ? L.pickOut : L.pickIn) + '</span>' +
        '<button type="button" class="cal-nav" data-m="1" aria-label="&#8594;">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="m9 18 6-6-6-6"/></svg></button>' +
        '</div><div class="cal-ms">';
      for (var i = 0; i < count(); i++) {
        h += month(new Date(cursor.getFullYear(), cursor.getMonth() + i, 1));
      }
      mount.innerHTML = h + '</div>';
      var prev = mount.querySelector('[data-m="-1"]');
      if (prev) prev.disabled = cursor <= new Date(today.getFullYear(), today.getMonth(), 1);
    }

    mount.addEventListener('click', function (e) {
      var nav = e.target.closest('.cal-nav');
      if (nav) {
        cursor = new Date(cursor.getFullYear(), cursor.getMonth() + (+nav.getAttribute('data-m')), 1);
        render();
        return;
      }
      var cell = e.target.closest('.d');
      if (!cell || cell.disabled) return;
      var d = parse(cell.getAttribute('data-d'));
      if (!from || to || d <= from) { from = d; to = null; }
      else { to = d; }
      hover = null;
      render();
      onChange(from, to);
    });

    mount.addEventListener('mouseover', function (e) {
      if (!from || to) return;
      var cell = e.target.closest('.d');
      if (!cell || cell.disabled) return;
      var d = parse(cell.getAttribute('data-d'));
      if (!d || +d === +hover) return;
      hover = d;
      render();
    });

    render();
    return {
      set: function (a, b) {
        from = a; to = b;
        if (a) cursor = new Date(a.getFullYear(), a.getMonth(), 1);
        render();
      },
      redraw: render
    };
  }

  /* ------------------------------------------------------------------
     The booking page: steps on the left, a live reservation summary on the
     right, and a demonstration checkout. No figure here is a quoted price —
     see DEMO_RATE in tools/build.mjs.
     ------------------------------------------------------------------ */
  var DEMO = { night: 240000, deposit: 0.3, fallbackNights: 3 };

  function cop(n) {
    return '$' + Math.round(n).toLocaleString('es-CO') + ' COP';
  }
  /* the "N nights x rate" label already sits next to a COP figure, so the
     suffix there only makes it wrap */
  function copShort(n) {
    return '$' + Math.round(n).toLocaleString('es-CO');
  }
  function ref() {
    var s = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789', o = '';
    for (var i = 0; i < 6; i++) o += s.charAt(Math.floor(Math.random() * s.length));
    return 'AHA-' + o;
  }

  var form = document.getElementById('bk');
  if (form) (function () {
    var cards = [].slice.call(form.querySelectorAll('.ucard'));
    var card0 = cards.length ? cards[0] : null;
    var unit = card0 ? card0.getAttribute('data-unit') : '';
    var pax = 2;
    var from = null, to = null;

    var vDates = document.getElementById('bkDatesV');
    var vPax = document.getElementById('bkPaxV');
    var note = document.getElementById('bkNote');
    var prog = [].slice.call(document.querySelectorAll('#bkProg .bpg'));
    var extra = document.getElementById('bkExtra');

    var el = {};
    ['bsImg', 'bsUnit', 'bsBadge', 'bsIn', 'bsOut', 'bsN', 'bsG',
     'bsRateL', 'bsRate', 'bsTot', 'bsDep'].forEach(function (id) {
      el[id] = document.getElementById(id);
    });

    function nights() { return (from && to) ? nightsBetween(from, to) : 0; }
    function demoNights() { return nights() || DEMO.fallbackNights; }
    function total() { return demoNights() * DEMO.night; }

    function set(node, txt) { if (node) node.textContent = txt; }

    function step(n, done) {
      var li = prog[n - 1];
      if (li) li.classList.toggle('is-done', !!done);
    }

    function sync() {
      var n = nights();

      if (!from) set(vDates, L.none);
      else if (!to) set(vDates, pretty(from) + ' → ?');
      else set(vDates, pretty(from) + ' – ' + pretty(to) + ' · ' +
        plural(n, L.night, L.nights));
      set(vPax, pax >= 5 ? L.plus : plural(pax, L.guest, L.guests));

      set(el.bsUnit, unit);
      set(el.bsIn, from ? pretty(from) : '—');
      set(el.bsOut, to ? pretty(to) : '—');
      set(el.bsN, n ? String(n) : '—');
      set(el.bsG, pax >= 5 ? L.plus : String(pax));

      set(el.bsRateL, plural(demoNights(), L.night, L.nights) + ' × ' + copShort(DEMO.night));
      set(el.bsRate, cop(total()));
      set(el.bsTot, cop(total()));
      set(el.bsDep, cop(total() * DEMO.deposit));

      step(1, true);
      step(2, !!(from && to));
      step(3, true);
      step(4, !!(extra && extra.value.trim()));
    }

    cards.forEach(function (c) {
      c.addEventListener('click', function () {
        cards.forEach(function (o) {
          o.classList.remove('is-on');
          o.setAttribute('aria-checked', 'false');
        });
        c.classList.add('is-on');
        c.setAttribute('aria-checked', 'true');
        unit = c.getAttribute('data-unit');
        if (el.bsImg) el.bsImg.src = c.getAttribute('data-cover') || el.bsImg.src;
        set(el.bsBadge, c.getAttribute('data-badge') || '');
        sync();
      });
    });

    if (extra) extra.addEventListener('input', sync);

    var cal = Calendar(document.getElementById('bkCal'), months, function (a, b) {
      from = a; to = b;
      sync();
      if (note) { note.textContent = L.ok; note.classList.remove('bad'); }
    });
    window.addEventListener('resize', function () { cal.redraw(); });

    form.querySelectorAll('#bkPaxUI button').forEach(function (btn) {
      btn.addEventListener('click', function () {
        pax = Math.min(5, Math.max(1, pax + (+btn.getAttribute('data-d'))));
        sync();
      });
    });

    /* carried over from the hero strip or an apartment page */
    (function preset() {
      var q = window.location.search;
      var u = /[?&]u=([a-z0-9-]+)/.exec(q);
      if (u) {
        var card = form.querySelector('.ucard[data-slug="' + u[1] + '"]');
        if (card) card.click();
      }
      var a = parse((/[?&]in=(\d{4}-\d{2}-\d{2})/.exec(q) || [])[1]);
      var b = parse((/[?&]out=(\d{4}-\d{2}-\d{2})/.exec(q) || [])[1]);
      if (a && a >= midnight()) {
        from = a;
        to = (b && b > a) ? b : null;
        cal.set(from, to);
      }
      var g = /[?&]g=([1-5])/.exec(q);
      if (g) pax = +g[1];
      sync();
    })();

    function waMessage() {
      var lines = [
        L.intro, '',
        L.unit + unit,
        L.arr + (from ? iso(from) : '?'),
        L.dep + (to ? iso(to) : '?'),
        L.pax + (pax >= 5 ? L.plus : pax)
      ];
      var want = (extra && extra.value ? extra.value.trim() : '');
      if (want) lines.push('', L.wants, want, L.quoted);
      lines.push('', L.close);
      return lines.join(NL);
    }

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      if (!from || !to) {
        note.textContent = L.need;
        note.classList.add('bad');
        document.getElementById('bkCal').scrollIntoView({ block: 'center', behavior: 'smooth' });
        return;
      }
      window.open('https://wa.me/' + wa + '?text=' + encodeURIComponent(waMessage()),
        '_blank', 'noopener');
    });

    /* --------------------------------------------------------------
       The checkout. A demonstration: nothing is submitted, the card
       fields are readonly test data, and every figure is labelled.
       -------------------------------------------------------------- */
    var chk = document.getElementById('chk');
    if (chk) (function () {
      var body = chk.querySelector('.chk-body');
      var foot = chk.querySelector('.chk-ft');
      var done = document.getElementById('chkDone');
      var go = document.getElementById('chkGo');
      var goAmt = document.getElementById('chkGoAmt');
      var tabs = [].slice.call(chk.querySelectorAll('.chk-tab'));
      var panes = [].slice.call(chk.querySelectorAll('.chk-pane'));
      var method = tabs.length ? tabs[0].getAttribute('data-label') : '';
      var lastFocus = null;
      var timer = null;

      function fill() {
        var t = total(), dep = t * DEMO.deposit;
        set(document.getElementById('chkUnit'), unit);
        set(document.getElementById('chkWhen'),
          (from && to)
            ? pretty(from) + ' – ' + pretty(to) + ' · ' +
              plural(pax, L.guest, L.guests)
            : plural(DEMO.fallbackNights, L.night, L.nights) + ' · ' +
              plural(pax, L.guest, L.guests));
        set(document.getElementById('chkRateL'),
          plural(demoNights(), L.night, L.nights) + ' × ' + copShort(DEMO.night));
        set(document.getElementById('chkRate'), cop(t));
        set(document.getElementById('chkTot'), cop(t));
        set(document.getElementById('chkDep'), cop(dep));
        set(document.getElementById('chkBal'), cop(t - dep));
        set(goAmt, cop(dep));
      }

      function show(k) {
        panes.forEach(function (p) { p.hidden = p.getAttribute('data-pane') !== k; });
      }
      show(tabs.length ? tabs[0].getAttribute('data-m') : '');

      tabs.forEach(function (b) {
        b.addEventListener('click', function () {
          tabs.forEach(function (o) {
            o.classList.remove('is-on');
            o.setAttribute('aria-selected', 'false');
          });
          b.classList.add('is-on');
          b.setAttribute('aria-selected', 'true');
          method = b.getAttribute('data-label');
          show(b.getAttribute('data-m'));
        });
      });

      function open() {
        lastFocus = document.activeElement;
        fill();
        done.hidden = true;
        body.hidden = false;
        foot.hidden = false;
        go.disabled = false;
        go.classList.remove('is-busy');
        chk.hidden = false;
        document.body.classList.add('chk-open');
        var x = chk.querySelector('.chk-x');
        if (x) x.focus();
      }
      function close() {
        if (timer) { window.clearTimeout(timer); timer = null; }
        chk.hidden = true;
        document.body.classList.remove('chk-open');
        if (lastFocus && lastFocus.focus) lastFocus.focus();
      }

      document.querySelectorAll('[data-chk-open]').forEach(function (b) {
        b.addEventListener('click', open);
      });
      chk.querySelectorAll('[data-chk-close]').forEach(function (b) {
        b.addEventListener('click', close);
      });
      chk.addEventListener('click', function (e) { if (e.target === chk) close(); });
      document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && !chk.hidden) close();
      });

      go.addEventListener('click', function () {
        if (go.disabled) return;
        go.disabled = true;
        go.classList.add('is-busy');
        timer = window.setTimeout(function () {
          timer = null;
          var dep = total() * DEMO.deposit;
          set(document.getElementById('chkRef'), ref());
          set(document.getElementById('chkDUnit'), unit);
          set(document.getElementById('chkDWhen'),
            (from && to) ? pretty(from) + ' – ' + pretty(to)
                         : plural(demoNights(), L.night, L.nights));
          set(document.getElementById('chkDHow'), method);
          set(document.getElementById('chkDAmt'), cop(dep));
          body.hidden = true;
          foot.hidden = true;
          done.hidden = false;
        }, 1400);
      });

      var wab = document.getElementById('chkWa');
      if (wab) wab.addEventListener('click', function () {
        window.open('https://wa.me/' + wa + '?text=' + encodeURIComponent(waMessage()),
          '_blank', 'noopener');
      });
    })();
  })();

  /* ------------------------------------------------------------------
     The hero strip: the same controls, folded into popovers
     ------------------------------------------------------------------ */
  var strip = document.getElementById('hsrch');
  if (strip) (function () {
    var firstOpt = strip.querySelector('.hopt');
    var state = { u: firstOpt ? firstOpt.getAttribute('data-slug') : '', from: null, to: null, g: 2 };

    function closeAll() {
      strip.querySelectorAll('.hf.open').forEach(function (f) { f.classList.remove('open'); });
    }

    /* the panels open downward; if one runs past the fold, bring it into view
       rather than flipping it up over the field the guest just clicked */
    function nudge(field) {
      if (window.matchMedia('(max-width:879px)').matches) return;
      var pop = field.querySelector('.hpop');
      window.requestAnimationFrame(function () {
        var over = pop.getBoundingClientRect().bottom - window.innerHeight + 24;
        if (over > 0) window.scrollBy({ top: over, behavior: 'smooth' });
      });
    }
    document.addEventListener('click', function (e) {
      if (!strip.contains(e.target)) closeAll();
    });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeAll(); });

    strip.querySelectorAll('.hf-btn').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.stopPropagation();
        var field = btn.parentNode;
        var wasOpen = field.classList.contains('open');
        closeAll();
        if (!wasOpen) {
          field.classList.add('open');
          nudge(field);
        }
      });
    });

    /* on a phone the dim backdrop is drawn by the field itself, so a click
       that lands on the field and not on the panel means close */
    strip.querySelectorAll('.hf').forEach(function (field) {
      field.addEventListener('click', function (e) {
        if (e.target === field) closeAll();
      });
    });
    strip.querySelectorAll('.hpop').forEach(function (p) {
      p.addEventListener('click', function (e) { e.stopPropagation(); });
    });

    /* apartment */
    var uv = document.getElementById('hsUV');
    strip.querySelectorAll('.hopt').forEach(function (o) {
      o.addEventListener('click', function () {
        state.u = o.getAttribute('data-slug') || '';
        uv.textContent = o.getAttribute('data-label');
        strip.querySelectorAll('.hopt').forEach(function (x) { x.classList.remove('is-on'); });
        o.classList.add('is-on');
        closeAll();
      });
    });

    /* dates */
    var dv = document.getElementById('hsDV');
    var hcal = Calendar(document.getElementById('hsCal'), months, function (a, b) {
      state.from = a; state.to = b;
      dv.textContent = !a ? L.pickIn
        : (!b ? pretty(a) + ' → ?' : pretty(a) + ' – ' + pretty(b));
      if (a && b) closeAll();
    });
    window.addEventListener('resize', function () { hcal.redraw(); });

    /* guests */
    var gv = document.getElementById('hsGV');
    strip.querySelectorAll('#hsGpop button').forEach(function (btn) {
      btn.addEventListener('click', function () {
        state.g = Math.min(5, Math.max(1, state.g + (+btn.getAttribute('data-d'))));
        gv.textContent = state.g >= 5 ? L.plus : plural(state.g, L.guest, L.guests);
      });
    });

    strip.addEventListener('submit', function (e) {
      e.preventDefault();
      var q = [];
      if (state.u) q.push('u=' + state.u);
      if (state.from) q.push('in=' + iso(state.from));
      if (state.from && state.to) q.push('out=' + iso(state.to));
      q.push('g=' + state.g);
      window.location.href = strip.getAttribute('action') + '?' + q.join('&');
    });
  })();

  /* ------------------------------------------------------------------
     Concierge enquiry: pick what you want to do, we send it to WhatsApp
     ------------------------------------------------------------------ */
  var conc = document.getElementById('conc');
  if (conc) (function () {
    var msg = document.getElementById('concMsg');
    var note = document.getElementById('concNote');

    /* pressing a service card drops its name into the box and puts the
       cursor after it, so the guest carries on typing what they want */
    document.querySelectorAll('[data-svc]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var name = btn.getAttribute('data-svc') || '';
        var cur = msg.value.trim();
        /* an empty data-svc is the "anything else" button: focus, insert nothing */
        if (name && cur.indexOf(name) === -1) {
          msg.value = (cur ? cur + NL : '') + name + ': ';
        }
        msg.focus();
        msg.setSelectionRange(msg.value.length, msg.value.length);
        msg.scrollIntoView({ block: 'center', behavior: 'smooth' });
        if (note) note.classList.remove('bad');
      });
    });

    var C = isEN
      ? { need: 'Tell us what you need and we will take it from there.',
          intro: 'Hello, we are looking at Apart Hotel Aruba in Barranquilla and we would like some advice.',
          want: 'This is what we would like:',
          close: 'What would you recommend? Thank you.' }
      : { need: 'Cuéntanos qué necesitas y nosotros seguimos desde ahí.',
          intro: 'Hola, estamos mirando Apart Hotel Aruba en Barranquilla y quisiéramos una orientación.',
          want: 'Esto es lo que nos gustaría:',
          close: '¿Qué nos recomiendan? Gracias.' };

    conc.addEventListener('submit', function (e) {
      e.preventDefault();
      var free = (msg.value || '').trim();
      if (!free) {
        note.textContent = C.need;
        note.classList.add('bad');
        msg.focus();
        return;
      }
      var lines = [C.intro, '', C.want, free, '', C.close];
      window.open('https://wa.me/' + wa + '?text=' + encodeURIComponent(lines.join(NL)),
                  '_blank', 'noopener');
    });
  })();

  /* ------------------------------------------------------------------
     The experiences page.

     Two pieces: a photograph that follows the cursor across the index,
     and a tray that collects whatever the guest taps. Both no-op when
     their root is absent, so this file stays safe on every other page.
     ------------------------------------------------------------------ */

  /* ---- the request tray ---- */
  var tray = document.getElementById('tray');
  if (tray) (function () {
    var picked = [];
    var msg = document.getElementById('concMsg');
    var note = document.getElementById('concNote');
    var buttons = [].slice.call(document.querySelectorAll('[data-ask]'));

    var X = isEN
      ? { many: 'in your request', see: 'See', drop: 'Remove' }
      : { many: 'en tu solicitud', see: 'Ver', drop: 'Quitar' };

    var bar = document.createElement('button');
    bar.type = 'button';
    bar.className = 'traybar';
    bar.innerHTML = '<b>0</b><span>' + X.many + ' &middot; ' + X.see + '</span>';
    document.body.appendChild(bar);
    bar.addEventListener('click', function () {
      tray.scrollIntoView({ block: 'center', behavior: 'smooth' });
    });

    function mark() {
      buttons.forEach(function (b) {
        b.classList.toggle('is-in', picked.indexOf(b.getAttribute('data-ask')) !== -1);
      });
      bar.querySelector('b').textContent = String(picked.length);
      bar.classList.toggle('on', picked.length > 0);
      if (note) note.classList.remove('bad');
    }

    function draw() {
      tray.textContent = '';
      picked.forEach(function (label) {
        var chip = document.createElement('span');
        chip.className = 'tchip';
        chip.appendChild(document.createTextNode(label));
        var x = document.createElement('button');
        x.type = 'button';
        x.setAttribute('aria-label', X.drop + ' ' + label);
        x.innerHTML = '&times;';
        x.addEventListener('click', function () {
          picked = picked.filter(function (p) { return p !== label; });
          draw();
        });
        chip.appendChild(x);
        tray.appendChild(chip);
      });
      mark();
    }

    buttons.forEach(function (b) {
      b.addEventListener('click', function () {
        var label = b.getAttribute('data-ask');
        if (picked.indexOf(label) === -1) picked.push(label);
        else picked = picked.filter(function (p) { return p !== label; });
        draw();
      });
    });

    /* the form on this page composes from the tray plus whatever was typed */
    var conc = document.getElementById('conc');
    if (conc) {
      var C = isEN
        ? { need: 'Pick something above, or tell us what you need.',
            intro: 'Hello, we are looking at Apart Hotel Aruba in Barranquilla.',
            want: 'We would like to ask about:',
            quoted: '(we understand each one is quoted separately)',
            close: 'Could you tell us what is possible and what it would cost? Thank you.' }
        : { need: 'Elige algo de arriba, o cuéntanos qué necesitas.',
            intro: 'Hola, estamos mirando Apart Hotel Aruba en Barranquilla.',
            want: 'Quisiéramos preguntar por:',
            quoted: '(entendemos que cada uno se cotiza aparte)',
            close: '¿Nos cuentan qué se puede y cuánto sería? Gracias.' };

      conc.addEventListener('submit', function (e) {
        e.preventDefault();
        e.stopImmediatePropagation();
        var free = (msg && msg.value ? msg.value.trim() : '');
        if (!picked.length && !free) {
          note.textContent = C.need;
          note.classList.add('bad');
          msg.focus();
          return;
        }
        var lines = [C.intro, ''];
        if (picked.length) {
          lines.push(C.want);
          picked.forEach(function (p) { lines.push('- ' + p); });
          lines.push(C.quoted);
        }
        if (free) lines.push('', free);
        lines.push('', C.close);
        window.open('https://wa.me/' + wa + '?text=' + encodeURIComponent(lines.join(NL)),
          '_blank', 'noopener');
      }, true);
    }

    mark();
  })();
})();
