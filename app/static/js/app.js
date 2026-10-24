document.addEventListener("submit", (event) => {
  const form = event.target;
  if (form instanceof HTMLFormElement && form.dataset.confirm === "true") {
    if (!window.confirm(form.dataset.confirmMessage || "Are you sure?")) {
      event.preventDefault();
    }
  }
});
