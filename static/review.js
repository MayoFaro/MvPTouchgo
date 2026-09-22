document.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-decision]");
  if (!button) return;

  const card = button.closest(".card");
  const itemId = card.dataset.itemId;
  const decision = button.dataset.decision;

  let reason = null;
  let comment = null;

  if (button.dataset.needsReason) {
    reason = window.prompt("Raison du rejet :\n" + window.REJECT_REASONS.join(", "));
    if (!reason || !window.REJECT_REASONS.includes(reason)) {
      showError(card, "Raison invalide ou annulée.");
      return;
    }
  }

  if (button.dataset.needsComment) {
    comment = window.prompt("Décrivez la catégorie suggérée :");
    if (!comment) {
      showError(card, "Commentaire requis pour cette action.");
      return;
    }
  }

  try {
    const response = await fetch(`/items/${itemId}/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision, reason, comment }),
    });

    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      showError(card, body.detail ? JSON.stringify(body.detail) : `Erreur ${response.status}`);
      return;
    }

    const updated = await response.json();
    updateCard(card, updated);
  } catch (err) {
    showError(card, "Erreur réseau.");
  }
});

function showError(card, message) {
  const errorBox = card.querySelector(".feedback-error");
  errorBox.textContent = message;
  errorBox.hidden = false;
}

function updateCard(card, item) {
  const errorBox = card.querySelector(".feedback-error");
  errorBox.hidden = true;
  const statusEl = card.querySelector(".status");
  statusEl.textContent = `Statut : ${item.verification_status || "—"} — traité : ${item.human_decision}`;
}
