const REASON_LABELS = {
  trop_mineur: "Trop mineur",
  pas_pertinent_touchgo: "Pas pertinent pour Touch-Go",
  trop_commercial: "Trop commercial",
  trop_local: "Trop local",
  signal_trop_faible: "Signal trop faible",
  doublon: "Doublon",
  information_douteuse: "Information douteuse",
  hors_perimetre: "Hors périmètre",
  autre: "Autre",
};

const reasonPanel = document.getElementById("reason-panel");
const reasonOptions = reasonPanel.querySelector(".reason-panel__options");
const reasonCancel = reasonPanel.querySelector(".reason-panel__cancel");
let pendingReasonChoice = null;

(window.REJECT_REASONS || []).forEach((code) => {
  const button = document.createElement("button");
  button.type = "button";
  button.dataset.reason = code;
  button.textContent = REASON_LABELS[code] || code;
  reasonOptions.appendChild(button);
});

reasonOptions.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-reason]");
  if (!button || !pendingReasonChoice) return;
  closeReasonPanel(button.dataset.reason);
});

reasonCancel.addEventListener("click", closeReasonPanel);
reasonPanel.addEventListener("click", (event) => {
  if (event.target === reasonPanel) closeReasonPanel();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !reasonPanel.hidden) closeReasonPanel();
});

function openReasonPanel() {
  return new Promise((resolve) => {
    pendingReasonChoice = resolve;
    reasonPanel.hidden = false;
  });
}

function closeReasonPanel(result = null) {
  reasonPanel.hidden = true;
  if (pendingReasonChoice) {
    const resolve = pendingReasonChoice;
    pendingReasonChoice = null;
    resolve(result);
  }
}

document.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-decision]");
  if (!button) return;

  const card = button.closest(".card");
  const itemId = card.dataset.itemId;
  const decision = button.dataset.decision;

  let reason = null;
  let comment = null;

  if (button.dataset.needsReason) {
    reason = await openReasonPanel();
    if (!reason) {
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
