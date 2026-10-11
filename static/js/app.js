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
  } catch (err) { /* clipboard unavailable: ignore */ }
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
  } catch (err) { el.select(); }
});
