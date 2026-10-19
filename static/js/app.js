// Toast notifications. Server messages arrive pre-rendered in #toasts; JS adds
// close buttons and auto-dismiss, and exposes ppToast() for client-side events.
function dismissToast(t) { t.classList.add("out"); setTimeout(() => t.remove(), 220); }
function armToast(t, ms) {
  if (!t.querySelector("button")) {
    const x = document.createElement("button");
    x.type = "button"; x.setAttribute("aria-label", "Dismiss"); x.innerHTML = "&times;";
    x.onclick = () => dismissToast(t);
    t.appendChild(x);
  }
  setTimeout(() => dismissToast(t), t.classList.contains("error") ? ms + 3000 : ms);
}
function ppToast(msg, kind) {
  const box = document.getElementById("toasts");
  if (!box) return;
  const t = document.createElement("div");
  t.className = "toast " + (kind || "info");
  const span = document.createElement("span");
  span.textContent = msg;
  t.appendChild(span);
  box.appendChild(t);
  armToast(t, 4000);
}
document.querySelectorAll("#toasts .toast").forEach((t) => armToast(t, 5000));

// In-page confirmation instead of the browser's "site says..." popup.
// Any form (data-confirm on the form) or submit button (data-confirm on the button).
document.addEventListener("submit", (e) => {
  const form = e.target;
  const trigger = e.submitter && e.submitter.dataset.confirm ? e.submitter : form.dataset.confirm ? form : null;
  const dlg = document.getElementById("confirm-dialog");
  if (!trigger || !dlg || typeof dlg.showModal !== "function" || form.dataset.confirmed) return;
  e.preventDefault();
  document.getElementById("confirm-text").textContent = trigger.dataset.confirm;
  const ok = document.getElementById("confirm-ok");
  ok.textContent = trigger.dataset.confirmOk || "Confirm";
  dlg.returnValue = "";
  dlg.onclose = () => {
    if (dlg.returnValue !== "ok") return;
    form.dataset.confirmed = "1";
    if (e.submitter && e.submitter.name) {  // keep the clicked button's name/value in the POST
      const h = document.createElement("input");
      h.type = "hidden"; h.name = e.submitter.name; h.value = e.submitter.value;
      form.appendChild(h);
    }
    form.submit();
  };
  dlg.showModal();
}, true);

// Progressive enhancement: the "Interested" button works as a normal form POST
// without JavaScript, and updates in place when JS is available.
document.addEventListener("submit", async (e) => {
  const form = e.target.closest("form[data-interested]");
  if (!form) return;
  e.preventDefault();
  const btn = form.querySelector("button");
  btn.disabled = true;
  try {
    const res = await fetch(form.action, {
      method: "POST",
      headers: { "X-Requested-With": "XMLHttpRequest", "X-CSRFToken": form.querySelector("[name=csrfmiddlewaretoken]").value },
      credentials: "same-origin",
    });
    if (!res.ok) throw new Error("bad response");
    const data = await res.json();
    btn.classList.toggle("on", data.interested);
    btn.textContent = (data.interested ? "✓ Interested" : "I'm interested") + " · " + data.count;
    ppToast(data.interested ? "Saved. We'll show you're interested." : "Removed from your interests.", "success");
  } catch (err) {
    form.submit(); // fall back to a normal POST
  } finally {
    btn.disabled = false;
  }
});

// Copy-link button on event pages.
document.addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-copy]");
  if (!btn) return;
  try {
    await navigator.clipboard.writeText(btn.dataset.copy);
    const old = btn.textContent;
    btn.textContent = "Link copied!";
    setTimeout(() => (btn.textContent = old), 1800);
    ppToast("Link copied.", "success");
  } catch (err) { ppToast("Couldn't copy. Copy the address from your browser instead.", "error"); }
});

// Desk: copy a caption textarea to the clipboard.
document.addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-copy-from]");
  if (!btn) return;
  const el = document.getElementById(btn.dataset.copyFrom);
  try {
    await navigator.clipboard.writeText(el.value);
    const old = btn.textContent; btn.textContent = "Copied!";
    setTimeout(() => (btn.textContent = old), 1500);
    ppToast("Caption copied.", "success");
  } catch (err) { el.select(); ppToast("Couldn't copy automatically. Text is selected, press Ctrl/Cmd+C.", "error"); }
});

// Giveaway: the "Enter the draw" link works as a normal page without JS; with JS it opens a dialog.
document.addEventListener("click", (e) => {
  const open = e.target.closest("[data-open-giveaway]");
  const dlg = document.getElementById("giveaway-dialog");
  if (open && dlg && typeof dlg.showModal === "function") { e.preventDefault(); dlg.showModal(); }
  if (e.target.closest("[data-close-giveaway]") && dlg) dlg.close();
  if (e.target === dlg) dlg.close(); // click on the backdrop
  const rules = e.target.closest("[data-open-rules]");
  if (rules) { e.preventDefault(); const d = document.getElementById("gw-rules"); if (d) { d.open = true; d.scrollIntoView({ block: "nearest" }); } }
});

document.addEventListener("submit", async (e) => {
  const form = e.target.closest("form[data-giveaway-form]");
  if (!form) return;
  e.preventDefault();
  const btn = form.querySelector("button[type=submit]");
  btn.disabled = true;
  form.querySelectorAll(".errorlist").forEach((n) => n.remove());
  try {
    const res = await fetch(form.action, {
      method: "POST", body: new FormData(form), credentials: "same-origin",
      headers: { "X-Requested-With": "XMLHttpRequest" },
    });
    const data = await res.json();
    if (data.ok) {
      const box = form.closest("[data-giveaway-body]") || form.parentElement;
      box.innerHTML = '<div class="ticket"><div class="muted small"></div><div class="ticket-code"></div>' +
        '<p class="small muted" style="margin:0">Screenshot this. It\'s your ticket, not a prize. Winners are picked at random after entries close and messaged on WhatsApp.</p></div>';
      box.querySelector(".muted").textContent = (data.message || "You're in!") + " Your entry code:";
      box.querySelector(".ticket-code").textContent = data.code;
      return;
    }
    const errs = data.errors || {};
    Object.keys(errs).forEach((k) => {
      const input = form.querySelector('[name="' + k + '"]');
      if (!input) return;
      const ul = document.createElement("ul"); ul.className = "errorlist";
      const li = document.createElement("li"); li.textContent = errs[k]; ul.appendChild(li);
      input.closest(".field").appendChild(ul);
    });
    ppToast(data.message || "Something went wrong.", "error");
  } catch (err) {
    form.submit(); // no-JS style fallback
  } finally {
    btn.disabled = false;
  }
});
