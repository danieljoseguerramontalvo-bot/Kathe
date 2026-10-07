const ICONS = {
  beach: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M2 22c4-3 16-3 20 0"/><path d="M12 15V4"/><path d="M12 4c3 0 6 2 6 6-4 0-6-2-6-6Z"/><path d="M12 9c-2 0-4 1.5-4 4 3 0 4-1.5 4-4Z"/></svg>',
  plane: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M10.5 21 12 16l7.5-7.5a2.1 2.1 0 0 0-3-3L9 13 4 14.5 3 15.5l4.5 1.5L10.5 21Z"/></svg>',
  pin: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 22s7-7.4 7-12a7 7 0 1 0-14 0c0 4.6 7 12 7 12Z"/><circle cx="12" cy="10" r="2.4"/></svg>',
  lock: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="4" y="10" width="16" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></svg>',
  check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M20 6 9 17l-5-5"/></svg>',
  building: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><rect x="4" y="3" width="16" height="18" rx="1.5"/><path d="M9 8h1M14 8h1M9 12h1M14 12h1M9 16h1M14 16h1"/></svg>',
};

function icon(name) {
  return ICONS[name] || "";
}

function mapEmbed(lat, lng, zoom = 14) {
  return `https://www.google.com/maps?q=${lat},${lng}&z=${zoom}&output=embed`;
}

/* ---------- Navbar ---------- */

function initNavbar() {
  const nav = document.getElementById("navbar");
  if (!nav) return;

  const onScroll = () => {
    nav.classList.toggle("scrolled", window.scrollY > 40);
  };
  onScroll();
  window.addEventListener("scroll", onScroll, { passive: true });

  const links = Array.from(nav.querySelectorAll(".nav-link"));
  const underline = nav.querySelector(".nav-underline");

  const moveUnderline = (el) => {
    if (!underline || !el) return;
    underline.style.width = `${el.offsetWidth}px`;
    underline.style.transform = `translateX(${el.offsetLeft}px)`;
    underline.classList.add("visible");
  };

  const activeLink = () => links.find((l) => l.classList.contains("active")) || links[0];

  links.forEach((link) => {
    link.addEventListener("mouseenter", () => moveUnderline(link));
  });

  const linksWrap = nav.querySelector(".nav-links");
  if (linksWrap) {
    linksWrap.addEventListener("mouseleave", () => moveUnderline(activeLink()));
  }

  window.addEventListener("load", () => moveUnderline(activeLink()));
  window.addEventListener("resize", () => moveUnderline(activeLink()));

  const sections = links
    .map((l) => document.querySelector(l.getAttribute("href")))
    .filter(Boolean);

  if (sections.length) {
    const spy = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          const id = `#${entry.target.id}`;
          links.forEach((l) => l.classList.toggle("active", l.getAttribute("href") === id));
          moveUnderline(activeLink());
        });
      },
      { rootMargin: "-45% 0px -50% 0px" }
    );
    sections.forEach((s) => spy.observe(s));
  }

  const toggle = document.getElementById("navToggle");
  const mobileMenu = document.getElementById("mobileMenu");
  if (toggle && mobileMenu) {
    const close = () => {
      toggle.classList.remove("open");
      toggle.setAttribute("aria-expanded", "false");
      mobileMenu.classList.remove("open");
      document.body.style.overflow = "";
    };
    toggle.addEventListener("click", () => {
      const open = !toggle.classList.contains("open");
      toggle.classList.toggle("open", open);
      toggle.setAttribute("aria-expanded", String(open));
      mobileMenu.classList.toggle("open", open);
      document.body.style.overflow = open ? "hidden" : "";
    });
    mobileMenu.querySelectorAll("a").forEach((a) => a.addEventListener("click", close));
  }
}

/* ---------- Hero video fallback ---------- */

function initHero() {
  const video = document.querySelector(".hero-video");
  if (!video) return;

  const markReady = () => video.classList.add("is-ready");
  const markFailed = () => video.classList.remove("is-ready");

  video.addEventListener("loadeddata", markReady);
  video.addEventListener("error", markFailed, true);

  setTimeout(() => {
    if (video.readyState < 2) markFailed();
  }, 2500);
}

/* ---------- Scroll reveal ---------- */

function initReveal() {
  const items = document.querySelectorAll(".reveal");
  if (!items.length) return;
  const io = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("in-view");
          io.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.15 }
  );
  items.forEach((el) => io.observe(el));
}

/* ---------- Apartments ---------- */

function renderApartments() {
  const grid = document.getElementById("apartmentsGrid");
  if (!grid || typeof APARTMENTS === "undefined") return;

  grid.innerHTML = APARTMENTS.map(
    (apt) => `
    <article class="apt-card reveal">
      <div class="apt-photo tile ${apt.tile}">
        <span class="city-badge">${apt.cityLabel}</span>
      </div>
      <div class="apt-body">
        <h3>${apt.name}</h3>
        <p class="apt-meta">${apt.beds} habitaciones · ${apt.zone}</p>
        <div class="apt-map">
          <iframe loading="lazy" src="${mapEmbed(apt.lat, apt.lng)}" title="Ubicación ${apt.name}"></iframe>
        </div>
        <ul class="apt-distances">
          ${apt.distances
            .map((d) => `<li>${icon(d.icon)}<span>${d.label} · ${d.time}</span></li>`)
            .join("")}
        </ul>
        <div class="apt-footer">
          <p class="apt-price">$${apt.price}<span> / noche</span></p>
          <a class="btn btn-outline" href="booking.html?apt=${apt.id}">Reservar</a>
        </div>
      </div>
    </article>`
  ).join("");
}

/* ---------- Experiences tabs ---------- */

function renderExperiences() {
  const panels = document.querySelectorAll(".tab-panel");
  if (!panels.length || typeof EXPERIENCES === "undefined") return;

  panels.forEach((panel) => {
    const city = panel.dataset.panel;
    const list = EXPERIENCES[city] || [];
    panel.innerHTML = `<div class="exp-grid">${list
      .map(
        (exp) => `
      <article class="exp-card">
        <div class="exp-photo tile ${exp.tile}"></div>
        <div class="exp-body">
          <h4>${exp.name}</h4>
          <p>${exp.desc}</p>
          <div class="exp-map"><iframe loading="lazy" src="${mapEmbed(exp.lat, exp.lng, 13)}" title="Ubicación ${exp.name}"></iframe></div>
          <p class="exp-distance">${icon("pin")}<span>${exp.time}</span></p>
        </div>
      </article>`
      )
      .join("")}</div>`;
  });
}

function initTabs() {
  const buttons = Array.from(document.querySelectorAll(".tab-btn"));
  const underline = document.querySelector(".tab-underline");
  if (!buttons.length) return;

  const move = (btn) => {
    if (!underline) return;
    underline.style.width = `${btn.offsetWidth}px`;
    underline.style.transform = `translateX(${btn.offsetLeft}px)`;
  };

  buttons.forEach((btn) => {
    btn.addEventListener("click", () => {
      buttons.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      move(btn);
      document.querySelectorAll(".tab-panel").forEach((p) => {
        p.classList.toggle("active", p.dataset.panel === btn.dataset.tab);
      });
    });
  });

  window.addEventListener("load", () => move(buttons.find((b) => b.classList.contains("active")) || buttons[0]));
  window.addEventListener("resize", () => move(buttons.find((b) => b.classList.contains("active")) || buttons[0]));
}

/* ---------- Gallery + lightbox ---------- */

const GALLERY = [
  { tile: "tile-1", caption: "Suite Wayaca Ocean · sala" },
  { tile: "tile-2", caption: "El Prado Boutique · balcón" },
  { tile: "tile-3", caption: "Loft Wayaca Sunset · terraza" },
  { tile: "tile-4", caption: "Penthouse Buenavista · vista" },
  { tile: "tile-5", caption: "Wayaca · atardecer" },
  { tile: "tile-6", caption: "Barranquilla · Malecón del Río" },
  { tile: "tile-2", caption: "El Prado · cocina" },
  { tile: "tile-1", caption: "Wayaca · playa cercana" },
];

function renderGallery() {
  const grid = document.getElementById("galleryGrid");
  if (!grid) return;
  grid.innerHTML = GALLERY.map(
    (g, i) => `
    <button class="gallery-item${i === 0 ? " wide" : ""}${i === 3 ? " tall" : ""}" data-index="${i}" aria-label="Ver ${g.caption}">
      <div class="tile ${g.tile}"></div>
    </button>`
  ).join("");

  const lightbox = document.getElementById("lightbox");
  const stage = lightbox?.querySelector(".lightbox-photo");
  const caption = lightbox?.querySelector(".lightbox-caption");
  let current = 0;

  const show = (i) => {
    current = (i + GALLERY.length) % GALLERY.length;
    const item = GALLERY[current];
    if (stage) stage.className = `lightbox-photo tile ${item.tile}`;
    if (caption) caption.textContent = item.caption;
  };

  grid.querySelectorAll(".gallery-item").forEach((btn) => {
    btn.addEventListener("click", () => {
      show(Number(btn.dataset.index));
      lightbox?.classList.add("open");
      document.body.style.overflow = "hidden";
    });
  });

  const close = () => {
    lightbox?.classList.remove("open");
    document.body.style.overflow = "";
  };

  lightbox?.querySelector(".lightbox-close")?.addEventListener("click", close);
  lightbox?.addEventListener("click", (e) => {
    if (e.target === lightbox) close();
  });
  lightbox?.querySelector(".lightbox-prev")?.addEventListener("click", () => show(current - 1));
  lightbox?.querySelector(".lightbox-next")?.addEventListener("click", () => show(current + 1));

  document.addEventListener("keydown", (e) => {
    if (!lightbox?.classList.contains("open")) return;
    if (e.key === "Escape") close();
    if (e.key === "ArrowLeft") show(current - 1);
    if (e.key === "ArrowRight") show(current + 1);
  });
}

/* ---------- Testimonials carousel ---------- */

function initCarousel() {
  const track = document.getElementById("carouselTrack");
  const dotsWrap = document.getElementById("carouselDots");
  if (!track || typeof TESTIMONIALS === "undefined") return;

  track.innerHTML = TESTIMONIALS.map(
    (t) => `<blockquote class="carousel-slide"><p>&ldquo;${t.quote}&rdquo;</p><cite>${t.author}</cite></blockquote>`
  ).join("");

  if (dotsWrap) {
    dotsWrap.innerHTML = TESTIMONIALS.map(
      (_, i) => `<button class="carousel-dot${i === 0 ? " active" : ""}" data-i="${i}" aria-label="Testimonio ${i + 1}"></button>`
    ).join("");
  }

  let index = 0;
  const dots = () => Array.from(dotsWrap?.querySelectorAll(".carousel-dot") || []);

  const goTo = (i) => {
    index = (i + TESTIMONIALS.length) % TESTIMONIALS.length;
    track.style.transform = `translateX(-${index * 100}%)`;
    dots().forEach((d, di) => d.classList.toggle("active", di === index));
  };

  dots().forEach((d) => d.addEventListener("click", () => goTo(Number(d.dataset.i))));
  document.getElementById("carouselPrev")?.addEventListener("click", () => goTo(index - 1));
  document.getElementById("carouselNext")?.addEventListener("click", () => goTo(index + 1));

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (!reducedMotion) {
    const carousel = document.getElementById("carousel");
    let timer = setInterval(() => goTo(index + 1), 6000);
    carousel?.addEventListener("mouseenter", () => clearInterval(timer));
    carousel?.addEventListener("mouseleave", () => {
      timer = setInterval(() => goTo(index + 1), 6000);
    });
  }
}

document.addEventListener("DOMContentLoaded", () => {
  initNavbar();
  initHero();
  renderApartments();
  renderExperiences();
  initTabs();
  renderGallery();
  initCarousel();
  initReveal();
});
