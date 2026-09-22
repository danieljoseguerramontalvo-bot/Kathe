const B_ICONS = {
  lock: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="4" y="10" width="16" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></svg>',
  check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"><path d="M20 6 9 17l-5-5"/></svg>',
};

function bMapEmbed(lat, lng, zoom = 13) {
  return `https://www.google.com/maps?q=${lat},${lng}&z=${zoom}&output=embed`;
}

function initBookingNav() {
  const nav = document.getElementById("navbar");
  if (nav) nav.classList.add("scrolled");

  const toggle = document.getElementById("navToggle");
  const mobileMenu = document.getElementById("mobileMenu");
  if (toggle && mobileMenu) {
    toggle.addEventListener("click", () => {
      const open = !toggle.classList.contains("open");
      toggle.classList.toggle("open", open);
      mobileMenu.classList.toggle("open", open);
      document.body.style.overflow = open ? "hidden" : "";
    });
    mobileMenu.querySelectorAll("a").forEach((a) =>
      a.addEventListener("click", () => {
        toggle.classList.remove("open");
        mobileMenu.classList.remove("open");
        document.body.style.overflow = "";
      })
    );
  }
}

const MESES = [
  "enero", "febrero", "marzo", "abril", "mayo", "junio",
  "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
];
const MESES_CORTOS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
const DOW = ["L", "M", "X", "J", "V", "S", "D"];

const state = {
  step: 1,
  viewYear: new Date().getFullYear(),
  viewMonth: new Date().getMonth(),
  checkin: null,
  checkout: null,
  aptId: null,
};

function todayStripped() {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d;
}

function isoDate(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function isOccupied(y, m, d) {
  const seed = y * 372 + m * 31 + d;
  return seed % 7 === 0 || seed % 11 === 0;
}

function renderCalendar() {
  const grid = document.getElementById("calGrid");
  const heading = document.getElementById("calHeading");
  if (!grid || !heading) return;

  heading.textContent = `${MESES[state.viewMonth]} ${state.viewYear}`;

  const first = new Date(state.viewYear, state.viewMonth, 1);
  const startOffset = (first.getDay() + 6) % 7; // Monday = 0
  const daysInMonth = new Date(state.viewYear, state.viewMonth + 1, 0).getDate();
  const today = todayStripped();

  let html = DOW.map((d) => `<div class="calendar-dow">${d}</div>`).join("");

  for (let i = 0; i < startOffset; i++) {
    html += `<button class="cal-day empty" disabled></button>`;
  }

  for (let d = 1; d <= daysInMonth; d++) {
    const date = new Date(state.viewYear, state.viewMonth, d);
    const iso = isoDate(date);
    const past = date < today;
    const occupied = !past && isOccupied(state.viewYear, state.viewMonth, d);
    const isCheckin = state.checkin && iso === isoDate(state.checkin);
    const isCheckout = state.checkout && iso === isoDate(state.checkout);
    const inRange =
      state.checkin && state.checkout && date > state.checkin && date < state.checkout;

    const classes = ["cal-day"];
    if (past || occupied) classes.push("occupied");
    if (isCheckin || isCheckout) classes.push("selected");
    if (inRange) classes.push("in-range");

    html += `<button class="${classes.join(" ")}" data-date="${iso}" ${past || occupied ? "disabled" : ""}>${d}</button>`;
  }

  grid.innerHTML = html;

  grid.querySelectorAll(".cal-day:not(.empty):not(:disabled)").forEach((btn) => {
    btn.addEventListener("click", () => onDayClick(btn.dataset.date));
  });
}

function onDayClick(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  const date = new Date(y, m - 1, d);

  if (!state.checkin || (state.checkin && state.checkout)) {
    state.checkin = date;
    state.checkout = null;
  } else if (date.getTime() === state.checkin.getTime()) {
    state.checkin = date;
    state.checkout = null;
  } else if (date > state.checkin) {
    state.checkout = date;
  } else {
    state.checkout = state.checkin;
    state.checkin = date;
  }

  renderCalendar();
  updateSummary();
  updateContinueButtons();
}

function initCalendarNav() {
  document.getElementById("calPrev")?.addEventListener("click", () => {
    state.viewMonth -= 1;
    if (state.viewMonth < 0) {
      state.viewMonth = 11;
      state.viewYear -= 1;
    }
    renderCalendar();
  });
  document.getElementById("calNext")?.addEventListener("click", () => {
    state.viewMonth += 1;
    if (state.viewMonth > 11) {
      state.viewMonth = 0;
      state.viewYear += 1;
    }
    renderCalendar();
  });
}

/* ---------- Apartment selection ---------- */

function renderAptSelect() {
  const grid = document.getElementById("aptSelectGrid");
  if (!grid || typeof APARTMENTS === "undefined") return;

  grid.innerHTML = APARTMENTS.map(
    (apt) => `
    <label class="apt-radio">
      <input type="radio" name="apt" value="${apt.id}" ${apt.id === state.aptId ? "checked" : ""}>
      <div class="tile ${apt.tile}"><span class="city-badge">${apt.cityLabel}</span></div>
      <div class="apt-radio-body">
        <h4>${apt.name}</h4>
        <p>${apt.zone} · $${apt.price} / noche</p>
      </div>
    </label>`
  ).join("");

  grid.querySelectorAll('input[name="apt"]').forEach((input) => {
    input.addEventListener("change", () => {
      state.aptId = input.value;
      updateSummary();
      updateContinueButtons();
    });
  });
}

function currentApt() {
  if (typeof APARTMENTS === "undefined") return null;
  return APARTMENTS.find((a) => a.id === state.aptId) || null;
}

/* ---------- Summary panel ---------- */

function nights() {
  if (!state.checkin || !state.checkout) return 0;
  return Math.round((state.checkout - state.checkin) / 86400000);
}

function fmtShort(date) {
  if (!date) return "—";
  return `${date.getDate()} ${MESES_CORTOS[date.getMonth()]}`;
}

function updateSummary() {
  const apt = currentApt();
  const n = nights();

  const photo = document.getElementById("summaryPhoto");
  const name = document.getElementById("summaryAptName");
  const zone = document.getElementById("summaryZone");
  const mapWrap = document.getElementById("summaryMap");
  const checkin = document.getElementById("summaryCheckin");
  const checkout = document.getElementById("summaryCheckout");
  const nightsEl = document.getElementById("summaryNights");
  const total = document.getElementById("summaryTotal");
  const drawerTotal = document.getElementById("drawerTotal");

  if (apt) {
    if (photo) photo.className = `summary-photo tile ${apt.tile}`;
    if (name) name.textContent = apt.name;
    if (zone) zone.textContent = apt.zone;
    if (mapWrap) {
      mapWrap.innerHTML = `<iframe loading="lazy" src="${bMapEmbed(apt.lat, apt.lng)}" title="Ubicación ${apt.name}"></iframe>`;
    }
  } else {
    if (name) name.textContent = "Elige un apartamento";
    if (zone) zone.textContent = "Aruba o Barranquilla";
  }

  if (checkin) checkin.textContent = fmtShort(state.checkin);
  if (checkout) checkout.textContent = fmtShort(state.checkout);
  if (nightsEl) nightsEl.textContent = String(n);

  const price = apt ? apt.price * Math.max(n, 0) : 0;
  if (total) total.textContent = `$${price}`;
  if (drawerTotal) drawerTotal.textContent = `$${price}`;

  renderPaymentSummary(apt, n, price);
}

/* ---------- Stepper ---------- */

function updateContinueButtons() {
  const step1Btn = document.getElementById("toStep2");
  const step2Btn = document.getElementById("toStep3");
  if (step1Btn) step1Btn.disabled = !(state.checkin && state.checkout);
  if (step2Btn) step2Btn.disabled = !state.aptId;
}

function goToStep(n) {
  state.step = n;
  document.querySelectorAll(".step").forEach((el) => {
    const s = Number(el.dataset.step);
    el.classList.toggle("active", s === n);
    el.classList.toggle("done", s < n);
  });
  document.querySelectorAll(".step-panel").forEach((el) => {
    el.classList.toggle("active", Number(el.dataset.panel) === n);
  });
  const fill = document.getElementById("stepperFill");
  if (fill) fill.style.width = `${((n - 1) / 3) * 100}%`;
  document.getElementById("bookingMain")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function initStepper() {
  document.getElementById("toStep2")?.addEventListener("click", () => {
    if (state.checkin && state.checkout) goToStep(2);
  });
  document.getElementById("toStep3")?.addEventListener("click", () => {
    if (state.aptId) goToStep(3);
  });
  document.getElementById("toStep4")?.addEventListener("click", () => {
    const form = document.getElementById("guestForm");
    if (form && !form.checkValidity()) {
      form.reportValidity();
      return;
    }
    goToStep(4);
  });
  document.querySelectorAll("[data-back]").forEach((btn) => {
    btn.addEventListener("click", () => goToStep(Math.max(1, state.step - 1)));
  });
}

/* ---------- Payment ---------- */

function renderPaymentSummary(apt, n, price) {
  const recap = document.getElementById("confirmRecap");
  if (recap) {
    recap.textContent = apt
      ? `${apt.name} · ${n} noche${n === 1 ? "" : "s"} · $${price}`
      : "";
  }
}

function initPayment() {
  const form = document.getElementById("paymentForm");
  const block = document.getElementById("paymentBlock");
  const skeleton = document.getElementById("paymentSkeleton");
  const confirm = document.getElementById("confirmPanel");

  form?.addEventListener("submit", (e) => {
    e.preventDefault();
    if (!form.checkValidity()) {
      form.reportValidity();
      return;
    }

    if (block) block.hidden = true;
    if (skeleton) skeleton.hidden = false;

    setTimeout(() => {
      if (skeleton) skeleton.hidden = true;
      if (confirm) confirm.hidden = false;
    }, 1800);
  });
}

/* ---------- Mobile summary drawer ---------- */

function initSummaryDrawer() {
  const summary = document.getElementById("bookingSummary");
  const toggle = document.getElementById("summaryToggle");
  const handle = document.getElementById("summaryHandle");
  toggle?.addEventListener("click", () => {
    summary?.classList.toggle("open");
  });
  handle?.addEventListener("click", () => {
    summary?.classList.remove("open");
  });
}

/* ---------- Init ---------- */

document.addEventListener("DOMContentLoaded", () => {
  const params = new URLSearchParams(window.location.search);
  const requested = params.get("apt");
  if (typeof APARTMENTS !== "undefined") {
    state.aptId = APARTMENTS.some((a) => a.id === requested) ? requested : APARTMENTS[0]?.id || null;
  }

  initBookingNav();
  renderCalendar();
  initCalendarNav();
  renderAptSelect();
  initStepper();
  initPayment();
  initSummaryDrawer();
  updateSummary();
  updateContinueButtons();
  goToStep(1);
});
